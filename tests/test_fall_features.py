from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from kangshield.information.artifacts import append_jsonl, atomic_write_json
from kangshield.information.contracts import (
    EvidenceLevel,
    FallFeatureConfig,
    FeatureEvent,
    ModelBinding,
    PoseBenchmarkCaseEvaluation,
    PoseBenchmarkVariantReport,
    PoseModelComparisonReport,
    PrivacyLevel,
    RunManifest,
    RunStatus,
    TimeRange,
)
from kangshield.information.fall_features import (
    FallMotionFeatureExtractor,
    run_fall_feature_benchmark,
    summarize_fall_features,
)
from kangshield.information.privacy import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FALL_CONFIG = PROJECT_ROOT / "configs" / "v1-g4-fall-features.json"
POSE_POLICY = PROJECT_ROOT / "configs" / "v1-m3-pose-models.json"
POSE_DIGEST = "12e1b9fcbcd867c3fb6d8f4d509cf1d8c5373df5e529676e32f6dd888758316c"
DETECTOR_DIGEST = "3dea6513388889f0fff4b77bf7a26013600321b9eb9ceb0e9a400a82572f5f23"


def _keypoints(*, score: float = 0.9, horizontal: bool = False) -> list[list[float]]:
    points = [[20.0, 20.0, score] for _ in range(17)]
    if horizontal:
        points[5] = [10.0, 15.0, score]
        points[6] = [10.0, 25.0, score]
        points[11] = [50.0, 15.0, score]
        points[12] = [50.0, 25.0, score]
    else:
        points[5] = [15.0, 10.0, score]
        points[6] = [25.0, 10.0, score]
        points[11] = [15.0, 50.0, score]
        points[12] = [25.0, 50.0, score]
    return points


def _detection(
    bbox: list[float],
    *,
    track_id: int | None = 1,
    point_score: float = 0.9,
    horizontal_keypoints: bool = False,
) -> dict:
    return {
        "bbox_xyxy": bbox,
        "keypoints_xyc": _keypoints(
            score=point_score,
            horizontal=horizontal_keypoints,
        ),
        "confidence": 0.8,
        "track_id": track_id,
    }


def _pose_event(
    sequence: int,
    timestamp_ms: int,
    detections: list[dict],
) -> FeatureEvent:
    return FeatureEvent(
        feature_id=f"pose-{sequence}",
        observation_id="video-observation",
        feature_type="video.pose_frame",
        time_range=TimeRange(start_ms=timestamp_ms, end_ms=timestamp_ms + 200),
        value={
            "frame_sequence": sequence,
            "person_count": len(detections),
            "detections": detections,
        },
        extractor_name="fake-pose",
        extractor_version="test",
        model_digest=POSE_DIGEST,
        privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
    )


def test_fall_feature_config_rejects_semantic_drift():
    with pytest.raises(ValidationError, match="minimum span"):
        FallFeatureConfig(
            descent_history_window_ms=500,
            descent_min_span_ms=600,
        )
    with pytest.raises(ValidationError, match="shoulders 5/6"):
        FallFeatureConfig(required_keypoint_indices=[0, 1, 2, 3])


def test_box_only_fallback_and_keypoint_geometry_are_explicit():
    config = FallFeatureConfig()
    extractor = FallMotionFeatureExtractor(config, frame_width=200, frame_height=400)

    passed = extractor.process(
        _pose_event(0, 0, [_detection([80.0, 20.0, 120.0, 180.0])])
    )
    assert passed.active_path == "box_plus_keypoints"
    assert passed.bbox_horizontal_proxy is False
    assert passed.keypoint_gate.status == "passed"
    assert passed.keypoint_gate.torso_angle_from_horizontal_deg == 90.0
    assert passed.risk_assessment_emitted is False
    assert passed.alert_emitted is False

    low_quality = extractor.process(
        _pose_event(
            1,
            200,
            [
                _detection([0.0, 0.0, 20.0, 20.0]),
                _detection(
                    [40.0, 100.0, 160.0, 160.0],
                    point_score=0.1,
                    horizontal_keypoints=True,
                ),
            ],
        )
    )
    assert low_quality.selected_detection_index == 1
    assert low_quality.active_path == "box_only"
    assert low_quality.bbox_horizontal_proxy is True
    assert low_quality.keypoint_gate.status == "failed_required_points"
    assert "multiple_people_largest_bbox_only" in low_quality.fallback_reasons
    assert (
        "keypoint_gate_failed_required_points_use_box_only"
        in low_quality.fallback_reasons
    )


def test_temporal_box_features_require_stable_track_history():
    extractor = FallMotionFeatureExtractor(
        FallFeatureConfig(), frame_width=200, frame_height=400
    )
    centers = [100.0, 120.0, 160.0, 200.0, 200.0, 200.0, 200.0]
    values = []
    for sequence, center_y in enumerate(centers):
        values.append(
            extractor.process(
                _pose_event(
                    sequence,
                    sequence * 200,
                    [
                        _detection(
                            [60.0, center_y - 20.0, 140.0, center_y + 20.0],
                            horizontal_keypoints=True,
                        )
                    ],
                )
            )
        )

    assert values[3].descent_history_span_ms == 600
    assert values[3].center_drop_frame_height_ratio == 0.25
    assert values[3].rapid_descent_proxy is True
    assert values[3].low_motion_proxy is False
    assert values[3].horizontal_duration_ms == 600
    assert values[-1].low_motion_proxy is True
    assert values[-1].max_center_displacement_diagonal_ratio == 0.0

    reset = extractor.process(
        _pose_event(
            7,
            1400,
            [
                _detection(
                    [60.0, 180.0, 140.0, 220.0],
                    track_id=2,
                    horizontal_keypoints=True,
                )
            ],
        )
    )
    assert reset.rapid_descent_proxy is None
    assert reset.low_motion_proxy is None
    assert "track_changed_history_reset" in reset.fallback_reasons
    assert "descent_history_not_ready" in reset.fallback_reasons


def test_no_detection_resets_history_and_metrics_keep_missingness():
    extractor = FallMotionFeatureExtractor(
        FallFeatureConfig(), frame_width=200, frame_height=400
    )
    available = extractor.process(
        _pose_event(
            0,
            0,
            [_detection([40.0, 100.0, 160.0, 160.0], point_score=0.1)],
        )
    )
    missing = extractor.process(_pose_event(1, 200, []))
    metrics = summarize_fall_features([available, missing])

    assert missing.active_path == "unavailable"
    assert missing.keypoint_gate.status == "failed_no_detection"
    assert metrics.sampled_frames == 2
    assert metrics.unavailable_frames == 1
    assert metrics.box_available_frames == 1
    assert metrics.box_only_frames == 1
    assert metrics.bbox_horizontal_rate == 1.0
    assert metrics.maximum_horizontal_duration_ms == 0
    assert metrics.fallback_reason_counts["no_person_detection"] == 1


def _build_source_pose_fixture(tmp_path: Path) -> tuple[Path, Path]:
    benchmark_dir = tmp_path / "benchmark"
    annotation_dir = benchmark_dir / "annotations"
    annotation_dir.mkdir(parents=True)
    annotation_path = annotation_dir / "fall-99.json"
    atomic_write_json(
        annotation_path,
        {
            "schema_version": "1.0",
            "width": 200,
            "height": 400,
            "frames": [
                {"replay_timestamp_ms": 0, "posture_label": -1},
                {"replay_timestamp_ms": 200, "posture_label": 0},
                {"replay_timestamp_ms": 400, "posture_label": 1},
                {"replay_timestamp_ms": 600, "posture_label": 1},
            ],
        },
    )
    benchmark_path = benchmark_dir / "benchmark-cases.json"
    atomic_write_json(
        benchmark_path,
        {
            "schema_version": "1.0",
            "benchmark_id": "fall-feature-test",
            "evidence_level": "E1",
            "pairing_kind": "cross_dataset_synthetic_common_zero",
            "source_manifest_sha256": "a" * 64,
            "cases": [
                {
                    "schema_version": "1.0",
                    "case_id": "fall-99-audio-1",
                    "evidence_level": "E1",
                    "pairing_kind": "cross_dataset_synthetic_common_zero",
                    "video_path": "video/fall-99.avi",
                    "audio_path": "audio/test.wav",
                    "annotation_path": "annotations/fall-99.json",
                    "video_dataset": "urfd",
                    "video_sequence": "fall-99",
                    "video_class": "fall",
                    "audio_dataset": "test-audio",
                    "audio_sample": "test.wav",
                    "audio_gender": "unknown",
                    "audio_duration_ms": 1000,
                    "reference_transcript": "测试",
                    "limitations": ["fixture"],
                }
            ],
            "limitations": ["fixture_e1_only"],
        },
    )

    source_runs = tmp_path / "source-runs"
    parent_dir = source_runs / "source-parent"
    child_dir = source_runs / "source-child"
    (parent_dir / "reports").mkdir(parents=True)
    child_dir.mkdir(parents=True)
    parent_manifest = RunManifest(
        run_id="source-parent",
        stage="v1-m3-pose-model-comparison",
        status=RunStatus.COMPLETED,
        evidence_level=EvidenceLevel.E1,
        code_version="source123",
        code_dirty=False,
    )
    child_manifest = RunManifest(
        run_id="source-child",
        stage="v1-m3-pose-model-case",
        status=RunStatus.COMPLETED,
        evidence_level=EvidenceLevel.E1,
        code_version="source123",
        code_dirty=False,
        configuration={
            "case_id": "fall-99-audio-1",
            "variant_id": "rtmpose-m-humanart",
        },
    )
    atomic_write_json(parent_dir / "manifest.json", parent_manifest)
    atomic_write_json(child_dir / "manifest.json", child_manifest)
    for sequence, center_y in enumerate((100.0, 140.0, 180.0, 220.0)):
        append_jsonl(
            child_dir / "features.jsonl",
            _pose_event(
                sequence,
                sequence * 200,
                [
                    _detection(
                        [60.0, center_y - 20.0, 140.0, center_y + 20.0],
                        horizontal_keypoints=True,
                    )
                ],
            ),
        )

    bindings = [
        ModelBinding(
            task="human_pose_estimation",
            backend="onnxruntime-openmmlab",
            model_name="rtmpose_m_humanart.onnx",
            model_digest=POSE_DIGEST,
            license="Apache-2.0",
            device="cuda",
            configuration={"keypoint_layout": "COCO-17"},
        ),
        ModelBinding(
            task="person_detection",
            backend="onnxruntime-openmmlab",
            model_name="yolox_m_humanart.onnx",
            model_digest=DETECTOR_DIGEST,
            license="Apache-2.0",
            device="cuda",
        ),
        ModelBinding(
            task="short_term_pose_tracking",
            backend="kangshield-iou-tracker",
            model_name="greedy-iou",
            license="project-internal",
            device="cpu",
        ),
    ]
    case = PoseBenchmarkCaseEvaluation(
        case_id="fall-99-audio-1",
        variant_id="rtmpose-m-humanart",
        run_id="source-child",
        video_sequence="fall-99",
        video_class="fall",
        sampled_frames=4,
        frames_with_people=4,
        pose_frame_coverage=1.0,
        tracked_frames=4,
        tracking_coverage=1.0,
        unique_track_count=1,
        maximum_annotation_match_error_ms=0,
        evaluated_media_duration_ms=800,
    )
    variant = PoseBenchmarkVariantReport(
        variant_id="rtmpose-m-humanart",
        model_bindings=bindings,
        case_count=1,
        cases=[case],
        sampled_frames=4,
        frames_with_people=4,
        pose_frame_coverage=1.0,
        tracked_frames=4,
        tracking_coverage=1.0,
    )
    report = PoseModelComparisonReport(
        benchmark_id="fall-feature-test",
        benchmark_version="test",
        source_manifest_sha256="a" * 64,
        benchmark_cases_sha256=sha256_file(benchmark_path),
        case_count=1,
        primary_metric="test",
        variants=[variant],
    )
    report_path = parent_dir / "reports" / "pose-model-comparison-report.json"
    atomic_write_json(report_path, report)
    return benchmark_path, report_path


def test_fall_feature_benchmark_reuses_clean_pose_events_without_risk(tmp_path):
    benchmark_path, pose_report_path = _build_source_pose_fixture(tmp_path)

    run, report = run_fall_feature_benchmark(
        benchmark_cases_path=benchmark_path,
        pose_comparison_report_path=pose_report_path,
        runs_dir=tmp_path / "output-runs",
        variant_id="rtmpose-m-humanart",
        config_path=FALL_CONFIG,
        model_binding_policy_path=POSE_POLICY,
    )

    assert report.case_count == 1
    assert report.risk_assessment_emitted is False
    assert report.alert_emitted is False
    assert len(report.source_binding_license_corrections) == 2
    assert {
        binding.license
        for binding in report.model_bindings
        if binding.model_digest in {POSE_DIGEST, DETECTOR_DIGEST}
    } == {"model-artifact-license-review-required"}
    assert report.cases[0].source_pose_code_dirty is False
    assert report.by_posture_phase["lying"].sampled_frames == 2
    assert run.manifest.status is RunStatus.COMPLETED
    assert len(run.manifest.inputs) >= 8

    derived_text = (run.run_dir / "features.jsonl").read_text(encoding="utf-8")
    assert derived_text.count("video.fall_motion_frame") == 4
    assert "bbox_xyxy" not in derived_text
    assert "keypoints_xyc" not in derived_text
    assert "posture_label" not in derived_text
    assert "risk_assessment_emitted\": false" in derived_text


def test_fall_feature_benchmark_rejects_dirty_source_by_default(tmp_path):
    benchmark_path, pose_report_path = _build_source_pose_fixture(tmp_path)
    manifest_path = pose_report_path.parent.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["code_dirty"] = True
    atomic_write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match="source pose comparison is dirty"):
        run_fall_feature_benchmark(
            benchmark_cases_path=benchmark_path,
            pose_comparison_report_path=pose_report_path,
            runs_dir=tmp_path / "output-runs",
            variant_id="rtmpose-m-humanart",
            config_path=FALL_CONFIG,
            model_binding_policy_path=POSE_POLICY,
        )
