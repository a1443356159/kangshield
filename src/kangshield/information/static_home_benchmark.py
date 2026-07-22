from __future__ import annotations

import gc
import json
import math
import os
import platform
import re
import socket
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Iterable

from .artifacts import RunArtifacts
from .contracts import (
    EvidenceLevel,
    Modality,
    ModelBinding,
    PrivacyLevel,
    SourceAsset,
    SourceType,
    StaticHomeBenchmarkReport,
    StaticHomeCaseEvaluation,
    StaticHomeGroupMetrics,
    StaticHomeImageCase,
    StaticHomeVariantReport,
)
from .fall_adl_benchmark import (
    KNOWN_VARIANTS,
    YOLO26N_POSE_SHA256,
    build_fall_adl_pose_backend,
)
from .fall_features import (
    correct_model_bindings,
    validate_torchvision_model_bindings,
)
from .pose_backend import PoseBackend, PoseDetection
from .privacy import safe_local_uri, sha256_file
from .static_home_preparation import (
    EXPECTED_ANNOTATION_ATTRIBUTION,
    EXPECTED_ANNOTATION_LICENSE,
    EXPECTED_ANNOTATION_LICENSE_URL,
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_HOMEPAGE,
    EXPECTED_DATASET_SPLIT,
    EXPECTED_DATASET_VERSION,
    EXPECTED_IMAGE_LICENSE,
    EXPECTED_IMAGE_LICENSE_URL,
    EXPECTED_PROVENANCE_URLS,
    EXPECTED_SCENARIO_COUNTS,
    EXPECTED_SUITE_ID,
)
from .torchvision_pose_backend import load_torchvision_pose_policy


STATIC_HOME_BENCHMARK_VERSION = "static-home-person-benchmark-v0.1.0"


def _safe_relative_path(manifest_path: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("static home path must remain relative to the suite")
    root = Path(manifest_path).parent.resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("static home path escapes the prepared suite")
    return resolved


def _validate_attribution(
    *, manifest_path: Path, suite: dict[str, Any], cases: list[StaticHomeImageCase]
) -> Path:
    value = suite.get("attribution_path")
    if not isinstance(value, str):
        raise ValueError("static home suite lacks an attribution path")
    path = _safe_relative_path(manifest_path, value)
    if not path.is_file():
        raise FileNotFoundError("static home attribution file is missing")
    with path.open(encoding="utf-8") as stream:
        attribution = json.load(stream)
    expected = {
        "schema_version": "1.0",
        "suite_id": suite["suite_id"],
        "source_manifest_sha256": suite["source_manifest_sha256"],
        "annotation_license": EXPECTED_ANNOTATION_LICENSE,
        "annotation_license_url": EXPECTED_ANNOTATION_LICENSE_URL,
        "annotation_attribution": EXPECTED_ANNOTATION_ATTRIBUTION,
        "annotation_source_url": EXPECTED_DATASET_HOMEPAGE,
        "required_image_license": EXPECTED_IMAGE_LICENSE,
        "license_reaudit_required_before_competition_submission": True,
    }
    if any(attribution.get(key) != value for key, value in expected.items()):
        raise ValueError("static home attribution metadata drifted")
    images = attribution.get("images")
    if not isinstance(images, list) or len(images) != len(cases):
        raise ValueError("static home attribution image list is incomplete")
    expected_ids = {case.image_id for case in cases}
    attributed_ids = {
        item.get("image_id") for item in images if isinstance(item, dict)
    }
    if attributed_ids != expected_ids:
        raise ValueError("static home attribution image ids drifted")
    case_by_image_id = {case.image_id: case for case in cases}
    for item in images:
        if not isinstance(item, dict):
            raise ValueError("static home attribution entry must be an object")
        case = case_by_image_id[item["image_id"]]
        if item.get("case_id") != case.case_id:
            raise ValueError("static home attribution case id drifted")
        if item.get("license") != EXPECTED_IMAGE_LICENSE:
            raise ValueError("static home attribution image license drifted")
        if item.get("license_url") != EXPECTED_IMAGE_LICENSE_URL:
            raise ValueError("static home attribution license URL drifted")
        if item.get("changes") != "none; CVDF validation image copied byte-for-byte":
            raise ValueError("static home attribution change declaration drifted")
        if not str(item.get("original_landing_url", "")).startswith("https://"):
            raise ValueError("static home attribution landing URL is invalid")
        if not str(item.get("author_profile_url", "")).startswith("https://"):
            raise ValueError("static home attribution author URL is invalid")
        if not all(str(item.get(key, "")).strip() for key in ("author", "title")):
            raise ValueError("static home attribution author or title is missing")
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            str(item.get("license_page_checked_on", "")),
        ):
            raise ValueError("static home attribution audit date is invalid")
    return path


def _validate_dataset_lock(
    *,
    manifest_path: Path,
    suite: dict[str, Any],
    cases: list[StaticHomeImageCase],
    attribution_path: Path,
) -> Path:
    lock_path = Path(manifest_path).parent / "dataset-lock.json"
    if not lock_path.is_file():
        raise FileNotFoundError("static home dataset lock is missing")
    with lock_path.open(encoding="utf-8") as stream:
        lock = json.load(stream)
    expected = {
        "schema_version": "1.0",
        "suite_id": suite["suite_id"],
        "source_manifest_sha256": suite["source_manifest_sha256"],
    }
    if any(lock.get(key) != value for key, value in expected.items()):
        raise ValueError("static home dataset lock metadata drifted")

    source_files = lock.get("source_files")
    if not isinstance(source_files, list) or len(source_files) != 16:
        raise ValueError("static home dataset lock source file set is incomplete")
    source_roles = Counter()
    source_paths: set[str] = set()
    source_case_rows: set[tuple[str, str, int, str]] = set()
    for item in source_files:
        if not isinstance(item, dict):
            raise ValueError("static home dataset lock source entry is invalid")
        role = item.get("role")
        path = item.get("path")
        byte_size = item.get("byte_size")
        digest = item.get("sha256")
        if (
            not isinstance(path, str)
            or not path
            or path in source_paths
            or not isinstance(byte_size, int)
            or byte_size <= 0
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ValueError("static home dataset lock source entry drifted")
        source_paths.add(path)
        source_roles[role] += 1
        if role == "image_case":
            source_case_rows.add(
                (str(item.get("case_id")), str(item.get("image_id")), byte_size, digest)
            )
    expected_roles = Counter({role: 1 for role in EXPECTED_PROVENANCE_URLS})
    expected_roles["image_case"] = len(cases)
    if source_roles != expected_roles:
        raise ValueError("static home dataset lock source roles drifted")
    expected_case_rows = {
        (case.case_id, case.image_id, case.image_byte_size, case.image_sha256)
        for case in cases
    }
    if source_case_rows != expected_case_rows:
        raise ValueError("static home dataset lock image sources drifted")

    processed_files = lock.get("processed_files")
    if not isinstance(processed_files, list) or len(processed_files) != 14:
        raise ValueError("static home dataset lock processed set is incomplete")
    processed_by_path: dict[str, dict[str, Any]] = {}
    for item in processed_files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("static home dataset lock processed entry is invalid")
        if item["path"] in processed_by_path:
            raise ValueError("static home dataset lock processed path is duplicated")
        processed_by_path[item["path"]] = item

    expected_processed: list[tuple[Path, str, str | None, str | None]] = [
        (attribution_path, "image_attribution", None, None),
        (Path(manifest_path), "static_home_cases", None, None),
    ]
    expected_processed.extend(
        (
            _safe_relative_path(manifest_path, case.image_path),
            "unaltered_cvdf_validation_image",
            case.case_id,
            case.image_id,
        )
        for case in cases
    )
    root = Path(manifest_path).parent.resolve()
    for path, kind, case_id, image_id in expected_processed:
        relative = path.resolve().relative_to(root).as_posix()
        item = processed_by_path.get(relative)
        if item is None or item.get("kind") != kind:
            raise ValueError("static home dataset lock processed entry is missing")
        if item.get("byte_size") != path.stat().st_size:
            raise ValueError("static home dataset lock processed size drifted")
        if item.get("sha256") != sha256_file(path):
            raise ValueError("static home dataset lock processed digest drifted")
        if case_id is not None and (
            item.get("case_id") != case_id or item.get("image_id") != image_id
        ):
            raise ValueError("static home dataset lock processed image id drifted")
    return lock_path


def load_static_home_cases(
    manifest_path: Path,
) -> tuple[dict[str, Any], list[StaticHomeImageCase], Path, Path]:
    manifest_path = Path(manifest_path)
    with manifest_path.open(encoding="utf-8") as stream:
        suite = json.load(stream)
    if suite.get("schema_version") != "1.0":
        raise ValueError("unsupported static home suite schema")
    if suite.get("suite_id") != EXPECTED_SUITE_ID:
        raise ValueError("static home prepared suite id is not frozen")
    if suite.get("evidence_level") != EvidenceLevel.E1.value:
        raise ValueError("static home suite must remain E1")
    source_digest = suite.get("source_manifest_sha256")
    if not isinstance(source_digest, str) or len(source_digest) != 64:
        raise ValueError("static home suite lacks a source manifest digest")
    dataset = suite.get("dataset")
    expected_dataset = {
        "dataset_id": EXPECTED_DATASET_ID,
        "version": EXPECTED_DATASET_VERSION,
        "split": EXPECTED_DATASET_SPLIT,
        "homepage": EXPECTED_DATASET_HOMEPAGE,
        "annotation_license": EXPECTED_ANNOTATION_LICENSE,
        "annotation_license_url": EXPECTED_ANNOTATION_LICENSE_URL,
        "annotation_attribution": EXPECTED_ANNOTATION_ATTRIBUTION,
        "required_image_license": EXPECTED_IMAGE_LICENSE,
    }
    if not isinstance(dataset, dict) or any(
        dataset.get(key) != value for key, value in expected_dataset.items()
    ):
        raise ValueError("static home prepared dataset metadata drifted")
    if suite.get("matching_iou_threshold") != 0.5:
        raise ValueError("static home IoU threshold is not frozen")
    if suite.get("scenario_case_counts") != EXPECTED_SCENARIO_COUNTS:
        raise ValueError("static home scenario policy drifted")
    payloads = suite.get("cases")
    if not isinstance(payloads, list):
        raise ValueError("static home suite cases must be a list")
    cases = [StaticHomeImageCase.model_validate(item) for item in payloads]
    if suite.get("case_count") != len(cases) or len(cases) != 12:
        raise ValueError("static home suite must contain the frozen 12 cases")
    if Counter(case.scenario for case in cases) != Counter(EXPECTED_SCENARIO_COUNTS):
        raise ValueError("static home suite scenario matrix is incomplete")
    case_ids = [case.case_id for case in cases]
    image_ids = [case.image_id for case in cases]
    image_paths = [case.image_path for case in cases]
    image_digests = [case.image_sha256 for case in cases]
    if any(
        len(values) != len(set(values))
        for values in (case_ids, image_ids, image_paths, image_digests)
    ):
        raise ValueError("static home suite contains duplicate identifiers or images")
    for case in cases:
        if case.evidence_level is not EvidenceLevel.E1:
            raise ValueError("static home cases must remain E1")
        if case.dataset_id != EXPECTED_DATASET_ID:
            raise ValueError("static home case dataset id disagrees with suite")
        if case.dataset_version != EXPECTED_DATASET_VERSION:
            raise ValueError("static home case dataset version disagrees with suite")
        _safe_relative_path(manifest_path, case.image_path)
    attribution_path = _validate_attribution(
        manifest_path=manifest_path,
        suite=suite,
        cases=cases,
    )
    lock_path = _validate_dataset_lock(
        manifest_path=manifest_path,
        suite=suite,
        cases=cases,
        attribution_path=attribution_path,
    )
    return suite, cases, attribution_path, lock_path


def _verify_case_image(manifest_path: Path, case: StaticHomeImageCase) -> Path:
    path = _safe_relative_path(manifest_path, case.image_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"prepared static home image is missing: {case.case_id}"
        )
    if path.stat().st_size != case.image_byte_size:
        raise ValueError(f"prepared static home image size mismatch: {case.case_id}")
    if sha256_file(path) != case.image_sha256:
        raise ValueError(f"prepared static home image digest mismatch: {case.case_id}")
    return path


def _source_asset(
    path: Path,
    *,
    kind: str,
    modality: Modality,
    privacy_level: PrivacyLevel,
    contains_raw_media: bool,
) -> SourceAsset:
    path = Path(path)
    digest = sha256_file(path)
    return SourceAsset(
        asset_id=f"asset_{digest[:20]}",
        modality=modality,
        source_type=SourceType.LOCAL_FILE,
        evidence_level=EvidenceLevel.E1,
        uri=safe_local_uri(path, digest),
        sha256=digest,
        byte_size=path.stat().st_size,
        privacy_level=privacy_level,
        metadata={
            "kind": kind,
            "filename_suffix": path.suffix.lower(),
            "contains_raw_media": contains_raw_media,
            "source_path_persisted": False,
            "public_dataset_asset": contains_raw_media,
        },
    )


def _bbox_iou(left: Iterable[float], right: Iterable[float]) -> float:
    a = list(left)
    b = list(right)
    if len(a) != 4 or len(b) != 4:
        return 0.0
    intersection_width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    intersection_height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    right_area = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0.0 else 0.0


def match_person_boxes(
    predictions: list[list[float]],
    ground_truth: list[list[float]],
    *,
    iou_threshold: float,
) -> list[float]:
    if not 0.0 <= iou_threshold <= 1.0:
        raise ValueError("person matching IoU threshold must be in [0, 1]")
    candidates: list[tuple[float, int, int]] = []
    for prediction_index, prediction in enumerate(predictions):
        for truth_index, truth in enumerate(ground_truth):
            score = _bbox_iou(prediction, truth)
            if score >= iou_threshold:
                candidates.append((score, prediction_index, truth_index))
    candidates.sort(key=lambda value: (-value[0], value[1], value[2]))
    matched_predictions: set[int] = set()
    matched_truth: set[int] = set()
    scores: list[float] = []
    for score, prediction_index, truth_index in candidates:
        if prediction_index in matched_predictions or truth_index in matched_truth:
            continue
        matched_predictions.add(prediction_index)
        matched_truth.add(truth_index)
        scores.append(score)
    return scores


def _prediction_boxes(
    detections: list[PoseDetection], *, width: int, height: int
) -> list[list[float]]:
    boxes: list[list[float]] = []
    for detection in detections:
        if len(detection.bbox_xyxy) != 4 or any(
            not math.isfinite(float(value)) for value in detection.bbox_xyxy
        ):
            raise ValueError("pose backend returned an invalid person box")
        x1, y1, x2, y2 = (float(value) for value in detection.bbox_xyxy)
        clipped = [
            max(0.0, min(float(width), x1)),
            max(0.0, min(float(height), y1)),
            max(0.0, min(float(width), x2)),
            max(0.0, min(float(height), y2)),
        ]
        if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
            raise ValueError("pose backend returned a zero-area person box")
        boxes.append(clipped)
    return boxes


def _ground_truth_boxes(case: StaticHomeImageCase) -> list[list[float]]:
    return [
        [
            box.bbox_norm_xyxy[0] * case.image_width,
            box.bbox_norm_xyxy[1] * case.image_height,
            box.bbox_norm_xyxy[2] * case.image_width,
            box.bbox_norm_xyxy[3] * case.image_height,
        ]
        for box in case.person_boxes
    ]


def _pose_binding(bindings: list[ModelBinding]) -> ModelBinding:
    matches = [
        item
        for item in bindings
        if item.task in {"human_pose_estimation", "human_pose_tracking"}
    ]
    if len(matches) != 1 or matches[0].model_digest is None:
        raise ValueError("static home backend must expose one digest-bound pose model")
    if matches[0].configuration.get("keypoint_layout") != "COCO-17":
        raise ValueError("static home backend must expose COCO-17 keypoints")
    return matches[0]


def _runtime_environment() -> dict[str, Any]:
    environment: dict[str, Any] = {
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
    }
    try:
        import onnxruntime

        environment["onnxruntime"] = onnxruntime.__version__
        environment["onnxruntime_available_providers"] = (
            onnxruntime.get_available_providers()
        )
    except ImportError:
        environment["onnxruntime"] = "unavailable"
    try:
        import torch
    except ImportError:
        environment["torch"] = "unavailable"
        return environment
    environment["torch"] = torch.__version__
    try:
        import torchvision

        environment["torchvision"] = torchvision.__version__
    except ImportError:
        environment["torchvision"] = "unavailable"
    environment["cuda_available"] = torch.cuda.is_available()
    if torch.cuda.is_available():
        environment["cuda_device"] = torch.cuda.get_device_name(0)
        environment["torch_cuda_peak_memory_allocated_mb"] = round(
            torch.cuda.max_memory_allocated(0) / 1024**2, 3
        )
    return environment


def _reset_torch_peak() -> None:
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def _empty_cuda_cache() -> None:
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def _load_image(path: Path, case: StaticHomeImageCase) -> Any:
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("OpenCV is required for static home benchmarking") from error
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3:
        raise ValueError(f"static home image cannot be decoded: {case.case_id}")
    height, width = image.shape[:2]
    if (width, height) != (case.image_width, case.image_height):
        raise ValueError(f"static home decoded dimensions drifted: {case.case_id}")
    return image


def _evaluate_case(
    *,
    case: StaticHomeImageCase,
    variant_id: str,
    image_path: Path,
    backend: PoseBackend,
    run: RunArtifacts,
    iou_threshold: float,
) -> StaticHomeCaseEvaluation:
    run.record_asset(
        _source_asset(
            image_path,
            kind="openimages_static_home_image",
            modality=Modality.VIDEO,
            privacy_level=PrivacyLevel.RAW_SENSITIVE,
            contains_raw_media=True,
        )
    )
    image = _load_image(image_path, case)
    with run.step("infer-static-home-pose") as step:
        started = perf_counter()
        detections = backend.infer(image)
        inference_ms = (perf_counter() - started) * 1000.0
        step.outputs.append("aggregate_detection_counts_only")
    predictions = _prediction_boxes(
        detections,
        width=case.image_width,
        height=case.image_height,
    )
    truth = _ground_truth_boxes(case)
    matched_ious = match_person_boxes(
        predictions,
        truth,
        iou_threshold=iou_threshold,
    )
    confidences = [
        float(detection.confidence)
        for detection in detections
        if detection.confidence is not None
    ]
    matched_count = len(matched_ious)
    return StaticHomeCaseEvaluation(
        case_id=case.case_id,
        variant_id=variant_id,
        run_id=run.run_id,
        scenario=case.scenario,
        source_image_sha256=case.image_sha256,
        image_width=case.image_width,
        image_height=case.image_height,
        ground_truth_person_count=len(truth),
        predicted_person_count=len(predictions),
        matched_person_count=matched_count,
        false_positive_count=len(predictions) - matched_count,
        false_negative_count=len(truth) - matched_count,
        person_activation=bool(predictions),
        mean_detection_confidence=(
            round(mean(confidences), 6) if confidences else None
        ),
        mean_matched_iou=(round(mean(matched_ious), 6) if matched_ious else None),
        inference_ms=round(inference_ms, 3),
        limitations=[
            *case.limitations,
            "person_box_iou_matching_only_without_keypoint_accuracy_scoring",
            "no_temporal_tracking_motion_or_fall_event_metric",
        ],
    )


def _group_metrics(
    evaluations: list[StaticHomeCaseEvaluation],
) -> StaticHomeGroupMetrics:
    truth = sum(item.ground_truth_person_count for item in evaluations)
    predictions = sum(item.predicted_person_count for item in evaluations)
    matched = sum(item.matched_person_count for item in evaluations)
    absent = [
        item for item in evaluations if item.scenario.startswith("person_absent")
    ]
    multi = [item for item in evaluations if item.scenario == "multi_person_indoor"]
    absent_activated = sum(item.person_activation for item in absent)
    return StaticHomeGroupMetrics(
        case_count=len(evaluations),
        ground_truth_person_count=truth,
        predicted_person_count=predictions,
        matched_person_count=matched,
        false_positive_count=predictions - matched,
        false_negative_count=truth - matched,
        detection_precision=round(matched / predictions, 6) if predictions else None,
        detection_recall=round(matched / truth, 6) if truth else None,
        person_absent_case_count=len(absent),
        person_absent_false_activation_cases=absent_activated,
        person_absent_false_activation_rate=(
            round(absent_activated / len(absent), 6) if absent else None
        ),
        multi_person_case_count=len(multi),
        multi_any_person_detected_cases=sum(item.person_activation for item in multi),
        multi_all_people_matched_cases=sum(
            item.matched_person_count == item.ground_truth_person_count
            for item in multi
        ),
    )


def _variant_report(
    *,
    variant_id: str,
    cases: list[StaticHomeImageCase],
    image_paths: dict[str, Path],
    runs_dir: Path,
    parent_run: RunArtifacts,
    policy_path: Path,
    iou_threshold: float,
    yolo_model: Path,
    yolo_device: str,
    yolo_image_size: int,
    yolo_confidence: float,
    rtmpose_detector_model: Path,
    rtmpose_pose_model: Path,
    rtmpose_device: str,
    rtmpose_detection_confidence: float,
    torchvision_model: Path,
    torchvision_policy: Path,
    torchvision_device: str,
    torchvision_detection_confidence: float,
    torchvision_min_size: int,
    torchvision_max_size: int,
) -> StaticHomeVariantReport:
    _reset_torch_peak()
    load_started = perf_counter()
    with parent_run.step(f"load-static-home-pose-variant:{variant_id}"):
        backend = build_fall_adl_pose_backend(
            variant_id,
            yolo_model=yolo_model,
            yolo_device=yolo_device,
            yolo_image_size=yolo_image_size,
            yolo_confidence=yolo_confidence,
            rtmpose_detector_model=rtmpose_detector_model,
            rtmpose_pose_model=rtmpose_pose_model,
            rtmpose_device=rtmpose_device,
            rtmpose_detection_confidence=rtmpose_detection_confidence,
            torchvision_model=torchvision_model,
            torchvision_policy=torchvision_policy,
            torchvision_device=torchvision_device,
            torchvision_detection_confidence=torchvision_detection_confidence,
            torchvision_min_size=torchvision_min_size,
            torchvision_max_size=torchvision_max_size,
            track=False,
        )
    model_load_ms = (perf_counter() - load_started) * 1000.0
    try:
        bindings, corrections = correct_model_bindings(
            backend.bindings,
            variant_id=variant_id,
            policy_path=policy_path,
        )
        if variant_id == "torchvision-keypointrcnn":
            bindings = validate_torchvision_model_bindings(
                bindings,
                policy_path=torchvision_policy,
            )
        pose = _pose_binding(bindings)
        if variant_id == "yolo26n-pose" and pose.model_digest != YOLO26N_POSE_SHA256:
            raise ValueError("YOLO26n-pose weight digest is not the frozen V1 baseline")

        evaluations: list[StaticHomeCaseEvaluation] = []
        for case in cases:
            reset = getattr(backend, "reset", None)
            if reset is not None:
                reset()
            with parent_run.step(
                f"run-static-home-case:{variant_id}:{case.case_id}"
            ) as parent_step:
                with RunArtifacts(
                    runs_dir,
                    stage="v1-g4-static-home-person-case",
                    evidence_level=EvidenceLevel.E1,
                    configuration={
                        "variant_id": variant_id,
                        "case_id": case.case_id,
                        "scenario": case.scenario,
                        "source_image_sha256": case.image_sha256,
                        "matching_iou_threshold": iou_threshold,
                        "tracking_enabled": False,
                        "risk_assessment_emitted": False,
                        "alert_emitted": False,
                    },
                ) as child_run:
                    evaluation = _evaluate_case(
                        case=case,
                        variant_id=variant_id,
                        image_path=image_paths[case.case_id],
                        backend=backend,
                        run=child_run,
                        iou_threshold=iou_threshold,
                    )
                    evaluation_path = child_run.write_report(
                        "static-home-case-evaluation.json", evaluation
                    )
                parent_step.outputs.append(
                    f"../{child_run.run_id}/{child_run.relative(evaluation_path)}"
                )
                evaluations.append(evaluation)

        by_scenario: dict[str, list[StaticHomeCaseEvaluation]] = defaultdict(list)
        for evaluation in evaluations:
            by_scenario[evaluation.scenario].append(evaluation)
        inference = [item.inference_ms for item in evaluations]
        runtime_environment = _runtime_environment()
        runtime_environment["case_run_ids"] = [item.run_id for item in evaluations]
        return StaticHomeVariantReport(
            variant_id=variant_id,
            model_bindings=bindings,
            source_binding_license_corrections=corrections,
            case_count=len(evaluations),
            cases=evaluations,
            overall=_group_metrics(evaluations),
            by_scenario={
                key: _group_metrics(value)
                for key, value in sorted(by_scenario.items())
            },
            runtime_environment=runtime_environment,
            timing_ms={
                "model_load_wall": round(model_load_ms, 3),
                "pose_inference_total": round(sum(inference), 3),
                "pose_inference_first": round(inference[0], 3) if inference else 0.0,
                "pose_inference_mean": round(mean(inference), 3) if inference else 0.0,
                "pose_inference_p95": _percentile(inference, 0.95),
                "pose_inference_max": round(max(inference), 3) if inference else 0.0,
            },
            limitations=[
                "public_openimages_evidence_is_e1_and_not_target_device_evidence",
                "static_person_detection_only_without_temporal_fall_decision",
                "keypoint_geometry_is_not_scored",
                "tracking_is_disabled_for_independent_images",
            ],
        )
    finally:
        del backend
        _empty_cuda_cache()


def run_static_home_benchmark(
    *,
    static_home_cases_path: Path,
    runs_dir: Path,
    variants: list[str],
    model_binding_policy_path: Path,
    yolo_model: Path = Path("models/yolo26n-pose.pt"),
    yolo_device: str = "auto",
    yolo_image_size: int = 640,
    yolo_confidence: float = 0.35,
    rtmpose_detector_model: Path = Path(
        "models/rtmpose/yolox_m_humanart/yolox_m_humanart.onnx"
    ),
    rtmpose_pose_model: Path = Path(
        "models/rtmpose/rtmpose_m_humanart/rtmpose_m_humanart.onnx"
    ),
    rtmpose_device: str = "auto",
    rtmpose_detection_confidence: float = 0.05,
    torchvision_model: Path = Path(
        "models/torchvision/keypointrcnn_resnet50_fpn_coco-fc266e95.pth"
    ),
    torchvision_policy: Path = Path("configs/v1-m3-torchvision-pose-model.json"),
    torchvision_device: str = "auto",
    torchvision_detection_confidence: float = 0.5,
    torchvision_min_size: int = 800,
    torchvision_max_size: int = 1333,
) -> tuple[RunArtifacts, StaticHomeBenchmarkReport]:
    static_home_cases_path = Path(static_home_cases_path).resolve()
    model_binding_policy_path = Path(model_binding_policy_path).resolve()
    torchvision_policy = Path(torchvision_policy).resolve()
    suite, cases, attribution_path, dataset_lock_path = load_static_home_cases(
        static_home_cases_path
    )
    if not variants or len(variants) != len(set(variants)):
        raise ValueError("static home variants must be non-empty and unique")
    unknown = sorted(set(variants) - set(KNOWN_VARIANTS))
    if unknown:
        raise ValueError(f"unknown static home variants: {', '.join(unknown)}")
    if yolo_image_size <= 0 or not 0.0 <= yolo_confidence <= 1.0:
        raise ValueError("YOLO image size or confidence is invalid")
    if not 0.0 <= rtmpose_detection_confidence <= 1.0:
        raise ValueError("RTMPose detection confidence is invalid")
    if not 0.0 <= torchvision_detection_confidence <= 1.0:
        raise ValueError("TorchVision detection confidence is invalid")
    if torchvision_min_size <= 0 or torchvision_max_size < torchvision_min_size:
        raise ValueError("TorchVision image size bounds are invalid")
    uses_torchvision = "torchvision-keypointrcnn" in variants
    if uses_torchvision:
        load_torchvision_pose_policy(torchvision_policy)

    image_paths = {
        case.case_id: _verify_case_image(static_home_cases_path, case)
        for case in cases
    }
    suite_digest = sha256_file(static_home_cases_path)
    policy_digest = sha256_file(model_binding_policy_path)
    torchvision_policy_digest = (
        sha256_file(torchvision_policy) if uses_torchvision else ""
    )
    pose_model_policy_sha256s = {
        "rtmpose-m-humanart": policy_digest,
        "torchvision-keypointrcnn": torchvision_policy_digest,
    }
    pose_model_policy_sha256s = {
        variant: digest
        for variant, digest in pose_model_policy_sha256s.items()
        if variant in variants
    }
    iou_threshold = float(suite["matching_iou_threshold"])
    configuration = {
        "command": "benchmark-static-home",
        "suite_id": suite["suite_id"],
        "suite_manifest_sha256": suite_digest,
        "source_manifest_sha256": suite["source_manifest_sha256"],
        "variants": variants,
        "model_binding_policy_sha256": policy_digest,
        "pose_model_policy_sha256s": pose_model_policy_sha256s,
        "matching_iou_threshold": iou_threshold,
        "tracking_enabled": False,
        "yolo_image_size": yolo_image_size,
        "yolo_confidence": yolo_confidence,
        "rtmpose_detection_confidence": rtmpose_detection_confidence,
        "torchvision_detection_confidence": torchvision_detection_confidence,
        "torchvision_min_size": torchvision_min_size,
        "torchvision_max_size": torchvision_max_size,
        "risk_assessment_emitted": False,
        "alert_emitted": False,
    }
    with RunArtifacts(
        runs_dir,
        stage="v1-g4-static-home-person-benchmark",
        evidence_level=EvidenceLevel.E1,
        configuration=configuration,
    ) as run:
        with run.step("record-static-home-benchmark-inputs") as step:
            input_assets = [
                (static_home_cases_path, "static_home_cases"),
                (attribution_path, "static_home_attribution"),
                (dataset_lock_path, "static_home_dataset_lock"),
                (model_binding_policy_path, "pose_model_binding_policy"),
            ]
            if uses_torchvision:
                input_assets.append(
                    (torchvision_policy, "torchvision_pose_model_policy")
                )
            for path, kind in input_assets:
                run.record_asset(
                    _source_asset(
                        path,
                        kind=kind,
                        modality=Modality.UNKNOWN,
                        privacy_level=PrivacyLevel.AGGREGATE,
                        contains_raw_media=False,
                    )
                )
            step.outputs.append("source_assets.jsonl")
        variant_reports = [
            _variant_report(
                variant_id=variant,
                cases=cases,
                image_paths=image_paths,
                runs_dir=Path(runs_dir),
                parent_run=run,
                policy_path=model_binding_policy_path,
                iou_threshold=iou_threshold,
                yolo_model=Path(yolo_model),
                yolo_device=yolo_device,
                yolo_image_size=yolo_image_size,
                yolo_confidence=yolo_confidence,
                rtmpose_detector_model=Path(rtmpose_detector_model),
                rtmpose_pose_model=Path(rtmpose_pose_model),
                rtmpose_device=rtmpose_device,
                rtmpose_detection_confidence=rtmpose_detection_confidence,
                torchvision_model=Path(torchvision_model),
                torchvision_policy=torchvision_policy,
                torchvision_device=torchvision_device,
                torchvision_detection_confidence=(
                    torchvision_detection_confidence
                ),
                torchvision_min_size=torchvision_min_size,
                torchvision_max_size=torchvision_max_size,
            )
            for variant in variants
        ]
        dataset = suite["dataset"]
        report = StaticHomeBenchmarkReport(
            suite_id=suite["suite_id"],
            benchmark_version=STATIC_HOME_BENCHMARK_VERSION,
            suite_manifest_sha256=suite_digest,
            source_manifest_sha256=suite["source_manifest_sha256"],
            model_binding_policy_sha256=policy_digest,
            pose_model_policy_sha256s=pose_model_policy_sha256s,
            dataset_id=dataset["dataset_id"],
            dataset_version=dataset["version"],
            annotation_license=dataset["annotation_license"],
            required_image_license=dataset["required_image_license"],
            matching_iou_threshold=iou_threshold,
            case_count=len(cases),
            variants=variant_reports,
            limitations=[
                *suite.get("limitations", []),
                "this_is_a_static_person_detection_stress_run_not_a_fall_benchmark",
                "no_motion_tracking_risk_assessment_or_alert_is_evaluated",
            ],
        )
        with run.step("write-static-home-benchmark-report") as step:
            report_path = run.write_report(
                "static-home-benchmark-report.json", report
            )
            step.outputs.append(run.relative(report_path))
    return run, report
