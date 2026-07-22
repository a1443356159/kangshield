from __future__ import annotations

from pathlib import Path

import pytest

from kangshield.information.contracts import (
    EvidenceLevel,
    FallCandidateCaseStressEvaluation,
    FallCandidatePublicStressReport,
    FallEventCandidatePolicy,
    FallKeypointGate,
    FallMotionFrameValue,
    RunManifest,
    RunStatus,
)
from kangshield.information.fall_candidates import (
    _require_clean_completed_run,
    generate_fall_candidate_episodes,
    load_fall_candidate_policy,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_POLICY = (
    PROJECT_ROOT / "configs" / "v1-g4-event-candidate-policy.json"
)


def _frame(
    sequence: int,
    timestamp_ms: int,
    *,
    track_id: int | None = 1,
    horizontal: bool = False,
    horizontal_duration_ms: int = 0,
    rapid_descent: bool | None = False,
    low_motion: bool | None = False,
) -> FallMotionFrameValue:
    available = track_id is not None
    return FallMotionFrameValue(
        feature_version="fall-motion-features-v0.1.0",
        frame_sequence=sequence,
        timestamp_ms=timestamp_ms,
        frame_width=640,
        frame_height=480,
        person_count=1 if available else 0,
        selected_detection_index=0 if available else None,
        selected_track_id=track_id,
        active_path="box_plus_keypoints" if available else "unavailable",
        bbox_horizontal_proxy=horizontal if available else None,
        horizontal_duration_ms=(horizontal_duration_ms if available else None),
        rapid_descent_proxy=rapid_descent if available else None,
        low_motion_proxy=low_motion if available else None,
        keypoint_gate=FallKeypointGate(
            expected_layout="COCO-17",
            expected_count=17,
            observed_count=17 if available else 0,
            confidence_threshold=0.5,
            visible_count=17 if available else 0,
            visible_ratio=1.0 if available else None,
            visible_ratio_threshold=0.5,
            required_indices=[5, 6, 11, 12],
            required_visible_count=4 if available else 0,
            required_all_visible=available,
            status="passed" if available else "failed_no_detection",
            geometry_available=available,
            torso_horizontal_proxy=horizontal if available else None,
        ),
    )


def test_transition_path_emits_one_closed_episode_with_no_risk_or_alert():
    policy = load_fall_candidate_policy(CANDIDATE_POLICY)
    frames = [
        _frame(0, 0),
        _frame(1, 200),
        _frame(2, 400, rapid_descent=True),
        _frame(3, 600, horizontal=True, horizontal_duration_ms=0),
        _frame(4, 800, horizontal=True, horizontal_duration_ms=200),
        _frame(5, 1000, horizontal=True, horizontal_duration_ms=400),
        _frame(6, 1200, horizontal=True, horizontal_duration_ms=600),
        _frame(7, 1400, horizontal=True, horizontal_duration_ms=800),
        _frame(8, 1600),
        _frame(9, 2000),
        _frame(10, 2200),
    ]

    episodes = generate_fall_candidate_episodes(
        frames,
        duration_ms=3000,
        case_ref="transition-case",
        policy=policy,
    )

    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.start_ms == 400
    assert episode.detected_at_ms == 1200
    assert episode.end_ms == 2000
    assert episode.trigger_path == "rapid_descent_then_horizontal"
    assert episode.risk_assessment_emitted is False
    assert episode.alert_emitted is False


def test_settled_fallback_backfills_horizontal_start():
    policy = load_fall_candidate_policy(CANDIDATE_POLICY)
    frames = [
        _frame(0, 0, horizontal=True, horizontal_duration_ms=0),
        _frame(1, 400, horizontal=True, horizontal_duration_ms=400),
        _frame(2, 800, horizontal=True, horizontal_duration_ms=800),
        _frame(
            3,
            1200,
            horizontal=True,
            horizontal_duration_ms=1200,
            low_motion=True,
        ),
        _frame(4, 1600),
        _frame(5, 2000),
    ]

    episodes = generate_fall_candidate_episodes(
        frames,
        duration_ms=2400,
        case_ref="settled-case",
        policy=policy,
    )

    assert len(episodes) == 1
    assert episodes[0].start_ms == 0
    assert episodes[0].detected_at_ms == 1200
    assert episodes[0].end_ms == 1800
    assert episodes[0].trigger_path == "settled_horizontal_low_motion"


@pytest.mark.parametrize("boundary", ["track_change", "frame_gap"])
def test_temporal_evidence_resets_at_identity_or_gap_boundary(boundary: str):
    policy = load_fall_candidate_policy(CANDIDATE_POLICY)
    last_timestamp = 800 if boundary == "track_change" else 1000
    last_track = 2 if boundary == "track_change" else 1
    frames = [
        _frame(0, 0, rapid_descent=True),
        _frame(1, 200, horizontal=True, horizontal_duration_ms=0),
        _frame(2, 400, horizontal=True, horizontal_duration_ms=200),
        _frame(3, last_timestamp, horizontal=True, horizontal_duration_ms=600, track_id=last_track),
    ]

    assert generate_fall_candidate_episodes(
        frames,
        duration_ms=1600,
        case_ref=boundary,
        policy=policy,
    ) == []


def test_persistent_horizontal_evidence_is_deduplicated_to_one_episode():
    policy = load_fall_candidate_policy(CANDIDATE_POLICY)
    frames = [_frame(0, 0, rapid_descent=True)] + [
        _frame(
            index,
            index * 200,
            horizontal=True,
            horizontal_duration_ms=(index - 1) * 200,
            low_motion=True,
        )
        for index in range(1, 9)
    ]

    episodes = generate_fall_candidate_episodes(
        frames,
        duration_ms=2400,
        case_ref="dedup-case",
        policy=policy,
    )

    assert len(episodes) == 1
    assert episodes[0].trigger_path == "rapid_descent_then_horizontal"


def test_generator_rejects_unordered_frames():
    policy = load_fall_candidate_policy(CANDIDATE_POLICY)
    with pytest.raises(ValueError, match="strictly increasing"):
        generate_fall_candidate_episodes(
            [_frame(0, 200), _frame(1, 100)],
            duration_ms=1000,
            case_ref="unordered",
            policy=policy,
        )


def test_rule_bearing_fixture_is_allowed_but_scorer_only_fixture_is_not():
    real = load_fall_candidate_policy(CANDIDATE_POLICY)
    fixture = real.model_copy(
        update={
            "policy_id": "rule-bearing-fixture",
            "fixture": True,
            "review_status": "fixture_only",
        }
    )
    assert generate_fall_candidate_episodes(
        [_frame(0, 0), _frame(1, 200)],
        duration_ms=1000,
        case_ref="fixture",
        policy=fixture,
    ) == []

    scorer_only = FallEventCandidatePolicy(
        policy_id="scorer-only-fixture",
        fixture=True,
        input_fall_feature_policy_sha256="0" * 64,
        decision_logic_summary="Fixed predictions only",
    )
    with pytest.raises(ValueError, match="missing generation rules"):
        generate_fall_candidate_episodes(
            [_frame(0, 0)],
            duration_ms=1000,
            case_ref="scorer-only",
            policy=scorer_only,
        )


def test_source_provenance_gate_rejects_dirty_or_wrong_stage(tmp_path):
    run_dir = tmp_path / "source-run"
    dirty = RunManifest(
        run_id=run_dir.name,
        stage="v1-g4-fall-feature-benchmark",
        status=RunStatus.COMPLETED,
        evidence_level=EvidenceLevel.E1,
        code_version="abc1234",
        code_dirty=True,
    )
    with pytest.raises(ValueError, match="dirty"):
        _require_clean_completed_run(
            dirty,
            run_dir=run_dir,
            expected_stage="v1-g4-fall-feature-benchmark",
            allow_dirty_source=False,
        )
    _require_clean_completed_run(
        dirty,
        run_dir=run_dir,
        expected_stage="v1-g4-fall-feature-benchmark",
        allow_dirty_source=True,
    )
    wrong_stage = dirty.model_copy(
        update={"stage": "v1-g4-fall-adl-negative-benchmark", "code_dirty": False}
    )
    with pytest.raises(ValueError, match="wrong stage"):
        _require_clean_completed_run(
            wrong_stage,
            run_dir=run_dir,
            expected_stage="v1-g4-fall-feature-benchmark",
            allow_dirty_source=False,
        )


def test_public_report_contract_has_no_exact_candidate_or_track_fields():
    forbidden = {
        "start_ms",
        "end_ms",
        "detected_at_ms",
        "selected_track_id",
        "source_path",
    }
    assert forbidden.isdisjoint(FallCandidateCaseStressEvaluation.model_fields)
    assert forbidden.isdisjoint(FallCandidatePublicStressReport.model_fields)
