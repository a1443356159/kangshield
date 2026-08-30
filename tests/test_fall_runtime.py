from __future__ import annotations

from kangshield.information.contracts import FallKeypointGate, FallMotionFrameValue
from kangshield.information.fall_candidates import (
    generate_fall_candidate_episodes,
    load_fall_candidate_policy,
)
from kangshield.information.fall_features import load_fall_feature_config


def _frame(
    sequence: int,
    timestamp_ms: int,
    *,
    rapid: bool,
    horizontal_ms: int,
) -> FallMotionFrameValue:
    return FallMotionFrameValue(
        feature_version="fall-motion-features-v0.1.0",
        frame_sequence=sequence,
        timestamp_ms=timestamp_ms,
        frame_width=640,
        frame_height=360,
        person_count=1,
        selected_detection_index=0,
        selected_track_id=1,
        active_path="box_only",
        bbox_horizontal_proxy=True,
        horizontal_duration_ms=horizontal_ms,
        rapid_descent_proxy=rapid,
        low_motion_proxy=True,
        keypoint_gate=FallKeypointGate(
            expected_layout="COCO-17",
            expected_count=17,
            observed_count=0,
            confidence_threshold=0.5,
            visible_count=0,
            visible_ratio=None,
            visible_ratio_threshold=0.5,
            required_indices=[5, 6, 11, 12],
            required_visible_count=0,
            required_all_visible=False,
            status="failed_layout",
            geometry_available=False,
        ),
    )


def test_final_fall_policies_are_loadable_and_digest_bound():
    feature = load_fall_feature_config("configs/v1-g4-fall-features.json")
    candidate = load_fall_candidate_policy(
        "configs/v1-g4-event-candidate-policy.json"
    )

    assert feature.feature_version == candidate.input_fall_feature_version
    assert len(candidate.input_fall_feature_policy_sha256) == 64
    assert candidate.risk_assessment_emitted is False
    assert candidate.alert_emitted is False


def test_rapid_descent_then_horizontal_emits_one_review_candidate():
    policy = load_fall_candidate_policy(
        "configs/v1-g4-event-candidate-policy.json"
    )
    frames = [
        _frame(0, 0, rapid=True, horizontal_ms=0),
        _frame(1, 300, rapid=False, horizontal_ms=300),
        _frame(2, 600, rapid=False, horizontal_ms=600),
        _frame(3, 900, rapid=False, horizontal_ms=900),
    ]

    episodes = generate_fall_candidate_episodes(
        frames,
        duration_ms=2_000,
        case_ref="edge-segment-1",
        policy=policy,
    )

    assert len(episodes) == 1
    assert episodes[0].trigger_path == "rapid_descent_then_horizontal"
    assert episodes[0].risk_assessment_emitted is False
    assert episodes[0].alert_emitted is False
