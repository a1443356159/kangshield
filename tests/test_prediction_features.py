from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from kangshield.information.contracts import EvidenceLevel, SourceType
from kangshield.information.pose_backend import PoseDetection
from kangshield.information.prediction_features import (
    FaceIdentityRunner,
    PoseC3DBatchRunner,
    PoseResultView,
    PredictionFeatureExtractor,
    load_prediction_feature_config,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREDICTION_POLICY = PROJECT_ROOT / "configs" / "v1-g4-prediction-features.json"
SYNC_DIR = PROJECT_ROOT / "src" / "kangshield" / "information" / "prediction_sync"


def _person(*, knee_angle: str = "standing", track_id: int = 1) -> PoseDetection:
    # Vertical torso: shoulders y=60, hips y=110.
    points = [[100.0, 60.0, 0.9] for _ in range(17)]
    for index in (11, 12):
        points[index] = [100.0, 110.0, 0.9]
    for index in (13, 14):
        points[index] = [100.0, 160.0, 0.9]
    if knee_angle == "standing":
        for index in (15, 16):
            points[index] = [100.0, 210.0, 0.9]
    elif knee_angle == "sitting":
        for index in (15, 16):
            points[index] = [150.0, 160.0, 0.9]
    else:  # transition: knee angle ~150 degrees (between sitting and standing)
        points[15] = [125.0, 203.3, 0.9]
        points[16] = [125.0, 203.3, 0.9]
    return PoseDetection(
        bbox_xyxy=[80.0, 40.0, 130.0, 220.0],
        keypoints_xyc=points,
        confidence=0.9,
        track_id=track_id,
    )


def _walking_person(phase: int, *, track_id: int = 1) -> PoseDetection:
    detection = _person(track_id=track_id)
    # phase flips which ankle is lower (larger y), normalized by torso length.
    offset = 0.1 * 50.0  # ankle_separation threshold 0.08 x torso 50 px
    detection.keypoints_xyc[15][1] = 210.0 + (offset if phase > 0 else 0.0)
    detection.keypoints_xyc[16][1] = 210.0 + (offset if phase < 0 else 0.0)
    return detection


def test_policy_loads_and_rejects_unknown_keys(tmp_path):
    config = load_prediction_feature_config(PREDICTION_POLICY)
    assert config.feature_version == "prediction-features-v0.1.0"
    assert config.meters_per_pixel == 0.0
    payload = json.loads(PREDICTION_POLICY.read_text(encoding="utf-8"))
    payload["unknown_key"] = True
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="schema validation"):
        load_prediction_feature_config(broken)


def test_pose_result_view_feeds_synced_selection():
    view = PoseResultView([_person()])
    assert view.boxes is not None and len(view.boxes) == 1
    assert view.keypoints is not None
    empty = PoseResultView([])
    assert empty.boxes is None and empty.keypoints is None


def test_extractor_stabilizes_posture_and_tracks_primary_person():
    config = load_prediction_feature_config(PREDICTION_POLICY)
    extractor = PredictionFeatureExtractor(
        config, frame_width=640, frame_height=480, sample_fps=15.0
    )
    value = None
    for sequence in range(6):
        value = extractor.process(
            [_person()], frame_sequence=sequence, timestamp_ms=sequence * 66
        )
    assert value is not None
    assert value.person_detected is True
    assert value.posture == "standing"
    assert value.raw_posture == "standing"
    assert value.selected_track_id == 1
    assert value.risk_assessment_emitted is False
    assert value.alert_emitted is False

    empty = extractor.process([], frame_sequence=6, timestamp_ms=6 * 66)
    assert empty.person_detected is False
    assert empty.posture == "no_person"
    assert empty.person_count == 0


def test_candidate_scores_stay_out_of_formal_positions():
    config = load_prediction_feature_config(PREDICTION_POLICY)
    extractor = PredictionFeatureExtractor(
        config, frame_width=640, frame_height=480, sample_fps=15.0
    )
    value = extractor.process([_person()], frame_sequence=0, timestamp_ms=0)
    assert value.candidate_scores["candidate_only"] is True
    serialized = value.model_dump()
    assert "score" not in serialized
    assert serialized["risk_assessment_emitted"] is False


def test_uncalibrated_gait_speed_is_null_with_limitation():
    config = load_prediction_feature_config(PREDICTION_POLICY)
    extractor = PredictionFeatureExtractor(
        config, frame_width=640, frame_height=480, sample_fps=5.0
    )
    value = extractor.process([_person()], frame_sequence=0, timestamp_ms=0)
    assert value.gait["gait_speed_m_s"] is None
    assert "gait_speed_requires_ground_calibration" in value.limitations
    assert "step_event_thresholds_tuned_for_15fps" in value.limitations


def test_step_events_and_cadence_from_phase_flips():
    config = load_prediction_feature_config(PREDICTION_POLICY)
    extractor = PredictionFeatureExtractor(
        config, frame_width=640, frame_height=480, sample_fps=15.0
    )
    timestamp = 0
    phase = 1
    value = None
    for sequence in range(12):
        value = extractor.process(
            [_walking_person(phase)], frame_sequence=sequence, timestamp_ms=timestamp
        )
        phase = -phase
        timestamp += 400
    assert value is not None
    assert value.gait["step_events"] >= 4
    assert value.gait["cadence_steps_min"] == pytest.approx(150.0, abs=1.0)
    assert value.gait["mean_step_time_s"] == pytest.approx(0.4, abs=0.01)


def test_sit_to_stand_state_machine_records_duration():
    config = load_prediction_feature_config(PREDICTION_POLICY)
    extractor = PredictionFeatureExtractor(
        config, frame_width=640, frame_height=480, sample_fps=15.0
    )
    timestamp = 0

    def feed(posture: str, frames: int) -> None:
        nonlocal timestamp
        for _ in range(frames):
            extractor.process(
                [_person(knee_angle=posture)],
                frame_sequence=0,
                timestamp_ms=timestamp,
            )
            timestamp += 200

    feed("sitting", 6)
    feed("transition", 5)
    feed("standing", 6)
    summary = extractor.summary()
    assert summary.sit_to_stand_completed_count == 1
    assert summary.sit_to_stand_durations_s[0] == pytest.approx(1.0, abs=0.3)


def test_track_switch_resets_temporal_state():
    config = load_prediction_feature_config(PREDICTION_POLICY)
    extractor = PredictionFeatureExtractor(
        config, frame_width=640, frame_height=480, sample_fps=15.0
    )
    for sequence in range(4):
        extractor.process([_person(track_id=1)], frame_sequence=sequence,
                          timestamp_ms=sequence * 200)
    assert extractor.state.primary_track_id == 1
    extractor.process([_person(track_id=2)], frame_sequence=4, timestamp_ms=800)
    assert extractor.state.primary_track_id == 2
    assert extractor.state.previous_time is not None


def test_summary_quality_gate_fails_closed():
    config = load_prediction_feature_config(PREDICTION_POLICY)
    extractor = PredictionFeatureExtractor(
        config, frame_width=640, frame_height=480, sample_fps=15.0
    )
    extractor.process([], frame_sequence=0, timestamp_ms=0)
    extractor.process([], frame_sequence=1, timestamp_ms=200)
    summary = extractor.summary()
    assert summary.assessability == "not_assessable"
    assert "insufficient_primary_person_frames" in summary.gate_failures


def test_posec3d_runner_degrades_when_prerequisites_missing(tmp_path):
    config = load_prediction_feature_config(PREDICTION_POLICY)
    runner = PoseC3DBatchRunner(
        config.posec3d,
        python_executable=tmp_path / "missing-python",
        service_file=tmp_path / "missing-service.py",
        checkpoint=tmp_path / "missing.pth",
        labels=tmp_path / "missing.txt",
        mmaction_config=tmp_path / "missing-config.py",
    )
    assert not runner.available
    extractor = PredictionFeatureExtractor(
        config, frame_width=640, frame_height=480, sample_fps=15.0
    )
    result = runner.run_window(extractor.state, tmp_path / "work")
    assert result["state"] == "unavailable"
    assert result["signal"] == "unavailable"


def test_face_runner_degrades_when_files_missing(tmp_path):
    runner = FaceIdentityRunner(
        model_dir=tmp_path / "no-models", gallery_path=tmp_path / "no-gallery.npz"
    )
    assert not runner.available
    result = runner.process_frame(
        frame=None,
        detections=[],
        timestamp_ms=0,
        frame_number=None,
        primary_track_id=None,
    )
    assert result["state"] == "unavailable"


def test_sync_manifest_integrity():
    manifest = json.loads(
        (SYNC_DIR / "SYNC_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["source_commit"]
    for entry in manifest["files"]:
        local = SYNC_DIR / entry["local_path"]
        assert local.is_file(), entry["local_path"]
        digest = hashlib.sha256(local.read_bytes()).hexdigest()
        assert digest == entry["local_sha256"], (
            f"synced file drifted from manifest: {entry['local_path']} — "
            "algorithm edits are forbidden locally; re-sync from fall-detection"
        )


class _FakePoseBackend:
    def __init__(self) -> None:
        from kangshield.information.contracts import ModelBinding
        from kangshield.information.fall_adl_benchmark import YOLO26N_POSE_SHA256

        self._bindings = [
            ModelBinding(
                task="human_pose_tracking",
                backend="fixture-pose-backend",
                model_name="fixture-yolo26n-pose",
                model_version="fixture-v0.1.0",
                model_digest=YOLO26N_POSE_SHA256,
                license="fixture-only",
                device="cpu",
                configuration={"tracking": True, "keypoint_layout": "COCO-17"},
            )
        ]

    @property
    def bindings(self):
        return [item.model_copy(deep=True) for item in self._bindings]

    def reset(self) -> None:
        return None

    def infer(self, frame) -> list[PoseDetection]:
        return [_person()]


def _prepare_capture(tmp_path: Path) -> tuple[Path, Path, Path]:
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    from scripts.prepare_v1_g4_event_evaluation_fixture import (
        build_event_evaluation_fixture,
    )
    from scripts.prepare_v1_m2c_timing_fixture import build_fixture

    media_path = tmp_path / "timing.avi"
    build_fixture(media_path)
    bundle_path = build_event_evaluation_fixture(
        tmp_path / "event-fixture",
        media_source=media_path,
        project_root=PROJECT_ROOT,
    )
    root = bundle_path.parent
    return (
        root / "capture" / "capture-manifest.json",
        root / "evidence" / "m2c-capture-readiness.json",
        root / "evidence" / "m2c-capture-run-manifest.json",
    )


def test_capture_with_prediction_policy_and_degraded_sidecars(tmp_path):
    from kangshield.information.fall_feature_capture import run_fall_feature_capture

    capture, readiness, readiness_run = _prepare_capture(tmp_path)
    run, feature_set, report = run_fall_feature_capture(
        capture_manifest_path=capture,
        readiness_report_path=readiness,
        readiness_run_manifest_path=readiness_run,
        variant_id="yolo26n-pose",
        backend_factory=lambda _: _FakePoseBackend(),
        config_path=PROJECT_ROOT / "configs" / "v1-g4-fall-features.json",
        runs_dir=tmp_path / "runs",
        evidence_level=EvidenceLevel.E1,
        source_type=SourceType.FIXTURE,
        sample_fps=5.0,
        prediction_policy_path=PREDICTION_POLICY,
        posec3d_mode="auto",
        face_mode="auto",
    )
    assert report.clip_count == 16
    assert all(clip.prediction_summary is not None for clip in report.clips)
    first = report.clips[0].prediction_summary
    assert first.frames_processed == 15
    assert first.frames_with_primary_person == 15
    assert first.meters_per_pixel == 0.0
    assert "gait_speed_requires_ground_calibration" in first.limitations
    assert "step_event_thresholds_tuned_for_15fps" in first.limitations
    assert any("posec3d_unavailable" in item for item in report.limitations)
    assert any("face_identity_unavailable" in item for item in report.limitations)
    assert any(
        "prediction_indicators_are_candidate_values" in item
        for item in report.limitations
    )
    feature_lines = (
        (run.run_dir / "features.jsonl").read_text(encoding="utf-8").splitlines()
    )
    feature_types = {json.loads(line)["feature_type"] for line in feature_lines}
    assert "video.prediction_frame" in feature_types
    assert "video.posec3d_window" in feature_types
    prediction_artifact = (
        run.artifacts_dir / "prediction-motion-000.jsonl"
    )
    assert prediction_artifact.is_file()
    serialized = report.model_dump_json()
    for forbidden in ('"bbox_xyxy"', '"keypoints_xyc"', '"start_ms"'):
        assert forbidden not in serialized


def test_capture_without_prediction_policy_is_unchanged(tmp_path):
    from kangshield.information.fall_feature_capture import run_fall_feature_capture

    capture, readiness, readiness_run = _prepare_capture(tmp_path)
    run, feature_set, report = run_fall_feature_capture(
        capture_manifest_path=capture,
        readiness_report_path=readiness,
        readiness_run_manifest_path=readiness_run,
        variant_id="yolo26n-pose",
        backend_factory=lambda _: _FakePoseBackend(),
        config_path=PROJECT_ROOT / "configs" / "v1-g4-fall-features.json",
        runs_dir=tmp_path / "runs",
        evidence_level=EvidenceLevel.E1,
        source_type=SourceType.FIXTURE,
        sample_fps=5.0,
    )
    assert all(clip.prediction_summary is None for clip in report.clips)
    feature_lines = (
        (run.run_dir / "features.jsonl").read_text(encoding="utf-8").splitlines()
    )
    feature_types = {json.loads(line)["feature_type"] for line in feature_lines}
    assert feature_types == {"video.pose_frame", "video.fall_motion_frame"}
    assert not (run.artifacts_dir / "prediction-motion-000.jsonl").exists()
