from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Sequence

from kangshield import __version__

from .artifacts import RunArtifacts
from .contracts import EvidenceLevel, SourceType
from .dataset_benchmark import run_dataset_benchmark
from .ezviz_snapshot import inspect_ezviz_snapshot
from .media_probe import probe_media
from .multimodal_pipeline import (
    MultimodalPipelineConfig,
    run_multimodal_pipeline,
)
from .pose_backend import UltralyticsPoseBackend
from .sleep_profile import profile_sleep_export
from .speech_backend import FunASRSpeechBackend


def _evidence(value: str) -> EvidenceLevel:
    try:
        return EvidenceLevel(value.upper())
    except ValueError as error:
        raise argparse.ArgumentTypeError("evidence level must be E0..E4") from error


def _source_type(value: str) -> SourceType:
    try:
        return SourceType(value)
    except ValueError as error:
        choices = ", ".join(item.value for item in SourceType)
        raise argparse.ArgumentTypeError(f"source type must be one of: {choices}") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kangshield-info",
        description="KangShield V1 information-side probes",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"kangshield-info {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    media = subparsers.add_parser(
        "probe-media",
        help="Inspect file facts and WAV/video metadata",
    )
    media.add_argument("paths", nargs="+", type=Path)
    media.add_argument("--runs-dir", type=Path, default=Path("runs"))
    media.add_argument("--evidence-level", type=_evidence, default=EvidenceLevel.E1)
    media.add_argument("--source-type", type=_source_type, default=SourceType.LOCAL_FILE)
    media.add_argument("--device-ref")
    media.add_argument("--elder-ref")

    sleep = subparsers.add_parser(
        "profile-sleep",
        help="Discover JSON/CSV sleep-export fields without persisting values",
    )
    sleep.add_argument("path", type=Path)
    sleep.add_argument("--runs-dir", type=Path, default=Path("runs"))
    sleep.add_argument("--evidence-level", type=_evidence, default=EvidenceLevel.E1)
    sleep.add_argument("--source-type", type=_source_type, default=SourceType.FIXTURE)
    sleep.add_argument("--device-ref")
    sleep.add_argument("--elder-ref")

    ezviz = subparsers.add_parser(
        "inspect-ezviz",
        help="Inspect and redact an EZVIZ SDK/API JSON snapshot",
    )
    ezviz.add_argument("path", type=Path)
    ezviz.add_argument("--runs-dir", type=Path, default=Path("runs"))
    ezviz.add_argument("--evidence-level", type=_evidence, default=EvidenceLevel.E1)
    ezviz.add_argument("--source-type", type=_source_type, default=SourceType.FIXTURE)

    multimodal = subparsers.add_parser(
        "run-multimodal",
        help="Replay video and speech into aligned multimodal feature windows",
    )
    multimodal.add_argument("video", type=Path)
    multimodal.add_argument("audio", type=Path)
    multimodal.add_argument("--runs-dir", type=Path, default=Path("runs"))
    multimodal.add_argument(
        "--evidence-level",
        type=_evidence,
        default=EvidenceLevel.E1,
    )
    multimodal.add_argument(
        "--source-type",
        type=_source_type,
        default=SourceType.LOCAL_FILE,
    )
    multimodal.add_argument("--device-ref")
    multimodal.add_argument("--elder-ref")
    multimodal.add_argument(
        "--pose-model",
        default="models/yolo26n-pose.pt",
    )
    multimodal.add_argument("--pose-device", default="auto")
    multimodal.add_argument("--pose-image-size", type=int, default=640)
    multimodal.add_argument("--pose-confidence", type=float, default=0.35)
    multimodal.add_argument("--pose-sample-fps", type=float, default=5.0)
    multimodal.add_argument("--no-track", action="store_true")
    multimodal.add_argument("--asr-model", default="paraformer-zh")
    multimodal.add_argument("--vad-model", default="fsmn-vad")
    multimodal.add_argument("--punc-model", default="ct-punc")
    multimodal.add_argument("--speech-device", default="auto")
    multimodal.add_argument("--language", default="zh")
    multimodal.add_argument("--offline-models", action="store_true")
    multimodal.add_argument("--fusion-window-ms", type=int, default=2000)
    multimodal.add_argument("--max-duration-s", type=float, default=30.0)

    benchmark = subparsers.add_parser(
        "benchmark-dataset",
        help="Run the pinned V1-M2b public dataset suite with separate modality metrics",
    )
    benchmark.add_argument("benchmark_cases", type=Path)
    benchmark.add_argument("--runs-dir", type=Path, default=Path("runs"))
    benchmark.add_argument("--pose-model", default="models/yolo26n-pose.pt")
    benchmark.add_argument("--pose-device", default="auto")
    benchmark.add_argument("--pose-image-size", type=int, default=640)
    benchmark.add_argument("--pose-confidence", type=float, default=0.35)
    benchmark.add_argument("--pose-sample-fps", type=float, default=5.0)
    benchmark.add_argument("--no-track", action="store_true")
    benchmark.add_argument("--asr-model", default="paraformer-zh")
    benchmark.add_argument("--vad-model", default="fsmn-vad")
    benchmark.add_argument("--punc-model", default="ct-punc")
    benchmark.add_argument("--speech-device", default="auto")
    benchmark.add_argument("--language", default="zh")
    benchmark.add_argument("--offline-models", action="store_true")
    benchmark.add_argument("--fusion-window-ms", type=int, default=1000)
    benchmark.add_argument("--max-duration-s", type=float, default=30.0)

    return parser


def _print_result(run: RunArtifacts, details: dict) -> None:
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "run_dir": str(run.run_dir),
                "manifest": str(run.manifest_path),
                **details,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _probe_media_command(args: argparse.Namespace) -> int:
    configuration = {
        "command": "probe-media",
        "path_count": len(args.paths),
        "source_type": args.source_type.value,
    }
    with RunArtifacts(
        args.runs_dir,
        stage="v1-media-probe",
        evidence_level=args.evidence_level,
        configuration=configuration,
    ) as run:
        reports = []
        for index, path in enumerate(args.paths):
            with run.step(f"probe-media:{index}") as step:
                report = probe_media(
                    path,
                    evidence_level=args.evidence_level,
                    device_ref=args.device_ref,
                    elder_ref=args.elder_ref,
                    source_type=args.source_type,
                )
                run.record_asset(report.asset)
                run.record_observation(report.observation)
                output = run.write_report(f"media-probe-{index:03d}.json", report)
                step.outputs.append(run.relative(output))
                reports.append(
                    {
                        "asset_id": report.asset.asset_id,
                        "modality": report.asset.modality.value,
                        "quality_status": report.observation.quality_status.value,
                    }
                )
    _print_result(run, {"reports": reports})
    return 0


def _profile_sleep_command(args: argparse.Namespace) -> int:
    with RunArtifacts(
        args.runs_dir,
        stage="v1-sleep-profile",
        evidence_level=args.evidence_level,
        configuration={
            "command": "profile-sleep",
            "source_type": args.source_type.value,
        },
    ) as run:
        with run.step("profile-sleep") as step:
            report = profile_sleep_export(
                args.path,
                evidence_level=args.evidence_level,
                source_type=args.source_type,
                device_ref=args.device_ref,
                elder_ref=args.elder_ref,
            )
            run.record_asset(report.asset)
            run.record_observation(report.observation)
            output = run.write_report("sleep-field-profile.json", report)
            step.outputs.append(run.relative(output))
    _print_result(
        run,
        {
            "record_count": report.record_count,
            "field_count": len(report.fields),
            "mapping_candidate_count": len(report.mapping_candidates),
        },
    )
    return 0


def _inspect_ezviz_command(args: argparse.Namespace) -> int:
    with RunArtifacts(
        args.runs_dir,
        stage="v1-ezviz-snapshot",
        evidence_level=args.evidence_level,
        configuration={
            "command": "inspect-ezviz",
            "source_type": args.source_type.value,
        },
    ) as run:
        with run.step("inspect-ezviz") as step:
            report = inspect_ezviz_snapshot(
                args.path,
                evidence_level=args.evidence_level,
                source_type=args.source_type,
            )
            run.record_asset(report.asset)
            output = run.write_report("ezviz-capability-snapshot.json", report)
            step.outputs.append(run.relative(output))
    _print_result(
        run,
        {
            "device_count": len(report.devices),
            "models_found": report.models_found,
            "target_models_found": report.target_models_found,
        },
    )
    return 0


def _run_multimodal_command(args: argparse.Namespace) -> int:
    configuration = {
        "command": "run-multimodal",
        "source_type": args.source_type.value,
        "pose_model": args.pose_model,
        "pose_device": args.pose_device,
        "pose_image_size": args.pose_image_size,
        "pose_confidence": args.pose_confidence,
        "pose_sample_fps": args.pose_sample_fps,
        "tracking": not args.no_track,
        "asr_model": args.asr_model,
        "vad_model": args.vad_model,
        "punc_model": args.punc_model,
        "speech_device": args.speech_device,
        "language": args.language,
        "offline_models": args.offline_models,
        "fusion_window_ms": args.fusion_window_ms,
        "max_duration_s": args.max_duration_s,
    }
    with RunArtifacts(
        args.runs_dir,
        stage="v1-multimodal-replay",
        evidence_level=args.evidence_level,
        configuration=configuration,
    ) as run:
        model_load_started = perf_counter()
        with run.step("load-multimodal-models"):
            pose_backend = UltralyticsPoseBackend(
                model=args.pose_model,
                device=args.pose_device,
                image_size=args.pose_image_size,
                confidence=args.pose_confidence,
                track=not args.no_track,
            )
            speech_backend = FunASRSpeechBackend(
                model=args.asr_model,
                vad_model=args.vad_model,
                punc_model=args.punc_model,
                device=args.speech_device,
                language=args.language,
                offline=args.offline_models,
            )
        model_load_wall_ms = (perf_counter() - model_load_started) * 1000.0
        report = run_multimodal_pipeline(
            video_path=args.video,
            audio_path=args.audio,
            pose_backend=pose_backend,
            speech_backend=speech_backend,
            run=run,
            config=MultimodalPipelineConfig(
                video_sample_fps=args.pose_sample_fps,
                fusion_window_ms=args.fusion_window_ms,
                max_duration_s=args.max_duration_s,
            ),
            evidence_level=args.evidence_level,
            source_type=args.source_type,
            device_ref=args.device_ref,
            elder_ref=args.elder_ref,
            model_load_wall_ms=model_load_wall_ms,
        )
    _print_result(
        run,
        {
            "duration_ms": report.duration_ms,
            "sampled_video_frames": report.sampled_video_frames,
            "pose_detection_count": report.pose_detection_count,
            "speech_segment_count": report.speech_segment_count,
            "multimodal_window_count": report.multimodal_window_count,
            "processing_realtime_factor": report.realtime_factors[
                "processing_end_to_end"
            ],
            "cold_start_realtime_factor": report.realtime_factors[
                "cold_start_end_to_end"
            ],
        },
    )
    return 0


def _benchmark_dataset_command(args: argparse.Namespace) -> int:
    run, report = run_dataset_benchmark(
        benchmark_cases_path=args.benchmark_cases,
        runs_dir=args.runs_dir,
        pose_model=args.pose_model,
        pose_device=args.pose_device,
        pose_image_size=args.pose_image_size,
        pose_confidence=args.pose_confidence,
        pose_sample_fps=args.pose_sample_fps,
        track=not args.no_track,
        asr_model=args.asr_model,
        vad_model=args.vad_model,
        punc_model=args.punc_model,
        speech_device=args.speech_device,
        language=args.language,
        offline_models=args.offline_models,
        fusion_window_ms=args.fusion_window_ms,
        max_duration_s=args.max_duration_s,
    )
    _print_result(
        run,
        {
            "benchmark_id": report.benchmark_id,
            "case_count": report.case_count,
            "pose_frame_coverage": report.pose_frame_coverage,
            "pose_tracking_coverage": report.pose_tracking_coverage,
            "corpus_character_error_rate": report.corpus_character_error_rate,
            "transcript_exact_match_count": report.transcript_exact_match_count,
        },
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "probe-media":
        return _probe_media_command(args)
    if args.command == "profile-sleep":
        return _profile_sleep_command(args)
    if args.command == "inspect-ezviz":
        return _inspect_ezviz_command(args)
    if args.command == "run-multimodal":
        return _run_multimodal_command(args)
    if args.command == "benchmark-dataset":
        return _benchmark_dataset_command(args)
    raise RuntimeError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
