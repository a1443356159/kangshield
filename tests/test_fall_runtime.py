from __future__ import annotations

from kangshield.information.contracts import FallKeypointGate, FallMotionFrameValue
from kangshield.information.fall_candidates import (
    generate_fall_candidate_episodes,
    load_fall_candidate_policy,
)
from kangshield.information.fall_features import load_fall_feature_config
from kangshield.information.privacy import sha256_file


def _frame(
    sequence: int,
    timestamp_ms: int,
    *,
    rapid: bool,
    horizontal_ms: int,
) -> FallMotionFrameValue:
    return FallMotionFrameValue(
        feature_version="fall-motion-features-v0.5.0",
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
        posture_horizontal_proxy=True,
        posture_horizontal_duration_ms=horizontal_ms,
        near_floor_proxy=False,
        near_floor_duration_ms=0,
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
    assert candidate.input_fall_feature_policy_sha256 == sha256_file(
        "configs/v1-g4-fall-features.json"
    )
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


def test_close_candidates_are_merged_into_one_review_episode():
    policy = load_fall_candidate_policy(
        "configs/v1-g4-event-candidate-policy.json"
    )
    frames = []
    sequence = 0
    for timestamp_ms in range(0, 10_001, 200):
        if timestamp_ms <= 1_400:
            horizontal_ms = timestamp_ms
        elif timestamp_ms < 2_200:
            horizontal_ms = 0
        elif timestamp_ms >= 4_800:
            horizontal_ms = timestamp_ms - 2_200
        else:
            horizontal_ms = 0
        frame = _frame(
            sequence,
            timestamp_ms,
            rapid=False,
            horizontal_ms=horizontal_ms,
        )
        if 1_400 < timestamp_ms < 2_200 or 2_200 <= timestamp_ms < 4_800:
            frame.bbox_horizontal_proxy = False
            frame.posture_horizontal_proxy = False
        frames.append(frame)
        sequence += 1

    episodes = generate_fall_candidate_episodes(
        frames,
        duration_ms=10_200,
        case_ref="edge-segment-two-episodes",
        policy=policy,
    )

    assert len(episodes) == 1
    assert episodes[0].start_ms == 0
    assert episodes[0].end_ms == 10_200


def test_upright_recovery_suppresses_a_torso_only_candidate():
    policy = load_fall_candidate_policy(
        "configs/v1-g4-event-candidate-policy.json"
    )
    frames = []
    for sequence, timestamp_ms in enumerate(range(0, 4_001, 200)):
        frame = _frame(
            sequence,
            timestamp_ms,
            rapid=False,
            horizontal_ms=0,
        )
        frame.bbox_horizontal_proxy = False
        if timestamp_ms <= 1_200:
            frame.posture_horizontal_proxy = True
            frame.posture_horizontal_duration_ms = timestamp_ms
        else:
            frame.posture_horizontal_proxy = False
            frame.posture_horizontal_duration_ms = 0
        frames.append(frame)

    episodes = generate_fall_candidate_episodes(
        frames,
        duration_ms=4_200,
        case_ref="edge-segment-upright-recovery",
        policy=policy,
    )

    assert episodes == []


def test_rapid_descent_that_remains_near_floor_emits_candidate():
    policy = load_fall_candidate_policy(
        "configs/v1-g4-event-candidate-policy.json"
    )
    frames = []
    for sequence, timestamp_ms in enumerate(range(0, 1_401, 200)):
        frame = _frame(
            sequence,
            timestamp_ms,
            rapid=timestamp_ms == 0,
            horizontal_ms=0,
        )
        frame.bbox_horizontal_proxy = False
        frame.posture_horizontal_proxy = False
        frame.posture_horizontal_duration_ms = 0
        frame.near_floor_proxy = True
        frame.near_floor_duration_ms = timestamp_ms
        frames.append(frame)

    episodes = generate_fall_candidate_episodes(
        frames,
        duration_ms=1_600,
        case_ref="edge-segment-near-floor",
        policy=policy,
    )

    assert len(episodes) == 1
    assert episodes[0].trigger_path == "rapid_descent_then_near_floor_low_motion"


def test_near_floor_proxy_is_suppressed_after_leaving_zone_and_recovering():
    policy = load_fall_candidate_policy(
        "configs/v1-g4-event-candidate-policy.json"
    )
    frames = []
    for sequence, timestamp_ms in enumerate(range(0, 2_001, 200)):
        frame = _frame(
            sequence,
            timestamp_ms,
            rapid=timestamp_ms == 0,
            horizontal_ms=0,
        )
        frame.bbox_horizontal_proxy = False
        frame.posture_horizontal_proxy = False
        frame.posture_horizontal_duration_ms = 0
        frame.near_floor_proxy = timestamp_ms <= 600
        frame.near_floor_duration_ms = timestamp_ms if timestamp_ms <= 600 else 0
        frames.append(frame)

    episodes = generate_fall_candidate_episodes(
        frames,
        duration_ms=2_200,
        case_ref="edge-segment-near-floor-recovery",
        policy=policy,
    )

    assert episodes == []
