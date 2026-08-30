"""Runtime fall-motion proxies used by the continuous edge product."""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import (
    FallFeatureConfig,
    FallKeypointGate,
    FallMotionFrameValue,
    FeatureEvent,
)


@dataclass(frozen=True)
class _HistorySample:
    timestamp_ms: int
    center_x: float
    center_y: float


def load_fall_feature_config(path: Path) -> FallFeatureConfig:
    with Path(path).open(encoding="utf-8") as stream:
        return FallFeatureConfig.model_validate(json.load(stream))


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _valid_bbox(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, dict):
        return None
    bbox = value.get("bbox_xyxy")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    numbers = [_finite_float(item) for item in bbox]
    if any(item is None for item in numbers):
        return None
    x1, y1, x2, y2 = (float(item) for item in numbers)
    return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def _empty_keypoint_gate(
    config: FallFeatureConfig, status: str = "failed_no_detection"
) -> FallKeypointGate:
    return FallKeypointGate(
        expected_layout=config.expected_keypoint_layout,
        expected_count=config.expected_keypoint_count,
        observed_count=0,
        confidence_threshold=config.keypoint_confidence_threshold,
        visible_count=0,
        visible_ratio=None,
        visible_ratio_threshold=config.keypoint_visible_ratio_threshold,
        required_indices=config.required_keypoint_indices,
        required_visible_count=0,
        required_all_visible=False,
        status=status,
        geometry_available=False,
    )


def _keypoint_gate(
    detection: dict[str, Any], config: FallFeatureConfig
) -> FallKeypointGate:
    points = detection.get("keypoints_xyc")
    if not isinstance(points, list) or len(points) != config.expected_keypoint_count:
        gate = _empty_keypoint_gate(config, "failed_layout")
        gate.observed_count = len(points) if isinstance(points, list) else 0
        return gate
    scores: list[float | None] = []
    coordinates: list[tuple[float, float] | None] = []
    for point in points:
        if not isinstance(point, list) or len(point) < 3:
            scores.append(None)
            coordinates.append(None)
            continue
        x, y, confidence = (_finite_float(item) for item in point[:3])
        scores.append(confidence)
        coordinates.append((x, y) if x is not None and y is not None else None)
    visible = [
        score is not None and score >= config.keypoint_confidence_threshold
        for score in scores
    ]
    visible_count = sum(visible)
    visible_ratio = visible_count / config.expected_keypoint_count
    required_visible_count = sum(
        visible[index] and coordinates[index] is not None
        for index in config.required_keypoint_indices
    )
    required_all_visible = required_visible_count == len(
        config.required_keypoint_indices
    )
    common = {
        "expected_layout": config.expected_keypoint_layout,
        "expected_count": config.expected_keypoint_count,
        "observed_count": len(points),
        "confidence_threshold": config.keypoint_confidence_threshold,
        "visible_count": visible_count,
        "visible_ratio": round(visible_ratio, 6),
        "visible_ratio_threshold": config.keypoint_visible_ratio_threshold,
        "required_indices": config.required_keypoint_indices,
        "required_visible_count": required_visible_count,
        "required_all_visible": required_all_visible,
    }
    if not required_all_visible:
        return FallKeypointGate(
            **common, status="failed_required_points", geometry_available=False
        )
    if visible_ratio < config.keypoint_visible_ratio_threshold:
        return FallKeypointGate(
            **common, status="failed_visible_ratio", geometry_available=False
        )
    left_shoulder, right_shoulder, left_hip, right_hip = (
        coordinates[index] for index in config.required_keypoint_indices
    )
    assert all(
        item is not None
        for item in (left_shoulder, right_shoulder, left_hip, right_hip)
    )
    shoulder_midpoint = (
        (left_shoulder[0] + right_shoulder[0]) / 2,
        (left_shoulder[1] + right_shoulder[1]) / 2,
    )
    hip_midpoint = (
        (left_hip[0] + right_hip[0]) / 2,
        (left_hip[1] + right_hip[1]) / 2,
    )
    dx = hip_midpoint[0] - shoulder_midpoint[0]
    dy = hip_midpoint[1] - shoulder_midpoint[1]
    if math.hypot(dx, dy) <= 1e-9:
        return FallKeypointGate(
            **common, status="failed_degenerate_geometry", geometry_available=False
        )
    angle = math.degrees(math.atan2(abs(dy), abs(dx)))
    return FallKeypointGate(
        **common,
        status="passed",
        geometry_available=True,
        torso_angle_from_horizontal_deg=round(angle, 6),
        torso_horizontal_proxy=angle <= config.torso_horizontal_angle_max_deg,
    )


class FallMotionFeatureExtractor:
    """Stateful largest-person motion extractor; it never emits a risk score."""

    def __init__(
        self, config: FallFeatureConfig, *, frame_width: int, frame_height: int
    ) -> None:
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("frame dimensions must be positive")
        self.config = config
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.frame_diagonal = math.hypot(frame_width, frame_height)
        self._history: deque[_HistorySample] = deque()
        self._track_id: int | None = None
        self._last_timestamp_ms: int | None = None
        self._horizontal_started_ms: int | None = None

    def _reset_temporal(self) -> None:
        self._history.clear()
        self._track_id = None
        self._horizontal_started_ms = None

    def process(self, pose_event: FeatureEvent) -> FallMotionFrameValue:
        if pose_event.feature_type != "video.pose_frame":
            raise ValueError("fall features require video.pose_frame")
        timestamp_ms = pose_event.time_range.start_ms
        if timestamp_ms is None:
            raise ValueError("pose frame requires relative start_ms")
        if self._last_timestamp_ms is not None and timestamp_ms <= self._last_timestamp_ms:
            raise ValueError("pose frame timestamps must be strictly increasing")
        payload = pose_event.value
        if not isinstance(payload, dict):
            raise ValueError("pose frame value must be an object")
        sequence = payload.get("frame_sequence")
        detections = payload.get("detections")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValueError("pose frame_sequence must be a non-negative integer")
        if not isinstance(detections, list) or payload.get("person_count") != len(
            detections
        ):
            raise ValueError("pose detections are inconsistent")
        reasons: list[str] = []
        if (
            self._last_timestamp_ms is not None
            and timestamp_ms - self._last_timestamp_ms > self.config.max_frame_gap_ms
        ):
            self._reset_temporal()
            reasons.append("frame_gap_history_reset")
        self._last_timestamp_ms = timestamp_ms
        valid = []
        for index, detection in enumerate(detections):
            bbox = _valid_bbox(detection)
            if bbox is None:
                continue
            x1, y1, x2, y2 = bbox
            valid.append((index, detection, bbox, (x2 - x1) * (y2 - y1)))
        if not valid:
            self._reset_temporal()
            reasons.append("no_person_detection" if not detections else "no_valid_bbox")
            return FallMotionFrameValue(
                feature_version=self.config.feature_version,
                frame_sequence=sequence,
                timestamp_ms=timestamp_ms,
                frame_width=self.frame_width,
                frame_height=self.frame_height,
                person_count=len(detections),
                active_path="unavailable",
                fallback_reasons=reasons,
                keypoint_gate=_empty_keypoint_gate(self.config),
            )
        if len(detections) > 1:
            reasons.append("multiple_people_largest_bbox_only")
        index, detection, (x1, y1, x2, y2), _ = max(
            valid, key=lambda item: (item[3], -item[0])
        )
        width, height = x2 - x1, y2 - y1
        center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
        ratio = width / height
        horizontal = ratio >= self.config.bbox_horizontal_ratio_threshold
        raw_track = detection.get("track_id")
        track_id = (
            raw_track
            if isinstance(raw_track, int) and not isinstance(raw_track, bool)
            else None
        )
        changed = self._track_id is not None and track_id != self._track_id
        if track_id is None:
            self._reset_temporal()
            reasons.append("track_id_missing_temporal_features_unavailable")
        elif changed:
            self._reset_temporal()
            reasons.append("track_changed_history_reset")

        descent_span = stationary_span = None
        center_drop = max_displacement = None
        rapid_descent = low_motion = None
        horizontal_duration: int | None = 0
        if track_id is not None:
            self._track_id = track_id
            self._history.append(_HistorySample(timestamp_ms, center_x, center_y))
            maximum_window = max(
                self.config.descent_history_window_ms,
                self.config.stationary_window_ms,
            )
            while timestamp_ms - self._history[0].timestamp_ms > maximum_window:
                self._history.popleft()
            descent = [
                item
                for item in self._history
                if timestamp_ms - item.timestamp_ms
                <= self.config.descent_history_window_ms
            ]
            descent_span = timestamp_ms - descent[0].timestamp_ms
            if descent_span >= self.config.descent_min_span_ms:
                center_drop = round((center_y - descent[0].center_y) / self.frame_height, 6)
                rapid_descent = (
                    center_drop >= self.config.rapid_descent_center_y_ratio_threshold
                )
            else:
                reasons.append("descent_history_not_ready")
            stationary = [
                item
                for item in self._history
                if timestamp_ms - item.timestamp_ms <= self.config.stationary_window_ms
            ]
            stationary_span = timestamp_ms - stationary[0].timestamp_ms
            if stationary_span >= self.config.stationary_min_span_ms:
                max_displacement = round(
                    max(
                        math.hypot(center_x - item.center_x, center_y - item.center_y)
                        / self.frame_diagonal
                        for item in stationary
                    ),
                    6,
                )
                low_motion = (
                    max_displacement
                    <= self.config.stationary_center_displacement_diagonal_ratio_threshold
                )
            else:
                reasons.append("stationary_history_not_ready")
            if horizontal:
                if self._horizontal_started_ms is None or changed:
                    self._horizontal_started_ms = timestamp_ms
                horizontal_duration = timestamp_ms - self._horizontal_started_ms
            else:
                self._horizontal_started_ms = None

        gate = _keypoint_gate(detection, self.config)
        active_path = "box_plus_keypoints" if gate.status == "passed" else "box_only"
        if active_path == "box_only":
            reasons.append(f"keypoint_gate_{gate.status}_use_box_only")
        return FallMotionFrameValue(
            feature_version=self.config.feature_version,
            frame_sequence=sequence,
            timestamp_ms=timestamp_ms,
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            person_count=len(detections),
            selected_detection_index=index,
            selected_track_id=track_id,
            active_path=active_path,
            fallback_reasons=reasons,
            bbox_width_height_ratio=round(ratio, 6),
            bbox_center_x_ratio=round(center_x / self.frame_width, 6),
            bbox_center_y_ratio=round(center_y / self.frame_height, 6),
            bbox_bottom_y_ratio=round(y2 / self.frame_height, 6),
            bbox_area_frame_ratio=round(
                width * height / (self.frame_width * self.frame_height), 6
            ),
            bbox_horizontal_proxy=horizontal,
            horizontal_duration_ms=horizontal_duration,
            descent_history_span_ms=descent_span,
            center_drop_frame_height_ratio=center_drop,
            rapid_descent_proxy=rapid_descent,
            stationary_history_span_ms=stationary_span,
            max_center_displacement_diagonal_ratio=max_displacement,
            low_motion_proxy=low_motion,
            keypoint_gate=gate,
        )
