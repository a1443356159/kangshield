#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kangshield.information.artifacts import atomic_write_json
from kangshield.information.contracts import (
    EvidenceLevel,
    RunManifest,
    RunStatus,
    SourceType,
)
from kangshield.information.m2c_capture import assess_m2c_capture
from kangshield.information.privacy import sha256_file

try:
    from scripts.prepare_v1_m2c_capture_fixture import build_capture_fixture
except ModuleNotFoundError:  # Direct script execution puts scripts/ on sys.path.
    from prepare_v1_m2c_capture_fixture import build_capture_fixture


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "public-smoke"
    / "v1-g4-event-evaluation"
)
DEFAULT_MEDIA = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "public-smoke"
    / "v1-m2c-timing.synthetic.avi"
)
ACTION_WINDOWS = {
    "C05": {"label": "bend_pick", "start_ms": 825, "end_ms": 1825},
    "C06": {"label": "bed_lie", "start_ms": 725, "end_ms": 2425},
    "C10": {"label": "bed_lie", "start_ms": 625, "end_ms": 2325},
    "C11": {"label": "simulated_fall", "start_ms": 950, "end_ms": 2025},
    "C12": {"label": "simulated_fall", "start_ms": 950, "end_ms": 2175},
}

ANNOTATOR_OFFSETS = {
    "annotation-a": {
        "C05": (-25, -25),
        "C06": (-25, -25),
        "C10": (-25, -25),
        "C11": (-50, -25),
        "C12": (50, 25),
    },
    "annotation-b": {
        "C05": (25, 25),
        "C06": (25, 25),
        "C10": (25, 25),
        "C11": (50, 25),
        "C12": (-50, -25),
    },
}

CANDIDATES = {
    "yolo26n-pose": {
        "C05": [("yolo-fp-bend", 1200, 1700, 1450)],
        "C11": [("yolo-tp-day", 900, 1400, 1150)],
    },
    "rtmpose-m-humanart": {
        "C06": [("rtmpose-fp-bed", 1250, 1750, 1500)],
        "C11": [("rtmpose-tp-day", 850, 1300, 1050)],
        "C12": [("rtmpose-tp-night", 1050, 1500, 1250)],
    },
    "torchvision-keypointrcnn": {
        "C05": [("torchvision-fp-bend", 1100, 1600, 1350)],
        "C10": [("torchvision-fp-bed", 1200, 1700, 1450)],
        "C11": [("torchvision-tp-day", 800, 1250, 1000)],
        "C12": [("torchvision-tp-night", 900, 1350, 1100)],
    },
}

MODEL_POLICY_SHA256S = {
    "yolo26n-pose": (
        "b5b4bcbf908221c7057794962c2cfd37a2d728c6f6b98695efbe2be73d1deeed"
    ),
    "rtmpose-m-humanart": (
        "b5b4bcbf908221c7057794962c2cfd37a2d728c6f6b98695efbe2be73d1deeed"
    ),
    "torchvision-keypointrcnn": (
        "921883358f6f2b23f0760d9f9612213adb044f54c9ac3e6ae24c8225e186f8db"
    ),
}


def _file_reference(path: Path, root: Path) -> dict[str, str | int]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
    }


def _annotation_clips(
    capture_clips: list[dict],
    *,
    offsets: dict[str, tuple[int, int]] | None,
) -> list[dict]:
    clips = []
    for clip in capture_clips:
        scenario_id = str(clip["scenario_id"])
        windows = []
        if scenario_id in ACTION_WINDOWS:
            window = ACTION_WINDOWS[scenario_id]
            start_offset, end_offset = (
                offsets[scenario_id] if offsets is not None else (0, 0)
            )
            windows.append(
                {
                    "label": window["label"],
                    "start_ms": int(window["start_ms"]) + start_offset,
                    "end_ms": int(window["end_ms"]) + end_offset,
                    "certainty": "certain",
                }
            )
        clips.append(
            {
                "scenario_id": scenario_id,
                "duration_ms": int(clip["duration_ms"]),
                "windows": windows,
            }
        )
    return clips


def _prediction_clips(capture_clips: list[dict], variant_id: str) -> list[dict]:
    by_scenario = CANDIDATES[variant_id]
    clips = []
    for clip in capture_clips:
        scenario_id = str(clip["scenario_id"])
        candidates = [
            {
                "candidate_id": candidate_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "detected_at_ms": detected_at_ms,
            }
            for candidate_id, start_ms, end_ms, detected_at_ms in by_scenario.get(
                scenario_id,
                [],
            )
        ]
        clips.append(
            {
                "scenario_id": scenario_id,
                "duration_ms": int(clip["duration_ms"]),
                "candidates": candidates,
            }
        )
    return clips


def build_event_evaluation_fixture(
    output_dir: Path,
    *,
    media_source: Path,
    project_root: Path = PROJECT_ROOT,
) -> Path:
    output_dir = Path(output_dir)
    media_source = Path(media_source)
    project_root = Path(project_root)
    if not media_source.is_file():
        raise FileNotFoundError(media_source)
    output_dir.mkdir(parents=True, exist_ok=False)

    capture_manifest_path = build_capture_fixture(
        output_dir / "capture",
        media_source=media_source,
        project_root=project_root,
        include_simulated_falls=True,
        freeze_first_inference=True,
    )
    capture_manifest = json.loads(
        capture_manifest_path.read_text(encoding="utf-8")
    )
    capture_manifest_sha256 = sha256_file(capture_manifest_path)
    capture_assessment = assess_m2c_capture(
        capture_manifest_path,
        policy_path=project_root / "configs" / "v1-m2c-capture-policy.json",
        evidence_level=EvidenceLevel.E1,
        source_type=SourceType.FIXTURE,
    )
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    capture_readiness_path = evidence_dir / "m2c-capture-readiness.json"
    atomic_write_json(capture_readiness_path, capture_assessment.report)

    fixture_tz = timezone(timedelta(hours=8))
    capture_run = RunManifest(
        run_id="fixture-m2c-capture-assessment",
        stage="v1-m2c-capture-readiness",
        status=RunStatus.COMPLETED,
        evidence_level=EvidenceLevel.E1,
        started_at=datetime(2026, 7, 22, 9, 45, tzinfo=fixture_tz),
        finished_at=datetime(2026, 7, 22, 9, 46, tzinfo=fixture_tz),
        code_version="fixture-v0.1.0",
        code_dirty=False,
        configuration={
            "capture_manifest_sha256": capture_manifest_sha256,
            "capture_readiness_report_sha256": sha256_file(
                capture_readiness_path
            ),
        },
        artifacts=["m2c-capture-readiness.json"],
    )
    capture_run_path = evidence_dir / "m2c-capture-run-manifest.json"
    atomic_write_json(capture_run_path, capture_run)

    candidate_policy_path = output_dir / "policies" / "candidate-policy.json"
    atomic_write_json(
        candidate_policy_path,
        {
            "schema_version": "1.0",
            "policy_id": "synthetic-fixed-event-candidates-v0.1.0",
            "fixture": True,
            "target_event_label": "simulated_fall",
            "input_fall_feature_policy_sha256": sha256_file(
                project_root / "configs" / "v1-g4-fall-features.json"
            ),
            "candidate_representation": "deduplicated_event_episode",
            "decision_logic_summary": (
                "Fixed synthetic candidate episodes for scorer contract tests only"
            ),
            "limitations": [
                "no_model_inference",
                "no_fall_decision_rule_is_claimed",
            ],
        },
    )
    candidate_policy_sha256 = sha256_file(candidate_policy_path)

    annotations_dir = output_dir / "annotations"
    annotations_dir.mkdir(parents=True)
    annotation_paths = []
    for index, annotation_id in enumerate(sorted(ANNOTATOR_OFFSETS), start=1):
        annotation_path = annotations_dir / f"{annotation_id}.json"
        atomic_write_json(
            annotation_path,
            {
                "schema_version": "1.0",
                "annotation_set_id": annotation_id,
                "annotator_ref": f"fixture-independent-annotator-{index}",
                "independent": True,
                "capture_manifest_sha256": capture_manifest_sha256,
                "frozen_at": datetime(
                    2026,
                    7,
                    22,
                    9,
                    34 + index,
                    tzinfo=fixture_tz,
                ).isoformat(),
                "clips": _annotation_clips(
                    capture_manifest["clips"],
                    offsets=ANNOTATOR_OFFSETS[annotation_id],
                ),
            },
        )
        annotation_paths.append(annotation_path)

    adjudication_path = annotations_dir / "adjudication.json"
    atomic_write_json(
        adjudication_path,
        {
            "schema_version": "1.0",
            "adjudication_id": "fixture-adjudication-v0.1.0",
            "adjudicator_ref": "fixture-adjudicator",
            "capture_manifest_sha256": capture_manifest_sha256,
            "input_annotation_sha256s": sorted(
                sha256_file(path) for path in annotation_paths
            ),
            "frozen_at": datetime(
                2026,
                7,
                22,
                9,
                40,
                tzinfo=fixture_tz,
            ).isoformat(),
            "all_disagreements_resolved": True,
            "resolved_disagreement_count": len(ACTION_WINDOWS),
            "clips": _annotation_clips(
                capture_manifest["clips"],
                offsets=None,
            ),
        },
    )

    prediction_bindings = []
    prediction_dir = output_dir / "predictions"
    prediction_dir.mkdir(parents=True)
    runs_dir = output_dir / "source-runs"
    runs_dir.mkdir(parents=True)
    generated_at = datetime(2026, 7, 22, 10, 1, tzinfo=fixture_tz)
    for variant_id in sorted(CANDIDATES):
        source_run_id = f"fixture-candidates-{variant_id}"
        prediction_path = prediction_dir / f"{variant_id}.json"
        atomic_write_json(
            prediction_path,
            {
                "schema_version": "1.0",
                "prediction_set_id": f"fixture-predictions-{variant_id}",
                "variant_id": variant_id,
                "source_run_id": source_run_id,
                "capture_manifest_sha256": capture_manifest_sha256,
                "model_policy_sha256": MODEL_POLICY_SHA256S[variant_id],
                "fall_feature_policy_sha256": sha256_file(
                    project_root / "configs" / "v1-g4-fall-features.json"
                ),
                "candidate_generator_policy_sha256": candidate_policy_sha256,
                "generated_at": generated_at.isoformat(),
                "clips": _prediction_clips(
                    capture_manifest["clips"],
                    variant_id,
                ),
            },
        )
        source_run = RunManifest(
            run_id=source_run_id,
            stage="v1-g4-fall-event-candidates",
            status=RunStatus.COMPLETED,
            evidence_level=EvidenceLevel.E1,
            started_at=datetime(2026, 7, 22, 10, 0, tzinfo=fixture_tz),
            finished_at=datetime(2026, 7, 22, 10, 2, tzinfo=fixture_tz),
            code_version="fixture-v0.1.0",
            code_dirty=False,
            configuration={
                "variant_id": variant_id,
                "capture_manifest_sha256": capture_manifest_sha256,
                "model_policy_sha256": MODEL_POLICY_SHA256S[variant_id],
                "fall_feature_policy_sha256": sha256_file(
                    project_root / "configs" / "v1-g4-fall-features.json"
                ),
                "candidate_generator_policy_sha256": candidate_policy_sha256,
                "candidate_events_sha256": sha256_file(prediction_path),
            },
            artifacts=[prediction_path.name],
        )
        source_run_path = runs_dir / f"{variant_id}.manifest.json"
        atomic_write_json(source_run_path, source_run)
        prediction_bindings.append(
            {
                "variant_id": variant_id,
                "candidate_events": _file_reference(
                    prediction_path,
                    output_dir,
                ),
                "source_run_manifest": _file_reference(
                    source_run_path,
                    output_dir,
                ),
            }
        )

    bundle_path = output_dir / "event-evaluation-bundle.json"
    atomic_write_json(
        bundle_path,
        {
            "schema_version": "1.0",
            "evaluation_id": "v1-g4-event-evaluation-fixture-v0.1.0",
            "fixture": True,
            "capture_manifest": _file_reference(
                capture_manifest_path,
                output_dir,
            ),
            "capture_readiness_report": _file_reference(
                capture_readiness_path,
                output_dir,
            ),
            "capture_assessment_run_manifest": _file_reference(
                capture_run_path,
                output_dir,
            ),
            "candidate_generator_policy": _file_reference(
                candidate_policy_path,
                output_dir,
            ),
            "annotation_sets": [
                _file_reference(path, output_dir) for path in annotation_paths
            ],
            "adjudication": _file_reference(adjudication_path, output_dir),
            "predictions": prediction_bindings,
            "limitations": [
                "synthetic_fixture_contains_no_person_or_device_data",
                "candidate_events_are_fixed_and_do_not_measure_model_quality",
            ],
        },
    )
    return bundle_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the deterministic V1 G4 event-evaluation fixture"
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
    bundle_path = build_event_evaluation_fixture(
        output,
        media_source=args.media_source.resolve(),
    )
    print(bundle_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
