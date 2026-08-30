"""Runtime fall-candidate episode state machine."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable

from .contracts import (
    FallEventCandidateEpisode,
    FallEventCandidatePolicy,
    FallMotionFrameValue,
)


@dataclass
class _OpenEpisode:
    start_ms: int
    detected_at_ms: int
    last_horizontal_ms: int
    trigger_path: str


def load_fall_candidate_policy(
    path: Path, *, allow_fixture: bool = False
) -> FallEventCandidatePolicy:
    policy = FallEventCandidatePolicy.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
    if policy.fixture and not allow_fixture:
        raise ValueError("candidate generation requires a non-fixture policy")
    return policy


def generate_fall_candidate_episodes(
    frames: Iterable[FallMotionFrameValue],
    *,
    duration_ms: int,
    case_ref: str,
    policy: FallEventCandidatePolicy,
) -> list[FallEventCandidateEpisode]:
    """Generate label-blind episodes from runtime motion proxies."""

    if duration_ms <= 0:
        raise ValueError("candidate input duration must be positive")
    if policy.fixture:
        if policy.review_status != "fixture_only":
            raise ValueError("fixture policy must remain fixture-only")
    elif policy.review_status != "e1_exploratory_frozen":
        raise ValueError("candidate policy must be frozen")
    transition = policy.transition_rule
    settled = policy.settled_rule
    machine = policy.state_machine
    if transition is None or settled is None or machine is None:
        raise ValueError("candidate policy is missing generation rules")
    values = list(frames)
    if not values:
        return []
    previous_timestamp = previous_sequence = None
    frame_size = None
    for value in values:
        if value.feature_version != policy.input_fall_feature_version:
            raise ValueError("fall feature version differs from candidate policy")
        if value.risk_assessment_emitted or value.alert_emitted:
            raise ValueError("candidate input must not contain risk or alert output")
        if value.timestamp_ms >= duration_ms:
            raise ValueError("fall frame timestamp must remain inside segment")
        if previous_timestamp is not None and value.timestamp_ms <= previous_timestamp:
            raise ValueError("fall frame timestamps must be strictly increasing")
        if previous_sequence is not None and value.frame_sequence <= previous_sequence:
            raise ValueError("fall frame sequences must be strictly increasing")
        size = (value.frame_width, value.frame_height)
        if frame_size is not None and size != frame_size:
            raise ValueError("fall frame dimensions cannot change")
        previous_timestamp = value.timestamp_ms
        previous_sequence = value.frame_sequence
        frame_size = size

    episodes: list[FallEventCandidateEpisode] = []
    opened: _OpenEpisode | None = None
    current_track_id: int | None = None
    previous_timestamp = None
    rapid_descent_timestamps: list[int] = []
    refractory_until_ms = -1
    case_digest = sha256(case_ref.encode()).hexdigest()[:12]

    def close(requested_end_ms: int) -> None:
        nonlocal opened, rapid_descent_timestamps, refractory_until_ms
        if opened is None:
            return
        end_ms = min(duration_ms, max(opened.detected_at_ms + 1, requested_end_ms))
        episode = FallEventCandidateEpisode(
            candidate_version=policy.candidate_event_version,
            candidate_id=f"candidate_{case_digest}_{len(episodes):03d}",
            start_ms=opened.start_ms,
            detected_at_ms=opened.detected_at_ms,
            end_ms=end_ms,
            trigger_path=opened.trigger_path,
        )
        if episodes and episode.start_ms < episodes[-1].end_ms:
            raise ValueError("candidate episodes overlap")
        episodes.append(episode)
        refractory_until_ms = end_ms + machine.refractory_ms
        rapid_descent_timestamps = []
        opened = None

    for value in values:
        timestamp_ms = value.timestamp_ms
        track_id = value.selected_track_id
        boundary = (
            previous_timestamp is not None
            and timestamp_ms - previous_timestamp > machine.max_frame_gap_ms
        )
        track_changed = (
            current_track_id is not None
            and track_id is not None
            and track_id != current_track_id
        )
        if boundary or track_changed or track_id is None:
            if opened is not None:
                close(opened.last_horizontal_ms + machine.release_grace_ms)
            rapid_descent_timestamps = []
            current_track_id = None
        if track_id is None:
            previous_timestamp = timestamp_ms
            continue
        if current_track_id is None:
            current_track_id = track_id
        if (
            opened is not None
            and timestamp_ms > opened.last_horizontal_ms + machine.release_grace_ms
        ):
            close(opened.last_horizontal_ms + machine.release_grace_ms)

        cutoff = timestamp_ms - transition.rapid_descent_lookback_ms
        rapid_descent_timestamps = [
            item for item in rapid_descent_timestamps if item >= cutoff
        ]
        if value.rapid_descent_proxy is True:
            rapid_descent_timestamps.append(timestamp_ms)
        horizontal = value.bbox_horizontal_proxy is True
        if horizontal and value.horizontal_duration_ms is None:
            raise ValueError("horizontal frame is missing duration")
        if opened is not None and horizontal:
            opened.last_horizontal_ms = timestamp_ms

        if opened is None and timestamp_ms >= refractory_until_ms and horizontal:
            horizontal_duration = value.horizontal_duration_ms or 0
            transition_ready = (
                horizontal_duration >= transition.minimum_horizontal_duration_ms
                and bool(rapid_descent_timestamps)
                and (
                    not transition.low_motion_required
                    or value.low_motion_proxy is True
                )
            )
            settled_ready = (
                horizontal_duration >= settled.minimum_horizontal_duration_ms
                and value.low_motion_proxy is True
            )
            if transition_ready:
                opened = _OpenEpisode(
                    rapid_descent_timestamps[0],
                    timestamp_ms,
                    timestamp_ms,
                    "rapid_descent_then_horizontal",
                )
            elif settled_ready:
                opened = _OpenEpisode(
                    max(0, timestamp_ms - horizontal_duration),
                    timestamp_ms,
                    timestamp_ms,
                    "settled_horizontal_low_motion",
                )
        previous_timestamp = timestamp_ms
    if opened is not None:
        close(opened.last_horizontal_ms + machine.release_grace_ms)
    return episodes
