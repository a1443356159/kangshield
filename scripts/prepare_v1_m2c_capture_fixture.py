#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kangshield.information.artifacts import atomic_write_json
from kangshield.information.privacy import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "public-smoke" / "v1-m2c-capture"
DEFAULT_MEDIA = (
    PROJECT_ROOT / "data" / "raw" / "public-smoke" / "v1-m2c-timing.synthetic.avi"
)


SCENARIOS = (
    {
        "scenario_id": "C01",
        "scenario": "empty_room_static",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "near",
        "occlusion": "none",
        "expected_person_presence": "absent",
        "labels": (),
    },
    {
        "scenario_id": "C02",
        "scenario": "walk_turn",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "walking", "turning"),
    },
    {
        "scenario_id": "C03",
        "scenario": "far_walk",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "far",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "walking"),
    },
    {
        "scenario_id": "C04",
        "scenario": "sit_stand",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "sit_down", "stand_up"),
    },
    {
        "scenario_id": "C05",
        "scenario": "bend_pick",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "bend_pick"),
    },
    {
        "scenario_id": "C06",
        "scenario": "bed_lie_rise",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "bed_lie", "bed_rise"),
    },
    {
        "scenario_id": "C07",
        "scenario": "furniture_partial_occlusion",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "mid",
        "occlusion": "furniture_partial",
        "expected_person_presence": "present",
        "labels": ("person_present", "furniture_occlusion"),
    },
    {
        "scenario_id": "C08",
        "scenario": "empty_room_static",
        "lighting": "night",
        "night_vision": True,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "absent",
        "labels": (),
    },
    {
        "scenario_id": "C09",
        "scenario": "walk_sit",
        "lighting": "night",
        "night_vision": True,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "walking", "sit_down"),
    },
    {
        "scenario_id": "C10",
        "scenario": "bed_lie_rise",
        "lighting": "night",
        "night_vision": True,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "bed_lie", "bed_rise"),
    },
    {
        "scenario_id": "C11",
        "scenario": "simulated_fall",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "simulated_fall"),
    },
    {
        "scenario_id": "C12",
        "scenario": "simulated_fall",
        "lighting": "night",
        "night_vision": True,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "simulated_fall"),
    },
    {
        "scenario_id": "C13",
        "scenario": "turn_180",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "turn_180"),
    },
    {
        "scenario_id": "C14",
        "scenario": "turn_360",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "turn_360"),
    },
    {
        "scenario_id": "C15",
        "scenario": "kneel_rise",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "mid",
        "occlusion": "none",
        "expected_person_presence": "present",
        "labels": ("person_present", "kneeling"),
    },
    {
        "scenario_id": "C16",
        "scenario": "multiple_people_crossing",
        "lighting": "day",
        "night_vision": False,
        "distance_band": "mid",
        "occlusion": "person_partial",
        "expected_person_presence": "present",
        "labels": ("person_present", "multiple_people", "track_crossing"),
    },
)


def _file_reference(path: Path, root: Path) -> dict[str, str | int]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
    }


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def build_capture_fixture(
    output_dir: Path,
    *,
    media_source: Path,
    project_root: Path = PROJECT_ROOT,
    include_simulated_falls: bool = False,
    freeze_first_inference: bool = False,
) -> Path:
    output_dir = Path(output_dir)
    media_source = Path(media_source)
    project_root = Path(project_root)
    if not media_source.is_file():
        raise FileNotFoundError(media_source)
    output_dir.mkdir(parents=True, exist_ok=False)

    consent_path = output_dir / "consent" / "consent.synthetic.json"
    consent_path.parent.mkdir(parents=True)
    atomic_write_json(
        consent_path,
        {"synthetic": True, "human_participant": False},
    )
    camera_capability = output_dir / "capabilities" / "c6c.synthetic.json"
    sleep_capability = output_dir / "capabilities" / "sdhy1.synthetic.json"
    atomic_write_json(
        camera_capability,
        {
            "synthetic": True,
            "model": "CS-C6c-V101-1J4WF",
            "capabilities": ["video", "audio"],
        },
    )
    atomic_write_json(
        sleep_capability,
        {
            "synthetic": True,
            "model": "CS-EP-SDHY1",
            "capabilities": ["fixture_export"],
        },
    )

    pose_policy = output_dir / "policies" / "v1-m3-pose-models.json"
    torchvision_policy = (
        output_dir / "policies" / "v1-m3-torchvision-pose-model.json"
    )
    _copy(project_root / "configs" / "v1-m3-pose-models.json", pose_policy)
    _copy(
        project_root / "configs" / "v1-m3-torchvision-pose-model.json",
        torchvision_policy,
    )
    sleep_path = output_dir / "sleep" / "sdhy1-export.synthetic.json"
    _copy(
        project_root / "tests" / "fixtures" / "sleep" / "sdhy1-export.synthetic.json",
        sleep_path,
    )

    capture_tz = timezone(timedelta(hours=8))
    capture_start = datetime(2026, 7, 22, 9, 0, tzinfo=capture_tz)
    clips = []
    scenarios = (
        SCENARIOS
        if include_simulated_falls
        else tuple(
            scenario
            for scenario in SCENARIOS
            if scenario["scenario_id"] not in {"C11", "C12"}
        )
    )
    for index, scenario in enumerate(scenarios):
        scenario_id = str(scenario["scenario_id"])
        media_path = output_dir / "camera" / f"{scenario_id}.synthetic.avi"
        _copy(media_source, media_path)
        labels = tuple(str(label) for label in scenario["labels"])
        windows = [
            {
                "label": label,
                "start_ms": 100,
                "end_ms": 2900,
                "certainty": "certain",
            }
            for label in labels
        ]
        synchronization_events = []
        if scenario_id == "C02":
            synchronization_events = [
                {
                    "event_id": "sync-start",
                    "position": "start",
                    "video_ms": 500,
                    "audio_ms": 500,
                    "annotation_method": "automatic_fixture",
                    "certainty": "certain",
                },
                {
                    "event_id": "sync-end",
                    "position": "end",
                    "video_ms": 2500,
                    "audio_ms": 2500,
                    "annotation_method": "automatic_fixture",
                    "certainty": "certain",
                },
            ]
        clips.append(
            {
                "scenario_id": scenario_id,
                "scenario": scenario["scenario"],
                "lighting": scenario["lighting"],
                "night_vision": scenario["night_vision"],
                "distance_band": scenario["distance_band"],
                "occlusion": scenario["occlusion"],
                "expected_person_presence": scenario[
                    "expected_person_presence"
                ],
                "expected_person_count": (
                    0
                    if scenario["expected_person_presence"] == "absent"
                    else 2
                    if scenario["scenario_id"] == "C16"
                    else 1
                ),
                **_file_reference(media_path, output_dir),
                "media_start_at": (
                    capture_start + timedelta(minutes=index + 1)
                ).isoformat(),
                "duration_ms": 3000,
                "audio_expected": scenario_id == "C02",
                "tracks": {
                    "video_present": True,
                    "audio_present": True,
                    "video_codec": "ffv1",
                    "audio_codec": "pcm_s16le",
                    "video_time_base": "1/10",
                    "audio_time_base": "1/8000",
                },
                "synchronization_events": synchronization_events,
                "annotation_windows": windows,
                "safety": {
                    "simulated_fall": scenario["scenario"] == "simulated_fall",
                    "safety_mat": scenario["scenario"] == "simulated_fall",
                    "spotter_present": scenario["scenario"] == "simulated_fall",
                    "area_cleared": True,
                },
                "issues": [],
            }
        )

    manifest = {
        "schema_version": "1.1",
        "template_only": False,
        "synthetic": True,
        "capture_id": "synthetic-m2c-tooling-fixture",
        "captured_start_at": capture_start.isoformat(),
        "captured_end_at": (capture_start + timedelta(minutes=30)).isoformat(),
        "operator_ref": "fixture-operator",
        "participant_ref": "fixture-no-human",
        "consent": _file_reference(consent_path, output_dir),
        "devices": [
            {
                "device_ref": "fixture-camera",
                "model": "CS-C6c-V101-1J4WF",
                "firmware_version": "synthetic",
                "capability_snapshot": _file_reference(
                    camera_capability, output_dir
                ),
                "acquisition_method": "synthetic_fixture",
            },
            {
                "device_ref": "fixture-sleep",
                "model": "CS-EP-SDHY1",
                "firmware_version": "synthetic",
                "capability_snapshot": _file_reference(
                    sleep_capability, output_dir
                ),
                "acquisition_method": "synthetic_fixture",
            },
        ],
        "camera_placement": {
            "height_cm": 180,
            "pitch_degrees": -15,
            "room_zone": "synthetic-zone",
            "distance_markers_cm": [150, 300, 500],
            "notes": ["synthetic fixture has no scene semantics"],
        },
        "held_out_protocol": {
            "partition": "held_out",
            "assignment_rule": "all_manifest_clips",
            "partition_frozen_at": (
                capture_start - timedelta(days=1)
            ).isoformat(),
            "labels_frozen_at": (
                capture_start + timedelta(minutes=40)
            ).isoformat(),
            "first_inference_at": (
                (capture_start + timedelta(minutes=50)).isoformat()
                if freeze_first_inference
                else None
            ),
            "model_policies": [
                {
                    "variant_id": "yolo26n-pose",
                    "relative_path": pose_policy.relative_to(output_dir).as_posix(),
                    "sha256": sha256_file(pose_policy),
                },
                {
                    "variant_id": "rtmpose-m-humanart",
                    "relative_path": pose_policy.relative_to(output_dir).as_posix(),
                    "sha256": sha256_file(pose_policy),
                },
                {
                    "variant_id": "torchvision-keypointrcnn",
                    "relative_path": torchvision_policy.relative_to(
                        output_dir
                    ).as_posix(),
                    "sha256": sha256_file(torchvision_policy),
                },
            ],
        },
        "clips": clips,
        "sleep_exports": [
            {
                "source_kind": "app_export",
                **_file_reference(sleep_path, output_dir),
                "requested_at": (
                    capture_start + timedelta(minutes=20)
                ).isoformat(),
                "covered_start_at": (
                    capture_start - timedelta(hours=8)
                ).isoformat(),
                "covered_end_at": capture_start.isoformat(),
                "device_timezone": "Asia/Shanghai",
                "documentation_version": "synthetic",
                "known_units": {},
                "issues": [],
            }
        ],
        "limitations": [
            "synthetic_fixture_contains_no_person_or_device_data",
            "scenario_annotations_only_exercise_contract_validation",
            "identical_media_bytes_are_allowed_only_because_synthetic_is_true",
        ],
    }
    manifest_path = output_dir / "capture-manifest.json"
    atomic_write_json(manifest_path, manifest)
    return manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the deterministic V1-M2c capture-readiness fixture"
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
    manifest_path = build_capture_fixture(
        output,
        media_source=args.media_source.resolve(),
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
