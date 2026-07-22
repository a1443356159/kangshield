from __future__ import annotations

import csv
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .artifacts import atomic_write_json
from .contracts import EvidenceLevel, StaticHomeImageCase, StaticPersonBox
from .dataset_preparation import download_and_verify, sha256_file, verify_file


EXPECTED_DATASET_ID = "open-images-v7"
EXPECTED_DATASET_VERSION = 7
EXPECTED_DATASET_SPLIT = "validation"
EXPECTED_DATASET_HOMEPAGE = (
    "https://storage.googleapis.com/openimages/web/index.html"
)
EXPECTED_ANNOTATION_LICENSE = "CC-BY-4.0"
EXPECTED_ANNOTATION_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
EXPECTED_ANNOTATION_ATTRIBUTION = "Open Images annotations by Google LLC"
EXPECTED_IMAGE_LICENSE = "CC-BY-2.0"
EXPECTED_IMAGE_LICENSE_URL = "https://creativecommons.org/licenses/by/2.0/"
EXPECTED_IMAGE_URL_PREFIX = (
    "https://open-images-dataset.s3.amazonaws.com/validation/"
)
EXPECTED_SUITE_ID = "v1-g4-openimages-static-home-negative-12"
PERSON_MID = "/m/01g317"
CONTEXT_CLASSES = {
    "/m/03ssj5": "Bed",
    "/m/01mzpv": "Chair",
    "/m/02crq1": "Couch",
    "/m/03m3pdh": "Sofa bed",
    "/m/026qbn5": "Studio couch",
    "/m/01yrx": "Cat",
    "/m/0bt9lr": "Dog",
}
EXPECTED_PROVENANCE_URLS = {
    "validation_image_metadata": (
        "https://storage.googleapis.com/openimages/2018_04/validation/"
        "validation-images-with-rotation.csv"
    ),
    "validation_human_image_labels": (
        "https://storage.googleapis.com/openimages/v5/"
        "validation-annotations-human-imagelabels-boxable.csv"
    ),
    "validation_bounding_boxes": (
        "https://storage.googleapis.com/openimages/v5/"
        "validation-annotations-bbox.csv"
    ),
    "boxable_class_descriptions": (
        "https://storage.googleapis.com/openimages/v7/"
        "oidv7-class-descriptions-boxable.csv"
    ),
}
EXPECTED_SCENARIO_COUNTS = {
    "person_absent_furniture": 4,
    "person_absent_pet": 4,
    "multi_person_indoor": 4,
}


def _relative_source_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("static home source path must stay inside its data root")
    return path


def _validate_download(
    item: dict[str, Any], *, expected_url: str | None = None
) -> None:
    required = ("path", "url", "byte_size", "sha256")
    if any(key not in item for key in required):
        raise ValueError("static home source file metadata is incomplete")
    _relative_source_path(str(item["path"]))
    if expected_url is not None and item["url"] != expected_url:
        raise ValueError("static home source URL is not the frozen official URL")
    if not isinstance(item["byte_size"], int) or item["byte_size"] <= 0:
        raise ValueError("static home source byte size must be positive")
    digest = item["sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("static home source SHA-256 is invalid")


def _validate_case(item: dict[str, Any]) -> None:
    required = (
        "case_id",
        "scenario",
        "image_id",
        "width",
        "height",
        "expected_person_label_confidence",
        "expected_person_box_count",
        "required_positive_labels",
        "license",
        "license_url",
        "original_landing_url",
        "author_profile_url",
        "author",
        "title",
        "rotation_degrees",
        "license_page_audit",
        "manual_review",
    )
    if any(key not in item for key in required):
        raise ValueError("static home case metadata is incomplete")
    _validate_download(item)
    image_id = item["image_id"]
    if not isinstance(image_id, str) or not re.fullmatch(r"[0-9a-f]{16}", image_id):
        raise ValueError("Open Images id must be a 16-character lowercase hex id")
    if item["url"] != f"{EXPECTED_IMAGE_URL_PREFIX}{image_id}.jpg":
        raise ValueError("static home image URL does not match its image id")
    if item["path"] != f"openimages-v7/validation/{image_id}.jpg":
        raise ValueError("static home image path does not match its image id")
    if not isinstance(item["width"], int) or item["width"] <= 0:
        raise ValueError("static home image width must be positive")
    if not isinstance(item["height"], int) or item["height"] <= 0:
        raise ValueError("static home image height must be positive")
    scenario = item["scenario"]
    if scenario not in EXPECTED_SCENARIO_COUNTS:
        raise ValueError("static home scenario is not frozen")
    person_confidence = item["expected_person_label_confidence"]
    person_box_count = item["expected_person_box_count"]
    if scenario.startswith("person_absent"):
        if person_confidence != 0 or person_box_count != 0:
            raise ValueError("person-absent case must have a verified negative label")
    elif (
        person_confidence != 1
        or not isinstance(person_box_count, int)
        or person_box_count < 2
    ):
        raise ValueError("multi-person case must have a positive label and two boxes")

    labels = item["required_positive_labels"]
    if not isinstance(labels, list) or not labels:
        raise ValueError("static home case requires positive context labels")
    mids: set[str] = set()
    names: set[str] = set()
    for label in labels:
        if not isinstance(label, dict):
            raise ValueError("static home required label must be an object")
        mid = label.get("mid")
        name = label.get("name")
        if mid not in CONTEXT_CLASSES or CONTEXT_CLASSES[mid] != name:
            raise ValueError("static home context label is not a frozen class")
        if mid in mids:
            raise ValueError("static home case repeats a context label")
        mids.add(mid)
        names.add(name)
    if scenario == "person_absent_furniture" and not names.intersection(
        {"Bed", "Chair", "Couch", "Sofa bed", "Studio couch"}
    ):
        raise ValueError("furniture case requires a positive furniture label")
    if scenario == "person_absent_pet" and not names.intersection({"Cat", "Dog"}):
        raise ValueError("pet case requires a positive Cat or Dog label")
    if scenario == "multi_person_indoor" and not names.intersection(
        {"Bed", "Chair", "Couch", "Sofa bed", "Studio couch"}
    ):
        raise ValueError("multi-person indoor case requires an indoor context label")

    if item["license"] != EXPECTED_IMAGE_LICENSE:
        raise ValueError("static home image license must remain CC-BY-2.0")
    if item["license_url"] != EXPECTED_IMAGE_LICENSE_URL:
        raise ValueError("static home image license URL is not frozen")
    for key in ("original_landing_url", "author_profile_url"):
        if not isinstance(item[key], str) or not item[key].startswith("https://"):
            raise ValueError(f"static home {key} must be an HTTPS URL")
    for key in ("author", "title"):
        if not isinstance(item[key], str) or not item[key].strip():
            raise ValueError(f"static home attribution {key} is missing")
    if item["rotation_degrees"] != 0:
        raise ValueError("static home suite only accepts zero-rotation images")

    license_audit = item["license_page_audit"]
    if not isinstance(license_audit, dict):
        raise ValueError("static home case lacks a license-page audit")
    expected_audit = {
        "status": "passed",
        "observed_license_url": EXPECTED_IMAGE_LICENSE_URL,
        "method": "original_landing_page_html_exact_license_link",
    }
    if any(license_audit.get(key) != value for key, value in expected_audit.items()):
        raise ValueError("static home license-page audit is not fail-closed")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(license_audit.get("checked_on", ""))):
        raise ValueError("static home license-page audit date is invalid")

    manual_review = item["manual_review"]
    if not isinstance(manual_review, dict):
        raise ValueError("static home case lacks manual visual review")
    if manual_review.get("status") != "passed":
        raise ValueError("static home case did not pass manual visual review")
    if manual_review.get("method") != "single_reviewer_visual_screening":
        raise ValueError("static home manual review method is not frozen")
    findings = manual_review.get("findings")
    if not isinstance(findings, list) or not all(
        isinstance(value, str) and value for value in findings
    ):
        raise ValueError("static home manual review findings are invalid")
    required_finding = (
        "no_visible_person"
        if scenario.startswith("person_absent")
        else "multiple_visible_people"
    )
    if required_finding not in findings:
        raise ValueError("static home manual review contradicts the scenario")


def load_static_home_source_manifest(path: Path) -> dict[str, Any]:
    path = Path(path)
    with path.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("schema_version") != "1.0":
        raise ValueError("unsupported static home source manifest schema")
    if manifest.get("suite_id") != EXPECTED_SUITE_ID:
        raise ValueError("static home suite id is not frozen")
    if manifest.get("evidence_level") != EvidenceLevel.E1.value:
        raise ValueError("public static home evidence must remain E1")
    dataset = manifest.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("static home source manifest lacks dataset metadata")
    expected_dataset = {
        "dataset_id": EXPECTED_DATASET_ID,
        "version": EXPECTED_DATASET_VERSION,
        "split": EXPECTED_DATASET_SPLIT,
        "homepage": EXPECTED_DATASET_HOMEPAGE,
        "annotation_license": EXPECTED_ANNOTATION_LICENSE,
        "annotation_license_url": EXPECTED_ANNOTATION_LICENSE_URL,
        "annotation_attribution": EXPECTED_ANNOTATION_ATTRIBUTION,
        "required_image_license": EXPECTED_IMAGE_LICENSE,
        "required_image_license_url": EXPECTED_IMAGE_LICENSE_URL,
        "license_acceptance_required": False,
    }
    for key, value in expected_dataset.items():
        if dataset.get(key) != value:
            raise ValueError(f"static home dataset {key} is not frozen")

    selection = manifest.get("selection")
    expected_selection = {
        "scenario_case_counts": EXPECTED_SCENARIO_COUNTS,
        "person_label_mid": PERSON_MID,
        "person_label_name": "Person",
        "human_label_source": "verification",
        "matching_iou_threshold": 0.5,
        "manual_review_required": True,
    }
    if not isinstance(selection, dict) or any(
        selection.get(key) != value for key, value in expected_selection.items()
    ):
        raise ValueError("static home selection policy is not frozen")

    provenance = manifest.get("provenance_files")
    if not isinstance(provenance, list) or len(provenance) != len(
        EXPECTED_PROVENANCE_URLS
    ):
        raise ValueError("static home provenance file set is incomplete")
    roles: set[str] = set()
    paths: set[str] = set()
    for item in provenance:
        if not isinstance(item, dict):
            raise ValueError("static home provenance file must be an object")
        role = item.get("role")
        if role not in EXPECTED_PROVENANCE_URLS or role in roles:
            raise ValueError("static home provenance role is invalid or duplicated")
        _validate_download(item, expected_url=EXPECTED_PROVENANCE_URLS[role])
        if item["path"] in paths:
            raise ValueError("static home provenance path is duplicated")
        roles.add(role)
        paths.add(item["path"])
    if roles != set(EXPECTED_PROVENANCE_URLS):
        raise ValueError("static home provenance roles are incomplete")

    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != 12:
        raise ValueError("static home source manifest must contain 12 cases")
    case_ids: set[str] = set()
    image_ids: set[str] = set()
    image_paths: set[str] = set()
    image_digests: set[str] = set()
    scenarios: Counter[str] = Counter()
    for item in cases:
        if not isinstance(item, dict):
            raise ValueError("static home case must be an object")
        _validate_case(item)
        if item["case_id"] in case_ids or item["image_id"] in image_ids:
            raise ValueError("static home cases contain duplicate identifiers")
        if item["path"] in image_paths or item["sha256"] in image_digests:
            raise ValueError("static home cases contain duplicate image content")
        case_ids.add(item["case_id"])
        image_ids.add(item["image_id"])
        image_paths.add(item["path"])
        image_digests.add(item["sha256"])
        scenarios[item["scenario"]] += 1
    if dict(scenarios) != EXPECTED_SCENARIO_COUNTS:
        raise ValueError("static home source manifest scenario matrix is incomplete")
    return manifest


def _copy_verified(source: Path, target: Path, *, byte_size: int, sha256: str) -> None:
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


def _image_dimensions(path: Path) -> tuple[int, int]:
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError(
            "OpenCV is required to validate static home images"
        ) from error
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3:
        raise ValueError("static home image cannot be decoded")
    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        raise ValueError("static home image dimensions are invalid")
    return width, height


def _load_selected_rows(
    *,
    manifest: dict[str, Any],
    download_dir: Path,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, dict[str, str]]],
    dict[str, list[dict[str, str]]],
]:
    by_role = {
        item["role"]: download_dir / _relative_source_path(item["path"])
        for item in manifest["provenance_files"]
    }
    selected = {item["image_id"] for item in manifest["cases"]}

    class_names: dict[str, str] = {}
    with by_role["boxable_class_descriptions"].open(
        newline="", encoding="utf-8"
    ) as stream:
        for row in csv.reader(stream):
            if len(row) == 2:
                class_names[row[0]] = row[1]
    expected_names = {PERSON_MID: "Person", **CONTEXT_CLASSES}
    if any(class_names.get(mid) != name for mid, name in expected_names.items()):
        raise ValueError("Open Images class descriptions drifted")

    metadata: dict[str, dict[str, str]] = {}
    with by_role["validation_image_metadata"].open(
        newline="", encoding="utf-8"
    ) as stream:
        for row in csv.DictReader(stream):
            if row.get("ImageID") in selected:
                metadata[row["ImageID"]] = row
    if set(metadata) != selected:
        raise ValueError("Open Images metadata lacks a selected image")

    labels: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    relevant_mids = {PERSON_MID, *CONTEXT_CLASSES}
    with by_role["validation_human_image_labels"].open(
        newline="", encoding="utf-8"
    ) as stream:
        for row in csv.DictReader(stream):
            image_id = row.get("ImageID")
            mid = row.get("LabelName")
            if image_id in selected and mid in relevant_mids:
                if mid in labels[image_id]:
                    raise ValueError("Open Images image label is duplicated")
                labels[image_id][mid] = row

    boxes: dict[str, list[dict[str, str]]] = defaultdict(list)
    with by_role["validation_bounding_boxes"].open(
        newline="", encoding="utf-8"
    ) as stream:
        for row in csv.DictReader(stream):
            image_id = row.get("ImageID")
            if image_id in selected and row.get("LabelName") == PERSON_MID:
                boxes[image_id].append(row)
    return metadata, labels, boxes


def _parse_person_boxes(rows: list[dict[str, str]]) -> list[StaticPersonBox]:
    boxes: list[StaticPersonBox] = []
    for row in rows:
        if row.get("Source") != "xclick" or row.get("Confidence") != "1":
            raise ValueError("selected validation person box is not manually drawn")
        if row.get("IsGroupOf") != "0" or row.get("IsDepiction") != "0":
            raise ValueError("selected person box cannot be group-of or depiction")
        if row.get("IsInside") not in {"0", "-1"}:
            raise ValueError("selected person box has unsupported inside metadata")
        try:
            box = StaticPersonBox(
                bbox_norm_xyxy=[
                    float(row["XMin"]),
                    float(row["YMin"]),
                    float(row["XMax"]),
                    float(row["YMax"]),
                ],
                is_occluded=row.get("IsOccluded") == "1",
                is_truncated=row.get("IsTruncated") == "1",
            )
        except (KeyError, ValueError) as error:
            raise ValueError("selected person box coordinates are invalid") from error
        boxes.append(box)
    return boxes


def _validate_annotation_rows(
    *,
    case: dict[str, Any],
    metadata: dict[str, str],
    labels: dict[str, dict[str, str]],
    box_rows: list[dict[str, str]],
) -> list[StaticPersonBox]:
    expected_metadata = {
        "ImageID": case["image_id"],
        "Subset": EXPECTED_DATASET_SPLIT,
        "License": EXPECTED_IMAGE_LICENSE_URL,
        "OriginalLandingURL": case["original_landing_url"],
        "AuthorProfileURL": case["author_profile_url"],
        "Author": case["author"],
        "Title": case["title"],
    }
    if any(metadata.get(key) != value for key, value in expected_metadata.items()):
        raise ValueError(f"Open Images attribution metadata drifted: {case['case_id']}")
    try:
        rotation = float(metadata.get("Rotation", "nan"))
    except ValueError as error:
        raise ValueError("Open Images rotation metadata is invalid") from error
    if rotation != float(case["rotation_degrees"]):
        raise ValueError(f"Open Images rotation drifted: {case['case_id']}")

    person_label = labels.get(PERSON_MID)
    if person_label is None:
        raise ValueError(
            f"selected image lacks a verified Person label: {case['case_id']}"
        )
    expected_person = case["expected_person_label_confidence"]
    if (
        person_label.get("Source") != "verification"
        or float(person_label.get("Confidence", "nan")) != expected_person
    ):
        raise ValueError(f"selected Person label drifted: {case['case_id']}")
    for expected in case["required_positive_labels"]:
        row = labels.get(expected["mid"])
        if (
            row is None
            or row.get("Source") != "verification"
            or row.get("Confidence") != "1"
        ):
            raise ValueError(f"selected context label drifted: {case['case_id']}")

    person_boxes = _parse_person_boxes(box_rows)
    if len(person_boxes) != case["expected_person_box_count"]:
        raise ValueError(f"selected Person box count drifted: {case['case_id']}")
    return person_boxes


def prepare_v1_g4_openimages_data(
    *,
    manifest_path: Path,
    download_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    download_dir = Path(download_dir)
    output_dir = Path(output_dir)
    manifest = load_static_home_source_manifest(manifest_path)
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
                "role": item.get("role", "image_case"),
                "case_id": item.get("case_id"),
                "image_id": item.get("image_id"),
                "path": relative.as_posix(),
                "byte_size": item["byte_size"],
                "sha256": item["sha256"],
            }
        )

    metadata_rows, label_rows, box_rows = _load_selected_rows(
        manifest=manifest,
        download_dir=download_dir,
    )
    prepared_cases: list[StaticHomeImageCase] = []
    attribution_entries: list[dict[str, Any]] = []
    processed_files: list[dict[str, Any]] = []
    for item in manifest["cases"]:
        image_id = item["image_id"]
        person_boxes = _validate_annotation_rows(
            case=item,
            metadata=metadata_rows[image_id],
            labels=label_rows[image_id],
            box_rows=box_rows.get(image_id, []),
        )
        source_path = download_dir / _relative_source_path(item["path"])
        image_path = output_dir / "images" / f"{image_id}.jpg"
        _copy_verified(
            source_path,
            image_path,
            byte_size=item["byte_size"],
            sha256=item["sha256"],
        )
        width, height = _image_dimensions(image_path)
        if (width, height) != (item["width"], item["height"]):
            raise ValueError(f"static home image dimensions drifted: {item['case_id']}")
        expected_presence = (
            "absent" if item["expected_person_box_count"] == 0 else "present"
        )
        prepared_cases.append(
            StaticHomeImageCase(
                case_id=item["case_id"],
                dataset_id=dataset["dataset_id"],
                dataset_version=dataset["version"],
                image_id=image_id,
                image_path=image_path.relative_to(output_dir).as_posix(),
                image_sha256=item["sha256"],
                image_byte_size=item["byte_size"],
                image_width=width,
                image_height=height,
                scenario=item["scenario"],
                expected_person_presence=expected_presence,
                expected_person_count=len(person_boxes),
                person_boxes=person_boxes,
                context_labels=sorted(
                    label["name"] for label in item["required_positive_labels"]
                ),
                limitations=[
                    "single_static_image_without_motion_or_event_timing",
                    "single_reviewer_visual_screening_not_independent_label_audit",
                    "public_dataset_e1_only",
                    "not_target_c6c_camera",
                ],
            )
        )
        attribution_entries.append(
            {
                "case_id": item["case_id"],
                "image_id": image_id,
                "title": item["title"],
                "author": item["author"],
                "author_profile_url": item["author_profile_url"],
                "original_landing_url": item["original_landing_url"],
                "license": item["license"],
                "license_url": item["license_url"],
                "changes": "none; CVDF validation image copied byte-for-byte",
                "license_page_checked_on": item["license_page_audit"]["checked_on"],
            }
        )
        processed_files.append(
            {
                "kind": "unaltered_cvdf_validation_image",
                "case_id": item["case_id"],
                "image_id": image_id,
                "path": image_path.relative_to(output_dir).as_posix(),
                "byte_size": image_path.stat().st_size,
                "sha256": sha256_file(image_path),
                "width": width,
                "height": height,
            }
        )

    source_manifest_digest = sha256_file(manifest_path)
    attribution = {
        "schema_version": "1.0",
        "suite_id": manifest["suite_id"],
        "source_manifest_sha256": source_manifest_digest,
        "annotation_license": dataset["annotation_license"],
        "annotation_license_url": dataset["annotation_license_url"],
        "annotation_attribution": dataset["annotation_attribution"],
        "annotation_source_url": dataset["homepage"],
        "required_image_license": dataset["required_image_license"],
        "license_reaudit_required_before_competition_submission": True,
        "images": attribution_entries,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    attribution_path = output_dir / "attribution.json"
    atomic_write_json(attribution_path, attribution)
    processed_files.append(
        {
            "kind": "image_attribution",
            "path": attribution_path.relative_to(output_dir).as_posix(),
            "byte_size": attribution_path.stat().st_size,
            "sha256": sha256_file(attribution_path),
        }
    )
    suite = {
        "schema_version": "1.0",
        "suite_id": manifest["suite_id"],
        "evidence_level": EvidenceLevel.E1.value,
        "source_manifest_sha256": source_manifest_digest,
        "dataset": {
            "dataset_id": dataset["dataset_id"],
            "version": dataset["version"],
            "split": dataset["split"],
            "homepage": dataset["homepage"],
            "annotation_license": dataset["annotation_license"],
            "annotation_license_url": dataset["annotation_license_url"],
            "annotation_attribution": dataset["annotation_attribution"],
            "required_image_license": dataset["required_image_license"],
        },
        "matching_iou_threshold": manifest["selection"][
            "matching_iou_threshold"
        ],
        "scenario_case_counts": EXPECTED_SCENARIO_COUNTS,
        "attribution_path": attribution_path.relative_to(output_dir).as_posix(),
        "case_count": len(prepared_cases),
        "cases": [case.model_dump(mode="json") for case in prepared_cases],
        "limitations": manifest["limitations"],
    }
    suite_path = output_dir / "static-home-cases.json"
    atomic_write_json(suite_path, suite)
    processed_files.append(
        {
            "kind": "static_home_cases",
            "path": suite_path.relative_to(output_dir).as_posix(),
            "byte_size": suite_path.stat().st_size,
            "sha256": sha256_file(suite_path),
        }
    )
    lock = {
        "schema_version": "1.0",
        "suite_id": manifest["suite_id"],
        "source_manifest_sha256": source_manifest_digest,
        "source_files": sorted(source_lock, key=lambda value: value["path"]),
        "processed_files": sorted(processed_files, key=lambda value: value["path"]),
    }
    lock_path = output_dir / "dataset-lock.json"
    atomic_write_json(lock_path, lock)
    return {
        "suite_id": manifest["suite_id"],
        "static_home_cases": str(suite_path),
        "attribution": str(attribution_path),
        "dataset_lock": str(lock_path),
        "case_count": len(prepared_cases),
        "source_file_count": len(source_lock),
        "processed_file_count": len(processed_files),
    }
