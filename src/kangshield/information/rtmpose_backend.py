"""OpenMMLab Human-Art detector + RTMPose ONNXRuntime adapter.

The preprocessing and SimCC decoding follow the Apache-2.0 MMPose/RTMLib
reference implementations and the pipeline metadata shipped with the pinned
ONNX exports.  Apache-2.0 describes the implementation, not the licensing
status of Human-Art-trained model artifacts.  This module intentionally does
not depend on MMCV, MMEngine, MMPose, or MMDetection.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .contracts import ModelBinding
from .pose_backend import PoseDetection
from .privacy import sha256_file


YOLOX_M_HUMANART_URL = (
    "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/"
    "yolox_m_8xb8-300e_humanart-c2c7a14a.zip"
)
RTMPOSE_M_HUMANART_URL = (
    "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/"
    "rtmpose-m_8xb256-420e_humanart-256x192-8430627b_20230611.zip"
)
HUMANART_MODEL_ARTIFACT_LICENSE = "model-artifact-license-review-required"
HUMANART_ANNOTATION_LICENSE = "CC-BY-NC-SA-4.0-noncommercial"
HUMANART_LICENSE_SOURCE = (
    "https://docs.google.com/document/d/"
    "19j-6GFOCYBDU4CxwRSKgORndse_j5iHGK0RCJ2TvXNQ/edit"
)


@dataclass(frozen=True)
class PersonBox:
    bbox_xyxy: list[float]
    confidence: float


@dataclass
class _TrackState:
    bbox_xyxy: list[float]
    missed_frames: int = 0


def bbox_iou(left: Iterable[float], right: Iterable[float]) -> float:
    a = list(left)
    b = list(right)
    if len(a) < 4 or len(b) < 4:
        return 0.0
    intersection_width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    intersection_height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    right_area = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0.0 else 0.0


class IoUTrackAssigner:
    """Small deterministic tracker used only to preserve stream identities."""

    def __init__(self, iou_threshold: float = 0.2, max_missed_frames: int = 2):
        if not 0.0 <= iou_threshold <= 1.0:
            raise ValueError("iou_threshold must be between 0 and 1")
        if max_missed_frames < 0:
            raise ValueError("max_missed_frames must be non-negative")
        self.iou_threshold = iou_threshold
        self.max_missed_frames = max_missed_frames
        self.reset()

    def reset(self) -> None:
        self._tracks: dict[int, _TrackState] = {}
        self._next_track_id = 1

    def update(self, boxes: list[list[float]]) -> list[int]:
        for state in self._tracks.values():
            state.missed_frames += 1

        candidates: list[tuple[float, int, int]] = []
        for detection_index, box in enumerate(boxes):
            for track_id, state in self._tracks.items():
                score = bbox_iou(box, state.bbox_xyxy)
                if score >= self.iou_threshold:
                    candidates.append((score, detection_index, track_id))
        candidates.sort(reverse=True)

        assigned_detections: set[int] = set()
        assigned_tracks: set[int] = set()
        result: list[int | None] = [None] * len(boxes)
        for _, detection_index, track_id in candidates:
            if (
                detection_index in assigned_detections
                or track_id in assigned_tracks
            ):
                continue
            assigned_detections.add(detection_index)
            assigned_tracks.add(track_id)
            result[detection_index] = track_id
            self._tracks[track_id] = _TrackState(boxes[detection_index])

        for detection_index, box in enumerate(boxes):
            if result[detection_index] is not None:
                continue
            track_id = self._next_track_id
            self._next_track_id += 1
            self._tracks[track_id] = _TrackState(box)
            result[detection_index] = track_id

        self._tracks = {
            track_id: state
            for track_id, state in self._tracks.items()
            if state.missed_frames <= self.max_missed_frames
            or track_id in assigned_tracks
            or track_id in result
        }
        return [int(track_id) for track_id in result if track_id is not None]


def preprocess_yolox(frame: Any, input_size: tuple[int, int]) -> tuple[Any, float]:
    import cv2
    import numpy as np

    input_width, input_height = input_size
    if input_width <= 0 or input_height <= 0:
        raise ValueError("detector input size must be positive")
    height, width = frame.shape[:2]
    ratio = min(input_height / height, input_width / width)
    resized_width = max(1, int(width * ratio))
    resized_height = max(1, int(height * ratio))
    resized = cv2.resize(
        frame,
        (resized_width, resized_height),
        interpolation=cv2.INTER_LINEAR,
    )
    padded = np.full((input_height, input_width, 3), 114, dtype=np.uint8)
    padded[:resized_height, :resized_width] = resized
    tensor = np.ascontiguousarray(
        padded.transpose(2, 0, 1)[None],
        dtype=np.float32,
    )
    return tensor, ratio


def decode_yolox_end2end(
    detections: Any,
    labels: Any,
    *,
    ratio: float,
    frame_width: int,
    frame_height: int,
    confidence: float,
    max_people: int,
) -> list[PersonBox]:
    import numpy as np

    if ratio <= 0:
        raise ValueError("detector resize ratio must be positive")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if max_people <= 0:
        raise ValueError("max_people must be positive")
    dets = np.asarray(detections)
    classes = np.asarray(labels)
    if dets.ndim != 3 or dets.shape[0] != 1 or dets.shape[-1] < 5:
        raise ValueError(f"unexpected YOLOX detections shape: {dets.shape}")
    if classes.ndim != 2 or classes.shape[0] != 1:
        raise ValueError(f"unexpected YOLOX labels shape: {classes.shape}")

    people: list[PersonBox] = []
    for detection, label in zip(dets[0], classes[0]):
        score = float(detection[4])
        if int(label) != 0 or score < confidence:
            continue
        x1, y1, x2, y2 = (float(value) / ratio for value in detection[:4])
        clipped = [
            max(0.0, min(float(frame_width), x1)),
            max(0.0, min(float(frame_height), y1)),
            max(0.0, min(float(frame_width), x2)),
            max(0.0, min(float(frame_height), y2)),
        ]
        if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
            continue
        people.append(PersonBox(clipped, score))
    people.sort(key=lambda item: item.confidence, reverse=True)
    return people[:max_people]


def bbox_center_scale(
    bbox_xyxy: Iterable[float],
    *,
    padding: float,
    input_size: tuple[int, int],
) -> tuple[Any, Any]:
    import numpy as np

    x1, y1, x2, y2 = (float(value) for value in bbox_xyxy)
    center = np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=np.float32)
    scale = np.array([x2 - x1, y2 - y1], dtype=np.float32) * padding
    aspect_ratio = input_size[0] / input_size[1]
    if scale[0] > scale[1] * aspect_ratio:
        scale[1] = scale[0] / aspect_ratio
    else:
        scale[0] = scale[1] * aspect_ratio
    return center, scale


def _third_point(first: Any, second: Any) -> Any:
    import numpy as np

    direction = first - second
    return second + np.array([-direction[1], direction[0]], dtype=np.float32)


def affine_matrix(center: Any, scale: Any, output_size: tuple[int, int]) -> Any:
    import cv2
    import numpy as np

    output_width, output_height = output_size
    source_direction = np.array([0.0, -scale[0] * 0.5], dtype=np.float32)
    destination_direction = np.array(
        [0.0, -output_width * 0.5], dtype=np.float32
    )
    source = np.zeros((3, 2), dtype=np.float32)
    source[0] = center
    source[1] = center + source_direction
    source[2] = _third_point(source[0], source[1])
    destination = np.zeros((3, 2), dtype=np.float32)
    destination[0] = [output_width * 0.5, output_height * 0.5]
    destination[1] = destination[0] + destination_direction
    destination[2] = _third_point(destination[0], destination[1])
    return cv2.getAffineTransform(source, destination)


def preprocess_rtmpose(
    frame: Any,
    bbox_xyxy: Iterable[float],
    input_size: tuple[int, int],
    *,
    padding: float = 1.25,
) -> tuple[Any, Any, Any]:
    import cv2
    import numpy as np

    center, scale = bbox_center_scale(
        bbox_xyxy,
        padding=padding,
        input_size=input_size,
    )
    transform = affine_matrix(center, scale, input_size)
    crop = cv2.warpAffine(
        frame,
        transform,
        input_size,
        flags=cv2.INTER_LINEAR,
    )
    # MMDeploy's exported pipeline declares Normalize(to_rgb=True).
    crop = crop[..., ::-1]
    mean = np.array([123.675, 116.28, 103.53], dtype=np.float32)
    std = np.array([58.395, 57.12, 57.375], dtype=np.float32)
    normalized = (crop.astype(np.float32) - mean) / std
    tensor = np.ascontiguousarray(normalized.transpose(2, 0, 1))
    return tensor, center, scale


def decode_simcc(
    simcc_x: Any,
    simcc_y: Any,
    centers: Any,
    scales: Any,
    *,
    input_size: tuple[int, int],
    split_ratio: float = 2.0,
) -> tuple[Any, Any]:
    import numpy as np

    x_axis = np.asarray(simcc_x)
    y_axis = np.asarray(simcc_y)
    if x_axis.ndim != 3 or y_axis.ndim != 3:
        raise ValueError("SimCC outputs must have shape [batch, keypoints, bins]")
    if x_axis.shape[:2] != y_axis.shape[:2]:
        raise ValueError("SimCC x/y batch and keypoint shapes must match")
    x_locations = np.argmax(x_axis, axis=2)
    y_locations = np.argmax(y_axis, axis=2)
    coordinates = np.stack((x_locations, y_locations), axis=-1).astype(np.float32)
    coordinates /= split_ratio
    x_scores = np.max(x_axis, axis=2)
    y_scores = np.max(y_axis, axis=2)
    scores = (x_scores + y_scores) * 0.5
    coordinates[scores <= 0.0] = -1.0

    centers_array = np.asarray(centers, dtype=np.float32)[:, None, :]
    scales_array = np.asarray(scales, dtype=np.float32)[:, None, :]
    input_array = np.asarray(input_size, dtype=np.float32)
    coordinates = (
        coordinates / input_array * scales_array
        + centers_array
        - scales_array / 2.0
    )
    return coordinates, scores


class HumanArtRTMPoseBackend:
    """Top-down Human-Art pose pipeline using pinned OpenMMLab ONNX exports."""

    def __init__(
        self,
        detector_model: str | Path,
        pose_model: str | Path,
        *,
        device: str = "auto",
        detector_input_size: tuple[int, int] = (640, 640),
        pose_input_size: tuple[int, int] = (192, 256),
        detection_confidence: float = 0.05,
        max_people: int = 4,
        track: bool = True,
        tracker_iou_threshold: float = 0.2,
        tracker_max_missed_frames: int = 2,
    ) -> None:
        try:
            import onnxruntime as ort
        except ImportError as error:
            raise RuntimeError(
                "onnxruntime-gpu (or onnxruntime for CPU) is required for RTMPose"
            ) from error
        if not 0.0 <= detection_confidence <= 1.0:
            raise ValueError("detection_confidence must be between 0 and 1")
        if max_people <= 0:
            raise ValueError("max_people must be positive")

        self.detector_path = Path(detector_model)
        self.pose_path = Path(pose_model)
        for path in (self.detector_path, self.pose_path):
            if not path.is_file():
                raise FileNotFoundError(path)
        self.detector_input_size = detector_input_size
        self.pose_input_size = pose_input_size
        self.detection_confidence = detection_confidence
        self.max_people = max_people
        self.track = track
        self._tracker = IoUTrackAssigner(
            iou_threshold=tracker_iou_threshold,
            max_missed_frames=tracker_max_missed_frames,
        )

        providers, requested_provider, normalized_device = _ort_providers(
            ort.get_available_providers(), device
        )
        if requested_provider == "CUDAExecutionProvider":
            preload = getattr(ort, "preload_dlls", None)
            if preload is not None:
                preload(directory="")
        self.device = normalized_device
        self._detector = ort.InferenceSession(
            str(self.detector_path), providers=providers
        )
        self._pose = ort.InferenceSession(str(self.pose_path), providers=providers)
        for name, session in (("detector", self._detector), ("pose", self._pose)):
            active = session.get_providers()
            if requested_provider not in active:
                raise RuntimeError(
                    f"{name} requested {requested_provider}, active providers: {active}"
                )
        self.active_providers = self._pose.get_providers()
        detector_digest = sha256_file(self.detector_path)
        pose_digest = sha256_file(self.pose_path)
        common = {
            "execution_provider": requested_provider,
            "active_providers": self.active_providers,
            "implementation_reference": "MMPose v1.3.2 / RTMLib 0.0.15",
            "implementation_license": "Apache-2.0",
            "training_domain": "Human-Art combined human pose datasets",
            "training_data_terms": HUMANART_ANNOTATION_LICENSE,
            "model_artifact_distribution_status": "blocked_pending_review",
            "license_sources": [
                "https://github.com/open-mmlab/mmpose",
                "https://github.com/IDEA-Research/HumanArt",
                HUMANART_LICENSE_SOURCE,
            ],
        }
        self._bindings = [
            ModelBinding(
                task="human_pose_estimation",
                backend="onnxruntime-openmmlab",
                model_name=self.pose_path.name,
                model_version="8430627b-20230611",
                model_digest=pose_digest,
                license=HUMANART_MODEL_ARTIFACT_LICENSE,
                device=self.device,
                configuration={
                    **common,
                    "source_url": RTMPOSE_M_HUMANART_URL,
                    "input_size": list(pose_input_size),
                    "keypoint_layout": "COCO-17",
                    "simcc_split_ratio": 2.0,
                    "normalize_to_rgb": True,
                },
            ),
            ModelBinding(
                task="person_detection",
                backend="onnxruntime-openmmlab",
                model_name=self.detector_path.name,
                model_version="c2c7a14a-20230928",
                model_digest=detector_digest,
                license=HUMANART_MODEL_ARTIFACT_LICENSE,
                device=self.device,
                configuration={
                    **common,
                    "source_url": YOLOX_M_HUMANART_URL,
                    "input_size": list(detector_input_size),
                    "confidence": detection_confidence,
                    "max_people": max_people,
                },
            ),
            ModelBinding(
                task="short_term_pose_tracking",
                backend="kangshield-iou-tracker",
                model_name="greedy-iou",
                model_version="0.1.0",
                license="project-internal",
                device="cpu",
                configuration={
                    "enabled": track,
                    "iou_threshold": tracker_iou_threshold,
                    "max_missed_frames": tracker_max_missed_frames,
                },
            ),
        ]

    @property
    def bindings(self) -> list[ModelBinding]:
        return list(self._bindings)

    def reset(self) -> None:
        self._tracker.reset()

    def infer(self, frame: Any) -> list[PoseDetection]:
        detector_input, ratio = preprocess_yolox(frame, self.detector_input_size)
        detector_outputs = self._detector.run(
            None,
            {self._detector.get_inputs()[0].name: detector_input},
        )
        if len(detector_outputs) != 2:
            raise RuntimeError(
                f"expected YOLOX dets and labels outputs, got {len(detector_outputs)}"
            )
        people = decode_yolox_end2end(
            detector_outputs[0],
            detector_outputs[1],
            ratio=ratio,
            frame_width=frame.shape[1],
            frame_height=frame.shape[0],
            confidence=self.detection_confidence,
            max_people=self.max_people,
        )
        if not people:
            if self.track:
                self._tracker.update([])
            return []

        pose_inputs = []
        centers = []
        scales = []
        for person in people:
            tensor, center, scale = preprocess_rtmpose(
                frame,
                person.bbox_xyxy,
                self.pose_input_size,
            )
            pose_inputs.append(tensor)
            centers.append(center)
            scales.append(scale)

        import numpy as np

        pose_batch = np.ascontiguousarray(np.stack(pose_inputs), dtype=np.float32)
        pose_outputs = self._pose.run(
            None,
            {self._pose.get_inputs()[0].name: pose_batch},
        )
        if len(pose_outputs) != 2:
            raise RuntimeError(
                f"expected RTMPose SimCC x/y outputs, got {len(pose_outputs)}"
            )
        keypoints, scores = decode_simcc(
            pose_outputs[0],
            pose_outputs[1],
            centers,
            scales,
            input_size=self.pose_input_size,
        )
        boxes = [person.bbox_xyxy for person in people]
        track_ids: list[int | None]
        if self.track:
            track_ids = self._tracker.update(boxes)
        else:
            track_ids = [None] * len(boxes)

        results: list[PoseDetection] = []
        for index, person in enumerate(people):
            points = [
                [
                    round(float(point[0]), 4),
                    round(float(point[1]), 4),
                    round(float(score), 6),
                ]
                for point, score in zip(keypoints[index], scores[index])
            ]
            results.append(
                PoseDetection(
                    bbox_xyxy=[round(value, 3) for value in person.bbox_xyxy],
                    keypoints_xyc=points,
                    confidence=round(person.confidence, 6),
                    track_id=track_ids[index],
                )
            )
        return results


def _ort_providers(
    available_providers: list[str], device: str
) -> tuple[list[Any], str, str]:
    normalized = device.strip().lower()
    if normalized == "auto":
        normalized = (
            "cuda:0"
            if "CUDAExecutionProvider" in available_providers
            and _cuda_runtime_available()
            else "cpu"
        )
    if normalized == "cpu":
        if "CPUExecutionProvider" not in available_providers:
            raise RuntimeError("ONNXRuntime CPUExecutionProvider is unavailable")
        return ["CPUExecutionProvider"], "CPUExecutionProvider", "cpu"
    if normalized in {"cuda", "gpu"}:
        normalized = "cuda:0"
    if normalized.isdigit():
        normalized = f"cuda:{normalized}"
    if normalized.startswith("cuda:"):
        if "CUDAExecutionProvider" not in available_providers:
            raise RuntimeError(
                "CUDAExecutionProvider requested but unavailable; install "
                "onnxruntime-gpu and run inside a GPU allocation"
            )
        device_id = int(normalized.split(":", 1)[1])
        return [
            ("CUDAExecutionProvider", {"device_id": device_id}),
            "CPUExecutionProvider",
        ], "CUDAExecutionProvider", normalized
    raise ValueError("device must be auto, cpu, cuda, cuda:N, or an integer GPU ID")


def _cuda_runtime_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        pass
    try:
        subprocess.run(
            ["nvidia-smi", "--list-gpus"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True
