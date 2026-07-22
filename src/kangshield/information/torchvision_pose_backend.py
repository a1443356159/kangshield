from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .contracts import ModelBinding
from .pose_backend import PoseDetection
from .privacy import sha256_file
from .rtmpose_backend import IoUTrackAssigner


TORCHVISION_KEYPOINT_RCNN_SHA256 = (
    "fc266e953d2b302cdcbb9ae66f71f6b0d4649928bf02dc573961e361e4918926"
)
TORCHVISION_KEYPOINT_RCNN_URL = (
    "https://download.pytorch.org/models/"
    "keypointrcnn_resnet50_fpn_coco-fc266e95.pth"
)
TORCHVISION_MODEL_ARTIFACT_LICENSE = "model-artifact-license-review-required"
TORCHVISION_VARIANT_ID = "torchvision-keypointrcnn"


def load_torchvision_pose_policy(path: Path) -> dict[str, Any]:
    path = Path(path)
    with path.open(encoding="utf-8") as stream:
        policy = json.load(stream)
    expected = {
        "schema_version": "1.0",
        "model_id": "torchvision-keypointrcnn-resnet50-fpn-coco-v1",
        "variant_id": TORCHVISION_VARIANT_ID,
        "weight_enum": "KeypointRCNN_ResNet50_FPN_Weights.COCO_V1",
        "url": TORCHVISION_KEYPOINT_RCNN_URL,
        "output_path": "keypointrcnn_resnet50_fpn_coco-fc266e95.pth",
        "sha256": TORCHVISION_KEYPOINT_RCNN_SHA256,
        "keypoint_layout": "COCO-17",
        "parameter_count": 59137258,
        "reference_metrics": {
            "dataset": "COCO-val2017",
            "box_map": 54.6,
            "keypoint_map": 65.0,
            "gflops": 137.42,
        },
        "implementation_license": "BSD-3-Clause",
        "model_artifact_license": TORCHVISION_MODEL_ARTIFACT_LICENSE,
        "distribution_status": "blocked_pending_review",
        "keypoint_confidence_transform": (
            "sigmoid_of_raw_keypoint_heatmap_max_logit"
        ),
    }
    for key, value in expected.items():
        if policy.get(key) != value:
            raise ValueError(f"TorchVision pose policy {key} is not frozen")
    if policy.get("byte_size") != 237034793:
        raise ValueError("TorchVision pose weight size is not frozen")
    expected_lineage = [
        {
            "dataset": "COCO 2017 keypoints",
            "role": "detection and keypoint training",
            "terms": "annotation-and-per-image-license-review-required",
        },
        {
            "dataset": "ImageNet-1K",
            "role": "ResNet-50 backbone initialization in the TorchVision recipe",
            "terms": "noncommercial-research-access-terms-review-required",
        },
    ]
    if policy.get("training_lineage") != expected_lineage:
        raise ValueError("TorchVision pose training lineage is incomplete")
    expected_sources = [
        "https://github.com/pytorch/vision/blob/main/LICENSE",
        "https://docs.pytorch.org/vision/stable/models/keypoint_rcnn.html",
        "https://docs.pytorch.org/vision/master/models.html",
        "https://cocodataset.org/#termsofuse",
        "https://www.image-net.org/about.php",
        "https://image-net.org/accessagreement",
    ]
    if policy.get("license_sources") != expected_sources:
        raise ValueError("TorchVision pose license sources are incomplete")
    return policy


def keypoint_logit_confidence(value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        return 0.0
    if value >= 0.0:
        result = 1.0 / (1.0 + math.exp(-value))
    else:
        exponential = math.exp(value)
        result = exponential / (1.0 + exponential)
    return round(result, 6)


def decode_keypoint_rcnn_output(
    output: dict[str, Any],
    *,
    frame_width: int,
    frame_height: int,
    detection_confidence: float,
    max_people: int,
) -> list[tuple[list[float], list[list[float]], float]]:
    import numpy as np

    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("frame dimensions must be positive")
    if not 0.0 <= detection_confidence <= 1.0:
        raise ValueError("detection_confidence must be between 0 and 1")
    if max_people <= 0:
        raise ValueError("max_people must be positive")
    required = ("boxes", "labels", "scores", "keypoints", "keypoints_scores")
    if any(key not in output for key in required):
        raise ValueError("Keypoint R-CNN output is incomplete")
    boxes = np.asarray(output["boxes"])
    labels = np.asarray(output["labels"])
    scores = np.asarray(output["scores"])
    keypoints = np.asarray(output["keypoints"])
    keypoint_scores = np.asarray(output["keypoints_scores"])
    count = len(scores)
    if (
        boxes.shape != (count, 4)
        or labels.shape != (count,)
        or keypoints.shape != (count, 17, 3)
        or keypoint_scores.shape != (count, 17)
    ):
        raise ValueError("Keypoint R-CNN output shape is invalid")

    decoded: list[tuple[list[float], list[list[float]], float]] = []
    ranked = sorted(
        range(count),
        key=lambda item: float(scores[item]),
        reverse=True,
    )
    for index in ranked:
        score = float(scores[index])
        if int(labels[index]) != 1 or score < detection_confidence:
            continue
        x1, y1, x2, y2 = (float(value) for value in boxes[index])
        bbox = [
            max(0.0, min(float(frame_width), x1)),
            max(0.0, min(float(frame_height), y1)),
            max(0.0, min(float(frame_width), x2)),
            max(0.0, min(float(frame_height), y2)),
        ]
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            continue
        points = [
            [
                round(float(point[0]), 4),
                round(float(point[1]), 4),
                keypoint_logit_confidence(float(keypoint_scores[index, point_index])),
            ]
            for point_index, point in enumerate(keypoints[index])
        ]
        decoded.append(
            ([round(value, 3) for value in bbox], points, round(score, 6))
        )
        if len(decoded) >= max_people:
            break
    return decoded


class TorchvisionKeypointRCNNBackend:
    """Pinned COCO_V1 Keypoint R-CNN adapter with explicit weight-policy limits."""

    def __init__(
        self,
        model: str | Path,
        *,
        policy_path: Path,
        device: str = "auto",
        detection_confidence: float = 0.5,
        min_size: int = 800,
        max_size: int = 1333,
        max_people: int = 4,
        track: bool = True,
        tracker_iou_threshold: float = 0.2,
        tracker_max_missed_frames: int = 2,
    ) -> None:
        if not 0.0 <= detection_confidence <= 1.0:
            raise ValueError("detection_confidence must be between 0 and 1")
        if min_size <= 0 or max_size < min_size:
            raise ValueError("Keypoint R-CNN image size bounds are invalid")
        if max_people <= 0:
            raise ValueError("max_people must be positive")
        try:
            import torch
            import torchvision
            from torchvision.models.detection import keypointrcnn_resnet50_fpn
        except ImportError as error:
            raise RuntimeError(
                "Torch and TorchVision are required for Keypoint R-CNN"
            ) from error

        self.model_path = Path(model)
        if not self.model_path.is_file():
            raise FileNotFoundError(self.model_path)
        digest = sha256_file(self.model_path)
        if digest != TORCHVISION_KEYPOINT_RCNN_SHA256:
            raise ValueError("Keypoint R-CNN weight digest is not the frozen value")
        policy = load_torchvision_pose_policy(policy_path)
        policy_digest = sha256_file(Path(policy_path))
        normalized_device = str(device)
        if normalized_device == "auto":
            normalized_device = "cuda:0" if torch.cuda.is_available() else "cpu"
        elif normalized_device.isdigit():
            normalized_device = f"cuda:{normalized_device}"
        requested = torch.device(normalized_device)
        if requested.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested for Keypoint R-CNN but is unavailable")

        model_instance = keypointrcnn_resnet50_fpn(
            weights=None,
            weights_backbone=None,
            min_size=min_size,
            max_size=max_size,
        )
        state = torch.load(self.model_path, map_location="cpu", weights_only=True)
        model_instance.load_state_dict(state, strict=True)
        self._model = model_instance.eval().to(requested)
        self._torch = torch
        self._device = requested
        self.detection_confidence = detection_confidence
        self.max_people = max_people
        self.track = track
        self._tracker = IoUTrackAssigner(
            iou_threshold=tracker_iou_threshold,
            max_missed_frames=tracker_max_missed_frames,
        )
        self._bindings = [
            ModelBinding(
                task="human_pose_tracking",
                backend="torchvision-keypoint-rcnn",
                model_name=self.model_path.name,
                model_version=torchvision.__version__,
                model_digest=digest,
                license=TORCHVISION_MODEL_ARTIFACT_LICENSE,
                device=str(requested),
                configuration={
                    "weight_enum": policy["weight_enum"],
                    "implementation_license": policy["implementation_license"],
                    "training_lineage": policy["training_lineage"],
                    "model_artifact_distribution_status": policy[
                        "distribution_status"
                    ],
                    "license_policy_sha256": policy_digest,
                    "license_sources": policy["license_sources"],
                    "keypoint_layout": "COCO-17",
                    "detection_confidence": detection_confidence,
                    "min_size": min_size,
                    "max_size": max_size,
                    "max_people": max_people,
                    "tracking": track,
                    "tracker": "greedy-iou" if track else None,
                    "keypoint_confidence_transform": policy[
                        "keypoint_confidence_transform"
                    ],
                    "keypoint_confidence_is_calibrated_probability": False,
                },
            )
        ]

    @property
    def bindings(self) -> list[ModelBinding]:
        return list(self._bindings)

    def reset(self) -> None:
        self._tracker.reset()

    def infer(self, frame: Any) -> list[PoseDetection]:
        import cv2
        import numpy as np

        if frame is None or not hasattr(frame, "shape") or len(frame.shape) < 2:
            raise ValueError("Keypoint R-CNN input frame is invalid")
        height, width = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        contiguous = np.ascontiguousarray(rgb)
        tensor = (
            self._torch.from_numpy(contiguous)
            .permute(2, 0, 1)
            .to(device=self._device, dtype=self._torch.float32)
            .div(255.0)
        )
        with self._torch.inference_mode():
            raw = self._model([tensor])[0]
        output = {
            key: value.detach().cpu().numpy()
            for key, value in raw.items()
            if key in {"boxes", "labels", "scores", "keypoints", "keypoints_scores"}
        }
        decoded = decode_keypoint_rcnn_output(
            output,
            frame_width=int(width),
            frame_height=int(height),
            detection_confidence=self.detection_confidence,
            max_people=self.max_people,
        )
        boxes = [item[0] for item in decoded]
        track_ids = self._tracker.update(boxes) if self.track else [None] * len(boxes)
        return [
            PoseDetection(
                bbox_xyxy=bbox,
                keypoints_xyc=points,
                confidence=confidence,
                track_id=track_ids[index],
            )
            for index, (bbox, points, confidence) in enumerate(decoded)
        ]
