from __future__ import annotations

from kangshield.information.pose_backend import PoseDetection
from kangshield.information.pose_benchmark import _FrameResult, phase_metrics


def _detection(track_id: int | None, point_score: float) -> PoseDetection:
    return PoseDetection(
        bbox_xyxy=[0.0, 0.0, 40.0, 20.0],
        keypoints_xyc=[[1.0, 2.0, point_score], [2.0, 3.0, point_score]],
        confidence=0.8,
        track_id=track_id,
    )


def test_phase_metrics_separates_coverage_tracking_and_keypoint_quality():
    results = [
        _FrameResult(0, "lying", 0, [_detection(1, 0.8)], 2.0),
        _FrameResult(200, "lying", 0, [_detection(None, 0.2)], 2.5),
        _FrameResult(400, "lying", 0, [], 1.0),
    ]

    metrics = phase_metrics(results)

    assert metrics.sampled_frames == 3
    assert metrics.frames_with_people == 2
    assert metrics.pose_frame_coverage == 0.666667
    assert metrics.tracked_frames == 1
    assert metrics.tracking_coverage == 0.5
    assert metrics.mean_pose_quality == 0.5
    assert metrics.mean_bbox_width_height_ratio == 2.0
