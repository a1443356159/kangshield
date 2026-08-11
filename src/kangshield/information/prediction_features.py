"""Thin kangshield adapter around the synced fall-detection prediction core.

This module contains no metric algorithms.  It maps kangshield pose
detections and media PTS timestamps into the synced fall-detection
``metrics_core`` (see ``prediction_sync/SYNC_MANIFEST.json``), wraps the
outputs in contract models, applies the fail-closed quality gates and keeps
the synced candidate scores out of any formal assessment position.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import ValidationError

from .contracts import (
    ContractModel,
    PredictionClipSummary,
    PredictionFrameValue,
)
from .pose_backend import PoseDetection
from .prediction_sync import metrics_core
from .prediction_sync.metrics_core import TemporalState


class _PostureThresholds(ContractModel):
    lying_aspect_ratio: float = 1.20
    lying_aspect_ratio_with_tilt: float = 0.85
    lying_torso_tilt_deg: float = 60.0
    upright_torso_tilt_max_deg: float = 45.0
    standing_knee_angle_min_deg: float = 155.0
    sitting_knee_angle_max_deg: float = 145.0
    stabilization_window_frames: int = 5
    stabilization_min_votes: int = 3


class _StepEventThresholds(ContractModel):
    ankle_separation_torso_ratio: float = 0.08
    min_step_interval_ms: int = 280
    max_step_interval_ms: int = 2000
    window_s: float = 20.0
    tuned_for_fps: float = 15.0


class _PoseC3DThresholds(ContractModel):
    window_frames: int = 48
    staggering_threshold: float = 0.35
    falling_threshold: float = 0.50
    required_windows: int = 2
    ema_alpha: float = 0.45


class _PrimaryPersonTuning(ContractModel):
    track_id_affinity: float = 4.0
    track_id_penalty: float = 0.25
    center_distance_decay: float = 5.0


class _BalanceThresholds(ContractModel):
    steady_horizontal_speed_widths_s: float = 0.015
    steady_vertical_speed_heights_s: float = 0.015
    recent_window_s: float = 5.0
    min_steady_samples: int = 10
    min_tilt_samples: int = 5


class _CandidateFlagThresholds(ContractModel):
    sway_rms_torso_percent: float = 5.0
    step_time_cv_percent: float = 10.0
    gait_symmetry_percent: float = 15.0
    trunk_tilt_std_deg: float = 8.0


class PredictionFeatureConfig(ContractModel):
    """Policy for the synced prediction indicators (candidate thresholds only)."""

    schema_version: str = "1.0"
    algorithm_authority: str | None = None
    feature_version: str
    keypoint_confidence_threshold: float = 0.35
    minimum_valid_keypoints: int = 8
    posture: _PostureThresholds = _PostureThresholds()
    primary_person: _PrimaryPersonTuning = _PrimaryPersonTuning()
    step_events: _StepEventThresholds = _StepEventThresholds()
    balance: _BalanceThresholds = _BalanceThresholds()
    candidate_flag_thresholds: _CandidateFlagThresholds = _CandidateFlagThresholds()
    sit_to_stand_candidate_thresholds_s: list[float] = [5.0, 10.0, 13.93]
    meters_per_pixel: float = 0.0
    posec3d: _PoseC3DThresholds = _PoseC3DThresholds()
    limitations: list[str] = []

    def model_post_init(self, __context: Any, /) -> None:
        if self.meters_per_pixel < 0:
            raise ValueError("meters_per_pixel must be non-negative")


def load_prediction_feature_config(path: Path) -> PredictionFeatureConfig:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("prediction feature policy could not be read as JSON") from error
    try:
        return PredictionFeatureConfig.model_validate(payload)
    except ValidationError as error:
        raise ValueError("prediction feature policy schema validation failed") from error


class _ArrayView:
    """Minimal numpy shim exposing the torch-style chain the synced core expects."""

    def __init__(self, array: np.ndarray) -> None:
        self._array = array

    def detach(self) -> "_ArrayView":
        return self

    def cpu(self) -> "_ArrayView":
        return self

    def numpy(self) -> np.ndarray:
        return self._array


class _BoxesView:
    def __init__(self, xyxy: np.ndarray, conf: np.ndarray, ids: np.ndarray | None) -> None:
        self.xyxy = _ArrayView(xyxy)
        self.conf = _ArrayView(conf)
        self.id = None if ids is None else _ArrayView(ids)

    def __len__(self) -> int:
        return int(self.xyxy.numpy().shape[0])


class _KeypointsView:
    def __init__(self, data: np.ndarray) -> None:
        self.data = _ArrayView(data)


class PoseResultView:
    """Duck-typed stand-in for an Ultralytics result over PoseDetection lists."""

    def __init__(self, detections: list[PoseDetection]) -> None:
        if not detections:
            self.boxes = None
            self.keypoints = None
            return
        xyxy = np.asarray([d.bbox_xyxy for d in detections], dtype=np.float32)
        conf = np.asarray(
            [d.confidence if d.confidence is not None else 0.0 for d in detections],
            dtype=np.float32,
        )
        ids = (
            np.asarray(
                [d.track_id if d.track_id is not None else -1 for d in detections],
                dtype=np.int64,
            )
            if any(d.track_id is not None for d in detections)
            else None
        )
        keypoints = np.asarray([d.keypoints_xyc for d in detections], dtype=np.float32)
        self.boxes = _BoxesView(xyxy, conf, ids)
        self.keypoints = _KeypointsView(keypoints)


class PredictionFeatureExtractor:
    """Per-clip stateful adapter feeding PTS-timed detections to the synced core."""

    def __init__(
        self,
        config: PredictionFeatureConfig,
        *,
        frame_width: int,
        frame_height: int,
        sample_fps: float,
    ) -> None:
        self.config = config
        self.frame_width = int(frame_width)
        self.frame_height = int(frame_height)
        self.sample_fps = float(sample_fps)
        self._state = TemporalState()
        self._frames_processed = 0
        self._frames_with_primary = 0
        self._posture_counts: Counter[str] = Counter()
        self._sts_durations: list[float] = []
        self._final_gait: dict[str, Any] = {}
        self._limitations: list[str] = []
        if self.sample_fps < self.config.step_events.tuned_for_fps:
            self._limitations.append(
                f"step_event_thresholds_tuned_for_{self.config.step_events.tuned_for_fps:g}fps"
            )
        if self.config.meters_per_pixel <= 0:
            self._limitations.append("gait_speed_requires_ground_calibration")

    @property
    def state(self) -> TemporalState:
        """Synced temporal state (exposed for the PoseC3D window collector)."""
        return self._state

    def process(
        self,
        detections: list[PoseDetection],
        *,
        frame_sequence: int,
        timestamp_ms: int,
    ) -> PredictionFrameValue:
        now = timestamp_ms / 1000.0
        result = PoseResultView(detections)
        primary = metrics_core.primary_person(
            result, self._state, (self.frame_height, self.frame_width),
            self.config.keypoint_confidence_threshold,
        )
        self._frames_processed += 1
        if primary is None:
            self._state.mark_no_person(now)
            self._state.pose_history.clear()
            self._final_gait = self._state.predictive_snapshot(
                now, self.config.meters_per_pixel
            )
            self._posture_counts["no_person"] += 1
            return PredictionFrameValue(
                feature_version=self.config.feature_version,
                frame_sequence=frame_sequence,
                timestamp_ms=timestamp_ms,
                frame_width=self.frame_width,
                frame_height=self.frame_height,
                person_detected=False,
                person_count=0,
                posture="no_person",
                gait=self._final_gait,
                sit_to_stand_state=self._sts_state(),
                limitations=list(self._limitations),
            )

        index, box, keypoints, confidence, valid_count, person_count = primary
        track_id = metrics_core.tracked_person_id(result, index)
        if (
            track_id is not None
            and self._state.primary_track_id is not None
            and track_id != self._state.primary_track_id
        ):
            self._state.reset_target_motion()
            self._state.reset_prediction()
            self._state.pose_history.clear()
            self._state.lying_since = None
            self._state.sit_stand_armed = False
            self._state.transition_started = None
        if track_id is not None:
            self._state.primary_track_id = track_id

        raw_pose, torso_tilt, knee_angle, aspect_ratio = metrics_core.classify_pose(
            box, keypoints, self.config.keypoint_confidence_threshold
        )
        stable_pose = self._state.stable_pose(raw_pose)
        center = np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])
        self._state.update_action_sequence(
            keypoints, now, self.frame_height, self.frame_width
        )
        self._state.update_motion(
            center, torso_tilt, now, self.frame_width, self.frame_height
        )
        previous_sts = self._state.last_sit_to_stand
        self._state.update_events(stable_pose, now)
        if (
            self._state.last_sit_to_stand is not None
            and self._state.last_sit_to_stand is not previous_sts
        ):
            self._sts_durations.append(
                float(self._state.last_sit_to_stand["duration_s"])
            )
        gait = self._state.update_predictive_metrics(
            keypoints,
            now,
            self.frame_width,
            self.config.keypoint_confidence_threshold,
            stable_pose,
            self.config.meters_per_pixel,
        )
        self._final_gait = gait
        prediction = metrics_core.prediction_summary(
            gait, self._state.last_sit_to_stand
        )
        lying_duration = (
            0.0 if self._state.lying_since is None else now - self._state.lying_since
        )
        self._frames_with_primary += 1
        self._posture_counts[stable_pose] += 1
        return PredictionFrameValue(
            feature_version=self.config.feature_version,
            frame_sequence=frame_sequence,
            timestamp_ms=timestamp_ms,
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            person_detected=True,
            person_count=person_count,
            selected_track_id=track_id,
            raw_posture=raw_pose,
            posture=stable_pose,
            bbox_aspect_ratio=round(aspect_ratio, 3),
            torso_tilt_deg=metrics_core.round_optional(torso_tilt, 1),
            knee_angle_deg=metrics_core.round_optional(knee_angle, 1),
            center_speed_px_s=metrics_core.round_optional(
                self._state.center_speed_px_s, 1
            ),
            horizontal_speed_frame_widths_s=metrics_core.round_optional(
                self._state.horizontal_speed_widths_s, 4
            ),
            vertical_speed_frame_heights_s=metrics_core.round_optional(
                self._state.vertical_speed_heights_s, 4
            ),
            lying_duration_s=round(lying_duration, 2),
            gait=gait,
            sit_to_stand_state=self._sts_state(),
            last_sit_to_stand=self._state.last_sit_to_stand,
            candidate_scores={
                "scored_components": prediction["scored_components"],
                "risk_percent_candidate": prediction["risk_percent"],
                "trend_flags": prediction["trend_flags"],
                "candidate_only": True,
            },
            limitations=list(self._limitations),
        )

    def _sts_state(self) -> str:
        if self._state.transition_started is not None:
            return "timing"
        if self._state.sit_stand_armed:
            return "armed"
        return "waiting_for_sitting"

    def summary(self) -> PredictionClipSummary:
        gate_failures: list[str] = []
        if self._frames_with_primary < 3:
            gate_failures.append("insufficient_primary_person_frames")
        if self._frames_processed and self._frames_with_primary / self._frames_processed < 0.7:
            gate_failures.append("insufficient_keypoint_visibility")
        return PredictionClipSummary(
            feature_version=self.config.feature_version,
            frames_processed=self._frames_processed,
            frames_with_primary_person=self._frames_with_primary,
            posture_frame_counts=dict(self._posture_counts),
            step_event_count=len(self._state.step_events),
            final_gait=self._final_gait,
            sit_to_stand_completed_count=len(self._sts_durations),
            sit_to_stand_durations_s=self._sts_durations,
            assessability="not_assessable" if gate_failures else "assessable",
            gate_failures=gate_failures,
            meters_per_pixel=self.config.meters_per_pixel,
            limitations=list(self._limitations),
        )


class PoseC3DBatchRunner:
    """Drive the verbatim-synced posec3d_service.py over collected windows.

    The synced service is used unmodified: the adapter writes one NPZ window,
    launches the isolated environment process, waits for the matching result
    sequence and stops the service again.  Any missing prerequisite degrades
    to ``unavailable`` without blocking the rest of the capture chain.
    """

    def __init__(
        self,
        config: _PoseC3DThresholds,
        *,
        python_executable: Path,
        service_file: Path,
        checkpoint: Path,
        labels: Path,
        mmaction_config: Path,
        device: str = "cuda:0",
        timeout_s: float = 120.0,
    ) -> None:
        self.config = config
        self.python_executable = Path(python_executable)
        self.service_file = Path(service_file)
        self.checkpoint = Path(checkpoint)
        self.labels = Path(labels)
        self.mmaction_config = Path(mmaction_config)
        self.device = device
        self.timeout_s = timeout_s
        self.unavailable_reason: str | None = None
        missing = [
            str(path)
            for path in (
                self.python_executable,
                self.service_file,
                self.checkpoint,
                self.labels,
                self.mmaction_config,
            )
            if not path.is_file()
        ]
        if missing:
            self.unavailable_reason = "posec3d prerequisites missing: " + ", ".join(missing)

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    def run_window(self, state: TemporalState, work_dir: Path) -> dict[str, Any]:
        """Run one 48-frame window from the extractor state through the service."""
        if self.unavailable_reason is not None:
            return {"state": "unavailable", "signal": "unavailable",
                    "message": self.unavailable_reason}
        samples = list(state.action_samples)[-self.config.window_frames:]
        if len(samples) < self.config.window_frames:
            return {"state": "collecting", "signal": "collecting",
                    "frames_collected": len(samples),
                    "window_frames": self.config.window_frames}
        work_dir.mkdir(parents=True, exist_ok=True)
        input_path = work_dir / "posec3d-input.npz"
        output_path = work_dir / "posec3d-result.json"
        keypoints = np.stack([sample[1][:, :2] for sample in samples]).astype(np.float32)
        scores = np.stack([sample[1][:, 2] for sample in samples]).astype(np.float32)
        np.savez_compressed(
            input_path,
            keypoints=keypoints,
            scores=scores,
            height=np.int32(samples[-1][2]),
            width=np.int32(samples[-1][3]),
            sequence=np.int64(1),
            frame_number=np.int64(-1),
            submitted_at=np.float64(time.time()),
            window_span_s=np.float64(samples[-1][0] - samples[0][0]),
        )
        if output_path.exists():
            output_path.unlink()
        process = subprocess.Popen(
            [
                str(self.python_executable),
                str(self.service_file),
                "--config", str(self.mmaction_config),
                "--checkpoint", str(self.checkpoint),
                "--labels", str(self.labels),
                "--input-file", str(input_path),
                "--output-file", str(output_path),
                "--device", self.device,
                "--staggering-threshold", str(self.config.staggering_threshold),
                "--falling-threshold", str(self.config.falling_threshold),
                "--required-windows", str(self.config.required_windows),
                "--ema-alpha", str(self.config.ema_alpha),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + self.timeout_s
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    return {"state": "error", "signal": "unavailable",
                            "message": f"posec3d service exited {process.returncode}"}
                if output_path.is_file():
                    try:
                        payload = json.loads(output_path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        payload = None
                    if isinstance(payload, dict) and payload.get("sequence") == 1:
                        return payload
                time.sleep(0.1)
            return {"state": "error", "signal": "unavailable",
                    "message": "posec3d service timed out"}
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


class FaceIdentityRunner:
    """Optional wrapper around the synced face whitelist recognizer."""

    def __init__(
        self,
        *,
        model_dir: Path,
        gallery_path: Path,
        device: str = "auto",
    ) -> None:
        self.unavailable_reason: str | None = None
        self._recognizer: Any = None
        try:
            from .prediction_sync.face_recognition import (
                FaceGallery,
                FaceRecognitionConfig,
                FaceXLibRetinaArcBackend,
                RealtimeFaceRecognizer,
                people_from_pose_result,
            )
        except ImportError as error:
            self.unavailable_reason = f"face recognition imports unavailable: {error}"
            return
        missing = [str(path) for path in (model_dir, gallery_path) if not Path(path).exists()]
        if missing:
            self.unavailable_reason = "face recognition files missing: " + ", ".join(missing)
            return
        try:
            backend = FaceXLibRetinaArcBackend(Path(model_dir), device=device)
            gallery = FaceGallery.load(Path(gallery_path))
            self._recognizer = RealtimeFaceRecognizer(
                backend, gallery, FaceRecognitionConfig()
            )
            self._people_adapter = people_from_pose_result
        except Exception as error:  # fail closed, never block the capture chain
            self.unavailable_reason = f"face recognition startup failed: {error}"

    @property
    def available(self) -> bool:
        return self._recognizer is not None

    def process_frame(
        self,
        frame: np.ndarray,
        detections: list[PoseDetection],
        *,
        timestamp_ms: int,
        frame_number: int | None,
        primary_track_id: int | None,
    ) -> dict[str, Any]:
        if self._recognizer is None:
            return {"state": "unavailable", "message": self.unavailable_reason,
                    "people": [], "primary": None}
        people = self._people_adapter(PoseResultView(detections))
        return self._recognizer.process_frame(
            frame,
            people,
            timestamp_ms=timestamp_ms,
            frame_number=frame_number,
            primary_track_id=primary_track_id,
        )
