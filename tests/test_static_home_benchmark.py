from __future__ import annotations

import json
from pathlib import Path

import pytest

from kangshield.information.artifacts import atomic_write_json
from kangshield.information.contracts import (
    ModelBinding,
    StaticHomeImageCase,
    StaticPersonBox,
)
from kangshield.information.fall_adl_benchmark import YOLO26N_POSE_SHA256
from kangshield.information.pose_backend import PoseDetection
from kangshield.information.privacy import sha256_file
from kangshield.information.static_home_benchmark import (
    load_static_home_cases,
    match_person_boxes,
    run_static_home_benchmark,
)
from kangshield.information.static_home_preparation import (
    EXPECTED_PROVENANCE_URLS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSE_POLICY = PROJECT_ROOT / "configs" / "v1-m3-pose-models.json"


class _FakePoseBackend:
    def __init__(self) -> None:
        self.calls = 0
        self._bindings = [
            ModelBinding(
                task="human_pose_tracking",
                backend="fake-pose",
                model_name="yolo26n-pose.pt",
                model_version="test",
                model_digest=YOLO26N_POSE_SHA256,
                license="test-only",
                device="cpu",
                configuration={
                    "keypoint_layout": "COCO-17",
                    "tracking": False,
                },
            )
        ]

    @property
    def bindings(self):
        return list(self._bindings)

    def reset(self) -> None:
        pass

    def infer(self, frame):
        del frame
        self.calls += 1
        if self.calls <= 8:
            return []
        points = [[16.0, 16.0, 0.9] for _ in range(17)]
        return [
            PoseDetection(
                bbox_xyxy=[6.4, 4.8, 25.6, 43.2],
                keypoints_xyc=points,
                confidence=0.9,
                track_id=None,
            ),
            PoseDetection(
                bbox_xyxy=[35.2, 4.8, 57.6, 43.2],
                keypoints_xyc=points,
                confidence=0.8,
                track_id=None,
            ),
        ]


def _write_image(path: Path, value: int) -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((48, 64, 3), value, dtype=np.uint8)
    assert cv2.imwrite(str(path), image)


def _build_suite(tmp_path: Path) -> Path:
    root = tmp_path / "suite"
    image_dir = root / "images"
    image_dir.mkdir(parents=True)
    cases = []
    attribution = []
    scenarios = [
        *("person_absent_furniture" for _ in range(4)),
        *("person_absent_pet" for _ in range(4)),
        *("multi_person_indoor" for _ in range(4)),
    ]
    for index, scenario in enumerate(scenarios, start=1):
        image_id = f"{index:016x}"
        image_path = image_dir / f"{image_id}.jpg"
        _write_image(image_path, index * 10)
        boxes = (
            [
                StaticPersonBox(bbox_norm_xyxy=[0.1, 0.1, 0.4, 0.9]),
                StaticPersonBox(bbox_norm_xyxy=[0.55, 0.1, 0.9, 0.9]),
            ]
            if scenario == "multi_person_indoor"
            else []
        )
        cases.append(
            StaticHomeImageCase(
                case_id=f"fixture-static-{index:02d}",
                dataset_id="open-images-v7",
                dataset_version=7,
                image_id=image_id,
                image_path=image_path.relative_to(root).as_posix(),
                image_sha256=sha256_file(image_path),
                image_byte_size=image_path.stat().st_size,
                image_width=64,
                image_height=48,
                scenario=scenario,
                expected_person_presence=(
                    "present" if scenario == "multi_person_indoor" else "absent"
                ),
                expected_person_count=len(boxes),
                person_boxes=boxes,
                context_labels=[
                    "Cat" if scenario == "person_absent_pet" else "Chair"
                ],
                limitations=["fixture"],
            )
        )
        attribution.append(
            {
                "case_id": f"fixture-static-{index:02d}",
                "image_id": image_id,
                "title": f"Fixture {index}",
                "author": "Fixture Author",
                "author_profile_url": "https://example.test/author",
                "original_landing_url": f"https://example.test/{image_id}",
                "license": "CC-BY-2.0",
                "license_url": "https://creativecommons.org/licenses/by/2.0/",
                "changes": "none; CVDF validation image copied byte-for-byte",
                "license_page_checked_on": "2026-07-22",
            }
        )
    source_digest = "a" * 64
    attribution_path = root / "attribution.json"
    atomic_write_json(
        attribution_path,
        {
            "schema_version": "1.0",
            "suite_id": "v1-g4-openimages-static-home-negative-12-r2",
            "source_manifest_sha256": source_digest,
            "annotation_license": "CC-BY-4.0",
            "annotation_license_url": (
                "https://creativecommons.org/licenses/by/4.0/"
            ),
            "annotation_attribution": "Open Images annotations by Google LLC",
            "annotation_source_url": (
                "https://storage.googleapis.com/openimages/web/index.html"
            ),
            "required_image_license": "CC-BY-2.0",
            "license_reaudit_required_before_competition_submission": True,
            "images": attribution,
        },
    )
    suite_path = root / "static-home-cases.json"
    atomic_write_json(
        suite_path,
        {
            "schema_version": "1.0",
            "suite_id": "v1-g4-openimages-static-home-negative-12-r2",
            "evidence_level": "E1",
            "source_manifest_sha256": source_digest,
            "dataset": {
                "dataset_id": "open-images-v7",
                "version": 7,
                "split": "validation",
                "homepage": "https://storage.googleapis.com/openimages/web/index.html",
                "annotation_license": "CC-BY-4.0",
                "annotation_license_url": (
                    "https://creativecommons.org/licenses/by/4.0/"
                ),
                "annotation_attribution": (
                    "Open Images annotations by Google LLC"
                ),
                "required_image_license": "CC-BY-2.0",
            },
            "matching_iou_threshold": 0.5,
            "scenario_case_counts": {
                "person_absent_furniture": 4,
                "person_absent_pet": 4,
                "multi_person_indoor": 4,
            },
            "attribution_path": "attribution.json",
            "case_count": len(cases),
            "cases": [case.model_dump(mode="json") for case in cases],
            "limitations": ["fixture_e1_only"],
        },
    )
    source_files = [
        {
            "role": "image_case",
            "case_id": case.case_id,
            "image_id": case.image_id,
            "path": f"source/{case.image_id}.jpg",
            "byte_size": case.image_byte_size,
            "sha256": case.image_sha256,
        }
        for case in cases
    ]
    source_files.extend(
        {
            "role": role,
            "case_id": None,
            "image_id": None,
            "path": f"source/{index}-{role}.csv",
            "byte_size": 1,
            "sha256": f"{index + 1:064x}",
        }
        for index, role in enumerate(EXPECTED_PROVENANCE_URLS)
    )
    processed_files = [
        {
            "kind": "unaltered_cvdf_validation_image",
            "case_id": case.case_id,
            "image_id": case.image_id,
            "path": case.image_path,
            "byte_size": case.image_byte_size,
            "sha256": case.image_sha256,
            "width": case.image_width,
            "height": case.image_height,
        }
        for case in cases
    ]
    processed_files.extend(
        [
            {
                "kind": "image_attribution",
                "path": attribution_path.relative_to(root).as_posix(),
                "byte_size": attribution_path.stat().st_size,
                "sha256": sha256_file(attribution_path),
            },
            {
                "kind": "static_home_cases",
                "path": suite_path.relative_to(root).as_posix(),
                "byte_size": suite_path.stat().st_size,
                "sha256": sha256_file(suite_path),
            },
        ]
    )
    atomic_write_json(
        root / "dataset-lock.json",
        {
            "schema_version": "1.0",
            "suite_id": "v1-g4-openimages-static-home-negative-12-r2",
            "source_manifest_sha256": source_digest,
            "source_files": sorted(source_files, key=lambda item: item["path"]),
            "processed_files": sorted(
                processed_files, key=lambda item: item["path"]
            ),
        },
    )
    return suite_path


def test_match_person_boxes_is_one_to_one():
    scores = match_person_boxes(
        [[0, 0, 10, 10], [0, 0, 10, 10]],
        [[0, 0, 10, 10]],
        iou_threshold=0.5,
    )

    assert scores == [1.0]


def test_static_home_loader_rejects_scenario_drift(tmp_path):
    suite_path = _build_suite(tmp_path)
    suite, cases, attribution, dataset_lock = load_static_home_cases(suite_path)
    assert suite["case_count"] == len(cases) == 12
    assert attribution.is_file()
    assert dataset_lock.is_file()

    payload = json.loads(suite_path.read_text(encoding="utf-8"))
    payload["cases"][0]["scenario"] = "person_absent_pet"
    atomic_write_json(suite_path, payload)
    with pytest.raises(ValueError, match="scenario matrix"):
        load_static_home_cases(suite_path)


def test_static_home_benchmark_keeps_parent_report_aggregate_only(
    tmp_path, monkeypatch
):
    suite_path = _build_suite(tmp_path)
    monkeypatch.setattr(
        "kangshield.information.static_home_benchmark.build_fall_adl_pose_backend",
        lambda *args, **kwargs: _FakePoseBackend(),
    )

    run, report = run_static_home_benchmark(
        static_home_cases_path=suite_path,
        runs_dir=tmp_path / "runs",
        variants=["yolo26n-pose"],
        model_binding_policy_path=POSE_POLICY,
    )

    variant = report.variants[0]
    overall = variant.overall
    assert report.case_count == 12
    assert report.matching_iou_threshold == 0.5
    assert overall.ground_truth_person_count == 8
    assert overall.predicted_person_count == 8
    assert overall.matched_person_count == 8
    assert overall.false_positive_count == 0
    assert overall.false_negative_count == 0
    assert overall.person_absent_false_activation_rate == 0.0
    assert overall.multi_any_person_detected_cases == 4
    assert overall.multi_all_people_matched_cases == 4
    assert report.risk_assessment_emitted is False
    assert report.alert_emitted is False
    assert len(variant.runtime_environment["case_run_ids"]) == 12

    report_text = (
        run.run_dir / "reports" / "static-home-benchmark-report.json"
    ).read_text(encoding="utf-8")
    assert "bbox_norm_xyxy" not in report_text
    assert "bbox_xyxy" not in report_text
    assert "/home/" not in report_text
    child_run = tmp_path / "runs" / variant.cases[0].run_id
    child_report = (
        child_run / "reports" / "static-home-case-evaluation.json"
    ).read_text(encoding="utf-8")
    assert "bbox_norm_xyxy" not in child_report
    assert "risk_assessment_emitted\": false" in child_report
