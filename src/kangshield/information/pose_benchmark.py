from __future__ import annotations

import bisect
import gc
import json
import os
import platform
import socket
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Callable

from .artifacts import RunArtifacts
from .contracts import (
    DatasetBenchmarkCase,
    DatasetPhaseMetrics,
    EvidenceLevel,
    FeatureEvent,
    ModelBinding,
    PoseBenchmarkCaseEvaluation,
    PoseBenchmarkVariantReport,
    PoseModelComparisonReport,
    PrivacyLevel,
    TimeRange,
)
from .dataset_benchmark import PHASE_NAMES, load_benchmark_cases
from .dataset_preparation import sha256_file
from .pose_backend import PoseBackend, PoseDetection, UltralyticsPoseBackend
from .streaming import OpenCVVideoReplay


POSE_BENCHMARK_VERSION = "pose-model-comparison-v0.1.0"
KNOWN_VARIANTS = ("yolo26n-pose", "rtmpose-m-humanart")


@dataclass(frozen=True)
class _FrameResult:
    timestamp_ms: int
    phase: str
    annotation_error_ms: int
    detections: list[PoseDetection]
    latency_ms: float


@dataclass(frozen=True)
class _CaseRuntime:
    evaluation: PoseBenchmarkCaseEvaluation
    latencies_ms: list[float]
    replay_wall_ms: float


def _resolved_path(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else manifest_path.parent / path


def _read_annotation(path: Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        annotation = json.load(stream)
    if annotation.get("schema_version") != "1.0":
        raise ValueError(f"unsupported annotation schema: {path}")
    frames = annotation.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError(f"annotation contains no frames: {path}")
    return annotation


def _nearest_annotation(
    timestamps: list[int],
    frames: list[dict[str, Any]],
    timestamp_ms: int,
) -> tuple[dict[str, Any], int]:
    insertion = bisect.bisect_left(timestamps, timestamp_ms)
    candidates = [
        index
        for index in (insertion - 1, insertion)
        if 0 <= index < len(timestamps)
    ]
    index = min(candidates, key=lambda item: abs(timestamps[item] - timestamp_ms))
    return frames[index], abs(timestamps[index] - timestamp_ms)


def _point_confidences(detections: list[PoseDetection]) -> list[float]:
    return [
        float(point[2])
        for detection in detections
        for point in detection.keypoints_xyc
        if len(point) >= 3
    ]


def _visible_ratio(detections: list[PoseDetection], threshold: float) -> float | None:
    scores = _point_confidences(detections)
    if not scores:
        return None
    return sum(score >= threshold for score in scores) / len(scores)


def _largest_bbox_ratio(detections: list[PoseDetection]) -> float | None:
    candidates: list[tuple[float, float]] = []
    for detection in detections:
        x1, y1, x2, y2 = detection.bbox_xyxy
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        if height > 0.0:
            candidates.append((width * height, width / height))
    return max(candidates)[1] if candidates else None


def phase_metrics(results: list[_FrameResult]) -> DatasetPhaseMetrics:
    positive = [item for item in results if item.detections]
    tracked = [
        item
        for item in positive
        if any(detection.track_id is not None for detection in item.detections)
    ]
    quality = [
        value
        for item in positive
        if (value := _visible_ratio(item.detections, 0.5)) is not None
    ]
    ratios = [
        value
        for item in positive
        if (value := _largest_bbox_ratio(item.detections)) is not None
    ]
    return DatasetPhaseMetrics(
        sampled_frames=len(results),
        frames_with_people=len(positive),
        pose_frame_coverage=(
            round(len(positive) / len(results), 6) if results else 0.0
        ),
        tracked_frames=len(tracked),
        tracking_coverage=(
            round(len(tracked) / len(positive), 6) if positive else 0.0
        ),
        mean_pose_quality=round(mean(quality), 6) if quality else None,
        mean_bbox_width_height_ratio=(
            round(mean(ratios), 6) if ratios else None
        ),
    )


def _mean_or_none(values: list[float]) -> float | None:
    return round(mean(values), 6) if values else None


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def _rtf(wall_ms: float, media_ms: int) -> float:
    return round(wall_ms / media_ms, 6) if media_ms > 0 else 0.0


def _pose_binding(bindings: list[ModelBinding]) -> ModelBinding | None:
    return next(
        (
            binding
            for binding in bindings
            if binding.task in {"human_pose_estimation", "human_pose_tracking"}
        ),
        None,
    )


def _pose_feature(
    *,
    run_id: str,
    sequence: int,
    timestamp_ms: int,
    sample_fps: float,
    detections: list[PoseDetection],
    binding: ModelBinding | None,
) -> FeatureEvent:
    confidences = [
        detection.confidence
        for detection in detections
        if detection.confidence is not None
    ]
    return FeatureEvent(
        feature_id=f"feature_{run_id}_pose_compare_{sequence:06d}",
        observation_id=f"observation_{run_id}_video",
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
                    "bbox_xyxy": detection.bbox_xyxy,
                    "keypoints_xyc": detection.keypoints_xyc,
                    "confidence": detection.confidence,
                    "track_id": detection.track_id,
                }
                for detection in detections
            ],
        },
        confidence=round(mean(confidences), 6) if confidences else None,
        quality=(
            round(value, 6)
            if (value := _visible_ratio(detections, 0.5)) is not None
            else None
        ),
        extractor_name=binding.backend if binding else "unknown-pose-backend",
        extractor_version=(binding.model_version if binding else None) or "unknown",
        model_digest=binding.model_digest if binding else None,
        privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
        limitations=[
            "uncalibrated_image_coordinates",
            "coco_17_keypoints",
            "public_dataset_e1_only",
        ],
    )


def evaluate_pose_case(
    *,
    case: DatasetBenchmarkCase,
    variant_id: str,
    benchmark_cases_path: Path,
    backend: PoseBackend,
    run: RunArtifacts,
    sample_fps: float,
    max_duration_s: float,
) -> _CaseRuntime:
    annotation_path = _resolved_path(benchmark_cases_path, case.annotation_path)
    annotation = _read_annotation(annotation_path)
    frames = sorted(
        annotation["frames"], key=lambda item: item["replay_timestamp_ms"]
    )
    timestamps = [int(item["replay_timestamp_ms"]) for item in frames]
    binding = _pose_binding(backend.bindings)
    results: list[_FrameResult] = []
    replay_started = perf_counter()
    replay = OpenCVVideoReplay(
        _resolved_path(benchmark_cases_path, case.video_path),
        sample_fps=sample_fps,
        max_duration_s=max_duration_s,
    )
    with run.step("extract-pose-comparison-features") as step:
        for sequence, packet in enumerate(replay):
            started = perf_counter()
            detections = backend.infer(packet.frame)
            latency_ms = (perf_counter() - started) * 1000.0
            annotation_frame, error = _nearest_annotation(
                timestamps,
                frames,
                packet.timestamp_ms,
            )
            label = annotation_frame.get("posture_label")
            if label not in PHASE_NAMES:
                raise ValueError(f"unexpected posture label: {label}")
            phase = PHASE_NAMES[label]
            result = _FrameResult(
                timestamp_ms=packet.timestamp_ms,
                phase=phase,
                annotation_error_ms=error,
                detections=detections,
                latency_ms=latency_ms,
            )
            results.append(result)
            run.record_feature(
                _pose_feature(
                    run_id=run.run_id,
                    sequence=sequence,
                    timestamp_ms=packet.timestamp_ms,
                    sample_fps=sample_fps,
                    detections=detections,
                    binding=binding,
                )
            )
        step.outputs.append("features.jsonl")
    replay_wall_ms = (perf_counter() - replay_started) * 1000.0
    latencies = [item.latency_ms for item in results]
    overall = phase_metrics(results)
    positive = [item for item in results if item.detections]
    detection_confidences = [
        float(detection.confidence)
        for item in positive
        for detection in item.detections
        if detection.confidence is not None
    ]
    keypoint_confidences = [
        confidence
        for item in positive
        for confidence in _point_confidences(item.detections)
    ]
    visible_30 = [
        value
        for item in positive
        if (value := _visible_ratio(item.detections, 0.3)) is not None
    ]
    visible_50 = [
        value
        for item in positive
        if (value := _visible_ratio(item.detections, 0.5)) is not None
    ]
    track_ids = {
        detection.track_id
        for item in positive
        for detection in item.detections
        if detection.track_id is not None
    }
    media_duration_ms = (
        results[-1].timestamp_ms + max(1, round(1000.0 / sample_fps))
        if results
        else 0
    )
    evaluation = PoseBenchmarkCaseEvaluation(
        case_id=case.case_id,
        variant_id=variant_id,
        run_id=run.run_id,
        video_sequence=case.video_sequence,
        video_class=case.video_class,
        sampled_frames=overall.sampled_frames,
        frames_with_people=overall.frames_with_people,
        pose_frame_coverage=overall.pose_frame_coverage,
        tracked_frames=overall.tracked_frames,
        tracking_coverage=overall.tracking_coverage,
        unique_track_count=len(track_ids),
        mean_detection_confidence=_mean_or_none(detection_confidences),
        mean_keypoint_confidence=_mean_or_none(keypoint_confidences),
        mean_keypoint_visible_ratio_30=_mean_or_none(visible_30),
        mean_keypoint_visible_ratio_50=_mean_or_none(visible_50),
        phase_metrics={
            phase: phase_metrics([item for item in results if item.phase == phase])
            for phase in PHASE_NAMES.values()
        },
        maximum_annotation_match_error_ms=max(
            (item.annotation_error_ms for item in results), default=0
        ),
        evaluated_media_duration_ms=media_duration_ms,
        timing_ms={
            "replay_wall": round(replay_wall_ms, 3),
            "pose_inference_total": round(sum(latencies), 3),
            "pose_inference_first": round(latencies[0], 3) if latencies else 0.0,
            "pose_inference_mean": round(mean(latencies), 3) if latencies else 0.0,
            "pose_inference_p95": _percentile(latencies, 0.95),
            "pose_inference_max": round(max(latencies), 3) if latencies else 0.0,
        },
        realtime_factors={
            "pose_inference": _rtf(sum(latencies), media_duration_ms),
            "replay_pipeline": _rtf(replay_wall_ms, media_duration_ms),
        },
        limitations=[
            *case.limitations,
            "coverage_requires_a_returned_person_box_not_correct_keypoint_geometry",
            "posture_labels_are_phase_labels_not_pose_ground_truth",
        ],
    )
    return _CaseRuntime(evaluation, latencies, replay_wall_ms)


def _aggregate_class(
    cases: list[PoseBenchmarkCaseEvaluation],
) -> dict[str, dict[str, float | int]]:
    groups: dict[str, list[PoseBenchmarkCaseEvaluation]] = defaultdict(list)
    for case in cases:
        groups[case.video_class].append(case)
    result: dict[str, dict[str, float | int]] = {}
    for name, members in sorted(groups.items()):
        sampled = sum(item.sampled_frames for item in members)
        people = sum(item.frames_with_people for item in members)
        tracked = sum(item.tracked_frames for item in members)
        result[name] = {
            "case_count": len(members),
            "sampled_frames": sampled,
            "frames_with_people": people,
            "pose_frame_coverage": round(people / sampled, 6) if sampled else 0.0,
            "tracked_frames": tracked,
            "tracking_coverage": round(tracked / people, 6) if people else 0.0,
        }
    return result


def _aggregate_phases(
    cases: list[PoseBenchmarkCaseEvaluation],
) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for phase in PHASE_NAMES.values():
        metrics = [case.phase_metrics[phase] for case in cases]
        sampled = sum(item.sampled_frames for item in metrics)
        people = sum(item.frames_with_people for item in metrics)
        tracked = sum(item.tracked_frames for item in metrics)
        qualities = [
            (item.mean_pose_quality, item.frames_with_people)
            for item in metrics
            if item.mean_pose_quality is not None and item.frames_with_people
        ]
        quality_weight = sum(weight for _, weight in qualities)
        result[phase] = {
            "sampled_frames": sampled,
            "frames_with_people": people,
            "pose_frame_coverage": round(people / sampled, 6) if sampled else 0.0,
            "tracked_frames": tracked,
            "tracking_coverage": round(tracked / people, 6) if people else 0.0,
            "mean_pose_quality": (
                round(
                    sum(value * weight for value, weight in qualities)
                    / quality_weight,
                    6,
                )
                if quality_weight
                else 0.0
            ),
        }
    return result


def _weighted_case_metric(
    cases: list[PoseBenchmarkCaseEvaluation], field: str
) -> float | None:
    values = [
        (getattr(case, field), case.frames_with_people)
        for case in cases
        if getattr(case, field) is not None and case.frames_with_people
    ]
    weight = sum(item[1] for item in values)
    if not weight:
        return None
    return round(sum(float(value) * count for value, count in values) / weight, 6)


def _runtime_environment() -> dict[str, Any]:
    environment: dict[str, Any] = {
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "gpu_process_memory_snapshot_mb": _gpu_process_memory_mb(),
        "gpu_memory_note": (
            "snapshot is current process memory after inference, not a sampled peak; "
            "torch peak excludes ONNXRuntime allocations"
        ),
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
    environment["cuda_available"] = torch.cuda.is_available()
    if torch.cuda.is_available():
        environment["cuda_device"] = torch.cuda.get_device_name(0)
        environment["torch_cuda_peak_memory_allocated_mb"] = round(
            torch.cuda.max_memory_allocated(0) / 1024**2,
            3,
        )
    return environment


def _gpu_process_memory_mb() -> float | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    total = 0.0
    found = False
    for line in result.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 2 or fields[0] != str(os.getpid()):
            continue
        try:
            total += float(fields[1])
            found = True
        except ValueError:
            continue
    return round(total, 3) if found else None


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


def _backend_factory(
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
) -> Callable[[], PoseBackend]:
    if variant_id == "yolo26n-pose":
        return lambda: UltralyticsPoseBackend(
            model=yolo_model,
            device=yolo_device,
            image_size=yolo_image_size,
            confidence=yolo_confidence,
            track=True,
        )
    if variant_id == "rtmpose-m-humanart":
        from .rtmpose_backend import HumanArtRTMPoseBackend

        return lambda: HumanArtRTMPoseBackend(
            detector_model=rtmpose_detector_model,
            pose_model=rtmpose_pose_model,
            device=rtmpose_device,
            detection_confidence=rtmpose_detection_confidence,
            track=True,
        )
    raise ValueError(f"unknown pose benchmark variant: {variant_id}")


def _run_variant(
    *,
    variant_id: str,
    cases: list[DatasetBenchmarkCase],
    benchmark_cases_path: Path,
    runs_dir: Path,
    parent_run: RunArtifacts,
    factory: Callable[[], PoseBackend],
    sample_fps: float,
    max_duration_s: float,
) -> PoseBenchmarkVariantReport:
    _reset_torch_peak()
    load_started = perf_counter()
    with parent_run.step(f"load-pose-variant:{variant_id}"):
        backend = factory()
    model_load_ms = (perf_counter() - load_started) * 1000.0
    case_runtimes: list[_CaseRuntime] = []
    try:
        for case in cases:
            reset = getattr(backend, "reset", None)
            if reset is not None:
                reset()
            with parent_run.step(
                f"run-pose-case:{variant_id}:{case.case_id}"
            ) as parent_step:
                with RunArtifacts(
                    runs_dir,
                    stage="v1-m3-pose-model-case",
                    evidence_level=EvidenceLevel.E1,
                    configuration={
                        "variant_id": variant_id,
                        "case_id": case.case_id,
                        "video_sequence": case.video_sequence,
                        "sample_fps": sample_fps,
                        "max_duration_s": max_duration_s,
                    },
                ) as child_run:
                    runtime = evaluate_pose_case(
                        case=case,
                        variant_id=variant_id,
                        benchmark_cases_path=benchmark_cases_path,
                        backend=backend,
                        run=child_run,
                        sample_fps=sample_fps,
                        max_duration_s=max_duration_s,
                    )
                    evaluation_path = child_run.write_report(
                        "pose-case-evaluation.json", runtime.evaluation
                    )
                parent_step.outputs.append(
                    f"../{child_run.run_id}/{child_run.relative(evaluation_path)}"
                )
                case_runtimes.append(runtime)

        evaluations = [item.evaluation for item in case_runtimes]
        sampled = sum(item.sampled_frames for item in evaluations)
        people = sum(item.frames_with_people for item in evaluations)
        tracked = sum(item.tracked_frames for item in evaluations)
        media_ms = sum(item.evaluated_media_duration_ms for item in evaluations)
        latencies = [
            latency for runtime in case_runtimes for latency in runtime.latencies_ms
        ]
        replay_wall_ms = sum(item.replay_wall_ms for item in case_runtimes)
        inference_wall_ms = sum(latencies)
        runtime_environment = _runtime_environment()
        runtime_environment["case_run_ids"] = [
            item.run_id for item in evaluations
        ]
        return PoseBenchmarkVariantReport(
            variant_id=variant_id,
            model_bindings=backend.bindings,
            case_count=len(evaluations),
            cases=evaluations,
            sampled_frames=sampled,
            frames_with_people=people,
            pose_frame_coverage=round(people / sampled, 6) if sampled else 0.0,
            tracked_frames=tracked,
            tracking_coverage=round(tracked / people, 6) if people else 0.0,
            by_video_class=_aggregate_class(evaluations),
            by_posture_phase=_aggregate_phases(evaluations),
            quality_metrics={
                "mean_detection_confidence": _weighted_case_metric(
                    evaluations, "mean_detection_confidence"
                ),
                "mean_keypoint_confidence": _weighted_case_metric(
                    evaluations, "mean_keypoint_confidence"
                ),
                "mean_keypoint_visible_ratio_30": _weighted_case_metric(
                    evaluations, "mean_keypoint_visible_ratio_30"
                ),
                "mean_keypoint_visible_ratio_50": _weighted_case_metric(
                    evaluations, "mean_keypoint_visible_ratio_50"
                ),
            },
            runtime_environment=runtime_environment,
            timing_ms={
                "model_load_wall": round(model_load_ms, 3),
                "replay_pipeline_total": round(replay_wall_ms, 3),
                "pose_inference_total": round(inference_wall_ms, 3),
                "pose_inference_first": (
                    round(latencies[0], 3) if latencies else 0.0
                ),
                "pose_inference_mean": (
                    round(mean(latencies), 3) if latencies else 0.0
                ),
                "pose_inference_p95": _percentile(latencies, 0.95),
                "pose_inference_max": (
                    round(max(latencies), 3) if latencies else 0.0
                ),
            },
            realtime_factors={
                "pose_inference": _rtf(inference_wall_ms, media_ms),
                "replay_pipeline": _rtf(replay_wall_ms, media_ms),
            },
            limitations=[
                "public_urfd_evidence_is_e1_and_not_target_device_evidence",
                "suite_has_no_person_presence_negative_labels_so_false_positive_rate_is_unmeasured",
                "coverage_does_not_validate_keypoint_geometry",
                "trackers_differ_between_variants_and_track_metrics_are_secondary",
                "gpu_process_memory_is_a_post_inference_snapshot_not_a_peak",
            ],
        )
    finally:
        del backend
        _empty_cuda_cache()


def _comparison(
    variants: list[PoseBenchmarkVariantReport],
) -> dict[str, dict[str, float | int | str | None]]:
    by_id = {variant.variant_id: variant for variant in variants}
    if "yolo26n-pose" not in by_id or "rtmpose-m-humanart" not in by_id:
        return {}
    baseline = by_id["yolo26n-pose"]
    candidate = by_id["rtmpose-m-humanart"]
    baseline_lying = float(
        baseline.by_posture_phase["lying"]["pose_frame_coverage"]
    )
    candidate_lying = float(
        candidate.by_posture_phase["lying"]["pose_frame_coverage"]
    )
    return {
        "rtmpose-m-humanart_vs_yolo26n-pose": {
            "baseline_variant": baseline.variant_id,
            "candidate_variant": candidate.variant_id,
            "overall_coverage_delta_percentage_points": round(
                (candidate.pose_frame_coverage - baseline.pose_frame_coverage)
                * 100.0,
                3,
            ),
            "lying_coverage_delta_percentage_points": round(
                (candidate_lying - baseline_lying) * 100.0,
                3,
            ),
            "pose_inference_rtf_delta": round(
                candidate.realtime_factors["pose_inference"]
                - baseline.realtime_factors["pose_inference"],
                6,
            ),
            "candidate_mean_keypoint_visible_ratio_30": (
                candidate.quality_metrics.get("mean_keypoint_visible_ratio_30")
            ),
            "baseline_mean_keypoint_visible_ratio_30": (
                baseline.quality_metrics.get("mean_keypoint_visible_ratio_30")
            ),
        }
    }


def run_pose_model_comparison(
    *,
    benchmark_cases_path: Path,
    runs_dir: Path,
    variants: list[str],
    yolo_model: Path,
    yolo_device: str,
    yolo_image_size: int,
    yolo_confidence: float,
    rtmpose_detector_model: Path,
    rtmpose_pose_model: Path,
    rtmpose_device: str,
    rtmpose_detection_confidence: float,
    sample_fps: float,
    max_duration_s: float,
) -> tuple[RunArtifacts, PoseModelComparisonReport]:
    benchmark_cases_path = Path(benchmark_cases_path).resolve()
    suite, cases = load_benchmark_cases(benchmark_cases_path)
    if not variants:
        raise ValueError("at least one pose variant is required")
    if len(variants) != len(set(variants)):
        raise ValueError("pose variants must be unique")
    unknown = sorted(set(variants) - set(KNOWN_VARIANTS))
    if unknown:
        raise ValueError(f"unknown pose variants: {', '.join(unknown)}")
    if sample_fps <= 0 or max_duration_s <= 0:
        raise ValueError("sample_fps and max_duration_s must be positive")

    configuration = {
        "command": "benchmark-pose-models",
        "benchmark_id": suite["benchmark_id"],
        "benchmark_cases_sha256": sha256_file(benchmark_cases_path),
        "variants": variants,
        "yolo_model": str(yolo_model),
        "yolo_device": yolo_device,
        "yolo_image_size": yolo_image_size,
        "yolo_confidence": yolo_confidence,
        "rtmpose_detector_model": str(rtmpose_detector_model),
        "rtmpose_pose_model": str(rtmpose_pose_model),
        "rtmpose_device": rtmpose_device,
        "rtmpose_detection_confidence": rtmpose_detection_confidence,
        "sample_fps": sample_fps,
        "max_duration_s": max_duration_s,
    }
    with RunArtifacts(
        runs_dir,
        stage="v1-m3-pose-model-comparison",
        evidence_level=EvidenceLevel.E1,
        configuration=configuration,
    ) as parent_run:
        variant_reports: list[PoseBenchmarkVariantReport] = []
        for variant_id in variants:
            factory = _backend_factory(
                variant_id,
                yolo_model=Path(yolo_model),
                yolo_device=yolo_device,
                yolo_image_size=yolo_image_size,
                yolo_confidence=yolo_confidence,
                rtmpose_detector_model=Path(rtmpose_detector_model),
                rtmpose_pose_model=Path(rtmpose_pose_model),
                rtmpose_device=rtmpose_device,
                rtmpose_detection_confidence=rtmpose_detection_confidence,
            )
            report = _run_variant(
                variant_id=variant_id,
                cases=cases,
                benchmark_cases_path=benchmark_cases_path,
                runs_dir=Path(runs_dir),
                parent_run=parent_run,
                factory=factory,
                sample_fps=sample_fps,
                max_duration_s=max_duration_s,
            )
            with parent_run.step(f"write-pose-variant-report:{variant_id}") as step:
                path = parent_run.write_report(
                    f"pose-variant-{variant_id}.json", report
                )
                step.outputs.append(parent_run.relative(path))
            variant_reports.append(report)

        comparison = PoseModelComparisonReport(
            benchmark_id=suite["benchmark_id"],
            benchmark_version=POSE_BENCHMARK_VERSION,
            evidence_level=EvidenceLevel.E1,
            source_manifest_sha256=suite["source_manifest_sha256"],
            benchmark_cases_sha256=sha256_file(benchmark_cases_path),
            case_count=len(cases),
            primary_metric="by_posture_phase.lying.pose_frame_coverage",
            variants=variant_reports,
            comparisons=_comparison(variant_reports),
            limitations=[
                *suite.get("limitations", []),
                "pose_comparison_reuses_video_only_and_does_not_rerun_asr",
                "suite_has_no_person_presence_negative_labels_so_detection_false_positive_rate_is_unmeasured",
                "urfd_has_phase_labels_but_no_keypoint_ground_truth",
                "target_c6c_day_night_occlusion_results_remain_v1_m2c",
            ],
        )
        with parent_run.step("write-pose-model-comparison-report") as step:
            path = parent_run.write_report(
                "pose-model-comparison-report.json", comparison
            )
            step.outputs.append(parent_run.relative(path))
    return parent_run, comparison
