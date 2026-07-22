from __future__ import annotations

import json
from pathlib import Path

import pytest

from kangshield.information.torchvision_pose_backend import (
    TORCHVISION_KEYPOINT_RCNN_SHA256,
    TORCHVISION_MODEL_ARTIFACT_LICENSE,
    decode_keypoint_rcnn_output,
    keypoint_logit_confidence,
    load_torchvision_pose_policy,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = PROJECT_ROOT / "configs" / "v1-m3-torchvision-pose-model.json"


def test_torchvision_pose_policy_freezes_weight_and_fail_closed_license():
    policy = load_torchvision_pose_policy(POLICY_PATH)

    assert policy["sha256"] == TORCHVISION_KEYPOINT_RCNN_SHA256
    assert policy["model_artifact_license"] == TORCHVISION_MODEL_ARTIFACT_LICENSE
    assert policy["distribution_status"] == "blocked_pending_review"
    assert {item["dataset"] for item in policy["training_lineage"]} == {
        "COCO 2017 keypoints",
        "ImageNet-1K",
    }


def test_torchvision_pose_policy_rejects_distribution_status_drift(tmp_path):
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["distribution_status"] = "approved"
    drifted = tmp_path / "policy.json"
    drifted.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(ValueError, match="distribution_status is not frozen"):
        load_torchvision_pose_policy(drifted)


def test_keypoint_logit_confidence_is_stable_uncalibrated_proxy():
    assert keypoint_logit_confidence(0.0) == 0.5
    assert keypoint_logit_confidence(2.0) == 0.880797
    assert keypoint_logit_confidence(-2.0) == 0.119203
    assert keypoint_logit_confidence(1000.0) == 1.0
    assert keypoint_logit_confidence(-1000.0) == 0.0
    assert keypoint_logit_confidence(float("nan")) == 0.0


def test_keypoint_rcnn_decoder_filters_sorts_clips_and_keeps_coco17():
    np = pytest.importorskip("numpy")
    keypoints = np.zeros((3, 17, 3), dtype=np.float32)
    keypoints[0, :, :2] = [10.0, 20.0]
    keypoints[1, :, :2] = [30.0, 40.0]
    keypoints[2, :, :2] = [50.0, 60.0]
    output = {
        "boxes": np.asarray(
            [
                [-2.0, -3.0, 110.0, 90.0],
                [1.0, 1.0, 2.0, 2.0],
                [5, 6, 20, 30],
            ],
            dtype=np.float32,
        ),
        "labels": np.asarray([1, 2, 1]),
        "scores": np.asarray([0.7, 0.99, 0.8], dtype=np.float32),
        "keypoints": keypoints,
        "keypoints_scores": np.asarray(
            [[0.0] * 17, [1.0] * 17, [2.0] * 17], dtype=np.float32
        ),
    }

    decoded = decode_keypoint_rcnn_output(
        output,
        frame_width=100,
        frame_height=80,
        detection_confidence=0.5,
        max_people=4,
    )

    assert len(decoded) == 2
    assert decoded[0][0] == [5.0, 6.0, 20.0, 30.0]
    assert len(decoded[0][1]) == 17
    assert decoded[0][1][0] == [50.0, 60.0, 0.880797]
    assert decoded[0][2] == 0.8
    assert decoded[1][0] == [0.0, 0.0, 100.0, 80.0]
    assert decoded[1][1][0][2] == 0.5


def test_keypoint_rcnn_decoder_rejects_shape_drift():
    np = pytest.importorskip("numpy")
    output = {
        "boxes": np.zeros((1, 4)),
        "labels": np.ones((1,)),
        "scores": np.ones((1,)),
        "keypoints": np.zeros((1, 16, 3)),
        "keypoints_scores": np.zeros((1, 17)),
    }

    with pytest.raises(ValueError, match="output shape is invalid"):
        decode_keypoint_rcnn_output(
            output,
            frame_width=100,
            frame_height=80,
            detection_confidence=0.5,
            max_people=4,
        )
