from __future__ import annotations

import bisect
import gc
import json
import unicodedata
from collections import defaultdict
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from .artifacts import RunArtifacts
from .contracts import (
    DatasetBenchmarkCase,
    DatasetBenchmarkReport,
    DatasetCaseEvaluation,
    DatasetPhaseMetrics,
    EvidenceLevel,
    FeatureEvent,
    ModelBinding,
    MultimodalPipelineReport,
    SourceType,
)
from .dataset_preparation import sha256_file
from .multimodal_pipeline import MultimodalPipelineConfig, run_multimodal_pipeline
from .pose_backend import UltralyticsPoseBackend
from .speech_backend import FunASRSpeechBackend


BENCHMARK_VERSION = "public-dataset-benchmark-v0.1.0"
PHASE_NAMES = {
    -1: "not_lying",
    0: "falling_transition",
    1: "lying",
    None: "unlabeled",
}


def normalize_transcript(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if character.isalnum())


def levenshtein_distance(reference: str, hypothesis: str) -> int:
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row, reference_character in enumerate(reference, start=1):
        current = [row]
        for column, hypothesis_character in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[column - 1] + 1,
                    previous[column] + 1,
                    previous[column - 1]
                    + int(reference_character != hypothesis_character),
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> tuple[int, int, float]:
    normalized_reference = normalize_transcript(reference)
    normalized_hypothesis = normalize_transcript(hypothesis)
    edits = levenshtein_distance(normalized_reference, normalized_hypothesis)
    denominator = len(normalized_reference)
    rate = edits / denominator if denominator else float(bool(normalized_hypothesis))
    return edits, denominator, round(rate, 6)


def load_benchmark_cases(
    path: Path,
) -> tuple[dict[str, Any], list[DatasetBenchmarkCase]]:
    path = Path(path)
    with path.open(encoding="utf-8") as stream:
        suite = json.load(stream)
    if suite.get("schema_version") != "1.0":
        raise ValueError("unsupported benchmark-cases schema")
    if suite.get("evidence_level") != "E1":
        raise ValueError("public dataset benchmark evidence must remain E1")
    pairing_kind = suite.get("pairing_kind")
    if pairing_kind != "cross_dataset_synthetic_common_zero":
        raise ValueError("public benchmark must preserve synthetic pairing semantics")
    cases = [DatasetBenchmarkCase.model_validate(item) for item in suite.get("cases", [])]
    if not cases:
        raise ValueError("benchmark-cases contains no cases")
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("benchmark-cases contains duplicate case IDs")
    if any(case.evidence_level != EvidenceLevel.E1 for case in cases):
        raise ValueError("all public benchmark cases must remain E1")
    if any(case.pairing_kind != pairing_kind for case in cases):
        raise ValueError("case pairing_kind disagrees with suite pairing_kind")
    return suite, cases


def _resolved_path(case_manifest: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else case_manifest.parent / path


def _read_features(path: Path) -> list[FeatureEvent]:
    events: list[FeatureEvent] = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                events.append(FeatureEvent.model_validate_json(line))
    return events


def _read_annotation(path: Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        annotation = json.load(stream)
    frames = annotation.get("frames")
    if annotation.get("schema_version") != "1.0" or not isinstance(frames, list):
        raise ValueError(f"invalid URFD annotation sidecar: {path}")
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
    if not candidates:
        raise ValueError("annotation sidecar contains no frames")
    index = min(candidates, key=lambda item: abs(timestamps[item] - timestamp_ms))
    return frames[index], abs(timestamps[index] - timestamp_ms)


def _bbox_width_height_ratio(event: FeatureEvent) -> float | None:
    detections = event.value.get("detections", [])
    candidates: list[tuple[float, float]] = []
    for detection in detections:
        bbox = detection.get("bbox_xyxy")
        if not isinstance(bbox, list) or len(bbox) < 4:
            continue
        width = max(0.0, float(bbox[2]) - float(bbox[0]))
        height = max(0.0, float(bbox[3]) - float(bbox[1]))
        if height > 0:
            candidates.append((width * height, width / height))
    return max(candidates)[1] if candidates else None


def _metrics_for_pose_events(events: list[FeatureEvent]) -> DatasetPhaseMetrics:
    people = [event for event in events if event.value.get("person_count", 0) > 0]
    tracked = [
        event
        for event in people
        if any(
            detection.get("track_id") is not None
            for detection in event.value.get("detections", [])
        )
    ]
    qualities = [event.quality for event in events if event.quality is not None]
    ratios = [
        value
        for event in events
        if (value := _bbox_width_height_ratio(event)) is not None
    ]
    return DatasetPhaseMetrics(
        sampled_frames=len(events),
        frames_with_people=len(people),
        pose_frame_coverage=round(len(people) / len(events), 6) if events else 0.0,
        tracked_frames=len(tracked),
        tracking_coverage=round(len(tracked) / len(people), 6) if people else 0.0,
        mean_pose_quality=round(mean(qualities), 6) if qualities else None,
        mean_bbox_width_height_ratio=round(mean(ratios), 6) if ratios else None,
    )


def _union_duration_ms(events: list[FeatureEvent], duration_ms: int) -> int:
    ranges: list[tuple[int, int]] = []
    for event in events:
        start = min(duration_ms, max(0, event.time_range.start_ms or 0))
        end = min(duration_ms, max(0, event.time_range.end_ms or 0))
        if end > start:
            ranges.append((start, end))
    ranges.sort()
    if not ranges:
        return 0
    total = 0
    current_start, current_end = ranges[0]
    for start, end in ranges[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    total += current_end - current_start
    return max(0, total)


def evaluate_dataset_case(
    *,
    case: DatasetBenchmarkCase,
    run: RunArtifacts,
    annotation_path: Path,
    pipeline_report: MultimodalPipelineReport,
) -> DatasetCaseEvaluation:
    events = _read_features(run.run_dir / "features.jsonl")
    annotation = _read_annotation(annotation_path)
    frames = sorted(annotation["frames"], key=lambda item: item["replay_timestamp_ms"])
    annotation_timestamps = [int(item["replay_timestamp_ms"]) for item in frames]
    pose_events = sorted(
        (event for event in events if event.feature_type == "video.pose_frame"),
        key=lambda event: event.time_range.start_ms or 0,
    )
    phase_events: dict[str, list[FeatureEvent]] = {
        phase: [] for phase in PHASE_NAMES.values()
    }
    annotation_errors: list[int] = []
    for event in pose_events:
        frame, error = _nearest_annotation(
            annotation_timestamps,
            frames,
            event.time_range.start_ms or 0,
        )
        label = frame.get("posture_label")
        phase = PHASE_NAMES.get(label)
        if phase is None:
            raise ValueError(f"unexpected posture label in sidecar: {label}")
        phase_events[phase].append(event)
        annotation_errors.append(error)

    overall_pose = _metrics_for_pose_events(pose_events)
    track_ids = {
        str(detection["track_id"])
        for event in pose_events
        for detection in event.value.get("detections", [])
        if detection.get("track_id") is not None
    }
    transcript_events = sorted(
        (
            event
            for event in events
            if event.feature_type == "language.transcript_segment"
        ),
        key=lambda event: event.time_range.start_ms or 0,
    )
    hypothesis = "".join(str(event.value.get("text", "")) for event in transcript_events)
    normalized_reference = normalize_transcript(case.reference_transcript)
    normalized_hypothesis = normalize_transcript(hypothesis)
    edits, reference_length, cer = character_error_rate(
        case.reference_transcript,
        hypothesis,
    )
    speech_events = [
        event for event in events if event.feature_type == "audio.speech_segment"
    ]
    speech_duration_ms = _union_duration_ms(speech_events, case.audio_duration_ms)
    return DatasetCaseEvaluation(
        case_id=case.case_id,
        run_id=run.run_id,
        video_sequence=case.video_sequence,
        video_class=case.video_class,
        audio_sample=case.audio_sample,
        audio_gender=case.audio_gender,
        pairing_kind=case.pairing_kind,
        sampled_pose_frames=overall_pose.sampled_frames,
        pose_frames_with_people=overall_pose.frames_with_people,
        pose_frame_coverage=overall_pose.pose_frame_coverage,
        pose_frames_with_tracks=overall_pose.tracked_frames,
        pose_tracking_coverage=overall_pose.tracking_coverage,
        unique_track_count=len(track_ids),
        mean_pose_quality=overall_pose.mean_pose_quality,
        phase_metrics={
            phase: _metrics_for_pose_events(phase_events[phase])
            for phase in PHASE_NAMES.values()
        },
        maximum_annotation_match_error_ms=max(annotation_errors, default=0),
        audio_duration_ms=case.audio_duration_ms,
        speech_duration_ms=speech_duration_ms,
        speech_coverage=(
            round(speech_duration_ms / case.audio_duration_ms, 6)
            if case.audio_duration_ms
            else 0.0
        ),
        reference_char_count=reference_length,
        hypothesis_char_count=len(normalized_hypothesis),
        edit_distance=edits,
        character_error_rate=cer,
        transcript_exact_match=normalized_reference == normalized_hypothesis,
        multimodal_window_count=pipeline_report.multimodal_window_count,
        processing_realtime_factor=pipeline_report.realtime_factors[
            "processing_end_to_end"
        ],
        limitations=sorted(
            set(
                [
                    *case.limitations,
                    "reference_and_hypothesis_text_are_omitted_from_aggregate_report",
                    "posture_labels_measure_frame_phase_not_fall_classification_accuracy",
                ]
            )
        ),
    )


def _aggregate_group(
    cases: list[DatasetCaseEvaluation],
    key: str,
) -> dict[str, dict[str, float | int]]:
    groups: dict[str, list[DatasetCaseEvaluation]] = defaultdict(list)
    for case in cases:
        groups[str(getattr(case, key))].append(case)
    result: dict[str, dict[str, float | int]] = {}
    for name, members in sorted(groups.items()):
        sampled = sum(item.sampled_pose_frames for item in members)
        people = sum(item.pose_frames_with_people for item in members)
        tracked = sum(item.pose_frames_with_tracks for item in members)
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
    cases: list[DatasetCaseEvaluation],
) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for phase in PHASE_NAMES.values():
        metrics = [case.phase_metrics[phase] for case in cases]
        sampled = sum(item.sampled_frames for item in metrics)
        people = sum(item.frames_with_people for item in metrics)
        tracked = sum(item.tracked_frames for item in metrics)
        result[phase] = {
            "sampled_frames": sampled,
            "frames_with_people": people,
            "pose_frame_coverage": round(people / sampled, 6) if sampled else 0.0,
            "tracked_frames": tracked,
            "tracking_coverage": round(tracked / people, 6) if people else 0.0,
        }
    return result


def _binding_identity(binding: ModelBinding) -> tuple[str, str, str, str | None]:
    return (
        binding.task,
        binding.backend,
        binding.model_name,
        binding.model_digest,
    )


def _empty_cuda_cache() -> None:
    try:
        import torch
    except ImportError:
        gc.collect()
        return
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _reset_cuda_peak() -> None:
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def run_dataset_benchmark(
    *,
    benchmark_cases_path: Path,
    runs_dir: Path,
    pose_model: str,
    pose_device: str,
    pose_image_size: int,
    pose_confidence: float,
    pose_sample_fps: float,
    track: bool,
    asr_model: str,
    vad_model: str,
    punc_model: str,
    speech_device: str,
    language: str,
    offline_models: bool,
    fusion_window_ms: int,
    max_duration_s: float,
) -> tuple[RunArtifacts, DatasetBenchmarkReport]:
    benchmark_cases_path = Path(benchmark_cases_path).resolve()
    suite, cases = load_benchmark_cases(benchmark_cases_path)
    if max_duration_s <= 0:
        raise ValueError("max_duration_s must be positive")
    configuration = {
        "command": "benchmark-dataset",
        "benchmark_id": suite["benchmark_id"],
        "benchmark_cases_sha256": sha256_file(benchmark_cases_path),
        "pairing_kind": suite["pairing_kind"],
        "case_count": len(cases),
        "pose_model": pose_model,
        "pose_device": pose_device,
        "pose_image_size": pose_image_size,
        "pose_confidence": pose_confidence,
        "pose_sample_fps": pose_sample_fps,
        "tracking": track,
        "asr_model": asr_model,
        "vad_model": vad_model,
        "punc_model": punc_model,
        "speech_device": speech_device,
        "language": language,
        "offline_models": offline_models,
        "fusion_window_ms": fusion_window_ms,
        "max_duration_s": max_duration_s,
    }
    benchmark_started = perf_counter()
    with RunArtifacts(
        runs_dir,
        stage="v1-m2b-public-dataset-benchmark",
        evidence_level=EvidenceLevel.E1,
        configuration=configuration,
    ) as parent_run:
        speech_load_started = perf_counter()
        with parent_run.step("load-shared-speech-models"):
            speech_backend = FunASRSpeechBackend(
                model=asr_model,
                vad_model=vad_model,
                punc_model=punc_model,
                device=speech_device,
                language=language,
                offline=offline_models,
            )
        speech_model_load_ms = (perf_counter() - speech_load_started) * 1000.0
        model_bindings = list(speech_backend.bindings)
        binding_identities = {_binding_identity(item) for item in model_bindings}
        evaluations: list[DatasetCaseEvaluation] = []
        pipeline_reports: list[MultimodalPipelineReport] = []
        pose_model_load_ms = 0.0

        for case in cases:
            with parent_run.step(f"run-case:{case.case_id}") as parent_step:
                _reset_cuda_peak()
                pose_load_started = perf_counter()
                pose_backend = UltralyticsPoseBackend(
                    model=pose_model,
                    device=pose_device,
                    image_size=pose_image_size,
                    confidence=pose_confidence,
                    track=track,
                )
                pose_model_load_ms += (perf_counter() - pose_load_started) * 1000.0
                for binding in pose_backend.bindings:
                    identity = _binding_identity(binding)
                    if identity not in binding_identities:
                        model_bindings.append(binding)
                        binding_identities.add(identity)
                child_configuration = {
                    "benchmark_id": suite["benchmark_id"],
                    "case_id": case.case_id,
                    "pairing_kind": case.pairing_kind,
                    "video_dataset": case.video_dataset,
                    "video_sequence": case.video_sequence,
                    "video_class": case.video_class,
                    "audio_dataset": case.audio_dataset,
                    "audio_sample": case.audio_sample,
                    "pose_sample_fps": pose_sample_fps,
                    "fusion_window_ms": fusion_window_ms,
                    "max_duration_s": max_duration_s,
                }
                try:
                    with RunArtifacts(
                        runs_dir,
                        stage="v1-m2b-public-dataset-case",
                        evidence_level=EvidenceLevel.E1,
                        configuration=child_configuration,
                    ) as child_run:
                        pipeline_report = run_multimodal_pipeline(
                            video_path=_resolved_path(
                                benchmark_cases_path, case.video_path
                            ),
                            audio_path=_resolved_path(
                                benchmark_cases_path, case.audio_path
                            ),
                            pose_backend=pose_backend,
                            speech_backend=speech_backend,
                            run=child_run,
                            config=MultimodalPipelineConfig(
                                video_sample_fps=pose_sample_fps,
                                fusion_window_ms=fusion_window_ms,
                                max_duration_s=max_duration_s,
                            ),
                            evidence_level=EvidenceLevel.E1,
                            source_type=SourceType.LOCAL_FILE,
                        )
                        evaluation = evaluate_dataset_case(
                            case=case,
                            run=child_run,
                            annotation_path=_resolved_path(
                                benchmark_cases_path, case.annotation_path
                            ),
                            pipeline_report=pipeline_report,
                        )
                        evaluation_path = child_run.write_report(
                            "dataset-case-evaluation.json", evaluation
                        )
                    parent_step.outputs.append(
                        f"../{child_run.run_id}/{child_run.relative(evaluation_path)}"
                    )
                    evaluations.append(evaluation)
                    pipeline_reports.append(pipeline_report)
                finally:
                    del pose_backend
                    _empty_cuda_cache()

        sampled = sum(item.sampled_pose_frames for item in evaluations)
        people = sum(item.pose_frames_with_people for item in evaluations)
        tracked = sum(item.pose_frames_with_tracks for item in evaluations)
        total_reference = sum(item.reference_char_count for item in evaluations)
        total_edits = sum(item.edit_distance for item in evaluations)
        runtime_environment = dict(pipeline_reports[0].runtime_environment)
        peaks = [
            report.runtime_environment.get("cuda_peak_memory_allocated_mb")
            for report in pipeline_reports
            if isinstance(
                report.runtime_environment.get("cuda_peak_memory_allocated_mb"),
                (int, float),
            )
        ]
        if peaks:
            runtime_environment["cuda_peak_memory_allocated_mb"] = max(peaks)
        runtime_environment["case_run_ids"] = [item.run_id for item in evaluations]
        benchmark_wall_ms = (perf_counter() - benchmark_started) * 1000.0
        report = DatasetBenchmarkReport(
            benchmark_id=suite["benchmark_id"],
            benchmark_version=BENCHMARK_VERSION,
            evidence_level=EvidenceLevel.E1,
            pairing_kind=suite["pairing_kind"],
            source_manifest_sha256=suite["source_manifest_sha256"],
            benchmark_cases_sha256=sha256_file(benchmark_cases_path),
            case_count=len(evaluations),
            cases=evaluations,
            model_bindings=model_bindings,
            total_reference_chars=total_reference,
            total_edit_distance=total_edits,
            corpus_character_error_rate=(
                round(total_edits / total_reference, 6) if total_reference else 0.0
            ),
            transcript_exact_match_count=sum(
                item.transcript_exact_match for item in evaluations
            ),
            pose_frame_coverage=round(people / sampled, 6) if sampled else 0.0,
            pose_tracking_coverage=round(tracked / people, 6) if people else 0.0,
            by_video_class=_aggregate_group(evaluations, "video_class"),
            by_posture_phase=_aggregate_phases(evaluations),
            runtime_environment=runtime_environment,
            timing_ms={
                "benchmark_wall": round(benchmark_wall_ms, 3),
                "shared_speech_model_load": round(speech_model_load_ms, 3),
                "pose_model_load_total": round(pose_model_load_ms, 3),
                "case_processing_total": round(
                    sum(
                        item.timing_ms["processing_total_wall"]
                        for item in pipeline_reports
                    ),
                    3,
                ),
            },
            limitations=sorted(
                set(
                    [
                        *suite.get("limitations", []),
                        "aggregate_report_omits_reference_and_hypothesis_text",
                        "fusion_windows_only_validate_schema_and_time_flow",
                        "modality_accuracy_is_evaluated_separately",
                        "no_target_device_or_natural_audio_video_sync_claim",
                    ]
                )
            ),
        )
        with parent_run.step("write-dataset-benchmark-report") as step:
            report_path = parent_run.write_report(
                "dataset-benchmark-report.json", report
            )
            step.outputs.append(parent_run.relative(report_path))
    return parent_run, report
