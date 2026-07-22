from __future__ import annotations

import gc
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
    EvidenceLevel,
    FeatureEvent,
    ModelBinding,
    PrivacyLevel,
    SpeechBenchmarkCaseEvaluation,
    SpeechBenchmarkVariantReport,
    SpeechModelComparisonReport,
    TimeRange,
)
from .dataset_benchmark import (
    character_error_rate,
    load_benchmark_cases,
    normalize_transcript,
)
from .dataset_preparation import sha256_file
from .speech_backend import (
    FunASRSpeechBackend,
    SpeechBackend,
    SpeechSegment,
    WhisperSpeechBackend,
)
from .streaming import AudioBuffer, read_pcm_wav


SPEECH_BENCHMARK_VERSION = "speech-model-comparison-v0.1.0"
KNOWN_VARIANTS = ("funasr-paraformer", "whisper-small")
SILENCE_PROBE_DURATION_MS = 2000


@dataclass(frozen=True)
class _CaseRuntime:
    evaluation: SpeechBenchmarkCaseEvaluation
    inference_ms: float


def _resolved_path(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else manifest_path.parent / path


def _binding_for_task(
    bindings: list[ModelBinding], task: str
) -> ModelBinding | None:
    return next((binding for binding in bindings if binding.task == task), None)


def _union_segment_duration_ms(
    segments: list[SpeechSegment], duration_ms: int
) -> int:
    ranges = sorted(
        (
            max(0, min(segment.start_ms, duration_ms)),
            max(0, min(segment.end_ms, duration_ms)),
        )
        for segment in segments
        if segment.end_ms > segment.start_ms
    )
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
    return total + current_end - current_start


def _record_segment_features(
    *,
    run: RunArtifacts,
    segments: list[SpeechSegment],
    bindings: list[ModelBinding],
) -> None:
    vad_binding = _binding_for_task(bindings, "voice_activity_detection")
    asr_binding = _binding_for_task(bindings, "mandarin_speech_recognition")
    speech_extractor = vad_binding or asr_binding
    for sequence, segment in enumerate(segments):
        speech_id = f"feature_{run.run_id}_speech_{sequence:04d}"
        time_range = TimeRange(
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
        )
        run.record_feature(
            FeatureEvent(
                feature_id=speech_id,
                observation_id=f"observation_{run.run_id}_audio",
                feature_type="audio.speech_segment",
                time_range=time_range,
                value={"speech_detected": True},
                confidence=segment.confidence,
                extractor_name=(
                    speech_extractor.backend
                    if speech_extractor
                    else "unknown-speech-backend"
                ),
                extractor_version=(
                    (speech_extractor.model_version if speech_extractor else None)
                    or "unknown"
                ),
                model_digest=(
                    speech_extractor.model_digest if speech_extractor else None
                ),
                privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
                limitations=[
                    "segment_boundaries_are_model_outputs_not_manual_labels",
                    "public_dataset_e1_only",
                ],
            )
        )
        if not segment.text:
            continue
        run.record_feature(
            FeatureEvent(
                feature_id=f"feature_{run.run_id}_transcript_{sequence:04d}",
                observation_id=f"observation_{run.run_id}_audio",
                feature_type="language.transcript_segment",
                time_range=time_range,
                value={"text": segment.text, "language": segment.language},
                confidence=segment.confidence,
                extractor_name=(
                    asr_binding.backend if asr_binding else "unknown-asr-backend"
                ),
                extractor_version=(
                    (asr_binding.model_version if asr_binding else None) or "unknown"
                ),
                model_digest=asr_binding.model_digest if asr_binding else None,
                privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
                source_feature_refs=[speech_id],
                limitations=[
                    "raw_transcript_is_sensitive_and_stays_in_ignored_run_artifacts",
                    "confidence_is_not_compared_across_model_families",
                ],
            )
        )


def evaluate_speech_case(
    *,
    case: DatasetBenchmarkCase,
    variant_id: str,
    benchmark_cases_path: Path,
    backend: SpeechBackend,
    run: RunArtifacts,
) -> _CaseRuntime:
    audio = read_pcm_wav(
        _resolved_path(benchmark_cases_path, case.audio_path),
        target_sample_rate_hz=16000,
    )
    if abs(audio.duration_ms - case.audio_duration_ms) > 2:
        raise ValueError(
            f"audio duration disagrees with frozen manifest for {case.case_id}: "
            f"expected {case.audio_duration_ms} ms, received {audio.duration_ms} ms"
        )
    with run.step("extract-speech-comparison-features") as step:
        started = perf_counter()
        segments = backend.transcribe(audio)
        inference_ms = (perf_counter() - started) * 1000.0
        _record_segment_features(
            run=run,
            segments=segments,
            bindings=backend.bindings,
        )
        if (run.run_dir / "features.jsonl").is_file():
            step.outputs.append("features.jsonl")

    hypothesis = "".join(segment.text for segment in segments)
    normalized_reference = normalize_transcript(case.reference_transcript)
    normalized_hypothesis = normalize_transcript(hypothesis)
    edits, reference_length, cer = character_error_rate(
        case.reference_transcript,
        hypothesis,
    )
    speech_duration_ms = _union_segment_duration_ms(
        segments, case.audio_duration_ms
    )
    evaluation = SpeechBenchmarkCaseEvaluation(
        case_id=case.case_id,
        variant_id=variant_id,
        run_id=run.run_id,
        audio_sample=case.audio_sample,
        audio_gender=case.audio_gender,
        audio_duration_ms=case.audio_duration_ms,
        segment_count=len(segments),
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
        blank_output=not normalized_hypothesis,
        timing_ms={"speech_inference": round(inference_ms, 3)},
        realtime_factor=(
            round(inference_ms / case.audio_duration_ms, 6)
            if case.audio_duration_ms
            else 0.0
        ),
        limitations=sorted(
            set(
                [
                    *case.limitations,
                    "reference_and_hypothesis_text_are_omitted_from_case_report",
                    "segment_coverage_is_secondary_and_not_a_common_vad_metric",
                    "confidence_scales_are_not_compared_across_model_families",
                ]
            )
        ),
    )
    return _CaseRuntime(evaluation=evaluation, inference_ms=inference_ms)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def aggregate_speech_cases(
    cases: list[SpeechBenchmarkCaseEvaluation],
) -> dict[str, int | float | dict[str, dict[str, int | float]]]:
    total_audio = sum(case.audio_duration_ms for case in cases)
    total_speech = sum(case.speech_duration_ms for case in cases)
    total_reference = sum(case.reference_char_count for case in cases)
    total_hypothesis = sum(case.hypothesis_char_count for case in cases)
    total_edits = sum(case.edit_distance for case in cases)
    groups: dict[str, list[SpeechBenchmarkCaseEvaluation]] = defaultdict(list)
    for case in cases:
        groups[case.audio_gender].append(case)
    by_gender: dict[str, dict[str, int | float]] = {}
    for gender, members in sorted(groups.items()):
        references = sum(case.reference_char_count for case in members)
        edits = sum(case.edit_distance for case in members)
        by_gender[gender] = {
            "case_count": len(members),
            "total_reference_chars": references,
            "total_edit_distance": edits,
            "corpus_character_error_rate": (
                round(edits / references, 6) if references else 0.0
            ),
            "transcript_exact_match_count": sum(
                case.transcript_exact_match for case in members
            ),
            "blank_output_count": sum(case.blank_output for case in members),
        }
    return {
        "total_audio_duration_ms": total_audio,
        "total_speech_duration_ms": total_speech,
        "speech_coverage": (
            round(total_speech / total_audio, 6) if total_audio else 0.0
        ),
        "total_reference_chars": total_reference,
        "total_hypothesis_chars": total_hypothesis,
        "total_edit_distance": total_edits,
        "corpus_character_error_rate": (
            round(total_edits / total_reference, 6) if total_reference else 0.0
        ),
        "transcript_exact_match_count": sum(
            case.transcript_exact_match for case in cases
        ),
        "blank_output_count": sum(case.blank_output for case in cases),
        "by_gender": by_gender,
    }


def _silence_probe(backend: SpeechBackend) -> tuple[dict[str, Any], float]:
    try:
        import numpy as np
    except ImportError as error:
        raise RuntimeError("NumPy is required for the silence probe") from error
    samples = np.zeros(SILENCE_PROBE_DURATION_MS * 16, dtype=np.float32)
    audio = AudioBuffer(
        samples=samples,
        sample_rate_hz=16000,
        duration_ms=SILENCE_PROBE_DURATION_MS,
    )
    started = perf_counter()
    segments = backend.transcribe(audio)
    inference_ms = (perf_counter() - started) * 1000.0
    normalized = normalize_transcript(
        "".join(segment.text for segment in segments)
    )
    return (
        {
            "probe_kind": "synthetic_zero_pcm_16khz_mono",
            "duration_ms": SILENCE_PROBE_DURATION_MS,
            "segment_count": len(segments),
            "hypothesis_char_count": len(normalized),
            "passed": not normalized,
            "inference_ms": round(inference_ms, 3),
            "realtime_factor": round(
                inference_ms / SILENCE_PROBE_DURATION_MS, 6
            ),
            "transcript_text_persisted": False,
        },
        inference_ms,
    )


def _backend_factory(
    variant_id: str,
    *,
    asr_model: str,
    vad_model: str,
    punc_model: str,
    funasr_device: str,
    language: str,
    offline_models: bool,
    whisper_model: Path,
    whisper_device: str,
    whisper_beam_size: int,
    whisper_fp16: bool | None,
) -> Callable[[], SpeechBackend]:
    if variant_id == "funasr-paraformer":
        return lambda: FunASRSpeechBackend(
            model=asr_model,
            vad_model=vad_model,
            punc_model=punc_model,
            device=funasr_device,
            language=language,
            offline=offline_models,
        )
    if variant_id == "whisper-small":
        return lambda: WhisperSpeechBackend(
            model_path=whisper_model,
            device=whisper_device,
            language=language,
            beam_size=whisper_beam_size,
            fp16=whisper_fp16,
        )
    raise ValueError(f"unknown speech benchmark variant: {variant_id}")


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


def _runtime_environment() -> dict[str, Any]:
    environment: dict[str, Any] = {
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "gpu_process_memory_snapshot_mb": _gpu_process_memory_mb(),
        "gpu_memory_note": (
            "snapshot is process memory after inference; torch peak includes "
            "PyTorch allocations but not external decoder allocations"
        ),
    }
    try:
        import funasr

        environment["funasr"] = funasr.__version__
    except ImportError:
        environment["funasr"] = "unavailable"
    try:
        import whisper

        environment["openai_whisper"] = whisper.__version__
    except ImportError:
        environment["openai_whisper"] = "unavailable"
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


def _run_variant(
    *,
    variant_id: str,
    cases: list[DatasetBenchmarkCase],
    benchmark_cases_path: Path,
    runs_dir: Path,
    parent_run: RunArtifacts,
    factory: Callable[[], SpeechBackend],
) -> SpeechBenchmarkVariantReport:
    _reset_torch_peak()
    load_started = perf_counter()
    with parent_run.step(f"load-speech-variant:{variant_id}"):
        backend = factory()
    model_load_ms = (perf_counter() - load_started) * 1000.0
    runtimes: list[_CaseRuntime] = []
    try:
        for case in cases:
            with parent_run.step(
                f"run-speech-case:{variant_id}:{case.case_id}"
            ) as parent_step:
                with RunArtifacts(
                    runs_dir,
                    stage="v1-m3-speech-model-case",
                    evidence_level=EvidenceLevel.E1,
                    configuration={
                        "variant_id": variant_id,
                        "case_id": case.case_id,
                        "audio_dataset": case.audio_dataset,
                        "audio_sample": case.audio_sample,
                        "language": "zh",
                        "transcript_text_in_report": False,
                    },
                ) as child_run:
                    runtime = evaluate_speech_case(
                        case=case,
                        variant_id=variant_id,
                        benchmark_cases_path=benchmark_cases_path,
                        backend=backend,
                        run=child_run,
                    )
                    path = child_run.write_report(
                        "speech-case-evaluation.json", runtime.evaluation
                    )
                parent_step.outputs.append(
                    f"../{child_run.run_id}/{child_run.relative(path)}"
                )
                runtimes.append(runtime)

        with parent_run.step(f"run-silence-probe:{variant_id}"):
            silence_probe, silence_inference_ms = _silence_probe(backend)

        evaluations = [runtime.evaluation for runtime in runtimes]
        aggregates = aggregate_speech_cases(evaluations)
        inference_latencies = [runtime.inference_ms for runtime in runtimes]
        inference_total = sum(inference_latencies)
        total_audio_ms = int(aggregates["total_audio_duration_ms"])
        runtime_environment = _runtime_environment()
        runtime_environment["case_run_ids"] = [
            case.run_id for case in evaluations
        ]
        return SpeechBenchmarkVariantReport(
            variant_id=variant_id,
            model_bindings=backend.bindings,
            case_count=len(evaluations),
            cases=evaluations,
            total_audio_duration_ms=total_audio_ms,
            total_speech_duration_ms=int(
                aggregates["total_speech_duration_ms"]
            ),
            speech_coverage=float(aggregates["speech_coverage"]),
            total_reference_chars=int(aggregates["total_reference_chars"]),
            total_hypothesis_chars=int(aggregates["total_hypothesis_chars"]),
            total_edit_distance=int(aggregates["total_edit_distance"]),
            corpus_character_error_rate=float(
                aggregates["corpus_character_error_rate"]
            ),
            transcript_exact_match_count=int(
                aggregates["transcript_exact_match_count"]
            ),
            blank_output_count=int(aggregates["blank_output_count"]),
            by_gender=aggregates["by_gender"],
            silence_probe=silence_probe,
            runtime_environment=runtime_environment,
            timing_ms={
                "model_load_wall": round(model_load_ms, 3),
                "speech_inference_total": round(inference_total, 3),
                "speech_inference_first": (
                    round(inference_latencies[0], 3)
                    if inference_latencies
                    else 0.0
                ),
                "speech_inference_mean": (
                    round(mean(inference_latencies), 3)
                    if inference_latencies
                    else 0.0
                ),
                "speech_inference_p95": _percentile(
                    inference_latencies, 0.95
                ),
                "speech_inference_max": (
                    round(max(inference_latencies), 3)
                    if inference_latencies
                    else 0.0
                ),
                "silence_probe_inference": round(silence_inference_ms, 3),
            },
            realtime_factors={
                "speech_inference": (
                    round(inference_total / total_audio_ms, 6)
                    if total_audio_ms
                    else 0.0
                ),
                "silence_probe": float(silence_probe["realtime_factor"]),
            },
            limitations=[
                "public_fleurs_clean_read_speech_is_e1_not_c6c_far_field_evidence",
                "six_cases_are_an_engineering_smoke_not_a_statistical_model_benchmark",
                "segment_coverage_is_not_comparable_to_standalone_vad_ground_truth",
                "reference_and_hypothesis_text_are_omitted_from_aggregate_reports",
                "synthetic_silence_probe_is_e1_and_does_not_measure_"
                "real_noise_false_alarms",
                "gpu_process_memory_is_a_post_inference_snapshot_not_a_peak",
            ],
        )
    finally:
        del backend
        _empty_cuda_cache()


def _comparison(
    variants: list[SpeechBenchmarkVariantReport],
) -> dict[str, dict[str, float | int | str | bool | None]]:
    by_id = {variant.variant_id: variant for variant in variants}
    if "funasr-paraformer" not in by_id or "whisper-small" not in by_id:
        return {}
    baseline = by_id["funasr-paraformer"]
    candidate = by_id["whisper-small"]
    return {
        "whisper-small_vs_funasr-paraformer": {
            "baseline_variant": baseline.variant_id,
            "candidate_variant": candidate.variant_id,
            "corpus_cer_delta": round(
                candidate.corpus_character_error_rate
                - baseline.corpus_character_error_rate,
                6,
            ),
            "corpus_cer_delta_percentage_points": round(
                (
                    candidate.corpus_character_error_rate
                    - baseline.corpus_character_error_rate
                )
                * 100.0,
                3,
            ),
            "exact_match_count_delta": (
                candidate.transcript_exact_match_count
                - baseline.transcript_exact_match_count
            ),
            "speech_inference_rtf_delta": round(
                candidate.realtime_factors["speech_inference"]
                - baseline.realtime_factors["speech_inference"],
                6,
            ),
            "baseline_silence_probe_passed": bool(
                baseline.silence_probe.get("passed")
            ),
            "candidate_silence_probe_passed": bool(
                candidate.silence_probe.get("passed")
            ),
        }
    }


def run_speech_model_comparison(
    *,
    benchmark_cases_path: Path,
    runs_dir: Path,
    variants: list[str],
    asr_model: str,
    vad_model: str,
    punc_model: str,
    funasr_device: str,
    language: str,
    offline_models: bool,
    whisper_model: Path,
    whisper_device: str,
    whisper_beam_size: int,
    whisper_fp16: bool | None,
) -> tuple[RunArtifacts, SpeechModelComparisonReport]:
    benchmark_cases_path = Path(benchmark_cases_path).resolve()
    suite, cases = load_benchmark_cases(benchmark_cases_path)
    if not variants:
        raise ValueError("at least one speech variant is required")
    if len(variants) != len(set(variants)):
        raise ValueError("speech variants must be unique")
    unknown = sorted(set(variants) - set(KNOWN_VARIANTS))
    if unknown:
        raise ValueError(f"unknown speech variants: {', '.join(unknown)}")
    if language != "zh":
        raise ValueError("V1-M3 fixed FLEURS comparison language must remain zh")
    if whisper_beam_size <= 0:
        raise ValueError("whisper_beam_size must be positive")

    configuration = {
        "command": "benchmark-speech-models",
        "benchmark_id": suite["benchmark_id"],
        "benchmark_cases_sha256": sha256_file(benchmark_cases_path),
        "variants": variants,
        "asr_model": asr_model,
        "vad_model": vad_model,
        "punc_model": punc_model,
        "funasr_device": funasr_device,
        "language": language,
        "offline_models": offline_models,
        "whisper_model": str(whisper_model),
        "whisper_device": whisper_device,
        "whisper_beam_size": whisper_beam_size,
        "whisper_fp16": whisper_fp16,
        "silence_probe_duration_ms": SILENCE_PROBE_DURATION_MS,
        "transcript_text_in_aggregate_reports": False,
    }
    with RunArtifacts(
        runs_dir,
        stage="v1-m3-speech-model-comparison",
        evidence_level=EvidenceLevel.E1,
        configuration=configuration,
    ) as parent_run:
        variant_reports: list[SpeechBenchmarkVariantReport] = []
        for variant_id in variants:
            factory = _backend_factory(
                variant_id,
                asr_model=asr_model,
                vad_model=vad_model,
                punc_model=punc_model,
                funasr_device=funasr_device,
                language=language,
                offline_models=offline_models,
                whisper_model=Path(whisper_model),
                whisper_device=whisper_device,
                whisper_beam_size=whisper_beam_size,
                whisper_fp16=whisper_fp16,
            )
            report = _run_variant(
                variant_id=variant_id,
                cases=cases,
                benchmark_cases_path=benchmark_cases_path,
                runs_dir=Path(runs_dir),
                parent_run=parent_run,
                factory=factory,
            )
            with parent_run.step(
                f"write-speech-variant-report:{variant_id}"
            ) as step:
                path = parent_run.write_report(
                    f"speech-variant-{variant_id}.json", report
                )
                step.outputs.append(parent_run.relative(path))
            variant_reports.append(report)

        comparison = SpeechModelComparisonReport(
            benchmark_id=suite["benchmark_id"],
            benchmark_version=SPEECH_BENCHMARK_VERSION,
            evidence_level=EvidenceLevel.E1,
            source_manifest_sha256=suite["source_manifest_sha256"],
            benchmark_cases_sha256=sha256_file(benchmark_cases_path),
            case_count=len(cases),
            primary_metric="corpus_character_error_rate",
            variants=variant_reports,
            comparisons=_comparison(variant_reports),
            limitations=[
                *suite.get("limitations", []),
                "speech_comparison_reuses_audio_only_and_does_not_rerun_pose",
                "fixed_six_case_fleurs_slice_is_too_small_for_final_model_selection",
                "same_normalization_preserves_traditional_simplified_and_"
                "wording_differences",
                "no_target_device_far_field_elderly_noisy_or_overlapping_speech_claim",
                "whisper_integrated_segments_are_not_a_replacement_for_"
                "vad_benchmarking",
                "decoding_was_frozen_before_candidate_results_were_observed",
            ],
        )
        with parent_run.step("write-speech-model-comparison-report") as step:
            path = parent_run.write_report(
                "speech-model-comparison-report.json", comparison
            )
            step.outputs.append(parent_run.relative(path))
    return parent_run, comparison
