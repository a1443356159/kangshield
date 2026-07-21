from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .contracts import (
    EvidenceLevel,
    FieldStat,
    MappingCandidate,
    Modality,
    Observation,
    PrivacyLevel,
    QualityIssue,
    QualityStatus,
    Severity,
    SleepProfileReport,
    SourceAsset,
    SourceType,
    ensure_source_evidence_compatible,
)
from .privacy import is_sensitive_key, safe_local_uri, sha256_file


PROFILER_VERSION = "sleep-profile-v0.1.0"
CANONICAL_ALIASES = {
    "heart_rate_bpm": (
        "heart_rate",
        "heartrate",
        "heart_rate_bpm",
        "hr",
        "心率",
    ),
    "respiratory_rate_bpm": (
        "respiratory_rate",
        "respiration_rate",
        "breath_rate",
        "resp",
        "呼吸率",
        "呼吸频率",
    ),
    "bed_presence": (
        "in_bed",
        "bed_presence",
        "presence",
        "body_status",
        "在床",
        "离床",
        "人体状态",
    ),
    "sleep_start_at": (
        "sleep_start",
        "sleep_onset",
        "bedtime",
        "入睡时间",
    ),
    "sleep_end_at": (
        "sleep_end",
        "wake_time",
        "起床时间",
        "醒来时间",
    ),
    "total_sleep_duration": (
        "total_sleep_time",
        "sleep_duration",
        "tst",
        "睡眠时长",
        "总睡眠时间",
    ),
    "awakening_count": (
        "awakening_count",
        "wake_count",
        "夜间觉醒次数",
        "觉醒次数",
    ),
}


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _flatten_scalars(value: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_scalars(item, path)
    elif isinstance(value, list):
        path = f"{prefix}[]" if prefix else "[]"
        if not value:
            yield path, []
        for item in value:
            yield from _flatten_scalars(item, path)
    else:
        yield prefix or "$", value


def _candidate_record_lists(
    value: Any,
    prefix: str = "$",
) -> Iterable[tuple[str, list[dict[str, Any]]]]:
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            yield prefix, value
        for index, item in enumerate(value):
            yield from _candidate_record_lists(item, f"{prefix}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _candidate_record_lists(item, f"{prefix}.{key}")


def _load_records(path: Path) -> tuple[list[dict[str, Any]], str, str]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            records = list(csv.DictReader(stream))
        return records, "$", "csv"
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        candidates = list(_candidate_record_lists(data))
        if candidates:
            container_path, records = max(candidates, key=lambda item: len(item[1]))
            return records, container_path, "json"
        if isinstance(data, dict):
            return [data], "$", "json"
        raise ValueError("JSON contains no object records")
    raise ValueError("sleep profile supports .json and .csv inputs")


def _normalized_leaf(path: str) -> str:
    leaf = re.split(r"[.\[\]]+", path)[-1]
    return re.sub(r"[^a-z0-9_\u4e00-\u9fff]+", "_", leaf.lower()).strip("_")


def _mapping_candidates(paths: Iterable[str]) -> list[MappingCandidate]:
    candidates: list[MappingCandidate] = []
    for path in paths:
        leaf = _normalized_leaf(path)
        for canonical, aliases in CANONICAL_ALIASES.items():
            normalized_aliases = {
                re.sub(r"[^a-z0-9_\u4e00-\u9fff]+", "_", alias.lower()).strip("_")
                for alias in aliases
            }
            if leaf in normalized_aliases:
                candidates.append(
                    MappingCandidate(
                        canonical_field=canonical,
                        source_path=path,
                        confidence="name_exact",
                    )
                )
            elif any(
                alias
                and (not alias.isascii() or len(alias) >= 4)
                and alias in leaf
                for alias in normalized_aliases
            ):
                candidates.append(
                    MappingCandidate(
                        canonical_field=canonical,
                        source_path=path,
                        confidence="name_partial",
                    )
                )
    unique: dict[tuple[str, str], MappingCandidate] = {}
    for candidate in candidates:
        unique[(candidate.canonical_field, candidate.source_path)] = candidate
    return sorted(
        unique.values(),
        key=lambda item: (item.canonical_field, item.source_path),
    )


def profile_sleep_export(
    path: Path,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.FIXTURE,
    device_ref: str | None = None,
    elder_ref: str | None = None,
) -> SleepProfileReport:
    ensure_source_evidence_compatible(source_type, evidence_level)
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    records, container_path, container_type = _load_records(path)
    digest = sha256_file(path)
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"types": set(), "present": 0, "non_null": 0}
    )
    for record in records:
        seen_paths: set[str] = set()
        for field_path, value in _flatten_scalars(record):
            item = stats[field_path]
            item["types"].add(_type_name(value))
            item["non_null"] += int(value is not None)
            seen_paths.add(field_path)
        for field_path in seen_paths:
            stats[field_path]["present"] += 1

    fields = [
        FieldStat(
            path=field_path,
            types=sorted(item["types"]),
            present_count=item["present"],
            non_null_count=item["non_null"],
            sensitive=any(is_sensitive_key(part) for part in re.split(r"[.\[\]]+", field_path)),
        )
        for field_path, item in sorted(stats.items())
    ]
    candidates = _mapping_candidates(item.path for item in fields if not item.sensitive)
    issues: list[QualityIssue] = [
        QualityIssue(
            code="mapping_requires_manual_confirmation",
            severity=Severity.INFO,
            message="Field-name matches do not establish units or clinical meaning",
        )
    ]
    if evidence_level in {EvidenceLevel.E0, EvidenceLevel.E1}:
        issues.append(
            QualityIssue(
                code="unverified_sleep_schema",
                severity=Severity.WARNING,
                message="This input does not prove the target device API schema",
            )
        )

    asset = SourceAsset(
        asset_id=f"asset_{digest[:20]}",
        modality=Modality.SLEEP,
        source_type=source_type,
        evidence_level=evidence_level,
        uri=safe_local_uri(path, digest),
        sha256=digest,
        byte_size=path.stat().st_size,
        privacy_level=PrivacyLevel.RAW_SENSITIVE,
        metadata={
            "container_type": container_type,
            "record_count": len(records),
            "values_persisted_in_report": False,
        },
    )
    sensitive_count = sum(field.sensitive for field in fields)
    observation = Observation(
        observation_id=f"observation_{digest[:20]}_{PROFILER_VERSION.rsplit('-', 1)[-1]}",
        asset_id=asset.asset_id,
        elder_ref=elder_ref,
        device_ref=device_ref,
        modality=Modality.SLEEP,
        quality_status=QualityStatus.PASS if records else QualityStatus.FAIL,
        quality_metrics={
            "record_count": len(records),
            "field_count": len(fields),
            "sensitive_field_count": sensitive_count,
            "mapping_candidate_count": len(candidates),
        },
        missing_reasons=[] if records else ["no_records"],
    )
    return SleepProfileReport(
        profiler_version=PROFILER_VERSION,
        asset=asset,
        observation=observation,
        container_path=container_path,
        record_count=len(records),
        fields=fields,
        mapping_candidates=candidates,
        issues=issues,
    )
