from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from kangshield.information.artifacts import atomic_write_json
from kangshield.information.static_home_preparation import (
    EXPECTED_PROVENANCE_URLS,
    EXPECTED_SCENARIO_COUNTS,
    load_static_home_source_manifest,
    prepare_v1_g4_openimages_data,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = (
    PROJECT_ROOT / "configs" / "v1-g4-openimages-static-home-negative.json"
)


def test_static_home_source_manifest_freezes_license_and_scenarios():
    manifest = load_static_home_source_manifest(SOURCE_MANIFEST)

    assert manifest["suite_id"] == "v1-g4-openimages-static-home-negative-12-r2"
    assert manifest["dataset"]["annotation_license"] == "CC-BY-4.0"
    assert manifest["dataset"]["required_image_license"] == "CC-BY-2.0"
    assert len(manifest["cases"]) == 12
    counts = {
        scenario: sum(case["scenario"] == scenario for case in manifest["cases"])
        for scenario in EXPECTED_SCENARIO_COUNTS
    }
    assert counts == EXPECTED_SCENARIO_COUNTS
    assert all(
        case["license_page_audit"]["status"] == "passed"
        for case in manifest["cases"]
    )
    assert all(
        case["manual_review"]["visible_person_count"]
        == case["expected_person_box_count"]
        for case in manifest["cases"]
    )


def test_static_home_source_manifest_rejects_license_page_drift(tmp_path):
    payload = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    payload["cases"][0]["license_page_audit"]["status"] = "unverified"
    drifted = tmp_path / "drifted.json"
    atomic_write_json(drifted, payload)

    with pytest.raises(ValueError, match="license-page audit"):
        load_static_home_source_manifest(drifted)


def test_static_home_source_manifest_rejects_visual_box_mismatch(tmp_path):
    payload = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    payload["cases"][-1]["manual_review"]["visible_person_count"] += 1
    drifted = tmp_path / "visual-drifted.json"
    atomic_write_json(drifted, payload)

    with pytest.raises(ValueError, match="visual person count"):
        load_static_home_source_manifest(drifted)


def _csv_bytes(fieldnames: list[str], rows: list[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _jpeg_bytes(value: int) -> bytes:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((48, 64, 3), value, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def _file_entry(*, role: str, path: str, url: str, content: bytes) -> dict:
    return {
        "role": role,
        "path": path,
        "url": url,
        "byte_size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _build_fixture_manifest(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    person_mid = "/m/01g317"
    chair_mid = "/m/01mzpv"
    cat_mid = "/m/01yrx"
    scenarios = [
        *("person_absent_furniture" for _ in range(4)),
        *("person_absent_pet" for _ in range(4)),
        *("multi_person_indoor" for _ in range(4)),
    ]
    files: dict[str, bytes] = {}
    cases: list[dict] = []
    metadata_rows: list[dict[str, object]] = []
    label_rows: list[dict[str, object]] = []
    box_rows: list[dict[str, object]] = []
    for index, scenario in enumerate(scenarios, start=1):
        image_id = f"{index:016x}"
        case_id = f"fixture-static-{index:02d}"
        url = f"https://open-images-dataset.s3.amazonaws.com/validation/{image_id}.jpg"
        content = _jpeg_bytes(index * 10)
        files[url] = content
        landing_url = f"https://example.test/photos/{image_id}"
        author_url = f"https://example.test/people/{image_id}"
        context_mid = cat_mid if scenario == "person_absent_pet" else chair_mid
        context_name = "Cat" if context_mid == cat_mid else "Chair"
        person_confidence = 1 if scenario == "multi_person_indoor" else 0
        person_count = 2 if scenario == "multi_person_indoor" else 0
        findings = (
            [
                "multiple_visible_people",
                "annotation_boxes_align_with_visible_people",
                "indoor_scene",
            ]
            if scenario == "multi_person_indoor"
            else [
                "no_visible_person",
                (
                    "pet_visible"
                    if scenario == "person_absent_pet"
                    else "indoor_furniture_scene"
                ),
            ]
        )
        cases.append(
            {
                "case_id": case_id,
                "scenario": scenario,
                "image_id": image_id,
                "path": f"openimages-v7/validation/{image_id}.jpg",
                "url": url,
                "byte_size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "width": 64,
                "height": 48,
                "expected_person_label_confidence": person_confidence,
                "expected_person_box_count": person_count,
                "required_positive_labels": [
                    {"mid": context_mid, "name": context_name}
                ],
                "license": "CC-BY-2.0",
                "license_url": "https://creativecommons.org/licenses/by/2.0/",
                "original_landing_url": landing_url,
                "author_profile_url": author_url,
                "author": f"Fixture Author {index}",
                "title": f"Fixture Title {index}",
                "rotation_degrees": 0,
                "license_page_audit": {
                    "status": "passed",
                    "checked_on": "2026-07-22",
                    "observed_license_url": (
                        "https://creativecommons.org/licenses/by/2.0/"
                    ),
                    "method": "original_landing_page_html_exact_license_link",
                },
                "manual_review": {
                    "status": "passed",
                    "reviewed_on": "2026-07-22",
                    "method": "single_reviewer_visual_screening",
                    "visible_person_count": person_count,
                    "person_box_alignment": (
                        "passed" if person_count else "not_applicable"
                    ),
                    "findings": findings,
                },
            }
        )
        metadata_rows.append(
            {
                "ImageID": image_id,
                "Subset": "validation",
                "OriginalURL": f"https://example.test/original/{image_id}.jpg",
                "OriginalLandingURL": landing_url,
                "License": "https://creativecommons.org/licenses/by/2.0/",
                "AuthorProfileURL": author_url,
                "Author": f"Fixture Author {index}",
                "Title": f"Fixture Title {index}",
                "OriginalSize": len(content),
                "OriginalMD5": "fixture",
                "Thumbnail300KURL": "",
                "Rotation": "0.0",
            }
        )
        label_rows.extend(
            [
                {
                    "ImageID": image_id,
                    "Source": "verification",
                    "LabelName": person_mid,
                    "Confidence": person_confidence,
                },
                {
                    "ImageID": image_id,
                    "Source": "verification",
                    "LabelName": context_mid,
                    "Confidence": 1,
                },
            ]
        )
        if person_count:
            for x1, x2 in ((0.1, 0.4), (0.55, 0.9)):
                box_rows.append(
                    {
                        "ImageID": image_id,
                        "Source": "xclick",
                        "LabelName": person_mid,
                        "Confidence": 1,
                        "XMin": x1,
                        "XMax": x2,
                        "YMin": 0.1,
                        "YMax": 0.9,
                        "IsOccluded": 0,
                        "IsTruncated": 0,
                        "IsGroupOf": 0,
                        "IsDepiction": 0,
                        "IsInside": 0,
                    }
                )

    metadata = _csv_bytes(
        [
            "ImageID",
            "Subset",
            "OriginalURL",
            "OriginalLandingURL",
            "License",
            "AuthorProfileURL",
            "Author",
            "Title",
            "OriginalSize",
            "OriginalMD5",
            "Thumbnail300KURL",
            "Rotation",
        ],
        metadata_rows,
    )
    image_labels = _csv_bytes(
        ["ImageID", "Source", "LabelName", "Confidence"], label_rows
    )
    boxes = _csv_bytes(
        [
            "ImageID",
            "Source",
            "LabelName",
            "Confidence",
            "XMin",
            "XMax",
            "YMin",
            "YMax",
            "IsOccluded",
            "IsTruncated",
            "IsGroupOf",
            "IsDepiction",
            "IsInside",
        ],
        box_rows,
    )
    classes = (
        "/m/01g317,Person\n/m/01mzpv,Chair\n/m/01yrx,Cat\n"
        "/m/03ssj5,Bed\n/m/02crq1,Couch\n/m/03m3pdh,Sofa bed\n"
        "/m/026qbn5,Studio couch\n/m/0bt9lr,Dog\n"
    ).encode()
    provenance_contents = {
        "validation_image_metadata": metadata,
        "validation_human_image_labels": image_labels,
        "validation_bounding_boxes": boxes,
        "boxable_class_descriptions": classes,
    }
    provenance_paths = {
        "validation_image_metadata": "fixture/metadata.csv",
        "validation_human_image_labels": "fixture/labels.csv",
        "validation_bounding_boxes": "fixture/boxes.csv",
        "boxable_class_descriptions": "fixture/classes.csv",
    }
    provenance = []
    for role, url in EXPECTED_PROVENANCE_URLS.items():
        content = provenance_contents[role]
        files[url] = content
        provenance.append(
            _file_entry(
                role=role,
                path=provenance_paths[role],
                url=url,
                content=content,
            )
        )
    manifest = {
        "schema_version": "1.0",
        "suite_id": "v1-g4-openimages-static-home-negative-12-r2",
        "evidence_level": "E1",
        "dataset": {
            "dataset_id": "open-images-v7",
            "version": 7,
            "split": "validation",
            "homepage": "https://storage.googleapis.com/openimages/web/index.html",
            "annotation_license": "CC-BY-4.0",
            "annotation_license_url": (
                "https://creativecommons.org/licenses/by/4.0/"
            ),
            "annotation_attribution": "Open Images annotations by Google LLC",
            "required_image_license": "CC-BY-2.0",
            "required_image_license_url": (
                "https://creativecommons.org/licenses/by/2.0/"
            ),
            "license_acceptance_required": False,
        },
        "selection": {
            "scenario_case_counts": EXPECTED_SCENARIO_COUNTS,
            "person_label_mid": person_mid,
            "person_label_name": "Person",
            "human_label_source": "verification",
            "matching_iou_threshold": 0.5,
            "manual_review_required": True,
        },
        "provenance_files": provenance,
        "cases": cases,
        "limitations": ["fixture_e1_only"],
    }
    manifest_path = tmp_path / "source-manifest.json"
    atomic_write_json(manifest_path, manifest)
    return manifest_path, files


def test_static_home_preparation_is_deterministic(tmp_path, monkeypatch):
    manifest_path, files = _build_fixture_manifest(tmp_path)

    def fake_download(url, target, *, byte_size, sha256):
        content = files[url]
        assert len(content) == byte_size
        assert hashlib.sha256(content).hexdigest() == sha256
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    monkeypatch.setattr(
        "kangshield.information.static_home_preparation.download_and_verify",
        fake_download,
    )
    first = prepare_v1_g4_openimages_data(
        manifest_path=manifest_path,
        download_dir=tmp_path / "downloads-one",
        output_dir=tmp_path / "processed-one",
    )
    second = prepare_v1_g4_openimages_data(
        manifest_path=manifest_path,
        download_dir=tmp_path / "downloads-two",
        output_dir=tmp_path / "processed-two",
    )

    assert first["case_count"] == 12
    assert first["source_file_count"] == 16
    assert first["processed_file_count"] == 14
    first_suite = Path(first["static_home_cases"])
    second_suite = Path(second["static_home_cases"])
    assert first_suite.read_bytes() == second_suite.read_bytes()
    assert Path(first["attribution"]).read_bytes() == Path(
        second["attribution"]
    ).read_bytes()
    assert Path(first["dataset_lock"]).read_bytes() == Path(
        second["dataset_lock"]
    ).read_bytes()
    suite = json.loads(first_suite.read_text(encoding="utf-8"))
    assert suite["case_count"] == 12
    assert sum(case["expected_person_count"] for case in suite["cases"]) == 8
    assert all(
        (first_suite.parent / case["image_path"]).is_file()
        for case in suite["cases"]
    )
