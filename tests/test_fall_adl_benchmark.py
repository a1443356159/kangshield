from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from kangshield.information.artifacts import atomic_write_json
from kangshield.information.contracts import FallAdlVideoCase, ModelBinding
from kangshield.information.fall_adl_benchmark import (
    FROZEN_ACTIVITIES,
    FROZEN_SUBJECT_LIGHTS,
    YOLO26N_POSE_SHA256,
    load_fall_adl_cases,
    run_fall_adl_benchmark,
)
from kangshield.information.pose_backend import PoseDetection
from kangshield.information.privacy import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FALL_CONFIG = PROJECT_ROOT / "configs" / "v1-g4-fall-features.json"
POSE_POLICY = PROJECT_ROOT / "configs" / "v1-m3-pose-models.json"


class _FakePoseBackend:
    def __init__(self) -> None:
        self.frame = 0
        self._bindings = [
            ModelBinding(
                task="human_pose_tracking",
                backend="fake-pose",
                model_name="yolo26n-pose.pt",
                model_version="test",
                model_digest=YOLO26N_POSE_SHA256,
                license="test-only",
                device="cpu",
                configuration={"keypoint_layout": "COCO-17"},
            )
        ]

    @property
    def bindings(self):
        return list(self._bindings)

    def reset(self) -> None:
        self.frame = 0

    def infer(self, frame):
        del frame
        points = [[30.0, 20.0, 0.9] for _ in range(17)]
        points[5] = [10.0, 15.0, 0.9]
        points[6] = [10.0, 25.0, 0.9]
        points[11] = [50.0, 15.0, 0.9]
        points[12] = [50.0, 25.0, 0.9]
        self.frame += 1
        return [
            PoseDetection(
                bbox_xyxy=[8.0, 14.0, 56.0, 38.0],
                keypoints_xyc=points,
                confidence=0.9,
                track_id=1,
            )
        ]


def _write_tiny_video(path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5, (64, 48)
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MJPG video writer unavailable")
    for value in range(10):
        writer.write(np.full((48, 64, 3), value * 10, dtype=np.uint8))
    writer.release()


def _build_suite(tmp_path: Path) -> Path:
    root = tmp_path / "suite"
    video_dir = root / "video"
    video_dir.mkdir(parents=True)
    source = tmp_path / "source.avi"
    _write_tiny_video(source)
    cases = []
    index = 0
    for subject, (illumination, lux) in FROZEN_SUBJECT_LIGHTS.items():
        for activity in FROZEN_ACTIVITIES:
            index += 1
            video_path = video_dir / f"case-{index:02d}.avi"
            shutil.copyfile(source, video_path)
            cases.append(
                FallAdlVideoCase(
                    case_id=f"fixture-{subject}-{activity}",
                    dataset_id="caucafall-v4",
                    dataset_version=4,
                    video_path=video_path.relative_to(root).as_posix(),
                    video_sha256=sha256_file(video_path),
                    video_byte_size=video_path.stat().st_size,
                    source_file_id=f"source-file-{index:02d}",
                    subject_ref=subject,
                    activity=activity,
                    illumination_group=illumination,
                    approx_lux=lux,
                    limitations=["fixture"],
                )
            )
    suite_path = root / "fall-adl-cases.json"
    atomic_write_json(
        suite_path,
        {
            "schema_version": "1.0",
            "suite_id": "v1-g4-caucafall-adl-negative-12",
            "evidence_level": "E1",
            "source_manifest_sha256": "a" * 64,
            "dataset": {
                "dataset_id": "caucafall-v4",
                "version": 4,
                "doi": "10.17632/7w7fccy7ky.4",
                "license": "CC-BY-4.0",
            },
            "case_count": len(cases),
            "cases": [item.model_dump(mode="json") for item in cases],
            "limitations": ["fixture_e1_only"],
        },
    )
    return suite_path


def test_fall_adl_loader_rejects_video_digest_drift(tmp_path):
    suite_path = _build_suite(tmp_path)
    suite, cases = load_fall_adl_cases(suite_path)
    assert suite["case_count"] == 12
    assert len(cases) == 12

    payload = json.loads(suite_path.read_text(encoding="utf-8"))
    payload["cases"][0]["subject_ref"] = "subject-06"
    atomic_write_json(suite_path, payload)
    with pytest.raises(ValueError, match="subject/activity matrix"):
        load_fall_adl_cases(suite_path)


def test_fall_adl_benchmark_keeps_parent_report_aggregate_only(
    tmp_path, monkeypatch
):
    suite_path = _build_suite(tmp_path)
    monkeypatch.setattr(
        "kangshield.information.fall_adl_benchmark.build_fall_adl_pose_backend",
        lambda *args, **kwargs: _FakePoseBackend(),
    )

    run, report = run_fall_adl_benchmark(
        fall_adl_cases_path=suite_path,
        runs_dir=tmp_path / "runs",
        variants=["yolo26n-pose"],
        config_path=FALL_CONFIG,
        model_binding_policy_path=POSE_POLICY,
        sample_fps=5.0,
        max_duration_s=30.0,
    )

    variant = report.variants[0]
    metrics = variant.overall.fall_feature_metrics
    assert report.case_count == 12
    assert report.pose_model_policy_sha256s == {}
    assert report.risk_assessment_emitted is False
    assert report.alert_emitted is False
    assert variant.overall.sampled_frames == 120
    assert variant.overall.pose_frame_coverage == 1.0
    assert metrics.bbox_horizontal_frames == 120
    assert metrics.maximum_horizontal_duration_ms == 1800
    assert set(variant.by_activity) == set(FROZEN_ACTIVITIES)
    assert set(variant.by_illumination) == {
        item[0] for item in FROZEN_SUBJECT_LIGHTS.values()
    }
    assert len(variant.runtime_environment["case_run_ids"]) == 12

    report_text = (
        run.run_dir / "reports" / "fall-adl-benchmark-report.json"
    ).read_text(encoding="utf-8")
    assert "bbox_xyxy" not in report_text
    assert "keypoints_xyc" not in report_text
    assert "/home/" not in report_text
    child_run = tmp_path / "runs" / variant.cases[0].run_id
    child_features = (child_run / "features.jsonl").read_text(encoding="utf-8")
    assert "video.pose_frame" in child_features
    assert "video.fall_motion_frame" in child_features
    assert "risk_assessment_emitted\": false" in child_features
