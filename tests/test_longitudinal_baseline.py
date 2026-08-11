from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kangshield.information.contracts import (
    LongitudinalAssessmentReport,
    LongitudinalBaselinePolicy,
    PersonalBaseline,
)
from kangshield.information.longitudinal.baseline import (
    ZERO_MAD_LIMITATION,
    detect_deviations,
    recompute_baselines,
)
from kangshield.information.longitudinal.report import build_assessment_reports
from kangshield.information.longitudinal.store import LongitudinalStore

POLICY_DIGEST = "e" * 64
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone(timedelta(hours=8)))


def _policy(**overrides) -> LongitudinalBaselinePolicy:
    payload = {
        "policy_id": "test-policy",
        "revision": "test-rev-1",
        "min_baseline_samples": 10,
        "score_z_thresholds": {1: 1.5, 2: 2.5, 3: 3.5},
        "indicators": [
            {"indicator_id": "test_metric", "risk_direction": "both"},
            {"indicator_id": "gait_speed", "risk_direction": "below"},
        ],
    }
    payload.update(overrides)
    return LongitudinalBaselinePolicy(**payload)


def _insert_samples(store, indicator_id, values, *, start_day=1, hour=10):
    rows = []
    for index, value in enumerate(values):
        moment = datetime(
            2026, 8, start_day + index, hour, 0, tzinfo=timezone(timedelta(hours=8))
        )
        rows.append(
            {
                "observed_at": moment.isoformat(),
                "bucket": "day" if 6 <= hour < 18 else "night",
                "indicator_id": indicator_id,
                "group_id": "test",
                "source_modality": "sleep",
                "value": float(value),
                "unit": "u",
                "assessability": "assessable",
                "quality_status": "pass",
                "sample_count": 1,
                "scenario_id": None,
                "time_start_at": moment.isoformat(),
                "time_end_at": None,
                "source_ref": "sha256:" + "0" * 64,
                "run_id": "test",
                "report_digest": f"{index:064x}",
                "limitations_json": "[]",
                "quality_metrics_json": "{}",
                "baseline_eligible": 1,
            }
        )
    store.insert_observations(rows)


def test_insufficient_samples_yield_no_scores(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        _insert_samples(store, "test_metric", [100.0] * 5)
        baselines, counts = recompute_baselines(store, _policy(), now=NOW)
        target = next(b for b in baselines if b.indicator_id == "test_metric" and b.bucket == "day")
        assert target.status == "insufficient_samples"
        assert target.median is None
        assert counts["insufficient_baseline"] >= 1
        candidates, detect_counts = detect_deviations(
            store, _policy(), policy_digest=POLICY_DIGEST
        )
        assert candidates == []
        assert detect_counts["skipped_no_baseline"] >= 1


def test_steady_sequence_emits_no_candidate(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        _insert_samples(store, "test_metric", [99, 100, 101] * 3 + [99, 100, 100])
        recompute_baselines(store, _policy(), now=NOW)
        candidates, counts = detect_deviations(
            store, _policy(), policy_digest=POLICY_DIGEST
        )
        assert candidates == []
        assert counts["steady"] >= 1


def test_step_shift_scores_by_z_threshold(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        values = [90, 95, 100, 105, 110, 90, 95, 100, 105, 110, 100, 120]
        _insert_samples(store, "test_metric", values)
        recompute_baselines(store, _policy(), now=NOW)
        candidates, _ = detect_deviations(store, _policy(), policy_digest=POLICY_DIGEST)
        assert len(candidates) == 1
        candidate = candidates[0]
        # median=100, MAD=5 -> z = 20 / (1.4826*5) ~= 2.70 -> score 2
        assert candidate.z_value == pytest.approx(2.698, abs=0.01)
        assert candidate.score == 2
        assert candidate.direction == "above"
        assert candidate.policy_digest == POLICY_DIGEST
        assert candidate.ewma_shift is not None


def test_zero_mad_degenerate_rule_uses_fixed_low_score(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        _insert_samples(store, "test_metric", [100.0] * 11 + [120.0])
        recompute_baselines(store, _policy(), now=NOW)
        candidates, _ = detect_deviations(store, _policy(), policy_digest=POLICY_DIGEST)
        assert len(candidates) == 1
        assert candidates[0].score == _policy().zero_mad_score == 1
        assert ZERO_MAD_LIMITATION in candidates[0].limitations


def test_non_risk_direction_is_not_a_candidate(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        # gait_speed risk direction is "below"; a sudden increase is skipped.
        _insert_samples(store, "gait_speed", [1.0] * 11 + [1.5])
        recompute_baselines(store, _policy(), now=NOW)
        candidates, counts = detect_deviations(
            store, _policy(), policy_digest=POLICY_DIGEST
        )
        assert candidates == []
        assert counts["skipped_non_risk_direction"] >= 1


def test_day_and_night_baselines_are_independent(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        _insert_samples(store, "test_metric", [100.0] * 10, hour=10)
        _insert_samples(store, "test_metric", [60.0] * 10, hour=22)
        baselines, _ = recompute_baselines(store, _policy(), now=NOW)
        day = next(b for b in baselines if b.indicator_id == "test_metric" and b.bucket == "day")
        night = next(b for b in baselines if b.indicator_id == "test_metric" and b.bucket == "night")
        assert day.status == "ready" and day.median == 100.0
        assert night.status == "ready" and night.median == 60.0


def test_detection_rerun_is_idempotent(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        values = [90, 95, 100, 105, 110, 90, 95, 100, 105, 110, 100, 120]
        _insert_samples(store, "test_metric", values)
        recompute_baselines(store, _policy(), now=NOW)
        first, _ = detect_deviations(store, _policy(), policy_digest=POLICY_DIGEST)
        second, counts = detect_deviations(store, _policy(), policy_digest=POLICY_DIGEST)
        assert len(first) == 1
        assert second == []
        assert counts["skipped_duplicate"] >= 1
        assert store.counts()["deviation_candidates"] == 1


def test_public_report_carries_no_values(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        values = [90, 95, 100, 105, 110, 90, 95, 100, 105, 110, 100, 120]
        _insert_samples(store, "test_metric", values)
        _, status_counts = recompute_baselines(store, _policy(), now=NOW)
        _, detect_counts = detect_deviations(store, _policy(), policy_digest=POLICY_DIGEST)
        owner, public = build_assessment_reports(
            store, _policy(), policy_digest=POLICY_DIGEST,
            status_counts={**status_counts, **detect_counts},
        )
        assert owner.baselines and owner.deviation_candidates
        assert public.baselines == [] and public.deviation_candidates == []
        assert public.global_score is None and owner.global_score is None


def test_contract_validators_enforce_governance():
    with pytest.raises(ValueError):
        _policy(score_z_thresholds={1: 2.5, 2: 1.5, 3: 3.5})
    with pytest.raises(ValueError):
        _policy(day_start_hour=18, day_end_hour=6)
    with pytest.raises(ValueError):
        _policy(
            indicators=[
                {"indicator_id": "x", "risk_direction": "both"},
                {"indicator_id": "x", "risk_direction": "above"},
            ]
        )
    with pytest.raises(ValueError):
        PersonalBaseline(
            elder_ref="e",
            indicator_id="x",
            bucket="day",
            computed_at=NOW,
            window_days=28,
            sample_count=0,
            status="ready",
            policy_revision="r",
        )
    with pytest.raises(ValueError):
        LongitudinalAssessmentReport(
            report_version="v",
            visibility="public_evidence",
            elder_ref="e",
            policy_revision="r",
            policy_digest=POLICY_DIGEST,
            baselines=[
                PersonalBaseline(
                    elder_ref="e",
                    indicator_id="x",
                    bucket="day",
                    computed_at=NOW,
                    window_days=28,
                    sample_count=12,
                    status="ready",
                    median=1.0,
                    mad=0.1,
                    ewma=1.0,
                    policy_revision="r",
                )
            ],
        )


def test_naive_now_is_rejected(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        with pytest.raises(ValueError, match="timezone-aware"):
            recompute_baselines(store, _policy(), now=datetime(2026, 8, 11, 12, 0))
