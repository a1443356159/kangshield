from __future__ import annotations

import json
from pathlib import Path

import pytest

from kangshield.information.artifacts import atomic_write_json
from kangshield.information.contracts import (
    EvidenceLevel,
    ModelBinding,
    RunManifest,
    SourceType,
)
from kangshield.information.fall_adl_benchmark import YOLO26N_POSE_SHA256
from kangshield.information.fall_candidate_export import run_fall_candidate_export
from kangshield.information.fall_feature_capture import (
    _pose_binding,
    run_fall_feature_capture,
)
from kangshield.information.pose_backend import PoseDetection
from kangshield.information.privacy import sha256_file
from scripts.prepare_v1_g4_event_evaluation_fixture import (
    build_event_evaluation_fixture,
)
from scripts.prepare_v1_m2c_timing_fixture import build_fixture


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FALL_FEATURE_POLICY = PROJECT_ROOT / "configs" / "v1-g4-fall-features.json"
REAL_CANDIDATE_POLICY = (
    PROJECT_ROOT / "configs" / "v1-g4-event-candidate-policy.json"
)


class _FakePoseBackend:
    def __init__(self, *, model_digest: str = YOLO26N_POSE_SHA256) -> None:
        self.reset_count = 0
        self._bindings = [
            ModelBinding(
                task="human_pose_tracking",
                backend="fixture-pose-backend",
                model_name="fixture-yolo26n-pose",
                model_version="fixture-v0.1.0",
                model_digest=model_digest,
                license="fixture-only",
                device="cpu",
                configuration={
                    "tracking": True,
                    "keypoint_layout": "COCO-17",
                },
            )
        ]

    @property
    def bindings(self) -> list[ModelBinding]:
        return [item.model_copy(deep=True) for item in self._bindings]

    def reset(self) -> None:
        self.reset_count += 1

    def infer(self, frame) -> list[PoseDetection]:
        points = [[120.0, 80.0 + index * 3.0, 0.9] for index in range(17)]
        return [
            PoseDetection(
                bbox_xyxy=[90.0, 40.0, 150.0, 210.0],
                keypoints_xyc=points,
                confidence=0.9,
                track_id=1,
            )
        ]


def test_capture_pose_binding_accepts_inline_or_explicit_tracking():
    inline = _FakePoseBackend().bindings[0]
    assert _pose_binding([inline]) == inline

    separated_pose = inline.model_copy(
        update={
            "task": "human_pose_estimation",
            "configuration": {"keypoint_layout": "COCO-17"},
        }
    )
    tracker = ModelBinding(
        task="short_term_pose_tracking",
        backend="fixture-iou-tracker",
        model_name="greedy-iou",
        model_version="fixture-v0.1.0",
        license="fixture-only",
        device="cpu",
        configuration={"enabled": True},
    )
    assert _pose_binding([separated_pose, tracker]) == separated_pose
    with pytest.raises(ValueError, match="exactly one"):
        _pose_binding([separated_pose])
    with pytest.raises(ValueError, match="exactly one"):
        _pose_binding([inline, tracker])
    with pytest.raises(ValueError, match="exactly one"):
        _pose_binding([separated_pose, tracker, tracker.model_copy(deep=True)])


def _prepare_capture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    media_path = tmp_path / "timing.avi"
    build_fixture(media_path)
    bundle_path = build_event_evaluation_fixture(
        tmp_path / "event-fixture",
        media_source=media_path,
        project_root=PROJECT_ROOT,
    )
    root = bundle_path.parent
    policy = json.loads(REAL_CANDIDATE_POLICY.read_text(encoding="utf-8"))
    policy.update(
        {
            "policy_id": "capture-producer-rule-fixture-v0.1.0",
            "fixture": True,
            "review_status": "fixture_only",
        }
    )
    candidate_policy_path = root / "policies" / "rule-candidate-policy.json"
    atomic_write_json(candidate_policy_path, policy)
    return (
        root / "capture" / "capture-manifest.json",
        root / "evidence" / "m2c-capture-readiness.json",
        root / "evidence" / "m2c-capture-run-manifest.json",
        candidate_policy_path,
    )


def test_capture_feature_producer_feeds_candidate_export_without_labels(tmp_path):
    capture, readiness, readiness_run, candidate_policy = _prepare_capture(tmp_path)
    backend = _FakePoseBackend()
    run, feature_set, report = run_fall_feature_capture(
        capture_manifest_path=capture,
        readiness_report_path=readiness,
        readiness_run_manifest_path=readiness_run,
        variant_id="yolo26n-pose",
        backend_factory=lambda _: backend,
        config_path=FALL_FEATURE_POLICY,
        runs_dir=tmp_path / "feature-runs",
        evidence_level=EvidenceLevel.E1,
        source_type=SourceType.FIXTURE,
        sample_fps=5.0,
    )

    assert run.manifest.stage == "v1-g4-fall-feature-capture"
    assert feature_set.clip_count == 16
    assert report.clip_count == 16
    assert report.input_frame_count == 240
    assert backend.reset_count == 16
    assert all(clip.frame_count == 15 for clip in feature_set.clips)
    assert all(clip.frames_with_people == 15 for clip in report.clips)
    assert all(clip.tracked_frames == 15 for clip in report.clips)
    assert report.labels_read_during_generation is False
    assert report.risk_assessment_emitted is False
    assert report.alert_emitted is False
    source_assets = [
        json.loads(line)
        for line in (run.run_dir / "source_assets.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(source_assets) == len({item["asset_id"] for item in source_assets})
    assert all(not item["uri"].startswith("file:") for item in source_assets)
    serialized = report.model_dump_json()
    for forbidden in (
        str(tmp_path),
        '"annotation_labels"',
        '"annotation_windows"',
        '"start_ms"',
        '"bbox_xyxy"',
        '"keypoints_xyc"',
    ):
        assert forbidden not in serialized

    candidate_run, prediction, summary = run_fall_candidate_export(
        capture_manifest_path=capture,
        feature_set_path=run.reports_dir / "fall-feature-capture-set.json",
        source_feature_run_manifest_path=run.manifest_path,
        policy_path=candidate_policy,
        runs_dir=tmp_path / "candidate-runs",
        evidence_level=EvidenceLevel.E1,
        allow_dirty_source=True,
    )
    assert candidate_run.manifest.status.value == "completed"
    assert len(prediction.clips) == 16
    assert summary.input_frame_count == 240
    assert summary.candidate_episode_count == 0


def test_capture_feature_producer_rejects_unusable_clip_or_weight_drift(tmp_path):
    capture, readiness, readiness_run, _ = _prepare_capture(tmp_path)
    report_payload = json.loads(readiness.read_text(encoding="utf-8"))
    report_payload["clips"][0]["structurally_usable"] = False
    atomic_write_json(readiness, report_payload)
    run_payload = RunManifest.model_validate_json(
        readiness_run.read_text(encoding="utf-8")
    ).model_dump(mode="json")
    run_payload["configuration"]["capture_readiness_report_sha256"] = sha256_file(
        readiness
    )
    atomic_write_json(readiness_run, run_payload)
    with pytest.raises(ValueError, match="every clip"):
        run_fall_feature_capture(
            capture_manifest_path=capture,
            readiness_report_path=readiness,
            readiness_run_manifest_path=readiness_run,
            variant_id="yolo26n-pose",
            backend_factory=lambda _: _FakePoseBackend(),
            config_path=FALL_FEATURE_POLICY,
            runs_dir=tmp_path / "unusable-runs",
        )

    report_payload["clips"][0]["structurally_usable"] = True
    atomic_write_json(readiness, report_payload)
    run_payload["configuration"]["capture_readiness_report_sha256"] = sha256_file(
        readiness
    )
    atomic_write_json(readiness_run, run_payload)
    with pytest.raises(ValueError, match="weight digest"):
        run_fall_feature_capture(
            capture_manifest_path=capture,
            readiness_report_path=readiness,
            readiness_run_manifest_path=readiness_run,
            variant_id="yolo26n-pose",
            backend_factory=lambda _: _FakePoseBackend(model_digest="0" * 64),
            config_path=FALL_FEATURE_POLICY,
            runs_dir=tmp_path / "drift-runs",
        )
