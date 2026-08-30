from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .contracts import ModelBinding
from .privacy import sha256_file


@dataclass(frozen=True)
class PoseDetection:
    bbox_xyxy: list[float]
    keypoints_xyc: list[list[float]]
    confidence: float | None
    track_id: int | None


class PoseBackend(Protocol):
    @property
    def bindings(self) -> list[ModelBinding]: ...

    def infer(self, frame: Any) -> list[PoseDetection]: ...


class UltralyticsPoseBackend:
    """YOLO pose adapter that keeps tracker state for consecutive stream frames."""

    def __init__(
        self,
        model: str | Path = "models/yolo26s-pose.pt",
        device: str = "auto",
        image_size: int = 640,
        confidence: float = 0.35,
        track: bool = True,
        tracker: str = "bytetrack.yaml",
    ) -> None:
        if image_size <= 0:
            raise ValueError("image_size must be positive")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        try:
            import torch
            import ultralytics
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError(
                "Ultralytics and Torch are required for the YOLO pose backend"
            ) from error

        self.model_name = str(model)
        if device == "auto":
            self.device = "0" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        self.image_size = image_size
        self.confidence = confidence
        self.track = track
        self.tracker = tracker
        self._model = YOLO(self.model_name)
        model_path = Path(self.model_name)
        digest = sha256_file(model_path) if model_path.is_file() else None
        self._bindings = [
            ModelBinding(
                task="human_pose_tracking",
                backend="ultralytics",
                model_name=model_path.name or self.model_name,
                model_version=ultralytics.__version__,
                model_digest=digest,
                license="AGPL-3.0-or-Ultralytics-Enterprise",
                device=self.device,
                configuration={
                    "image_size": image_size,
                    "confidence": confidence,
                    "tracking": track,
                    "tracker": tracker if track else None,
                    "keypoint_layout": "COCO-17",
                },
            )
        ]

    @property
    def bindings(self) -> list[ModelBinding]:
        return list(self._bindings)

    def reset(self) -> None:
        """Reset tracker state before replaying an independent video."""
        predictor = getattr(self._model, "predictor", None)
        trackers = getattr(predictor, "trackers", None)
        if trackers:
            for tracker in trackers:
                reset = getattr(tracker, "reset", None)
                if reset is not None:
                    reset()
        if predictor is not None and hasattr(predictor, "vid_path"):
            predictor.vid_path = [None] * len(predictor.vid_path or [None])

    def infer(self, frame: Any) -> list[PoseDetection]:
        arguments = {
            "source": frame,
            "imgsz": self.image_size,
            "conf": self.confidence,
            "device": self.device,
            "verbose": False,
        }
        if self.track:
            results = self._model.track(
                **arguments,
                persist=True,
                tracker=self.tracker,
            )
        else:
            results = self._model.predict(**arguments)
        if not results:
            return []
        result = results[0]
        if result.boxes is None or result.keypoints is None:
            return []

        boxes = result.boxes.xyxy.detach().cpu().tolist()
        confidences = (
            result.boxes.conf.detach().cpu().tolist()
            if result.boxes.conf is not None
            else [None] * len(boxes)
        )
        track_ids = (
            result.boxes.id.detach().cpu().tolist()
            if result.boxes.id is not None
            else [None] * len(boxes)
        )
        keypoints = result.keypoints.data.detach().cpu().tolist()

        detections: list[PoseDetection] = []
        for index, bbox in enumerate(boxes):
            points = keypoints[index] if index < len(keypoints) else []
            detections.append(
                PoseDetection(
                    bbox_xyxy=[round(float(value), 3) for value in bbox],
                    keypoints_xyc=[
                        [round(float(value), 4) for value in point]
                        for point in points
                    ],
                    confidence=(
                        round(float(confidences[index]), 6)
                        if confidences[index] is not None
                        else None
                    ),
                    track_id=(
                        int(track_ids[index])
                        if track_ids[index] is not None
                        else None
                    ),
                )
            )
        return detections
