from __future__ import annotations

import gc
import json
import os
import platform
import socket
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from .artifacts import RunArtifacts
from .contracts import (
    EvidenceLevel,
    FallAdlBenchmarkReport,
    FallAdlCaseEvaluation,
    FallAdlGroupMetrics,
    FallAdlVariantReport,
    FallAdlVideoCase,
    FallMotionFrameValue,
    FeatureEvent,
    Modality,
    ModelBinding,
    PrivacyLevel,
    SourceAsset,
    SourceType,
    TimeRange,
)
from .fall_adl_preparation import (
    EXPECTED_DATASET_DOI,
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_LICENSE,
    EXPECTED_DATASET_VERSION,
)
from .fall_features import (
    FallMotionFeatureExtractor,
    correct_model_bindings,
    load_fall_feature_config,
    summarize_fall_features,
)
from .pose_backend import PoseBackend, PoseDetection, UltralyticsPoseBackend
from .privacy import safe_local_uri, sha256_file
from .streaming import OpenCVVideoReplay
from .torchvision_pose_backend import (
    TORCHVISION_KEYPOINT_RCNN_SHA256,
    TORCHVISION_MODEL_ARTIFACT_LICENSE,
    load_torchvision_pose_policy,
)


FALL_ADL_BENCHMARK_VERSION = "fall-adl-negative-benchmark-v0.1.0"
KNOWN_VARIANTS = (
    "yolo26n-pose",
    "rtmpose-m-humanart",
    "torchvision-keypointrcnn",
)
YOLO26N_POSE_SHA256 = (
    "eb3bb8268828aeaf515cec23a4bfafd793944a86fe9af94ba7823609c14522a9"
)
FROZEN_SUBJECT_LIGHTS = {
    "subject-01": ("natural_210_lux", 210),
    "subject-06": ("zero_lux_ir", 0),
    "subject-10": ("artificial_130_lux", 130),
}
FROZEN_ACTIVITIES = ("pick_up_object", "sit_down", "kneel", "walk")


@dataclass(frozen=True)
class _CaseRuntime:
    evaluation: FallAdlCaseEvaluation
    values: list[FallMotionFrameValue]
    inference_latencies_ms: list[float]
    feature_latencies_ms: list[float]
    replay_wall_ms: float


def _safe_relative_path(manifest_path: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("fall ADL video path must remain relative to the suite")
    root = Path(manifest_path).parent.resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("fall ADL video path escapes the prepared suite")
    return resolved


def load_fall_adl_cases(
    manifest_path: Path,
) -> tuple[dict[str, Any], list[FallAdlVideoCase]]:
    manifest_path = Path(manifest_path)
    with manifest_path.open(encoding="utf-8") as stream:
        suite = json.load(stream)
    if suite.get("schema_version") != "1.0":
        raise ValueError("unsupported fall ADL suite schema")
    if suite.get("evidence_level") != EvidenceLevel.E1.value:
        raise ValueError("fall ADL suite must remain E1")
    if not isinstance(suite.get("suite_id"), str) or not suite["suite_id"]:
        raise ValueError("fall ADL suite id is missing")
    dataset = suite.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("fall ADL suite dataset metadata is missing")
    expected = {
        "dataset_id": EXPECTED_DATASET_ID,
        "version": EXPECTED_DATASET_VERSION,
        "doi": EXPECTED_DATASET_DOI,
        "license": EXPECTED_DATASET_LICENSE,
    }
    for key, value in expected.items():
        if dataset.get(key) != value:
            raise ValueError(f"fall ADL suite dataset {key} is not frozen")
    payloads = suite.get("cases")
    if not isinstance(payloads, list):
        raise ValueError("fall ADL suite cases must be a list")
    cases = [FallAdlVideoCase.model_validate(item) for item in payloads]
    if suite.get("case_count") != len(cases) or len(cases) != 12:
        raise ValueError("fall ADL suite must contain the frozen 12 cases")

    case_ids = [case.case_id for case in cases]
    video_paths = [case.video_path for case in cases]
    source_ids = [case.source_file_id for case in cases]
    if any(len(values) != len(set(values)) for values in (case_ids, video_paths, source_ids)):
        raise ValueError("fall ADL suite contains duplicate identifiers")
    matrix = {(case.subject_ref, case.activity) for case in cases}
    expected_matrix = {
        (subject, activity)
        for subject in FROZEN_SUBJECT_LIGHTS
        for activity in FROZEN_ACTIVITIES
    }
    if matrix != expected_matrix:
        raise ValueError("fall ADL suite no longer has the frozen subject/activity matrix")
    for case in cases:
        if case.evidence_level is not EvidenceLevel.E1:
            raise ValueError("fall ADL cases must remain E1")
        illumination, lux = FROZEN_SUBJECT_LIGHTS[case.subject_ref]
        if case.illumination_group != illumination or case.approx_lux != lux:
            raise ValueError("fall ADL subject/light binding has drifted")
        if case.dataset_id != EXPECTED_DATASET_ID:
            raise ValueError("fall ADL case dataset id disagrees with the suite")
        if case.dataset_version != EXPECTED_DATASET_VERSION:
            raise ValueError("fall ADL case dataset version disagrees with the suite")
        _safe_relative_path(manifest_path, case.video_path)
    return suite, cases


def _verify_case_video(manifest_path: Path, case: FallAdlVideoCase) -> Path:
    path = _safe_relative_path(manifest_path, case.video_path)
    if not path.is_file():
        raise FileNotFoundError(f"prepared fall ADL video is missing: {case.case_id}")
    if path.stat().st_size != case.video_byte_size:
        raise ValueError(f"prepared fall ADL video size mismatch: {case.case_id}")
    if sha256_file(path) != case.video_sha256:
        raise ValueError(f"prepared fall ADL video digest mismatch: {case.case_id}")
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
        },
    )


def _pose_binding(bindings: list[ModelBinding]) -> ModelBinding:
    matches = [
        item
        for item in bindings
        if item.task in {"human_pose_estimation", "human_pose_tracking"}
    ]
    if len(matches) != 1 or matches[0].model_digest is None:
        raise ValueError("fall ADL backend must expose one digest-bound pose model")
    if matches[0].configuration.get("keypoint_layout") != "COCO-17":
        raise ValueError("fall ADL backend must expose the COCO-17 keypoint layout")
    return matches[0]


def _validate_variant_bindings(
    variant_id: str,
    bindings: list[ModelBinding],
    *,
    torchvision_policy_sha256: str,
) -> None:
    pose = _pose_binding(bindings)
    if variant_id == "yolo26n-pose" and pose.model_digest != YOLO26N_POSE_SHA256:
        raise ValueError("YOLO26n-pose weight digest is not the frozen V1 baseline")
    if variant_id == "torchvision-keypointrcnn":
        if pose.model_digest != TORCHVISION_KEYPOINT_RCNN_SHA256:
            raise ValueError("Keypoint R-CNN weight digest is not frozen")
        if pose.license != TORCHVISION_MODEL_ARTIFACT_LICENSE:
            raise ValueError("Keypoint R-CNN artifact license must remain fail closed")
        if (
            pose.configuration.get("license_policy_sha256")
            != torchvision_policy_sha256
        ):
            raise ValueError("Keypoint R-CNN policy binding digest is not frozen")


def _visible_ratio(detections: list[PoseDetection], threshold: float = 0.5) -> float | None:
    scores = [
        float(point[2])
        for detection in detections
        for point in detection.keypoints_xyc
        if len(point) >= 3
    ]
    if not scores:
        return None
    return sum(score >= threshold for score in scores) / len(scores)


def _pose_feature(
    *,
    run: RunArtifacts,
    sequence: int,
    timestamp_ms: int,
    sample_fps: float,
    detections: list[PoseDetection],
    binding: ModelBinding,
) -> FeatureEvent:
    confidences = [
        item.confidence for item in detections if item.confidence is not None
    ]
    quality = _visible_ratio(detections)
    return FeatureEvent(
        feature_id=f"feature_{run.run_id}_pose_{sequence:06d}",
        observation_id=f"observation_{run.run_id}_video",
        feature_type="video.pose_frame",
        time_range=TimeRange(
            start_ms=timestamp_ms,
            end_ms=timestamp_ms + max(1, round(1000.0 / sample_fps)),
        ),
        value={
            "frame_sequence": sequence,
            "person_count": len(detections),
            "detections": [
                {
                    "bbox_xyxy": item.bbox_xyxy,
                    "keypoints_xyc": item.keypoints_xyc,
                    "confidence": item.confidence,
                    "track_id": item.track_id,
                }
                for item in detections
            ],
        },
        confidence=round(mean(confidences), 6) if confidences else None,
        quality=round(quality, 6) if quality is not None else None,
        extractor_name=binding.backend,
        extractor_version=binding.model_version or "unknown",
        model_digest=binding.model_digest,
        privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
        limitations=[
            "uncalibrated_image_coordinates",
            "coco_17_keypoints",
            "public_dataset_e1_only",
        ],
    )


def _fall_feature(
    *, run: RunArtifacts, source: FeatureEvent, value: FallMotionFrameValue
) -> FeatureEvent:
    return FeatureEvent(
        feature_id=f"feature_{run.run_id}_fall_{value.frame_sequence:06d}",
        observation_id=source.observation_id,
        feature_type="video.fall_motion_frame",
        time_range=source.time_range,
        value=value.model_dump(mode="json"),
        extractor_name="kangshield-fall-motion-features",
        extractor_version=value.feature_version,
        privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
        source_feature_refs=[source.feature_id],
        limitations=[
            "not_a_risk_assessment",
            "largest_bbox_is_not_person_identity",
            "action_level_no_fall_label_only",
            "public_dataset_e1_only",
        ],
    )


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def _rtf(wall_ms: float, media_ms: int) -> float:
    return round(wall_ms / media_ms, 6) if media_ms > 0 else 0.0


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


def build_fall_adl_pose_backend(
    variant_id: str,
    *,
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
    track: bool = True,
) -> PoseBackend:
    if variant_id == "yolo26n-pose":
        return UltralyticsPoseBackend(
            model=yolo_model,
            device=yolo_device,
            image_size=yolo_image_size,
            confidence=yolo_confidence,
            track=track,
        )
    if variant_id == "rtmpose-m-humanart":
        from .rtmpose_backend import HumanArtRTMPoseBackend

        return HumanArtRTMPoseBackend(
            detector_model=rtmpose_detector_model,
            pose_model=rtmpose_pose_model,
            device=rtmpose_device,
            detection_confidence=rtmpose_detection_confidence,
            track=track,
        )
    if variant_id == "torchvision-keypointrcnn":
        from .torchvision_pose_backend import TorchvisionKeypointRCNNBackend

        return TorchvisionKeypointRCNNBackend(
            model=torchvision_model,
            policy_path=torchvision_policy,
            device=torchvision_device,
            detection_confidence=torchvision_detection_confidence,
            min_size=torchvision_min_size,
            max_size=torchvision_max_size,
            track=track,
        )
    raise ValueError(f"unknown fall ADL pose variant: {variant_id}")


def _evaluate_case(
    *,
    case: FallAdlVideoCase,
    variant_id: str,
    video_path: Path,
    backend: PoseBackend,
    binding: ModelBinding,
    config_path: Path,
    run: RunArtifacts,
    sample_fps: float,
    max_duration_s: float,
) -> _CaseRuntime:
    config = load_fall_feature_config(config_path)
    run.record_asset(
        _source_asset(
            video_path,
            kind="caucafall_adl_source_video",
            modality=Modality.VIDEO,
            privacy_level=PrivacyLevel.RAW_SENSITIVE,
            contains_raw_media=True,
        )
    )
    replay = OpenCVVideoReplay(
        video_path, sample_fps=sample_fps, max_duration_s=max_duration_s
    )
    extractor: FallMotionFeatureExtractor | None = None
    values: list[FallMotionFrameValue] = []
    inference_latencies: list[float] = []
    feature_latencies: list[float] = []
    frames_with_people = 0
    tracked_frames = 0
    track_ids: set[int] = set()
    replay_started = perf_counter()
    with run.step("extract-pose-and-fall-motion-features") as step:
        for sequence, packet in enumerate(replay):
            if extractor is None:
                height, width = packet.frame.shape[:2]
                extractor = FallMotionFeatureExtractor(
                    config, frame_width=int(width), frame_height=int(height)
                )
            inference_started = perf_counter()
            detections = backend.infer(packet.frame)
            inference_latencies.append((perf_counter() - inference_started) * 1000.0)
            pose_event = _pose_feature(
                run=run,
                sequence=sequence,
                timestamp_ms=packet.timestamp_ms,
                sample_fps=sample_fps,
                detections=detections,
                binding=binding,
            )
            feature_started = perf_counter()
            value = extractor.process(pose_event)
            feature_latencies.append((perf_counter() - feature_started) * 1000.0)
            values.append(value)
            if detections:
                frames_with_people += 1
            ids = {item.track_id for item in detections if item.track_id is not None}
            if ids:
                tracked_frames += 1
                track_ids.update(int(item) for item in ids)
            run.record_feature(pose_event)
            run.record_feature(_fall_feature(run=run, source=pose_event, value=value))
        step.outputs.append("features.jsonl")
    replay_wall_ms = (perf_counter() - replay_started) * 1000.0
    if extractor is None or not values:
        raise ValueError(f"fall ADL video produced no sampled frames: {case.case_id}")
    media_duration_ms = values[-1].timestamp_ms + max(1, round(1000.0 / sample_fps))
    sampled = len(values)
    evaluation = FallAdlCaseEvaluation(
        case_id=case.case_id,
        variant_id=variant_id,
        run_id=run.run_id,
        dataset_id=case.dataset_id,
        activity=case.activity,
        illumination_group=case.illumination_group,
        source_video_sha256=case.video_sha256,
        frame_width=extractor.frame_width,
        frame_height=extractor.frame_height,
        sampled_frames=sampled,
        frames_with_people=frames_with_people,
        pose_frame_coverage=round(frames_with_people / sampled, 6),
        tracked_frames=tracked_frames,
        tracking_coverage=(
            round(tracked_frames / frames_with_people, 6)
            if frames_with_people
            else 0.0
        ),
        unique_track_count=len(track_ids),
        evaluated_media_duration_ms=media_duration_ms,
        fall_feature_metrics=summarize_fall_features(values),
        timing_ms={
            "replay_wall": round(replay_wall_ms, 3),
            "pose_inference_total": round(sum(inference_latencies), 3),
            "pose_inference_first": (
                round(inference_latencies[0], 3) if inference_latencies else 0.0
            ),
            "pose_inference_mean": (
                round(mean(inference_latencies), 3) if inference_latencies else 0.0
            ),
            "pose_inference_p95": _percentile(inference_latencies, 0.95),
            "fall_feature_total": round(sum(feature_latencies), 3),
        },
        realtime_factors={
            "pose_inference": _rtf(sum(inference_latencies), media_duration_ms),
            "fall_feature": _rtf(sum(feature_latencies), media_duration_ms),
            "replay_pipeline": _rtf(replay_wall_ms, media_duration_ms),
        },
        limitations=[
            *case.limitations,
            "no_fall_classifier_or_false_alarm_decision_is_evaluated",
            "motion_proxy_activation_is_not_a_false_alarm",
            "coverage_requires_a_returned_person_box_not_correct_pose_geometry",
        ],
    )
    return _CaseRuntime(
        evaluation=evaluation,
        values=values,
        inference_latencies_ms=inference_latencies,
        feature_latencies_ms=feature_latencies,
        replay_wall_ms=replay_wall_ms,
    )


def _group_metrics(runtimes: list[_CaseRuntime]) -> FallAdlGroupMetrics:
    evaluations = [item.evaluation for item in runtimes]
    sampled = sum(item.sampled_frames for item in evaluations)
    people = sum(item.frames_with_people for item in evaluations)
    return FallAdlGroupMetrics(
        case_count=len(evaluations),
        sampled_frames=sampled,
        frames_with_people=people,
        pose_frame_coverage=round(people / sampled, 6) if sampled else 0.0,
        fall_feature_metrics=summarize_fall_features(
            value for runtime in runtimes for value in runtime.values
        ),
    )


def _variant_report(
    *,
    variant_id: str,
    cases: list[FallAdlVideoCase],
    video_paths: dict[str, Path],
    runs_dir: Path,
    parent_run: RunArtifacts,
    config_path: Path,
    policy_path: Path,
    sample_fps: float,
    max_duration_s: float,
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
    torchvision_policy_sha256: str,
    torchvision_device: str,
    torchvision_detection_confidence: float,
    torchvision_min_size: int,
    torchvision_max_size: int,
) -> FallAdlVariantReport:
    _reset_torch_peak()
    load_started = perf_counter()
    with parent_run.step(f"load-fall-adl-pose-variant:{variant_id}"):
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
            torchvision_detection_confidence=(
                torchvision_detection_confidence
            ),
            torchvision_min_size=torchvision_min_size,
            torchvision_max_size=torchvision_max_size,
        )
    model_load_ms = (perf_counter() - load_started) * 1000.0
    try:
        bindings, corrections = correct_model_bindings(
            backend.bindings, variant_id=variant_id, policy_path=policy_path
        )
        _validate_variant_bindings(
            variant_id,
            bindings,
            torchvision_policy_sha256=torchvision_policy_sha256,
        )
        binding = _pose_binding(bindings)
        runtimes: list[_CaseRuntime] = []
        for case in cases:
            reset = getattr(backend, "reset", None)
            if reset is not None:
                reset()
            with parent_run.step(
                f"run-fall-adl-case:{variant_id}:{case.case_id}"
            ) as parent_step:
                with RunArtifacts(
                    runs_dir,
                    stage="v1-g4-fall-adl-negative-case",
                    evidence_level=EvidenceLevel.E1,
                    configuration={
                        "variant_id": variant_id,
                        "case_id": case.case_id,
                        "source_video_sha256": case.video_sha256,
                        "sample_fps": sample_fps,
                        "max_duration_s": max_duration_s,
                        "risk_assessment_emitted": False,
                        "alert_emitted": False,
                    },
                ) as child_run:
                    runtime = _evaluate_case(
                        case=case,
                        variant_id=variant_id,
                        video_path=video_paths[case.case_id],
                        backend=backend,
                        binding=binding,
                        config_path=config_path,
                        run=child_run,
                        sample_fps=sample_fps,
                        max_duration_s=max_duration_s,
                    )
                    evaluation_path = child_run.write_report(
                        "fall-adl-case-evaluation.json", runtime.evaluation
                    )
                parent_step.outputs.append(
                    f"../{child_run.run_id}/{child_run.relative(evaluation_path)}"
                )
                runtimes.append(runtime)

        by_activity: dict[str, list[_CaseRuntime]] = defaultdict(list)
        by_illumination: dict[str, list[_CaseRuntime]] = defaultdict(list)
        for runtime in runtimes:
            by_activity[runtime.evaluation.activity].append(runtime)
            by_illumination[runtime.evaluation.illumination_group].append(runtime)
        evaluations = [item.evaluation for item in runtimes]
        media_ms = sum(item.evaluated_media_duration_ms for item in evaluations)
        inference = [
            latency for runtime in runtimes for latency in runtime.inference_latencies_ms
        ]
        feature = [
            latency for runtime in runtimes for latency in runtime.feature_latencies_ms
        ]
        replay_wall_ms = sum(item.replay_wall_ms for item in runtimes)
        runtime_environment = _runtime_environment()
        runtime_environment["case_run_ids"] = [item.run_id for item in evaluations]
        return FallAdlVariantReport(
            variant_id=variant_id,
            model_bindings=bindings,
            source_binding_license_corrections=corrections,
            case_count=len(evaluations),
            cases=evaluations,
            overall=_group_metrics(runtimes),
            by_activity={
                key: _group_metrics(value) for key, value in sorted(by_activity.items())
            },
            by_illumination={
                key: _group_metrics(value)
                for key, value in sorted(by_illumination.items())
            },
            runtime_environment=runtime_environment,
            timing_ms={
                "model_load_wall": round(model_load_ms, 3),
                "replay_pipeline_total": round(replay_wall_ms, 3),
                "pose_inference_total": round(sum(inference), 3),
                "pose_inference_first": round(inference[0], 3) if inference else 0.0,
                "pose_inference_mean": round(mean(inference), 3) if inference else 0.0,
                "pose_inference_p95": _percentile(inference, 0.95),
                "pose_inference_max": round(max(inference), 3) if inference else 0.0,
                "fall_feature_total": round(sum(feature), 3),
            },
            realtime_factors={
                "pose_inference": _rtf(sum(inference), media_ms),
                "fall_feature": _rtf(sum(feature), media_ms),
                "replay_pipeline": _rtf(replay_wall_ms, media_ms),
                "cold_start_pipeline": _rtf(replay_wall_ms + model_load_ms, media_ms),
            },
            limitations=[
                "public_caucafall_evidence_is_e1_and_not_target_device_evidence",
                "action_labels_are_no_fall_at_clip_level_without_event_timestamps",
                "motion_proxy_activation_is_reported_but_is_not_a_false_alarm",
                "no_classifier_threshold_is_tuned_or_evaluated",
                "pose_coverage_does_not_validate_keypoint_geometry",
            ],
        )
    finally:
        del backend
        _empty_cuda_cache()


def run_fall_adl_benchmark(
    *,
    fall_adl_cases_path: Path,
    runs_dir: Path,
    variants: list[str],
    config_path: Path,
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
    torchvision_policy: Path = Path(
        "configs/v1-m3-torchvision-pose-model.json"
    ),
    torchvision_device: str = "auto",
    torchvision_detection_confidence: float = 0.5,
    torchvision_min_size: int = 800,
    torchvision_max_size: int = 1333,
    sample_fps: float = 5.0,
    max_duration_s: float = 30.0,
) -> tuple[RunArtifacts, FallAdlBenchmarkReport]:
    fall_adl_cases_path = Path(fall_adl_cases_path).resolve()
    config_path = Path(config_path).resolve()
    model_binding_policy_path = Path(model_binding_policy_path).resolve()
    torchvision_policy = Path(torchvision_policy).resolve()
    suite, cases = load_fall_adl_cases(fall_adl_cases_path)
    load_fall_feature_config(config_path)
    if not variants or len(variants) != len(set(variants)):
        raise ValueError("fall ADL variants must be non-empty and unique")
    unknown = sorted(set(variants) - set(KNOWN_VARIANTS))
    if unknown:
        raise ValueError(f"unknown fall ADL variants: {', '.join(unknown)}")
    if sample_fps <= 0 or max_duration_s <= 0:
        raise ValueError("sample_fps and max_duration_s must be positive")
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

    video_paths = {
        case.case_id: _verify_case_video(fall_adl_cases_path, case) for case in cases
    }
    suite_digest = sha256_file(fall_adl_cases_path)
    config_digest = sha256_file(config_path)
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
    configuration = {
        "command": "benchmark-fall-adl",
        "suite_id": suite["suite_id"],
        "suite_manifest_sha256": suite_digest,
        "variants": variants,
        "feature_version": load_fall_feature_config(config_path).feature_version,
        "configuration_sha256": config_digest,
        "model_binding_policy_sha256": policy_digest,
        "pose_model_policy_sha256s": pose_model_policy_sha256s,
        "sample_fps": sample_fps,
        "max_duration_s": max_duration_s,
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
        stage="v1-g4-fall-adl-negative-benchmark",
        evidence_level=EvidenceLevel.E1,
        configuration=configuration,
    ) as run:
        with run.step("record-fall-adl-benchmark-inputs") as step:
            input_assets = [
                (fall_adl_cases_path, "fall_adl_cases", Modality.VIDEO),
                (config_path, "fall_feature_config", Modality.UNKNOWN),
                (
                    model_binding_policy_path,
                    "pose_model_binding_policy",
                    Modality.UNKNOWN,
                ),
            ]
            if uses_torchvision:
                input_assets.append(
                    (
                        torchvision_policy,
                        "torchvision_pose_model_policy",
                        Modality.UNKNOWN,
                    )
                )
            for path, kind, modality in input_assets:
                run.record_asset(
                    _source_asset(
                        path,
                        kind=kind,
                        modality=modality,
                        privacy_level=PrivacyLevel.AGGREGATE,
                        contains_raw_media=False,
                    )
                )
            step.outputs.append("source_assets.jsonl")
        variant_reports = [
            _variant_report(
                variant_id=variant,
                cases=cases,
                video_paths=video_paths,
                runs_dir=Path(runs_dir),
                parent_run=run,
                config_path=config_path,
                policy_path=model_binding_policy_path,
                sample_fps=sample_fps,
                max_duration_s=max_duration_s,
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
                torchvision_policy_sha256=torchvision_policy_digest,
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
        report = FallAdlBenchmarkReport(
            suite_id=suite["suite_id"],
            benchmark_version=FALL_ADL_BENCHMARK_VERSION,
            feature_version=load_fall_feature_config(config_path).feature_version,
            suite_manifest_sha256=suite_digest,
            configuration_sha256=config_digest,
            model_binding_policy_sha256=policy_digest,
            pose_model_policy_sha256s=pose_model_policy_sha256s,
            dataset_id=dataset["dataset_id"],
            dataset_version=dataset["version"],
            dataset_doi=dataset["doi"],
            dataset_license=dataset["license"],
            case_count=len(cases),
            variants=variant_reports,
            limitations=[
                *suite.get("limitations", []),
                "this_is_a_pose_and_motion_proxy_stress_run_not_a_classifier_benchmark",
                "no_risk_assessment_or_alert_is_emitted",
            ],
        )
        with run.step("write-fall-adl-benchmark-report") as step:
            report_path = run.write_report("fall-adl-benchmark-report.json", report)
            step.outputs.append(run.relative(report_path))
    return run, report
