"""L1 personal-baseline engine: rolling median/MAD/EWMA and deviation candidates.

Everything here is fail-closed and candidate-only:
- observations without timezone-aware timestamps, non-numeric values or
  non-assessable status never enter a baseline (``baseline_eligible = 0``);
- a (indicator, bucket) pair with fewer than ``min_baseline_samples`` eligible
  observations gets an ``insufficient_samples`` baseline and emits no score;
- deviation candidates are owner-only 0-3 scores bound to the policy revision
  and digest; they never merge into any global score and never confirm a fall.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from ..contracts import (
    BaselineDeviationCandidate,
    LongitudinalBaselinePolicy,
    LongitudinalBucket,
    PersonalBaseline,
)
from .store import LongitudinalStore, dumps_compact

ENGINE_VERSION = "longitudinal-baseline-v0.1.0"
MAD_SCALE = 1.4826
ZERO_MAD_LIMITATION = "zero_mad_degenerate_rule_fixed_score"

_BUCKETS = (LongitudinalBucket.DAY.value, LongitudinalBucket.NIGHT.value)


def _candidate_id(
    elder_ref: str, indicator_id: str, bucket: str, observed_at: str
) -> str:
    digest = hashlib.sha256(
        f"{elder_ref}|{indicator_id}|{bucket}|{observed_at}".encode()
    ).hexdigest()[:20]
    return f"deviation_{digest}"


def _score_for(z_abs: float, thresholds: dict[int, float]) -> int:
    score = 0
    for level in (1, 2, 3):
        if z_abs >= thresholds[level]:
            score = level
    return score


def _ewma(values: list[float], alpha: float) -> float:
    estimate = values[0]
    for value in values[1:]:
        estimate = alpha * value + (1.0 - alpha) * estimate
    return estimate


def recompute_baselines(
    store: LongitudinalStore,
    policy: LongitudinalBaselinePolicy,
    *,
    now: datetime,
) -> tuple[list[PersonalBaseline], dict[str, int]]:
    """Recompute every whitelisted (indicator, bucket) baseline from the store."""
    if now.utcoffset() is None:
        raise ValueError("baseline computation requires a timezone-aware now")
    window_start = now - timedelta(days=policy.window_days)
    baselines: list[PersonalBaseline] = []
    status_counts = {"ready_baseline": 0, "insufficient_baseline": 0}
    for spec in policy.indicators:
        for bucket in _BUCKETS:
            rows = store.fetch_eligible_values(spec.indicator_id, bucket)
            # Window filtering happens on parsed datetimes (not ISO strings)
            # so mixed UTC offsets stay correct.
            values = [
                float(row["value"])
                for row in rows
                if datetime.fromisoformat(str(row["observed_at"])) >= window_start
            ]
            computed_at = now.isoformat()
            if len(values) < policy.min_baseline_samples:
                baseline = PersonalBaseline(
                    elder_ref=store.elder_ref,
                    indicator_id=spec.indicator_id,
                    bucket=bucket,
                    computed_at=now,
                    window_days=policy.window_days,
                    sample_count=len(values),
                    status="insufficient_samples",
                    policy_revision=policy.revision,
                )
                status_counts["insufficient_baseline"] += 1
            else:
                center = median(values)
                mad = median([abs(value - center) for value in values])
                baseline = PersonalBaseline(
                    elder_ref=store.elder_ref,
                    indicator_id=spec.indicator_id,
                    bucket=bucket,
                    computed_at=now,
                    window_days=policy.window_days,
                    sample_count=len(values),
                    status="ready",
                    median=float(center),
                    mad=float(mad),
                    ewma=float(_ewma(values, policy.ewma_alpha)),
                    policy_revision=policy.revision,
                )
                status_counts["ready_baseline"] += 1
            store.upsert_baseline(
                {
                    "indicator_id": baseline.indicator_id,
                    "bucket": baseline.bucket,
                    "computed_at": computed_at,
                    "window_days": baseline.window_days,
                    "sample_count": baseline.sample_count,
                    "status": baseline.status,
                    "median": baseline.median,
                    "mad": baseline.mad,
                    "ewma": baseline.ewma,
                    "policy_revision": baseline.policy_revision,
                }
            )
            baselines.append(baseline)
    return baselines, status_counts


def detect_deviations(
    store: LongitudinalStore,
    policy: LongitudinalBaselinePolicy,
    *,
    policy_digest: str,
) -> tuple[list[BaselineDeviationCandidate], dict[str, int]]:
    """Evaluate the latest eligible observation per (indicator, bucket).

    Steady state (score 0) persists nothing; re-runs are idempotent because
    the candidate id is derived from the observation timestamp.
    """
    candidates: list[BaselineDeviationCandidate] = []
    status_counts = {
        "evaluated": 0,
        "skipped_no_baseline": 0,
        "skipped_no_observation": 0,
        "skipped_duplicate": 0,
        "skipped_non_risk_direction": 0,
        "steady": 0,
    }
    specs = {spec.indicator_id: spec for spec in policy.indicators}
    rows: list[dict[str, Any]] = []
    for indicator_id, spec in specs.items():
        for bucket in _BUCKETS:
            baseline = store.fetch_baseline(indicator_id, bucket)
            if baseline is None or baseline["status"] != "ready":
                status_counts["skipped_no_baseline"] += 1
                continue
            latest = store.latest_eligible_observation(indicator_id, bucket)
            if latest is None:
                status_counts["skipped_no_observation"] += 1
                continue
            status_counts["evaluated"] += 1
            candidate_id = _candidate_id(
                store.elder_ref, indicator_id, bucket, str(latest["observed_at"])
            )
            if store.has_deviation_candidate(candidate_id):
                status_counts["skipped_duplicate"] += 1
                continue
            value = float(latest["value"])
            center = float(baseline["median"])
            mad = float(baseline["mad"])
            limitations: list[str] = []
            if mad == 0.0:
                if value == center:
                    status_counts["steady"] += 1
                    continue
                score = policy.zero_mad_score
                z_value = value - center
                ewma_shift = None
                limitations.append(ZERO_MAD_LIMITATION)
            else:
                z_value = (value - center) / (MAD_SCALE * mad)
                score = _score_for(abs(z_value), policy.score_z_thresholds)
                ewma_shift = (float(baseline["ewma"]) - center) / (MAD_SCALE * mad)
            direction = "above" if z_value > 0 else "below"
            if score == 0:
                status_counts["steady"] += 1
                continue
            if (
                spec.risk_direction != "both"
                and direction != spec.risk_direction
            ):
                status_counts["skipped_non_risk_direction"] += 1
                continue
            candidate = BaselineDeviationCandidate(
                candidate_id=candidate_id,
                elder_ref=store.elder_ref,
                indicator_id=indicator_id,
                bucket=bucket,
                detected_at=datetime.fromisoformat(str(latest["observed_at"])),
                direction=direction,
                z_value=z_value,
                ewma_shift=ewma_shift,
                score=score,
                policy_revision=policy.revision,
                policy_digest=policy_digest,
                baseline_sample_count=int(baseline["sample_count"]),
                limitations=limitations,
            )
            rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "detected_at": candidate.detected_at.isoformat(),
                    "indicator_id": candidate.indicator_id,
                    "bucket": candidate.bucket,
                    "direction": candidate.direction,
                    "z_value": candidate.z_value,
                    "ewma_shift": candidate.ewma_shift,
                    "score": candidate.score,
                    "policy_revision": candidate.policy_revision,
                    "policy_digest": candidate.policy_digest,
                    "baseline_sample_count": candidate.baseline_sample_count,
                    "limitations_json": dumps_compact(candidate.limitations),
                }
            )
            candidates.append(candidate)
    store.insert_deviation_candidates(rows)
    return candidates, status_counts
