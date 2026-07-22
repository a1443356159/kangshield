#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kangshield.information.artifacts import append_jsonl, atomic_write_json
from kangshield.information.contracts import (
    EvidenceLevel,
    FallFeatureCaptureSet,
    FallFeatureClipStream,
    FallKeypointGate,
    FallMotionFrameValue,
    FeatureEvent,
    PrivacyLevel,
    RunManifest,
    RunStatus,
    TimeRange,
)
from kangshield.information.fall_candidate_export import run_fall_candidate_export
from kangshield.information.privacy import sha256_file

try:
    from scripts.prepare_v1_g4_event_evaluation_fixture import (
        CANDIDATES,
        PROJECT_ROOT,
        _file_reference,
        build_event_evaluation_fixture,
    )
except ModuleNotFoundError:  # Direct execution puts scripts/ on sys.path.
    from prepare_v1_g4_event_evaluation_fixture import (
        CANDIDATES,
        PROJECT_ROOT,
        _file_reference,
        build_event_evaluation_fixture,
    )


DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "public-smoke"
    / "v1-g4-candidate-export"
)
DEFAULT_MEDIA = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "public-smoke"
    / "v1-m2c-timing.synthetic.avi"
)
FEATURE_VERSION = "fall-motion-features-v0.1.0"


def _frame(
    sequence: int,
    timestamp_ms: int,
    *,
    horizontal: bool = False,
    horizontal_duration_ms: int = 0,
    rapid_descent: bool = False,
) -> FallMotionFrameValue:
    return FallMotionFrameValue(
        feature_version=FEATURE_VERSION,
        frame_sequence=sequence,
        timestamp_ms=timestamp_ms,
        frame_width=640,
        frame_height=480,
        person_count=1,
        selected_detection_index=0,
        selected_track_id=1,
        active_path="box_plus_keypoints",
        bbox_horizontal_proxy=horizontal,
        horizontal_duration_ms=horizontal_duration_ms,
        rapid_descent_proxy=rapid_descent,
        low_motion_proxy=False,
        keypoint_gate=FallKeypointGate(
            expected_layout="COCO-17",
            expected_count=17,
            observed_count=17,
            confidence_threshold=0.5,
            visible_count=17,
            visible_ratio=1.0,
            visible_ratio_threshold=0.5,
            required_indices=[5, 6, 11, 12],
            required_visible_count=4,
            required_all_visible=True,
            status="passed",
            geometry_available=True,
            torso_horizontal_proxy=horizontal,
        ),
    )


def _frames(*, activated: bool) -> list[FallMotionFrameValue]:
    if activated:
        return [
            _frame(0, 0),
            _frame(1, 200),
            _frame(2, 400, rapid_descent=True),
            _frame(3, 600, horizontal=True),
            _frame(4, 800, horizontal=True, horizontal_duration_ms=200),
            _frame(5, 1000, horizontal=True, horizontal_duration_ms=400),
            _frame(6, 1200, horizontal=True, horizontal_duration_ms=600),
            _frame(7, 1400, horizontal=True, horizontal_duration_ms=800),
            _frame(8, 1600),
            _frame(9, 2000),
            _frame(10, 2200),
        ]
    return [
        _frame(index, timestamp_ms)
        for index, timestamp_ms in enumerate(range(0, 2401, 400))
    ]


def _write_stream(
    path: Path,
    *,
    scenario_id: str,
    observation_id: str,
    duration_ms: int,
    activated: bool,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = _frames(activated=activated)
    for frame in frames:
        append_jsonl(
            path,
            FeatureEvent(
                feature_id=(
                    f"feature_fixture_{scenario_id}_{frame.frame_sequence:03d}"
                ),
                observation_id=observation_id,
                feature_type="video.fall_motion_frame",
                time_range=TimeRange(
                    start_ms=frame.timestamp_ms,
                    end_ms=min(duration_ms, frame.timestamp_ms + 100),
                ),
                value=frame.model_dump(mode="json"),
                extractor_name="kangshield-fixture-fall-features",
                extractor_version=FEATURE_VERSION,
                privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
                limitations=[
                    "synthetic_fixture_only",
                    "no_risk_assessment_or_alert",
                ],
            ),
        )
    return len(frames)


def _write_feature_source(
    root: Path,
    *,
    variant_id: str,
    capture_manifest: dict,
    capture_manifest_sha256: str,
    model_policy_sha256: str,
    fall_feature_policy_sha256: str,
) -> tuple[Path, Path]:
    run_id = f"fixture-features-{variant_id}"
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    clip_streams = []
    activated_scenarios = set(CANDIDATES[variant_id])
    for clip in capture_manifest["clips"]:
        scenario_id = str(clip["scenario_id"])
        relative_path = f"artifacts/{scenario_id}.jsonl"
        path = run_dir / relative_path
        observation_id = f"observation_{variant_id}_{scenario_id}"
        frame_count = _write_stream(
            path,
            scenario_id=scenario_id,
            observation_id=observation_id,
            duration_ms=int(clip["duration_ms"]),
            activated=scenario_id in activated_scenarios,
        )
        clip_streams.append(
            FallFeatureClipStream(
                scenario_id=scenario_id,
                duration_ms=int(clip["duration_ms"]),
                observation_id=observation_id,
                relative_path=relative_path,
                sha256=sha256_file(path),
                byte_size=path.stat().st_size,
                frame_count=frame_count,
            )
        )

    fixture_tz = timezone(timedelta(hours=8))
    feature_set = FallFeatureCaptureSet(
        feature_set_id=f"fixture-feature-set-{variant_id}",
        fixture=True,
        evidence_level=EvidenceLevel.E1,
        variant_id=variant_id,
        source_run_id=run_id,
        capture_manifest_sha256=capture_manifest_sha256,
        model_policy_sha256=model_policy_sha256,
        fall_feature_policy_sha256=fall_feature_policy_sha256,
        feature_version=FEATURE_VERSION,
        generated_at=datetime(2026, 7, 22, 10, 2, tzinfo=fixture_tz),
        clip_count=len(clip_streams),
        clips=clip_streams,
        limitations=[
            "synthetic_rule_bearing_fixture",
            "activation_layout_is_for_contract_testing_only",
        ],
    )
    feature_set_path = run_dir / "reports" / "fall-feature-capture-set.json"
    atomic_write_json(feature_set_path, feature_set)
    source_run = RunManifest(
        run_id=run_id,
        stage="v1-g4-fall-feature-capture",
        status=RunStatus.COMPLETED,
        evidence_level=EvidenceLevel.E1,
        started_at=datetime(2026, 7, 22, 10, 0, tzinfo=fixture_tz),
        finished_at=datetime(2026, 7, 22, 10, 5, tzinfo=fixture_tz),
        code_version="fixture-feature-v0.1.0",
        code_dirty=False,
        configuration={
            "variant_id": variant_id,
            "capture_manifest_sha256": capture_manifest_sha256,
            "model_policy_sha256": model_policy_sha256,
            "fall_feature_policy_sha256": fall_feature_policy_sha256,
            "fall_feature_set_sha256": sha256_file(feature_set_path),
            "feature_version": FEATURE_VERSION,
            "labels_read_during_generation": False,
            "risk_assessment_emitted": False,
            "alert_emitted": False,
        },
        artifacts=[
            feature_set_path.relative_to(run_dir).as_posix(),
            *(stream.relative_path for stream in clip_streams),
        ],
    )
    source_run_path = run_dir / "manifest.json"
    atomic_write_json(source_run_path, source_run)
    return feature_set_path, source_run_path


def build_candidate_export_fixture(
    output_dir: Path,
    *,
    media_source: Path,
    project_root: Path = PROJECT_ROOT,
) -> Path:
    """Build a rule-bearing fixture whose predictions come from the real exporter."""

    output_dir = Path(output_dir)
    bundle_path = build_event_evaluation_fixture(
        output_dir,
        media_source=media_source,
        project_root=project_root,
    )
    capture_manifest_path = output_dir / "capture" / "capture-manifest.json"
    capture_manifest = json.loads(capture_manifest_path.read_text(encoding="utf-8"))
    capture_manifest_sha256 = sha256_file(capture_manifest_path)
    model_policy_sha256s = {
        binding["variant_id"]: binding["sha256"]
        for binding in capture_manifest["held_out_protocol"]["model_policies"]
    }

    real_policy_path = project_root / "configs" / "v1-g4-event-candidate-policy.json"
    candidate_policy = json.loads(real_policy_path.read_text(encoding="utf-8"))
    candidate_policy.update(
        {
            "policy_id": "v1-g4-rule-bearing-export-fixture-v0.1.0",
            "fixture": True,
            "review_status": "fixture_only",
            "decision_logic_summary": (
                "Real frozen candidate state machine over synthetic G4 frame streams"
            ),
            "limitations": [
                "synthetic_fixture_only",
                "candidate_activation_layout_is_not_model_quality_evidence",
                "candidate_episode_is_not_risk_assessment_or_alert",
            ],
        }
    )
    candidate_policy_path = output_dir / "policies" / "candidate-policy.json"
    atomic_write_json(candidate_policy_path, candidate_policy)

    prediction_bindings = []
    feature_runs_root = output_dir / "feature-runs"
    feature_runs_root.mkdir()
    candidate_runs_root = output_dir / "candidate-runs"
    candidate_runs_root.mkdir()
    for variant_id in sorted(CANDIDATES):
        feature_set_path, source_run_path = _write_feature_source(
            feature_runs_root,
            variant_id=variant_id,
            capture_manifest=capture_manifest,
            capture_manifest_sha256=capture_manifest_sha256,
            model_policy_sha256=model_policy_sha256s[variant_id],
            fall_feature_policy_sha256=candidate_policy[
                "input_fall_feature_policy_sha256"
            ],
        )
        run, _, _ = run_fall_candidate_export(
            capture_manifest_path=capture_manifest_path,
            feature_set_path=feature_set_path,
            source_feature_run_manifest_path=source_run_path,
            policy_path=candidate_policy_path,
            runs_dir=candidate_runs_root,
            evidence_level=EvidenceLevel.E1,
        )
        prediction_path = run.reports_dir / "fall-candidate-predictions.json"
        prediction_bindings.append(
            {
                "variant_id": variant_id,
                "candidate_events": _file_reference(
                    prediction_path,
                    output_dir,
                ),
                "source_run_manifest": _file_reference(
                    run.manifest_path,
                    output_dir,
                ),
            }
        )

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["evaluation_id"] = "v1-g4-candidate-export-fixture-v0.1.0"
    bundle["candidate_generator_policy"] = _file_reference(
        candidate_policy_path,
        output_dir,
    )
    bundle["predictions"] = prediction_bindings
    bundle["limitations"] = [
        "synthetic_fixture_contains_no_person_or_device_data",
        "predictions_are_generated_by_the_real_candidate_exporter",
        "synthetic_features_do_not_measure_pose_or_event_quality",
    ]
    atomic_write_json(bundle_path, bundle)
    return bundle_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the V1 G4 feature-to-candidate export fixture"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--media-source", type=Path, default=DEFAULT_MEDIA)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    if output in {Path("/").resolve(), PROJECT_ROOT.resolve()}:
        raise ValueError("refusing to replace a broad output directory")
    if output.exists():
        if not args.force:
            raise FileExistsError(f"output already exists; use --force: {output}")
        shutil.rmtree(output)
    bundle_path = build_candidate_export_fixture(
        output,
        media_source=args.media_source.resolve(),
    )
    print(bundle_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
