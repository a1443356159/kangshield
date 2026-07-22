from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .artifacts import atomic_write_json
from .contracts import EvidenceLevel, FallAdlVideoCase
from .dataset_preparation import download_and_verify, sha256_file, verify_file


EXPECTED_DATASET_ID = "caucafall-v4"
EXPECTED_DATASET_VERSION = 4
EXPECTED_DATASET_DOI = "10.17632/7w7fccy7ky.4"
EXPECTED_DATASET_LICENSE = "CC-BY-4.0"
EXPECTED_DOWNLOAD_PREFIX = (
    "https://data.mendeley.com/public-files/datasets/7w7fccy7ky/files/"
)
ACTIVITY_SOURCE_NAMES = {
    "pick_up_object": "Pick up object",
    "sit_down": "Sit down",
    "kneel": "Kneel",
    "walk": "Walk",
}
ILLUMINATION_LUX = {
    "natural_210_lux": 210,
    "zero_lux_ir": 0,
    "artificial_130_lux": 130,
}


def _relative_source_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("fall ADL source path must stay inside the download directory")
    return path


def _validate_source_file(item: dict[str, Any]) -> None:
    required = ("path", "url", "file_id", "byte_size", "sha256")
    if any(key not in item for key in required):
        raise ValueError("fall ADL source file metadata is incomplete")
    _relative_source_path(str(item["path"]))
    if not isinstance(item["byte_size"], int) or item["byte_size"] <= 0:
        raise ValueError("fall ADL source byte size must be positive")
    digest = item["sha256"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("fall ADL source SHA-256 is invalid")
    file_id = item["file_id"]
    expected_url = f"{EXPECTED_DOWNLOAD_PREFIX}{file_id}/file_downloaded"
    if item["url"] != expected_url:
        raise ValueError("fall ADL source URL does not match its Mendeley file id")


def load_fall_adl_source_manifest(path: Path) -> dict[str, Any]:
    path = Path(path)
    with path.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("schema_version") != "1.0":
        raise ValueError("unsupported fall ADL source manifest schema")
    if manifest.get("evidence_level") != EvidenceLevel.E1.value:
        raise ValueError("public fall ADL evidence must remain E1")
    if not isinstance(manifest.get("suite_id"), str) or not manifest["suite_id"]:
        raise ValueError("fall ADL source manifest lacks a suite id")

    dataset = manifest.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("fall ADL source manifest lacks dataset metadata")
    expected_dataset = {
        "dataset_id": EXPECTED_DATASET_ID,
        "version": EXPECTED_DATASET_VERSION,
        "doi": EXPECTED_DATASET_DOI,
        "license": EXPECTED_DATASET_LICENSE,
        "license_acceptance_required": False,
    }
    for key, expected in expected_dataset.items():
        if dataset.get(key) != expected:
            raise ValueError(f"fall ADL dataset {key} is not the frozen value")

    selection = manifest.get("selection")
    cases = manifest.get("cases")
    if not isinstance(selection, dict) or not isinstance(cases, list) or not cases:
        raise ValueError("fall ADL source manifest lacks selection or cases")
    subjects = selection.get("subjects")
    activities = selection.get("activities")
    illuminations = selection.get("illumination_groups")
    if not all(isinstance(value, list) and value for value in (subjects, activities, illuminations)):
        raise ValueError("fall ADL selection dimensions must be non-empty lists")
    if set(activities) != set(ACTIVITY_SOURCE_NAMES):
        raise ValueError("fall ADL selection must retain the four frozen activities")
    if set(illuminations) != set(ILLUMINATION_LUX):
        raise ValueError("fall ADL selection must retain the three light groups")
    if selection.get("expected_person_presence") != "present":
        raise ValueError("fall ADL selected clips must expect a present person")
    if selection.get("ground_truth_scope") != "dataset_action_level_no_fall":
        raise ValueError("fall ADL ground truth must remain action-level no-fall")
    if len(cases) != len(subjects) * len(activities):
        raise ValueError("fall ADL cases must form a complete subject/activity matrix")

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    seen_files: set[str] = set()
    matrix: set[tuple[str, str]] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("fall ADL case must be an object")
        _validate_source_file(case)
        case_id = case.get("case_id")
        subject = case.get("subject_ref")
        activity = case.get("activity")
        illumination = case.get("illumination_group")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("fall ADL case id is invalid")
        if subject not in subjects or activity not in activities:
            raise ValueError("fall ADL case is outside the frozen selection")
        if illumination not in illuminations:
            raise ValueError("fall ADL case illumination is outside the selection")
        if case.get("source_activity") != ACTIVITY_SOURCE_NAMES[activity]:
            raise ValueError("fall ADL source activity does not match its normalized name")
        if case.get("approx_lux") != ILLUMINATION_LUX[illumination]:
            raise ValueError("fall ADL illumination and lux metadata disagree")
        if not str(case.get("filename", "")).lower().endswith(".avi"):
            raise ValueError("fall ADL selected source must be an AVI video")
        if case_id in seen_ids or case["path"] in seen_paths or case["file_id"] in seen_files:
            raise ValueError("fall ADL source manifest contains duplicate identifiers")
        key = (subject, activity)
        if key in matrix:
            raise ValueError("fall ADL source manifest repeats a subject/activity pair")
        seen_ids.add(case_id)
        seen_paths.add(case["path"])
        seen_files.add(case["file_id"])
        matrix.add(key)
    expected_matrix = {(subject, activity) for subject in subjects for activity in activities}
    if matrix != expected_matrix:
        raise ValueError("fall ADL source manifest has an incomplete selection matrix")
    if {case["subject_ref"] for case in cases} != set(subjects):
        raise ValueError("fall ADL source subjects disagree with selection")
    if {case["illumination_group"] for case in cases} != set(illuminations):
        raise ValueError("fall ADL source light groups disagree with selection")

    provenance = manifest.get("provenance_files")
    if not isinstance(provenance, list) or not provenance:
        raise ValueError("fall ADL source manifest lacks provenance files")
    for item in provenance:
        if not isinstance(item, dict):
            raise ValueError("fall ADL provenance file must be an object")
        _validate_source_file(item)
    return manifest


def _copy_verified(source: Path, target: Path, *, byte_size: int, sha256: str) -> None:
    source = Path(source)
    target = Path(target)
    verify_file(source, byte_size=byte_size, sha256=sha256)
    if target.is_file():
        verify_file(target, byte_size=byte_size, sha256=sha256)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.partial")
    try:
        with source.open("rb") as input_stream, partial.open("wb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
        verify_file(partial, byte_size=byte_size, sha256=sha256)
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _video_metadata(path: Path) -> dict[str, int | float | str]:
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("OpenCV is required to validate fall ADL videos") from error
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError("fall ADL video cannot be decoded")
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fourcc_value = int(capture.get(cv2.CAP_PROP_FOURCC))
    finally:
        capture.release()
    if width <= 0 or height <= 0 or fps <= 0 or frame_count <= 0:
        raise ValueError("fall ADL video metadata is incomplete")
    fourcc = "".join(chr((fourcc_value >> 8 * index) & 0xFF) for index in range(4))
    return {
        "width": width,
        "height": height,
        "fps": round(fps, 6),
        "frame_count": frame_count,
        "duration_ms": round(frame_count * 1000.0 / fps),
        "fourcc": fourcc,
    }


def prepare_v1_g4_caucafall_data(
    *,
    manifest_path: Path,
    download_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    download_dir = Path(download_dir)
    output_dir = Path(output_dir)
    manifest = load_fall_adl_source_manifest(manifest_path)
    dataset = manifest["dataset"]
    source_lock: list[dict[str, Any]] = []

    for item in [*manifest["provenance_files"], *manifest["cases"]]:
        relative = _relative_source_path(item["path"])
        target = download_dir / relative
        download_and_verify(
            item["url"],
            target,
            byte_size=item["byte_size"],
            sha256=item["sha256"],
        )
        source_lock.append(
            {
                "role": item.get("role", "video_case"),
                "file_id": item["file_id"],
                "path": relative.as_posix(),
                "byte_size": item["byte_size"],
                "sha256": item["sha256"],
            }
        )

    prepared_cases: list[FallAdlVideoCase] = []
    processed_files: list[dict[str, Any]] = []
    for item in manifest["cases"]:
        source_path = download_dir / _relative_source_path(item["path"])
        video_path = output_dir / "video" / f"{item['case_id']}.avi"
        _copy_verified(
            source_path,
            video_path,
            byte_size=item["byte_size"],
            sha256=item["sha256"],
        )
        metadata = _video_metadata(video_path)
        processed_files.append(
            {
                "kind": "unaltered_source_video",
                "case_id": item["case_id"],
                "path": video_path.relative_to(output_dir).as_posix(),
                "byte_size": video_path.stat().st_size,
                "sha256": sha256_file(video_path),
                "technical_metadata": metadata,
            }
        )
        prepared_cases.append(
            FallAdlVideoCase(
                case_id=item["case_id"],
                evidence_level=EvidenceLevel.E1,
                dataset_id=dataset["dataset_id"],
                dataset_version=dataset["version"],
                video_path=video_path.relative_to(output_dir).as_posix(),
                video_sha256=item["sha256"],
                video_byte_size=item["byte_size"],
                source_file_id=item["file_id"],
                subject_ref=item["subject_ref"],
                activity=item["activity"],
                illumination_group=item["illumination_group"],
                approx_lux=item["approx_lux"],
                expected_person_presence="present",
                ground_truth_scope="dataset_action_level_no_fall",
                limitations=[
                    "action_level_no_fall_label_only",
                    "no_event_timestamp_or_pose_ground_truth",
                    "public_dataset_subject_not_target_elder",
                    "not_target_c6c_camera",
                ],
            )
        )

    source_manifest_digest = sha256_file(manifest_path)
    suite = {
        "schema_version": "1.0",
        "suite_id": manifest["suite_id"],
        "evidence_level": EvidenceLevel.E1.value,
        "source_manifest_sha256": source_manifest_digest,
        "dataset": {
            "dataset_id": dataset["dataset_id"],
            "version": dataset["version"],
            "doi": dataset["doi"],
            "homepage": dataset["homepage"],
            "license": dataset["license"],
            "license_url": dataset["license_url"],
            "attribution": dataset["attribution"],
        },
        "case_count": len(prepared_cases),
        "cases": [case.model_dump(mode="json") for case in prepared_cases],
        "limitations": manifest["limitations"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    suite_path = output_dir / "fall-adl-cases.json"
    atomic_write_json(suite_path, suite)
    processed_files.append(
        {
            "kind": "fall_adl_cases",
            "path": suite_path.relative_to(output_dir).as_posix(),
            "byte_size": suite_path.stat().st_size,
            "sha256": sha256_file(suite_path),
        }
    )
    lock = {
        "schema_version": "1.0",
        "suite_id": manifest["suite_id"],
        "source_manifest_sha256": source_manifest_digest,
        "source_files": sorted(source_lock, key=lambda item: item["path"]),
        "processed_files": sorted(processed_files, key=lambda item: item["path"]),
    }
    lock_path = output_dir / "dataset-lock.json"
    atomic_write_json(lock_path, lock)
    return {
        "suite_id": manifest["suite_id"],
        "fall_adl_cases": str(suite_path),
        "dataset_lock": str(lock_path),
        "case_count": len(prepared_cases),
        "source_file_count": len(source_lock),
        "processed_file_count": len(processed_files),
    }
