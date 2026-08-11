#!/usr/bin/env python3
"""Prediction metric algorithms synced from fall-detection `simple_metrics.py`.

This module is the pure-algorithm subset of the fall-detection realtime
prototype (source commit recorded in SYNC_MANIFEST.json): posture
classification and stabilization, primary-person selection, motion and step
events, gait/balance/sit-to-stand metrics and the candidate scoring helpers.
The fall-detection repository is the authoritative source for this logic;
local edits are not allowed — update via re-sync only.

Wiring layers from the source file (YOLO inference, face recognition,
dashboard, bridge polling, PoseC3D process management, argparse/main) are
deliberately excluded; kangshield provides equivalents in its own skeleton.
"""

from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np


# COCO human-pose keypoint indices used by Ultralytics pose models.
NOSE = 0
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_HIP, RIGHT_HIP = 11, 12
LEFT_KNEE, RIGHT_KNEE = 13, 14
LEFT_ANKLE, RIGHT_ANKLE = 15, 16

SKELETON = (
    (LEFT_SHOULDER, RIGHT_SHOULDER),
    (LEFT_SHOULDER, LEFT_HIP),
    (RIGHT_SHOULDER, RIGHT_HIP),
    (LEFT_HIP, RIGHT_HIP),
    (LEFT_HIP, LEFT_KNEE),
    (LEFT_KNEE, LEFT_ANKLE),
    (RIGHT_HIP, RIGHT_KNEE),
    (RIGHT_KNEE, RIGHT_ANKLE),
)


def midpoint(points: np.ndarray, first: int, second: int, minimum: float) -> np.ndarray | None:
    if points[first, 2] < minimum or points[second, 2] < minimum:
        return None
    return (points[first, :2] + points[second, :2]) / 2.0


def joint_angle(
    points: np.ndarray, first: int, middle: int, last: int, minimum: float
) -> float | None:
    if min(points[first, 2], points[middle, 2], points[last, 2]) < minimum:
        return None
    a = points[first, :2] - points[middle, :2]
    b = points[last, :2] - points[middle, :2]
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator < 1e-6:
        return None
    cosine = float(np.clip(np.dot(a, b) / denominator, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def median_or_none(values: list[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    return float(np.median(valid)) if valid else None


def round_optional(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def score_color(score: int) -> str:
    # The document maps score / 3 to green <=25%, yellow <=60%, red >60%.
    percentage = score / 3 * 100
    if percentage <= 25:
        return "green"
    if percentage <= 60:
        return "yellow"
    return "red"


def sit_to_stand_score(duration: float) -> dict[str, Any]:
    if duration >= 13.93:
        score = 3
    elif duration >= 10.0:
        score = 2
    elif duration >= 5.0:
        score = 1
    else:
        score = 0
    return {
        "duration_s": round(duration, 2),
        "score": score,
        "color": score_color(score),
    }


def cadence_score(cadence: float | None) -> dict[str, Any] | None:
    if cadence is None:
        return None
    if cadence < 80:
        score = 3
    elif cadence <= 90:
        score = 2
    elif cadence <= 100:
        score = 1
    else:
        score = 0
    return {"value_steps_min": round(cadence, 1), "score": score, "color": score_color(score)}


def gait_speed_score(speed: float | None) -> dict[str, Any] | None:
    if speed is None:
        return None
    if speed <= 0.8:
        score = 3
    elif speed <= 1.0:
        score = 2
    elif speed <= 1.5:
        score = 1
    else:
        score = 0
    return {"value_m_s": round(speed, 3), "score": score, "color": score_color(score)}


def prediction_summary(
    gait: dict[str, Any], sit_to_stand: dict[str, Any] | None
) -> dict[str, Any]:
    components: dict[str, dict[str, Any]] = {}
    if gait.get("cadence_assessment") is not None:
        components["cadence"] = gait["cadence_assessment"]
    if gait.get("gait_speed_assessment") is not None:
        components["gait_speed"] = gait["gait_speed_assessment"]
    if sit_to_stand is not None:
        components["sit_to_stand"] = sit_to_stand

    risk_percent = None
    risk_level = "collecting"
    if len(components) >= 2:
        risk_percent = round(
            sum(int(component["score"]) for component in components.values())
            / (3 * len(components))
            * 100,
            1,
        )
        if risk_percent <= 25:
            risk_level = "low"
        elif risk_percent <= 60:
            risk_level = "medium"
        else:
            risk_level = "high"

    flags: list[str] = []
    if gait.get("step_time_cv_percent") is not None and gait["step_time_cv_percent"] >= 10:
        flags.append("high_step_time_variability")
    if gait.get("gait_symmetry_percent") is not None and gait["gait_symmetry_percent"] >= 15:
        flags.append("gait_asymmetry")
    if gait.get("sway_rms_torso_percent") is not None and gait["sway_rms_torso_percent"] >= 5:
        flags.append("high_postural_sway")
    if gait.get("trunk_tilt_std_deg") is not None and gait["trunk_tilt_std_deg"] >= 8:
        flags.append("unstable_trunk")

    return {
        "risk_percent": risk_percent,
        "risk_level": risk_level,
        "readiness": "ready" if len(components) >= 2 else "collecting",
        "scored_component_count": len(components),
        "scored_components": components,
        "trend_flags": flags,
        "gait": gait,
        "note": (
            "Composite score uses only document-defined thresholds. "
            "Variability, symmetry and sway are trend signals pending validation."
        ),
    }


@dataclass
class TemporalState:
    pose_history: deque[str] = field(default_factory=lambda: deque(maxlen=5))
    previous_center: np.ndarray | None = None
    previous_time: float | None = None
    previous_tilt: float | None = None
    center_speed_px_s: float | None = None
    horizontal_speed_widths_s: float | None = None
    vertical_speed_heights_s: float | None = None
    tilt_speed_deg_s: float | None = None
    last_rapid_motion_at: float | None = None
    lying_since: float | None = None
    sit_stand_armed: bool = False
    transition_started: float | None = None
    last_sit_to_stand: dict[str, Any] | None = None
    prediction_samples: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=300)
    )
    action_samples: deque[tuple[float, np.ndarray, int, int]] = field(
        default_factory=lambda: deque(maxlen=90)
    )
    step_events: deque[tuple[float, int]] = field(
        default_factory=lambda: deque(maxlen=40)
    )
    ankle_phase: int = 0
    target_missing_since: float | None = None
    primary_track_id: int | None = None

    def reset_target_motion(self) -> None:
        self.previous_center = None
        self.previous_time = None
        self.previous_tilt = None
        self.center_speed_px_s = None
        self.horizontal_speed_widths_s = None
        self.vertical_speed_heights_s = None
        self.tilt_speed_deg_s = None
        self.last_rapid_motion_at = None

    def reset_prediction(self) -> None:
        self.prediction_samples.clear()
        self.step_events.clear()
        self.action_samples.clear()
        self.ankle_phase = 0

    def mark_no_person(self, now: float) -> None:
        self.reset_target_motion()
        if self.target_missing_since is None:
            self.target_missing_since = now
        elif now - self.target_missing_since >= 2.0:
            self.reset_prediction()
            self.primary_track_id = None

    def stable_pose(self, raw_pose: str) -> str:
        self.pose_history.append(raw_pose)
        counts = Counter(self.pose_history)
        pose, count = counts.most_common(1)[0]
        return pose if count >= 3 else "transition"

    def update_motion(
        self,
        center: np.ndarray,
        torso_tilt: float | None,
        now: float,
        frame_width: int,
        frame_height: int,
    ) -> None:
        if self.previous_center is not None and self.previous_time is not None:
            elapsed = now - self.previous_time
            jump = float(np.linalg.norm(center - self.previous_center))
            diagonal = math.hypot(frame_width, frame_height)
            if 0.02 <= elapsed <= 2.0 and jump < diagonal * 0.45:
                instant = jump / elapsed
                alpha = 0.35
                if self.center_speed_px_s is None:
                    self.center_speed_px_s = instant
                else:
                    self.center_speed_px_s = alpha * instant + (1 - alpha) * self.center_speed_px_s
                self.horizontal_speed_widths_s = float(
                    (center[0] - self.previous_center[0]) / elapsed / frame_width
                )
                self.vertical_speed_heights_s = float(
                    (center[1] - self.previous_center[1]) / elapsed / frame_height
                )
                if torso_tilt is not None and self.previous_tilt is not None:
                    self.tilt_speed_deg_s = (torso_tilt - self.previous_tilt) / elapsed
            else:
                self.center_speed_px_s = None
                self.horizontal_speed_widths_s = None
                self.vertical_speed_heights_s = None
                self.tilt_speed_deg_s = None
        self.previous_center = center
        self.previous_time = now
        self.previous_tilt = torso_tilt

    def update_events(self, pose: str, now: float) -> None:
        if pose == "lying":
            if self.lying_since is None:
                self.lying_since = now
        else:
            self.lying_since = None

        if pose == "sitting":
            self.sit_stand_armed = True
            self.transition_started = None
        elif self.sit_stand_armed and pose == "transition" and self.transition_started is None:
            self.transition_started = now
        elif self.sit_stand_armed and pose == "standing":
            if self.transition_started is not None:
                self.last_sit_to_stand = sit_to_stand_score(now - self.transition_started)
                self.last_sit_to_stand["completed_at"] = datetime.now().isoformat(timespec="seconds")
            self.sit_stand_armed = False
            self.transition_started = None

    def update_predictive_metrics(
        self,
        keypoints: np.ndarray,
        now: float,
        frame_width: int,
        keypoint_confidence: float,
        posture: str,
        meters_per_pixel: float,
    ) -> dict[str, Any]:
        self.target_missing_since = None
        shoulders = midpoint(
            keypoints, LEFT_SHOULDER, RIGHT_SHOULDER, keypoint_confidence
        )
        hips = midpoint(keypoints, LEFT_HIP, RIGHT_HIP, keypoint_confidence)
        if shoulders is None or hips is None:
            return self.predictive_snapshot(now, meters_per_pixel)

        torso_length = float(np.linalg.norm(shoulders - hips))
        if torso_length < 2:
            return self.predictive_snapshot(now, meters_per_pixel)

        lower_body_visible = (
            keypoints[LEFT_ANKLE, 2] >= keypoint_confidence
            and keypoints[RIGHT_ANKLE, 2] >= keypoint_confidence
        )
        step_width_ratio = None
        ankle_separation = None
        if lower_body_visible:
            left_ankle = keypoints[LEFT_ANKLE, :2]
            right_ankle = keypoints[RIGHT_ANKLE, :2]
            hip_width = float(
                np.linalg.norm(
                    keypoints[LEFT_HIP, :2] - keypoints[RIGHT_HIP, :2]
                )
            )
            if hip_width >= 2:
                step_width_ratio = abs(float(left_ankle[0] - right_ankle[0])) / hip_width
            ankle_separation = float(left_ankle[1] - right_ankle[1]) / torso_length

            phase = 1 if ankle_separation >= 0.08 else -1 if ankle_separation <= -0.08 else 0
            if phase and self.ankle_phase == 0:
                self.ankle_phase = phase
            elif phase and phase != self.ankle_phase:
                elapsed = now - self.step_events[-1][0] if self.step_events else None
                if elapsed is None or 0.28 <= elapsed <= 2.0:
                    self.step_events.append((now, phase))
                elif elapsed > 2.0:
                    self.step_events.clear()
                    self.step_events.append((now, phase))
                self.ankle_phase = phase

        while self.step_events and now - self.step_events[0][0] > 20.0:
            self.step_events.popleft()

        steady = (
            posture == "standing"
            and abs(self.horizontal_speed_widths_s or 0.0) <= 0.015
            and abs(self.vertical_speed_heights_s or 0.0) <= 0.015
        )
        self.prediction_samples.append(
            {
                "time": now,
                "hip_x": float(hips[0]),
                "torso_length": torso_length,
                "tilt": self.previous_tilt,
                "steady": steady,
                "step_width_ratio": step_width_ratio,
                "lower_body_visible": lower_body_visible,
            }
        )
        while self.prediction_samples and now - self.prediction_samples[0]["time"] > 20.0:
            self.prediction_samples.popleft()
        return self.predictive_snapshot(now, meters_per_pixel)

    def update_action_sequence(
        self, keypoints: np.ndarray, now: float, frame_height: int, frame_width: int
    ) -> None:
        self.action_samples.append(
            (now, keypoints.astype(np.float32, copy=True), frame_height, frame_width)
        )

    def predictive_snapshot(self, now: float, meters_per_pixel: float) -> dict[str, Any]:
        events = list(self.step_events)
        step_intervals = [
            events[index][0] - events[index - 1][0]
            for index in range(1, len(events))
            if 0.28 <= events[index][0] - events[index - 1][0] <= 2.0
        ]
        cadence = None
        step_time_cv = None
        if len(step_intervals) >= 3:
            recent_intervals = step_intervals[-10:]
            cadence = 60.0 / float(np.median(recent_intervals))
            if len(recent_intervals) >= 5:
                step_time_cv = (
                    float(np.std(recent_intervals, ddof=1))
                    / float(np.mean(recent_intervals))
                    * 100
                )

        phase_times = {
            phase: [event_time for event_time, event_phase in events if event_phase == phase]
            for phase in (-1, 1)
        }
        stride_intervals: dict[int, list[float]] = {}
        for phase, timestamps in phase_times.items():
            stride_intervals[phase] = [
                timestamps[index] - timestamps[index - 1]
                for index in range(1, len(timestamps))
                if 0.55 <= timestamps[index] - timestamps[index - 1] <= 4.0
            ]
        gait_symmetry = None
        if stride_intervals[-1] and stride_intervals[1]:
            left = float(np.mean(stride_intervals[-1]))
            right = float(np.mean(stride_intervals[1]))
            gait_symmetry = abs(left - right) / max(0.01, (left + right) / 2) * 100

        samples = list(self.prediction_samples)
        recent_five = [sample for sample in samples if now - sample["time"] <= 5.0]
        steady_samples = [sample for sample in recent_five if sample["steady"]]
        sway_rms = None
        if len(steady_samples) >= 10:
            hip_positions = np.array([sample["hip_x"] for sample in steady_samples])
            torso_lengths = np.array([sample["torso_length"] for sample in steady_samples])
            centered = hip_positions - np.median(hip_positions)
            sway_rms = float(
                np.sqrt(np.mean(np.square(centered))) / max(2.0, float(np.median(torso_lengths))) * 100
            )

        tilts = [sample["tilt"] for sample in recent_five if sample["tilt"] is not None]
        trunk_tilt_std = float(np.std(tilts, ddof=1)) if len(tilts) >= 5 else None
        widths = [
            sample["step_width_ratio"]
            for sample in recent_five
            if sample["step_width_ratio"] is not None
        ]
        step_width_ratio = float(np.median(widths)) if widths else None
        lower_body_visible = any(sample["lower_body_visible"] for sample in recent_five)
        walking_active = bool(events and now - events[-1][0] <= 2.5 and cadence is not None)
        gait_speed = None
        if walking_active and meters_per_pixel > 0 and self.center_speed_px_s is not None:
            gait_speed = self.center_speed_px_s * meters_per_pixel

        cadence_assessment = cadence_score(cadence)
        speed_assessment = gait_speed_score(gait_speed)
        return {
            "window_s": round(now - samples[0]["time"], 1) if samples else 0.0,
            "walking_active": walking_active,
            "lower_body_visible": lower_body_visible,
            "step_events": len(events),
            "cadence_steps_min": round_optional(cadence, 1),
            "cadence_assessment": cadence_assessment,
            "mean_step_time_s": round_optional(
                float(np.mean(step_intervals[-10:])) if step_intervals else None, 3
            ),
            "step_time_cv_percent": round_optional(step_time_cv, 1),
            "gait_symmetry_percent": round_optional(gait_symmetry, 1),
            "step_width_hip_ratio": round_optional(step_width_ratio, 2),
            "gait_speed_m_s": round_optional(gait_speed, 3),
            "gait_speed_assessment": speed_assessment,
            "meters_per_pixel": meters_per_pixel if meters_per_pixel > 0 else None,
            "sway_rms_torso_percent": round_optional(sway_rms, 2),
            "trunk_tilt_std_deg": round_optional(trunk_tilt_std, 2),
        }


def classify_pose(
    box: np.ndarray, keypoints: np.ndarray, keypoint_confidence: float
) -> tuple[str, float | None, float | None, float]:
    x1, y1, x2, y2 = (float(value) for value in box)
    width = max(1.0, x2 - x1)
    height = max(1.0, y2 - y1)
    aspect_ratio = width / height

    shoulders = midpoint(
        keypoints, LEFT_SHOULDER, RIGHT_SHOULDER, keypoint_confidence
    )
    hips = midpoint(keypoints, LEFT_HIP, RIGHT_HIP, keypoint_confidence)
    torso_tilt = None
    if shoulders is not None and hips is not None:
        axis = shoulders - hips
        torso_tilt = math.degrees(math.atan2(abs(float(axis[0])), abs(float(axis[1])) + 1e-6))

    knee_angle = median_or_none(
        [
            joint_angle(
                keypoints, LEFT_HIP, LEFT_KNEE, LEFT_ANKLE, keypoint_confidence
            ),
            joint_angle(
                keypoints, RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE, keypoint_confidence
            ),
        ]
    )

    # Conservative posture heuristics.  A single crouch should not become "lying".
    if aspect_ratio >= 1.20 or (
        aspect_ratio >= 0.85 and torso_tilt is not None and torso_tilt >= 60
    ):
        pose = "lying"
    elif torso_tilt is not None and torso_tilt <= 45 and knee_angle is not None:
        if knee_angle >= 155:
            pose = "standing"
        elif knee_angle <= 145:
            pose = "sitting"
        else:
            pose = "transition"
    else:
        pose = "transition"
    return pose, torso_tilt, knee_angle, aspect_ratio


def valid_person_candidates(
    result: Any,
    keypoint_confidence: float,
) -> list[tuple[int, np.ndarray, np.ndarray, float, int]]:
    if result.boxes is None or result.keypoints is None or len(result.boxes) == 0:
        return []
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    confidences = result.boxes.conf.detach().cpu().numpy()
    keypoints = result.keypoints.data.detach().cpu().numpy()
    candidates: list[tuple[int, np.ndarray, np.ndarray, float, int]] = []
    for index, (box, points, confidence) in enumerate(
        zip(boxes, keypoints, confidences)
    ):
        valid = points[:, 2] >= keypoint_confidence
        valid_count = int(valid.sum())
        core = valid[[LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP]]
        # Metrics need a coherent torso.  This deliberately rejects ambiguous
        # boxes on coats, chairs and furniture, even if the detector labels them
        # as a person.  Occluded people remain "no reliable person" rather than
        # producing invented angles.
        if valid_count >= 8 and bool(core.all()):
            candidates.append((index, box, points, float(confidence), valid_count))
    return candidates


def primary_person(
    result: Any,
    state: TemporalState,
    frame_shape: tuple[int, ...],
    keypoint_confidence: float,
) -> tuple[int, np.ndarray, np.ndarray, float, int, int] | None:
    candidates = valid_person_candidates(result, keypoint_confidence)
    if not candidates:
        return None

    height, width = frame_shape[:2]
    diagonal = math.hypot(width, height)
    scored: list[tuple[float, tuple[int, np.ndarray, np.ndarray, float, int]]] = []
    for candidate in candidates:
        candidate_index, box, _, confidence, valid_count = candidate
        area = max(1.0, float((box[2] - box[0]) * (box[3] - box[1])))
        score = confidence * math.sqrt(area) * (valid_count / 17)
        candidate_track_id = tracked_person_id(result, candidate_index)
        if state.primary_track_id is not None and candidate_track_id is not None:
            score *= 4.0 if candidate_track_id == state.primary_track_id else 0.25
        if state.previous_center is not None:
            center = np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])
            distance = float(np.linalg.norm(center - state.previous_center)) / diagonal
            score *= math.exp(-5.0 * distance)
        scored.append((score, candidate))
    _, selected = max(scored, key=lambda item: item[0])
    index, box, points, confidence, valid_count = selected
    return index, box, points, confidence, valid_count, len(candidates)


def tracked_person_id(result: Any, index: int) -> int | None:
    if result.boxes is None or result.boxes.id is None:
        return None
    track_ids = result.boxes.id.detach().cpu().numpy()
    if index < 0 or index >= len(track_ids):
        return None
    return int(track_ids[index])
