from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable

from .contracts import (
    IndicatorAssessability,
    IndicatorAssessment,
    IndicatorAssessmentStatus,
    IndicatorExtractionReport,
    IndicatorObservation,
    IndicatorSummaryReport,
    EvidenceLevel,
    QualityStatus,
    SourceType,
    TimeRange,
    ensure_source_evidence_compatible,
)
from .privacy import sha256_file


VIDEO_EXTRACTOR_VERSION = "video-indicators-fixture-v0.1.0"
SLEEP_EXTRACTOR_VERSION = "sleep-indicators-v0.1.0"
REPORT_VERSION = "indicator-summary-v0.1.0"

_VIDEO_SPECS = {
    "gait_speed": ("gait", "m/s", True),
    "gait_cadence": ("gait", "steps/min", False),
    "sit_to_stand_duration": ("posture", "s", False),
    "turn_180_duration": ("posture", "s", False),
    "turn_360_duration": ("posture", "s", False),
}


def _source_ref(path: Path) -> str:
    return f"sha256:{sha256_file(path)}"


def _observation_id(source_ref: str, indicator_id: str, scenario_id: str | None) -> str:
    digest = hashlib.sha256(
        f"{source_ref}|{indicator_id}|{scenario_id or '-'}".encode()
    ).hexdigest()[:20]
    return f"indicator_{digest}"


def _quality_gate(
    quality: dict[str, Any], *, calibration_required: bool, sample_count: int
) -> tuple[IndicatorAssessability, QualityStatus, list[str]]:
    failures: list[str] = []
    if not quality.get("timestamp_continuous", False):
        failures.append("timestamp_discontinuity")
    if float(quality.get("keypoint_visibility_ratio", 0.0)) < 0.7:
        failures.append("insufficient_keypoint_visibility")
    if not quality.get("track_continuous", False):
        failures.append("track_discontinuity")
    if not quality.get("action_complete", False):
        failures.append("incomplete_action")
    if sample_count < 3:
        failures.append("insufficient_complete_repetitions")
    if calibration_required:
        if not quality.get("calibration_valid", False):
            failures.append("missing_or_invalid_ground_calibration")
        if float(quality.get("foot_visibility_ratio", 0.0)) < 0.7:
            failures.append("insufficient_foot_visibility")
    if failures:
        return IndicatorAssessability.NOT_ASSESSABLE, QualityStatus.FAIL, failures
    return IndicatorAssessability.ASSESSABLE, QualityStatus.PASS, []


def extract_video_indicators(
    path: Path,
    *,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.FIXTURE,
) -> IndicatorExtractionReport:
    """Normalize deterministic fixture measurements through the production gate.

    This first adapter deliberately consumes measured repetition values, not pixels or
    labels. A pose backend can later supply the same values without changing contracts.
    """

    path = Path(path)
    ensure_source_evidence_compatible(source_type, evidence_level)
    if source_type is not SourceType.FIXTURE or evidence_level is not EvidenceLevel.E1:
        raise ValueError("the initial video indicator adapter is E1 fixture-only")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("fixture") is not True:
        raise ValueError("the initial video indicator adapter accepts fixture input only")
    if payload.get("device_model") != "CS-C6c-V101-1J4WF":
        raise ValueError("video indicator fixture must target CS-C6c-V101-1J4WF")

    source_ref = _source_ref(path)
    observations: list[IndicatorObservation] = []
    for item in payload.get("measurements", []):
        indicator_id = str(item.get("indicator_id", ""))
        if indicator_id not in _VIDEO_SPECS:
            raise ValueError(f"unsupported video indicator: {indicator_id}")
        group, unit, calibration_required = _VIDEO_SPECS[indicator_id]
        if item.get("unit") != unit:
            raise ValueError(f"{indicator_id} requires unit {unit}")
        values = [float(value) for value in item.get("values", [])]
        quality = dict(item.get("quality", {}))
        assessability, quality_status, failures = _quality_gate(
            quality,
            calibration_required=calibration_required,
            sample_count=len(values),
        )
        scenario_id = str(item.get("scenario_id", "")) or None
        value = round(fmean(values), 4) if assessability.value == "assessable" else None
        observations.append(
            IndicatorObservation(
                observation_id=_observation_id(source_ref, indicator_id, scenario_id),
                indicator_id=indicator_id,
                group=group,
                source_modality="video",
                source_ref=source_ref,
                scenario_id=scenario_id,
                value=value,
                unit=unit,
                time_range=TimeRange(
                    start_ms=item.get("start_ms"), end_ms=item.get("end_ms")
                ),
                assessability=assessability,
                quality_status=quality_status,
                quality_metrics={**quality, "complete_repetition_count": len(values)},
                sample_count=len(values),
                limitations=failures,
            )
        )
    if not observations:
        raise ValueError("video indicator fixture contains no measurements")
    return IndicatorExtractionReport(
        extractor_version=VIDEO_EXTRACTOR_VERSION,
        source_modality="video",
        source_type=source_type,
        evidence_level=evidence_level,
        source_ref=source_ref,
        observations=observations,
        limitations=[
            "fixture_measurements_do_not_prove_pose_extraction_or_target_device_accuracy",
            "risk_scoring_is_not_performed",
        ],
    )


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records", payload.get("data", []))
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ValueError("sleep input must contain a records or data object list")
    return records


def _mean_numeric(records: Iterable[dict[str, Any]], names: tuple[str, ...]) -> list[float]:
    values: list[float] = []
    for record in records:
        for name in names:
            value = record.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))
                break
    return values


def _parse_times(records: Iterable[dict[str, Any]]) -> list[datetime]:
    parsed: list[datetime] = []
    for record in records:
        raw = record.get("timestamp", record.get("ts"))
        if not isinstance(raw, str):
            continue
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if value.tzinfo is not None:
            parsed.append(value)
    return sorted(parsed)


def extract_sleep_indicators(
    path: Path,
    *,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.FIXTURE,
) -> IndicatorExtractionReport:
    path = Path(path)
    ensure_source_evidence_compatible(source_type, evidence_level)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("fixture") is True and source_type is not SourceType.FIXTURE:
        raise ValueError("sleep fixture marker requires fixture source type")
    records = _records(payload)
    source_ref = _source_ref(path)
    times = _parse_times(records)
    time_range = TimeRange(
        start_at=times[0] if times else None,
        end_at=times[-1] if times else None,
    )
    observations: list[IndicatorObservation] = []

    for indicator_id, aliases, unit in (
        ("sleep_heart_rate_trend", ("heart_rate", "heartRate"), "bpm"),
        (
            "sleep_respiratory_rate_trend",
            ("respiratory_rate", "breathRate"),
            "breaths/min",
        ),
    ):
        values = _mean_numeric(records, aliases)
        assessable = bool(values and times)
        observations.append(
            IndicatorObservation(
                observation_id=_observation_id(source_ref, indicator_id, None),
                indicator_id=indicator_id,
                group="physiology",
                source_modality="sleep",
                source_ref=source_ref,
                value=round(fmean(values), 4) if assessable else None,
                unit=unit,
                time_range=time_range,
                assessability=(
                    IndicatorAssessability.ASSESSABLE
                    if assessable
                    else IndicatorAssessability.NOT_ASSESSABLE
                ),
                quality_status=QualityStatus.PASS if assessable else QualityStatus.FAIL,
                quality_metrics={
                    "value_count": len(values),
                    "timestamp_count": len(times),
                    "trend_only": True,
                },
                sample_count=len(values),
                limitations=(
                    ["trend_only_no_risk_threshold"]
                    if assessable
                    else ["missing_values_or_timezone_aware_timestamps"]
                ),
            )
        )

    night = payload.get("night") if isinstance(payload.get("night"), dict) else {}
    semantics_ready = all(
        night.get(key) is True
        for key in ("complete_night", "timezone_confirmed", "missing_semantics_confirmed")
    )
    for indicator_id, key, unit in (
        ("sleep_bedtime_local", "bedtime_local", "local_time"),
        ("sleep_wake_time_local", "wake_time_local", "local_time"),
        ("sleep_duration_h", "duration_h", "h"),
    ):
        raw_value = night.get(key)
        has_value = isinstance(raw_value, (str, int, float)) and not isinstance(raw_value, bool)
        ready = semantics_ready and has_value
        observations.append(
            IndicatorObservation(
                observation_id=_observation_id(source_ref, indicator_id, None),
                indicator_id=indicator_id,
                group="sleep",
                source_modality="sleep",
                source_ref=source_ref,
                value=raw_value if ready else None,
                unit=unit,
                time_range=time_range,
                assessability=(
                    IndicatorAssessability.ASSESSABLE
                    if ready
                    else IndicatorAssessability.BLOCKED_SEMANTICS
                ),
                quality_status=QualityStatus.PASS if ready else QualityStatus.UNKNOWN,
                quality_metrics={
                    "complete_night": bool(night.get("complete_night")),
                    "timezone_confirmed": bool(night.get("timezone_confirmed")),
                    "missing_semantics_confirmed": bool(
                        night.get("missing_semantics_confirmed")
                    ),
                },
                sample_count=1 if ready else 0,
                limitations=[] if ready else ["complete_night_semantics_not_confirmed"],
            )
        )

    return IndicatorExtractionReport(
        extractor_version=SLEEP_EXTRACTOR_VERSION,
        source_modality="sleep",
        source_type=source_type,
        evidence_level=evidence_level,
        source_ref=source_ref,
        observations=observations,
        limitations=[
            "heart_and_respiratory_outputs_are_trends_not_risk_scores",
            "sleep_boundaries_fail_closed_until_complete_night_semantics_are_confirmed",
        ],
    )


def load_extraction_report(path: Path) -> IndicatorExtractionReport:
    return IndicatorExtractionReport.model_validate_json(Path(path).read_text(encoding="utf-8"))


def build_indicator_reports(
    reports: Iterable[IndicatorExtractionReport],
) -> tuple[IndicatorSummaryReport, IndicatorSummaryReport]:
    observations = [observation for report in reports for observation in report.observations]
    if not observations:
        raise ValueError("at least one indicator observation is required")
    assessments: list[IndicatorAssessment] = []
    for observation in observations:
        status = {
            IndicatorAssessability.ASSESSABLE: IndicatorAssessmentStatus.POLICY_NOT_FROZEN,
            IndicatorAssessability.NOT_ASSESSABLE: IndicatorAssessmentStatus.NOT_ASSESSABLE,
            IndicatorAssessability.BLOCKED_SEMANTICS: IndicatorAssessmentStatus.BLOCKED_SEMANTICS,
        }[observation.assessability]
        assessments.append(
            IndicatorAssessment(
                assessment_id=f"assessment_{observation.observation_id.removeprefix('indicator_')}",
                observation_id=observation.observation_id,
                indicator_id=observation.indicator_id,
                status=status,
                limitations=(
                    ["scoring_policy_not_frozen"]
                    if status is IndicatorAssessmentStatus.POLICY_NOT_FROZEN
                    else list(observation.limitations)
                ),
            )
        )
    indicator_counts = dict(Counter(item.group for item in observations))
    quality_counts = dict(Counter(item.quality_status.value for item in observations))
    status_counts = dict(Counter(item.status.value for item in assessments))
    common = dict(
        report_version=REPORT_VERSION,
        assessments=assessments,
        indicator_counts=indicator_counts,
        quality_counts=quality_counts,
        status_counts=status_counts,
        global_score=None,
        limitations=[
            "engineering_risk_indicators_not_clinical_diagnosis",
            "global_scoring_policy_not_frozen",
            "fall_candidates_require_separate_human_adjudication",
        ],
    )
    owner = IndicatorSummaryReport(
        visibility="owner_only", observations=observations, **common
    )
    public = IndicatorSummaryReport(
        visibility="public_evidence", observations=[], **common
    )
    return owner, public


def render_indicator_markdown(report: IndicatorSummaryReport) -> str:
    lines = [
        "# KangShield 指标摘要",
        "",
        f"- 可见范围：`{report.visibility}`",
        "- 全局分数：`null`",
        "- 结论：工程风险指标，不是临床诊断。",
        "",
        "## 状态计数",
        "",
    ]
    for status, count in sorted(report.status_counts.items()):
        lines.append(f"- `{status}`: {count}")
    if report.visibility == "owner_only":
        lines.extend(["", "## 分项观测", "", "| 指标 | 值 | 单位 | 状态 |", "|---|---:|---|---|"])
        for observation in report.observations:
            value = "null" if observation.value is None else str(observation.value)
            lines.append(
                f"| `{observation.indicator_id}` | {value} | {observation.unit} | "
                f"`{observation.assessability.value}` |"
            )
    else:
        lines.extend(
            [
                "",
                "公开证据不包含真实分项值、原始健康数据、媒体或人员标识。",
            ]
        )
    lines.extend(["", "## 限制", ""])
    lines.extend(f"- `{item}`" for item in report.limitations)
    return "\n".join(lines) + "\n"
