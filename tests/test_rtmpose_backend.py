from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from kangshield.information.rtmpose_backend import (
    HUMANART_ANNOTATION_LICENSE,
    HUMANART_MODEL_ARTIFACT_LICENSE,
    IoUTrackAssigner,
    bbox_center_scale,
    bbox_iou,
    decode_simcc,
    decode_yolox_end2end,
    preprocess_yolox,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_humanart_artifacts_never_inherit_the_framework_license():
    assert HUMANART_MODEL_ARTIFACT_LICENSE == "model-artifact-license-review-required"
    assert HUMANART_ANNOTATION_LICENSE == "CC-BY-NC-SA-4.0-noncommercial"

    config = json.loads(
        (PROJECT_ROOT / "configs" / "v1-m3-pose-models.json").read_text(
            encoding="utf-8"
        )
    )
    for model in config["models"]:
        assert model["license"] == HUMANART_MODEL_ARTIFACT_LICENSE
        assert model["implementation_license"] == "Apache-2.0"
        assert model["training_data_terms"] == HUMANART_ANNOTATION_LICENSE
        assert model["distribution_status"] == "blocked_pending_review"


def test_iou_tracker_preserves_and_expires_tracks():
    tracker = IoUTrackAssigner(iou_threshold=0.2, max_missed_frames=2)

    assert tracker.update([[0.0, 0.0, 100.0, 100.0]]) == [1]
    assert tracker.update([[5.0, 5.0, 105.0, 105.0]]) == [1]
    assert tracker.update([[300.0, 300.0, 350.0, 350.0]]) == [2]
    tracker.update([])
    tracker.update([])
    tracker.update([])
    assert tracker.update([[0.0, 0.0, 100.0, 100.0]]) == [3]


def test_bbox_iou_and_center_scale_are_deterministic():
    assert bbox_iou([0, 0, 10, 10], [5, 5, 15, 15]) == 25 / 175
    center, scale = bbox_center_scale(
        [10, 20, 110, 220],
        padding=1.0,
        input_size=(192, 256),
    )
    assert center.tolist() == [60.0, 120.0]
    assert scale.tolist() == [150.0, 200.0]


def test_yolox_preprocess_and_end2end_decode():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    tensor, ratio = preprocess_yolox(frame, (640, 640))
    assert tensor.shape == (1, 3, 640, 640)
    assert ratio == 3.2
    assert tensor[0, :, 500, 500].tolist() == [114.0, 114.0, 114.0]

    detections = np.array(
        [[[32.0, 64.0, 320.0, 256.0, 0.8], [0, 0, 1, 1, 0.9]]],
        dtype=np.float32,
    )
    labels = np.array([[0, 1]], dtype=np.int64)
    people = decode_yolox_end2end(
        detections,
        labels,
        ratio=3.2,
        frame_width=200,
        frame_height=100,
        confidence=0.05,
        max_people=4,
    )
    assert len(people) == 1
    assert people[0].bbox_xyxy == [10.0, 20.0, 100.0, 80.0]
    assert round(people[0].confidence, 3) == 0.8


def test_simcc_decode_maps_center_bin_back_to_bbox_center():
    simcc_x = np.zeros((1, 2, 384), dtype=np.float32)
    simcc_y = np.zeros((1, 2, 512), dtype=np.float32)
    simcc_x[0, 0, 192] = 0.8
    simcc_y[0, 0, 256] = 0.6
    simcc_x[0, 1, 96] = 0.4
    simcc_y[0, 1, 128] = 0.2

    keypoints, scores = decode_simcc(
        simcc_x,
        simcc_y,
        centers=[[50.0, 100.0]],
        scales=[[150.0, 200.0]],
        input_size=(192, 256),
    )
    assert keypoints.shape == (1, 2, 2)
    assert keypoints[0, 0].tolist() == [50.0, 100.0]
    assert keypoints[0, 1].tolist() == [12.5, 50.0]
    assert np.allclose(scores, [[0.7, 0.3]])
