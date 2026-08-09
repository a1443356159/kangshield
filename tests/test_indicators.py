from __future__ import annotations

import json
from pathlib import Path

import pytest

from kangshield.information.contracts import (
    EvidenceLevel,
    IndicatorAssessability,
    IndicatorAssessment,
    IndicatorAssessmentStatus,
    IndicatorObservation,
    QualityStatus,
    SourceType,
)
from kangshield.information.indicators import (
    build_indicator_reports,
    extract_sleep_indicators,
    extract_video_indicators,
)


FIXTURES = Path(__file__).parent / "fixtures"
VIDEO_FIXTURE = FIXTURES / "indicators" / "video-indicators.synthetic.json"
SLEEP_FIXTURE = FIXTURES / "sleep" / "sdhy1-export.synthetic.json"


def test_indicator_contract_fails_closed_for_missing_value():
    with pytest.raises(ValueError, match="requires a value"):
        IndicatorObservation(
            observation_id="indicator-test",
            indicator_id="gait_speed",
            group="gait",
            source_modality="video",
            source_ref="sha256:test",
            value=None,
            unit="m/s",
            assessability=IndicatorAssessability.ASSESSABLE,
            quality_status=QualityStatus.PASS,
        )


def test_assessment_cannot_score_without_frozen_policy():
    with pytest.raises(ValueError, match="must not contain a score"):
        IndicatorAssessment(
            assessment_id="assessment-test",
            observation_id="indicator-test",
            indicator_id="gait_speed",
            status=IndicatorAssessmentStatus.POLICY_NOT_FROZEN,
            score=1,
        )


def test_video_fixture_extracts_five_assessable_observations():
    report = extract_video_indicators(VIDEO_FIXTURE)

    assert len(report.observations) == 5
    assert all(
        item.assessability is IndicatorAssessability.ASSESSABLE
        for item in report.observations
    )
    assert {item.scenario_id for item in report.observations} >= {"C13", "C14"}
    assert next(
        item for item in report.observations if item.indicator_id == "gait_speed"
    ).value == 1.05


def test_video_fixture_cannot_be_promoted_to_live_evidence():
    with pytest.raises(ValueError, match="E1 fixture-only"):
        extract_video_indicators(
            VIDEO_FIXTURE,
            evidence_level=EvidenceLevel.E2,
            source_type=SourceType.LOCAL_FILE,
        )


def test_video_quality_gate_rejects_missing_calibration(tmp_path):
    payload = json.loads(VIDEO_FIXTURE.read_text(encoding="utf-8"))
    payload["measurements"] = [payload["measurements"][0]]
    payload["measurements"][0]["quality"]["calibration_valid"] = False
    path = tmp_path / "video.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    observation = extract_video_indicators(path).observations[0]
    assert observation.assessability is IndicatorAssessability.NOT_ASSESSABLE
    assert observation.value is None
    assert "missing_or_invalid_ground_calibration" in observation.limitations


def test_sleep_fixture_outputs_trends_and_blocks_incomplete_night_semantics():
    report = extract_sleep_indicators(SLEEP_FIXTURE)
    by_id = {item.indicator_id: item for item in report.observations}

    assert by_id["sleep_heart_rate_trend"].value == 67.5
    assert by_id["sleep_respiratory_rate_trend"].value == 14.5
    assert by_id["sleep_duration_h"].assessability is IndicatorAssessability.BLOCKED_SEMANTICS
    assert by_id["sleep_duration_h"].value is None


def test_summary_keeps_values_owner_only_and_never_scores_globally():
    owner, public = build_indicator_reports(
        [extract_video_indicators(VIDEO_FIXTURE), extract_sleep_indicators(SLEEP_FIXTURE)]
    )

    assert owner.global_score is None
    assert public.global_score is None
    assert owner.observations
    assert public.observations == []
    assert owner.status_counts == {
        "policy_not_frozen": 7,
        "blocked_semantics": 3,
    }
    assert all(assessment.score is None for assessment in owner.assessments)
