"""Versioned, fail-closed three-domain pilot risk rules."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from .contracts import (
    CandidateReviewStatus,
    DomainCandidate,
    DomainRiskAssessment,
    DomainRiskStatus,
    MultidomainSnapshotReport,
    RiskDomain,
    TimeRange,
)
from .longitudinal.store import LongitudinalStore, dumps_compact
from .privacy import sha256_file

REPORT_VERSION = "multidomain-snapshot-v0.1.0"
DEFAULT_POLICY_PATH = Path("configs/v2-multidomain-risk-policy.json")


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> tuple[dict[str, Any], str]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("policy_id") != "v2-multidomain-risk-policy":
        raise ValueError("unexpected multidomain policy id")
    if payload.get("pilot_unvalidated") is not True:
        raise ValueError("multidomain MVP policy must remain pilot_unvalidated")
    return payload, sha256_file(path)


def classify_fraud_text(
    text: str, policy: dict[str, Any]
) -> tuple[list[str], bool]:
    """Return matched contexts and whether a hard negative suppressed the text."""

    fraud = policy["fraud"]
    normalized = _normalize_lexical_text(text)
    if any(
        _normalize_lexical_text(phrase) in normalized
        for phrase in fraud["hard_negative"]
        if _normalize_lexical_text(phrase)
    ):
        return [], True
    categories = sorted(
        category
        for category, phrases in fraud["categories"].items()
        if any(
            _normalize_lexical_text(phrase) in normalized
            for phrase in phrases
            if _normalize_lexical_text(phrase)
        )
    )
    return categories, False


def _normalize_lexical_text(text: str) -> str:
    """Normalize width, case, whitespace, and punctuation-based obfuscation."""

    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    return "".join(character for character in normalized if character.isalnum())


def candidate_from_row(row: Any) -> DomainCandidate:
    return DomainCandidate(
        candidate_id=str(row["candidate_id"]),
        domain=str(row["domain"]),
        category=str(row["category"]),
        occurred_at=_parse_datetime(row["occurred_at"]),
        evidence_refs=json.loads(row["evidence_refs_json"]),
        evidence_summary=json.loads(row["evidence_summary_json"]),
        quality=row["quality"],
        review_status=str(row["review_status"]),
        created_at=_parse_datetime(row["created_at"]),
    )


def insert_candidate(
    store: LongitudinalStore,
    candidate: DomainCandidate,
    *,
    device_ref: str | None,
    payload: dict[str, Any] | None = None,
) -> bool:
    serialized = candidate.model_dump(mode="json")
    return store.upsert_domain_candidate(
        {
            "candidate_id": candidate.candidate_id,
            "device_ref": device_ref,
            "domain": candidate.domain.value,
            "category": candidate.category,
            "occurred_at": candidate.occurred_at.isoformat(),
            "evidence_refs_json": dumps_compact(serialized["evidence_refs"]),
            "evidence_summary_json": dumps_compact(serialized["evidence_summary"]),
            "quality": candidate.quality,
            "review_status": candidate.review_status.value,
            "created_at": candidate.created_at.isoformat(),
            "updated_at": candidate.created_at.isoformat(),
            "payload_json": dumps_compact(payload or {}),
        }
    )


def build_snapshot(
    store: LongitudinalStore,
    *,
    device_ref: str,
    policy_path: Path = DEFAULT_POLICY_PATH,
    now: datetime | None = None,
    persist: bool = False,
) -> MultidomainSnapshotReport:
    policy, policy_digest = load_policy(policy_path)
    now = _aware_utc(now or datetime.now(timezone.utc))
    start_24h = now - timedelta(hours=24)
    coverage = store.coverage_since(start_24h.isoformat(), device_ref)
    latest_row = store.latest_successful_capture(device_ref)
    latest_capture = (
        _parse_datetime(latest_row["captured_end_at"])
        if latest_row is not None and latest_row["captured_end_at"]
        else None
    )
    stale = latest_capture is None or now - latest_capture > timedelta(
        hours=float(policy["stale_after_hours"])
    )
    candidate_rows = store.fetch_domain_candidates()
    candidates = [candidate_from_row(row) for row in candidate_rows]
    candidate_payload = {
        str(row["candidate_id"]): json.loads(row["payload_json"])
        for row in candidate_rows
    }
    deviations = [dict(row) for row in store.fetch_deviation_candidates()]
    daily = [dict(row) for row in store.fetch_daily_features(limit=60)]
    wellbeing_checkins = [
        dict(row) for row in store.fetch_wellbeing_checkins(limit=12)
    ]

    fall = score_fall(
        candidates,
        deviations=deviations,
        pose_seconds=coverage["pose_seconds"],
        now=now,
        stale=stale,
        policy=policy,
        policy_digest=policy_digest,
    )
    mental = score_mental_wellbeing(
        daily,
        checkins=wellbeing_checkins,
        now=now,
        stale=stale,
        policy=policy,
        policy_digest=policy_digest,
    )
    fraud = score_fraud(
        candidates,
        candidate_payload=candidate_payload,
        audio_seconds=coverage["audio_seconds"],
        now=now,
        stale=stale,
        policy=policy,
        policy_digest=policy_digest,
    )
    latest_failure = (
        str(latest_row["failure_code"])
        if latest_row is not None
        and "failure_code" in latest_row.keys()
        and latest_row["failure_code"]
        else None
    )
    if latest_failure:
        affected = {
            "pose_model_failed": (fall, mental),
            "speech_model_failed": (mental, fraud),
            "pose_and_speech_models_failed": (fall, mental, fraud),
        }.get(latest_failure, ())
        for assessment in affected:
            if assessment.score is None:
                assessment.status = DomainRiskStatus.MODEL_UNAVAILABLE
                marker = f"latest_edge_segment_{latest_failure}"
                if marker not in assessment.limitations:
                    assessment.limitations.append(marker)
    failures = store.analysis_failure_count()
    if failures and latest_capture is None:
        for assessment in (fall, mental, fraud):
            if assessment.score is None:
                assessment.status = DomainRiskStatus.MODEL_UNAVAILABLE
                if "analysis_model_unavailable_or_failed" not in assessment.limitations:
                    assessment.limitations.append("analysis_model_unavailable_or_failed")
    snapshot = MultidomainSnapshotReport(
        report_version=REPORT_VERSION,
        assessments=[fall, mental, fraud],
        data_freshness={
            "device_ref": device_ref,
            "latest_successful_capture_at": (
                latest_capture.isoformat() if latest_capture else None
            ),
            "stale": stale,
            "stale_after_hours": policy["stale_after_hours"],
        },
        timeline=sorted(candidates, key=lambda item: item.occurred_at, reverse=True),
        quality_status={
            "analysis_failures": failures,
            "pose_valid_minutes_24h": round(coverage["pose_seconds"] / 60, 3),
            "audio_valid_minutes_24h": round(coverage["audio_seconds"] / 60, 3),
            "latest_edge_status": (
                str(latest_row["status"])
                if latest_row is not None and latest_row["source"] == "edge_stream"
                else None
            ),
        },
        limitations=list(policy["limitations"]),
    )
    if persist:
        for assessment in snapshot.assessments:
            payload = assessment.model_dump(mode="json")
            digest = hashlib.sha256(
                dumps_compact(payload).encode("utf-8")
            ).hexdigest()[:20]
            store.record_domain_assessment(
                {
                    "assessment_id": f"assessment_{digest}_{now.timestamp():.0f}",
                    "domain": assessment.domain.value,
                    "score": assessment.score,
                    "status": assessment.status.value,
                    "assessed_at": now.isoformat(),
                    "policy_revision": assessment.policy_revision,
                    "policy_digest": assessment.policy_digest,
                    "payload_json": dumps_compact(payload),
                }
            )
    return snapshot


def score_fall(
    candidates: Iterable[DomainCandidate],
    *,
    deviations: Iterable[dict[str, Any]],
    pose_seconds: float,
    now: datetime,
    stale: bool,
    policy: dict[str, Any],
    policy_digest: str,
) -> DomainRiskAssessment:
    cutoff = now - timedelta(hours=24)
    active = [
        item
        for item in candidates
        if item.domain is RiskDomain.FALL
        and item.review_status is not CandidateReviewStatus.REJECTED
        and item.occurred_at >= cutoff
    ]
    falls = [item for item in active if item.category == "fall_candidate"]
    speech = [
        item
        for item in active
        if item.category in {"help_speech", "fall_speech"}
    ]
    score: int | None = None
    evidence: list[str] = []
    if any(item.review_status is CandidateReviewStatus.CONFIRMED for item in falls):
        score = 3
        evidence.append("human_confirmed_fall")
    else:
        window = float(policy["fall"]["speech_cooccurrence_seconds"])
        if any(
            abs((fall.occurred_at - voice.occurred_at).total_seconds()) <= window
            for fall in falls
            for voice in speech
        ):
            score = 3
            evidence.append("fall_candidate_with_help_or_fall_speech_within_10s")
        elif falls:
            score = 2
            evidence.append("unrejected_fall_candidate")
        else:
            recent_deviations = [
                item
                for item in deviations
                if _parse_datetime(item["detected_at"]) >= cutoff
            ]
            maximum = max((int(item["score"]) for item in recent_deviations), default=0)
            if maximum >= 2:
                score = 2
                evidence.append("severe_mobility_baseline_deviation")
            elif maximum == 1:
                score = 1
                evidence.append("mild_or_moderate_mobility_baseline_deviation")
            elif pose_seconds >= float(policy["fall"]["zero_pose_minutes_24h"]) * 60:
                score = 0
                evidence.append("qualified_pose_coverage_without_active_evidence")
    return _assessment(
        RiskDomain.FALL,
        score,
        now=now,
        stale=stale and score == 0,
        coverage={"qualified_pose_seconds_24h": round(pose_seconds, 3)},
        evidence=evidence,
        insufficient_reason="insufficient_pose_coverage_or_fall_evidence",
        policy=policy,
        policy_digest=policy_digest,
    )


def score_mental_wellbeing(
    daily_rows: Iterable[dict[str, Any]],
    *,
    checkins: Iterable[dict[str, Any]] = (),
    now: datetime,
    stale: bool,
    policy: dict[str, Any],
    policy_digest: str,
) -> DomainRiskAssessment:
    spec = policy["mental_wellbeing"]
    rows = sorted(daily_rows, key=lambda item: str(item["local_date"]))
    eligible = [
        item
        for item in rows
        if int(item["eligible_segments"]) >= int(spec["minimum_segments_per_day"])
    ]
    score: int | None = None
    evidence: list[str] = []
    usable_features = 0
    daily_stale = False
    if eligible:
        current = eligible[-1]
        current_day = date.fromisoformat(str(current["local_date"]))
        today = now.astimezone().date()
        daily_stale = current_day < today - timedelta(days=1) or current_day > today
        baseline_start = current_day - timedelta(days=int(spec["baseline_window_days"]))
        baseline = [
            item
            for item in eligible[:-1]
            if date.fromisoformat(str(item["local_date"])) >= baseline_start
        ]
        if not daily_stale and len({item["local_date"] for item in baseline}) >= int(
            spec["minimum_baseline_days"]
        ):
            levels: list[int] = []
            for offset in range(3):
                index = len(eligible) - 1 - offset
                if index < 0:
                    break
                level, summaries, feature_count = _mental_level(
                    eligible[index], eligible[:index], spec
                )
                if level is None:
                    break
                levels.append(level)
                if offset == 0:
                    evidence.extend(summaries)
                    usable_features = feature_count
            current_level = levels[0] if levels else None
            if current_level is not None:
                score = (
                    3
                    if len(levels) >= int(spec["level_two_streak_days"])
                    and all(level >= 2 for level in levels[:3])
                    else current_level
                )
                if score == 3 and current_level < 3:
                    evidence.append("level_2_or_higher_for_three_days")
    checkin_spec = spec["monthly_wellbeing_checkin"]
    current_month = now.astimezone().strftime("%Y-%m")
    current_checkin = next(
        (
            item
            for item in checkins
            if str(item.get("checkin_month")) == current_month
        ),
        None,
    )
    extra_limitations = ["who5_self_report_is_not_a_clinical_diagnosis"]
    if current_checkin is None:
        extra_limitations.append("monthly_wellbeing_checkin_due")
    else:
        raw_score = int(current_checkin["raw_score"])
        if raw_score < int(checkin_spec["low_wellbeing_raw_score_below"]):
            questionnaire_level = int(
                checkin_spec["low_wellbeing_minimum_risk_level"]
            )
            score = max(score if score is not None else 0, questionnaire_level)
            evidence.append("who5_below_suggested_further_assessment_cutoff")
        else:
            if score is None:
                score = 0
            evidence.append("who5_not_below_suggested_further_assessment_cutoff")
    return _assessment(
        RiskDomain.MENTAL_WELLBEING,
        score,
        now=now,
        stale=current_checkin is None
        and (daily_stale or (stale and score == 0)),
        coverage={
            "eligible_distinct_days": len({item["local_date"] for item in eligible}),
            "usable_features": usable_features,
            "required_baseline_days": spec["minimum_baseline_days"],
            "monthly_checkin_completed": current_checkin is not None,
        },
        evidence=evidence,
        insufficient_reason="personal_baseline_requires_7_days_with_3_segments_each",
        policy=policy,
        policy_digest=policy_digest,
        extra_limitations=extra_limitations,
        stale_reason=(
            "behavioral_daily_features_out_of_date"
            if daily_stale
            else "latest_successful_capture_older_than_6_hours"
        ),
    )


def _mental_level(
    current: dict[str, Any], baseline_rows: list[dict[str, Any]], spec: dict[str, Any]
) -> tuple[int | None, list[str], int]:
    current_day = date.fromisoformat(str(current["local_date"]))
    start = current_day - timedelta(days=int(spec["baseline_window_days"]))
    baseline = [
        item
        for item in baseline_rows
        if date.fromisoformat(str(item["local_date"])) >= start
        and int(item["eligible_segments"]) >= int(spec["minimum_segments_per_day"])
    ]
    if len({item["local_date"] for item in baseline}) < int(
        spec["minimum_baseline_days"]
    ):
        return None, [], 0
    mild = 0
    severe = 0
    summaries: list[str] = []
    usable = 0
    for feature in spec["features"]:
        if feature == "sleep_regularity" and not bool(current.get("sleep_confirmed")):
            continue
        value = current.get(feature)
        values = [
            float(item[feature])
            for item in baseline
            if item.get(feature) is not None
            and (feature != "sleep_regularity" or bool(item.get("sleep_confirmed")))
        ]
        if value is None or len(values) < int(spec["minimum_baseline_days"]):
            continue
        center = median(values)
        mad = median(abs(item - center) for item in values)
        if mad == 0:
            if float(value) == center:
                z_value = 0.0
            else:
                continue
        else:
            z_value = abs((float(value) - center) / mad)
        usable += 1
        if z_value >= float(spec["severe_z"]):
            severe += 1
            summaries.append(f"{feature}:severe_personal_baseline_change")
        elif z_value >= float(spec["mild_z"]):
            mild += 1
            summaries.append(f"{feature}:mild_personal_baseline_change")
    if usable == 0:
        return None, [], 0
    if severe >= 2:
        return 3, summaries, usable
    if severe >= 1 or mild >= 2:
        return 2, summaries, usable
    if mild == 1:
        return 1, summaries, usable
    return 0, ["no_personal_baseline_change_above_threshold"], usable


def score_fraud(
    candidates: Iterable[DomainCandidate],
    *,
    candidate_payload: dict[str, dict[str, Any]],
    audio_seconds: float,
    now: datetime,
    stale: bool,
    policy: dict[str, Any],
    policy_digest: str,
) -> DomainRiskAssessment:
    cutoff = now - timedelta(hours=24)
    active = [
        item
        for item in candidates
        if item.domain is RiskDomain.FRAUD
        and item.review_status is not CandidateReviewStatus.REJECTED
        and item.occurred_at >= cutoff
    ]
    score: int | None = None
    evidence: list[str] = []
    if active:
        score = 1
        window = float(policy["fraud"]["combination_window_seconds"])
        expanded = [
            (
                item,
                set(candidate_payload.get(item.candidate_id, {}).get("categories", []))
                or {item.category},
            )
            for item in active
        ]
        for index, (first, first_categories) in enumerate(expanded):
            for second, second_categories in expanded[index:]:
                if abs((first.occurred_at - second.occurred_at).total_seconds()) > window:
                    continue
                combined = first_categories | second_categories
                high = bool(
                    combined
                    & {"transfer_investment", "credential_request", "remote_control"}
                ) and bool(combined & {"impersonation", "urgency_secrecy"})
                if high:
                    score = 3
                    evidence = ["high_risk_fraud_context_combination_within_30s"]
                    break
                if len(combined) >= 2:
                    score = max(score, 2)
                    evidence = ["two_complementary_fraud_contexts_within_30s"]
            if score == 3:
                break
        if score == 1:
            evidence = ["single_unsuppressed_suspicious_context"]
    elif audio_seconds >= float(policy["fraud"]["zero_audio_minutes_24h"]) * 60:
        score = 0
        evidence = ["qualified_audio_coverage_without_active_candidate"]
    return _assessment(
        RiskDomain.FRAUD,
        score,
        now=now,
        stale=stale and score == 0,
        coverage={"valid_audio_seconds_24h": round(audio_seconds, 3)},
        evidence=evidence,
        insufficient_reason="insufficient_audio_coverage_or_fraud_language_evidence",
        policy=policy,
        policy_digest=policy_digest,
        extra_limitations=[
            "covers_only_environment_dialogue_audible_to_the_camera",
            "does_not_cover_the_inaudible_other_side_of_phone_calls",
            "suspicion_level_is_not_fraud_confirmation",
        ],
    )


def _assessment(
    domain: RiskDomain,
    score: int | None,
    *,
    now: datetime,
    stale: bool,
    coverage: dict[str, Any],
    evidence: list[str],
    insufficient_reason: str,
    policy: dict[str, Any],
    policy_digest: str,
    extra_limitations: list[str] | None = None,
    stale_reason: str = "latest_successful_capture_older_than_6_hours",
) -> DomainRiskAssessment:
    limitations = ["pilot_unvalidated_not_probability", *(extra_limitations or [])]
    if stale:
        score = None
        status = DomainRiskStatus.DATA_STALE
        limitations.append(stale_reason)
    elif score is None:
        status = DomainRiskStatus.INSUFFICIENT_DATA
        limitations.append(insufficient_reason)
    else:
        status = DomainRiskStatus.ASSESSED
    return DomainRiskAssessment(
        domain=domain,
        score=score,
        status=status,
        window=TimeRange(start_at=now - timedelta(hours=24), end_at=now),
        data_coverage=coverage,
        evidence_summary=evidence,
        policy_revision=str(policy["revision"]),
        policy_digest=policy_digest,
        policy_summary=str(policy["policy_summary"][domain.value]),
        limitations=limitations,
    )


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    return _aware_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
