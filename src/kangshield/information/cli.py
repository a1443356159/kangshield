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
    media.add_argument(
        "--require-audio-track",
        action="store_true",
        help="Fail the media observation when an audio track cannot be verified",
    )
    media.add_argument(
        "--max-packets-per-stream",
        type=int,
        default=200_000,
        help="Maximum packets scanned for PTS/DTS statistics in each stream",
    )

    capture = subparsers.add_parser(
        "assess-m2c-capture",
        help="Validate a controlled C6c/SDNL1 capture bundle without copying raw data",
    )
    capture.add_argument("manifest", type=Path)
    capture.add_argument("--runs-dir", type=Path, default=Path("runs"))
    capture.add_argument(
        "--policy",
        type=Path,
        default=Path("configs/v1-m2c-capture-policy.json"),
    )
    capture.add_argument(
        "--evidence-level", type=_evidence, default=EvidenceLevel.E1
    )
    capture.add_argument(
        "--source-type", type=_source_type, default=SourceType.FIXTURE
    )
    capture.add_argument(
        "--max-packets-per-stream",
        type=int,
        default=200_000,
        help="Maximum packets scanned for PTS/DTS statistics in each media stream",
    )
    capture.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit 2 unless the complete real-device capture-bundle gate is ready",
    )

    event_evaluation = subparsers.add_parser(
        "assess-event-evaluation",
        help="Score held-out fall candidates against independently adjudicated labels",
    )
    event_evaluation.add_argument("bundle", type=Path)
    event_evaluation.add_argument("--runs-dir", type=Path, default=Path("runs"))
    event_evaluation.add_argument(
        "--policy",
        type=Path,
        default=Path("configs/v1-g4-event-evaluation-policy.json"),
    )
    event_evaluation.add_argument(
        "--evidence-level", type=_evidence, default=EvidenceLevel.E1
    )
    event_evaluation.add_argument(
        "--source-type", type=_source_type, default=SourceType.FIXTURE
    )
    event_evaluation.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit 2 unless real E2+ event metrics are ready for review",
    )

    event_bundle = subparsers.add_parser(
        "assemble-event-evaluation-bundle",
        help="Atomically assemble and preflight a self-contained event bundle",
    )
    event_bundle.add_argument("capture_manifest", type=Path)
    event_bundle.add_argument("readiness_report", type=Path)
    event_bundle.add_argument("readiness_run_manifest", type=Path)
    event_bundle.add_argument("candidate_policy", type=Path)
    event_bundle.add_argument("adjudication", type=Path)
    event_bundle.add_argument(
        "--annotation",
        type=Path,
        action="append",
        required=True,
        help="Repeat for each independent annotation set",
    )
    event_bundle.add_argument(
        "--prediction-source",
        type=Path,
        nargs=2,
        action="append",
        required=True,
        metavar=("PREDICTION", "RUN_MANIFEST"),
        help="Repeat for each pose variant",
    )
    event_bundle.add_argument("--output", type=Path, required=True)
    event_bundle.add_argument(
        "--evaluation-policy",
        type=Path,
        default=Path("configs/v1-g4-event-evaluation-policy.json"),
    )
    event_bundle.add_argument(
        "--evidence-level", type=_evidence, default=EvidenceLevel.E1
    )
    event_bundle.add_argument(
        "--source-type", type=_source_type, default=SourceType.FIXTURE
    )
    event_bundle.add_argument("--evaluation-id")

    candidate_export = subparsers.add_parser(
        "export-fall-candidates",
        help=(
            "Convert one capture-bound G4 feature set into candidate events "
            "for the held-out evaluator"
        ),
    )
    candidate_export.add_argument("capture_manifest", type=Path)
    candidate_export.add_argument("feature_set", type=Path)
    candidate_export.add_argument("source_feature_run_manifest", type=Path)
    candidate_export.add_argument(
        "--policy",
        type=Path,
        default=Path("configs/v1-g4-event-candidate-policy.json"),
    )
    candidate_export.add_argument("--runs-dir", type=Path, default=Path("runs"))
    candidate_export.add_argument(
        "--evidence-level", type=_evidence, default=EvidenceLevel.E1
    )
    candidate_export.add_argument(
        "--allow-dirty-source",
        action="store_true",
        help="Allow a dirty upstream G4 feature run for development only",
    )

    feature_capture = subparsers.add_parser(
        "capture-fall-features",
        help=(
            "Replay every frozen capture clip through one pose variant and "
            "the G4 fall-motion extractor"
        ),
    )
    feature_capture.add_argument("capture_manifest", type=Path)
    feature_capture.add_argument("readiness_report", type=Path)
    feature_capture.add_argument("readiness_run_manifest", type=Path)
    feature_capture.add_argument(
        "--variant",
        required=True,
        choices=(
            "yolo26n-pose",
            "rtmpose-m-humanart",
            "torchvision-keypointrcnn",
        ),
    )
    feature_capture.add_argument("--runs-dir", type=Path, default=Path("runs"))
    feature_capture.add_argument(
        "--evidence-level", type=_evidence, default=EvidenceLevel.E1
    )
    feature_capture.add_argument(
        "--source-type", type=_source_type, default=SourceType.FIXTURE
    )
    feature_capture.add_argument(
        "--feature-config",
        type=Path,
        default=Path("configs/v1-g4-fall-features.json"),
    )
    feature_capture.add_argument("--sample-fps", type=float, default=5.0)
    feature_capture.add_argument(
        "--allow-dirty-readiness",
        action="store_true",
        help="Allow a dirty capture-readiness source for development only",
    )
    feature_capture.add_argument(
        "--yolo-model", type=Path, default=Path("models/yolo26n-pose.pt")
    )
    feature_capture.add_argument("--yolo-device", default="auto")
    feature_capture.add_argument("--yolo-image-size", type=int, default=640)
    feature_capture.add_argument("--yolo-confidence", type=float, default=0.35)
    feature_capture.add_argument(
        "--rtmpose-detector-model",
        type=Path,
        default=Path(
            "models/rtmpose/yolox_m_humanart/yolox_m_humanart.onnx"
        ),
    )
    feature_capture.add_argument(
        "--rtmpose-pose-model",
        type=Path,
        default=Path(
            "models/rtmpose/rtmpose_m_humanart/rtmpose_m_humanart.onnx"
        ),
    )
    feature_capture.add_argument("--rtmpose-device", default="auto")
    feature_capture.add_argument(
        "--rtmpose-detection-confidence", type=float, default=0.05
    )
    feature_capture.add_argument(
        "--torchvision-model",
        type=Path,
        default=Path(
            "models/torchvision/"
            "keypointrcnn_resnet50_fpn_coco-fc266e95.pth"
        ),
    )
    feature_capture.add_argument("--torchvision-device", default="auto")
    feature_capture.add_argument(
        "--torchvision-detection-confidence", type=float, default=0.5
    )
    feature_capture.add_argument("--torchvision-min-size", type=int, default=800)
    feature_capture.add_argument("--torchvision-max-size", type=int, default=1333)

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

    sleep_route = subparsers.add_parser(
        "assess-sleep-route",
        help="Assess fail-closed sleep field readiness without persisting values",
    )
    sleep_route.add_argument("path", type=Path)
    sleep_route.add_argument("--runs-dir", type=Path, default=Path("runs"))
    sleep_route.add_argument(
        "--evidence-level", type=_evidence, default=EvidenceLevel.E1
    )
    sleep_route.add_argument(
        "--source-type", type=_source_type, default=SourceType.FIXTURE
    )
    sleep_route.add_argument("--device-ref")
    sleep_route.add_argument("--elder-ref")
    sleep_route.add_argument(
        "--policy",
        type=Path,
        default=Path("configs/sleep/v1-sleep-route-policy.json"),
    )
    sleep_route.add_argument(
        "--mapping-config",
        type=Path,
        default=Path("configs/sleep/sdnl1-field-map.example.json"),
    )

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
    multimodal.add_argument("audio", type=Path, nargs="?")
    multimodal.add_argument(
        "--audio-from-video",
        action="store_true",
        help="Decode the single audio track from the video container and align by PTS",
    )
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

    pose_benchmark = subparsers.add_parser(
        "benchmark-pose-models",
        help="Compare the three frozen V1 pose variants on V1-M2b video",
    )
    pose_benchmark.add_argument("benchmark_cases", type=Path)
    pose_benchmark.add_argument("--runs-dir", type=Path, default=Path("runs"))
    pose_benchmark.add_argument(
        "--variant",
        action="append",
        choices=(
            "yolo26n-pose",
            "rtmpose-m-humanart",
            "torchvision-keypointrcnn",
        ),
        help="Repeat to select variants; defaults to all three in this order",
    )
    pose_benchmark.add_argument(
        "--yolo-model", type=Path, default=Path("models/yolo26n-pose.pt")
    )
    pose_benchmark.add_argument("--yolo-device", default="auto")
    pose_benchmark.add_argument("--yolo-image-size", type=int, default=640)
    pose_benchmark.add_argument("--yolo-confidence", type=float, default=0.35)
    pose_benchmark.add_argument(
        "--rtmpose-detector-model",
        type=Path,
        default=Path(
            "models/rtmpose/yolox_m_humanart/yolox_m_humanart.onnx"
        ),
    )
    pose_benchmark.add_argument(
        "--rtmpose-pose-model",
        type=Path,
        default=Path(
            "models/rtmpose/rtmpose_m_humanart/rtmpose_m_humanart.onnx"
        ),
    )
    pose_benchmark.add_argument("--rtmpose-device", default="auto")
    pose_benchmark.add_argument(
        "--rtmpose-detection-confidence", type=float, default=0.05
    )
    pose_benchmark.add_argument(
        "--torchvision-model",
        type=Path,
        default=Path(
            "models/torchvision/"
            "keypointrcnn_resnet50_fpn_coco-fc266e95.pth"
        ),
    )
    pose_benchmark.add_argument(
        "--torchvision-policy",
        type=Path,
        default=Path("configs/v1-m3-torchvision-pose-model.json"),
    )
    pose_benchmark.add_argument("--torchvision-device", default="auto")
    pose_benchmark.add_argument(
        "--torchvision-detection-confidence", type=float, default=0.5
    )
    pose_benchmark.add_argument("--torchvision-min-size", type=int, default=800)
    pose_benchmark.add_argument("--torchvision-max-size", type=int, default=1333)
    pose_benchmark.add_argument("--pose-sample-fps", type=float, default=5.0)
    pose_benchmark.add_argument("--max-duration-s", type=float, default=30.0)

    fall_benchmark = subparsers.add_parser(
        "benchmark-fall-features",
        help="Derive non-risk fall motion features from a clean pose comparison run",
    )
    fall_benchmark.add_argument("benchmark_cases", type=Path)
    fall_benchmark.add_argument("pose_comparison_report", type=Path)
    fall_benchmark.add_argument("--runs-dir", type=Path, default=Path("runs"))
    fall_benchmark.add_argument(
        "--variant",
        choices=(
            "yolo26n-pose",
            "rtmpose-m-humanart",
            "torchvision-keypointrcnn",
        ),
        default="rtmpose-m-humanart",
    )
    fall_benchmark.add_argument(
        "--config",
        type=Path,
        default=Path("configs/v1-g4-fall-features.json"),
    )
    fall_benchmark.add_argument(
        "--model-binding-policy",
        type=Path,
        default=Path("configs/v1-m3-pose-models.json"),
    )
    fall_benchmark.add_argument(
        "--torchvision-policy",
        type=Path,
        default=Path("configs/v1-m3-torchvision-pose-model.json"),
    )
    fall_benchmark.add_argument(
        "--allow-dirty-source",
        action="store_true",
        help="Allow dirty source pose runs for development only",
    )

    fall_adl = subparsers.add_parser(
        "benchmark-fall-adl",
        help="Stress G4 pose and motion proxies on the fixed CAUCAFall no-fall ADL set",
    )
    fall_adl.add_argument("fall_adl_cases", type=Path)
    fall_adl.add_argument("--runs-dir", type=Path, default=Path("runs"))
    fall_adl.add_argument(
        "--variant",
        action="append",
        choices=(
            "yolo26n-pose",
            "rtmpose-m-humanart",
            "torchvision-keypointrcnn",
        ),
        help="Repeat to select variants; defaults to all three in this order",
    )
    fall_adl.add_argument(
        "--config",
        type=Path,
        default=Path("configs/v1-g4-fall-features.json"),
    )
    fall_adl.add_argument(
        "--model-binding-policy",
        type=Path,
        default=Path("configs/v1-m3-pose-models.json"),
    )
    fall_adl.add_argument(
        "--yolo-model", type=Path, default=Path("models/yolo26n-pose.pt")
    )
    fall_adl.add_argument("--yolo-device", default="auto")
    fall_adl.add_argument("--yolo-image-size", type=int, default=640)
    fall_adl.add_argument("--yolo-confidence", type=float, default=0.35)
    fall_adl.add_argument(
        "--rtmpose-detector-model",
        type=Path,
        default=Path(
            "models/rtmpose/yolox_m_humanart/yolox_m_humanart.onnx"
        ),
    )
    fall_adl.add_argument(
        "--rtmpose-pose-model",
        type=Path,
        default=Path(
            "models/rtmpose/rtmpose_m_humanart/rtmpose_m_humanart.onnx"
        ),
    )
    fall_adl.add_argument("--rtmpose-device", default="auto")
    fall_adl.add_argument(
        "--rtmpose-detection-confidence", type=float, default=0.05
    )
    fall_adl.add_argument(
        "--torchvision-model",
        type=Path,
        default=Path(
            "models/torchvision/"
            "keypointrcnn_resnet50_fpn_coco-fc266e95.pth"
        ),
    )
    fall_adl.add_argument(
        "--torchvision-policy",
        type=Path,
        default=Path("configs/v1-m3-torchvision-pose-model.json"),
    )
    fall_adl.add_argument("--torchvision-device", default="auto")
    fall_adl.add_argument(
        "--torchvision-detection-confidence", type=float, default=0.5
    )
    fall_adl.add_argument("--torchvision-min-size", type=int, default=800)
    fall_adl.add_argument("--torchvision-max-size", type=int, default=1333)
    fall_adl.add_argument("--pose-sample-fps", type=float, default=5.0)
    fall_adl.add_argument("--max-duration-s", type=float, default=30.0)

    fall_candidates = subparsers.add_parser(
        "benchmark-fall-candidates",
        help=(
            "Generate deduplicated fall candidate episodes and stress them on "
            "existing URFD and CAUCAFall G4 feature runs"
        ),
    )
    fall_candidates.add_argument(
        "--urfd-run",
        action="append",
        type=Path,
        required=True,
        help="Repeat exactly three times for the frozen pose variants",
    )
    fall_candidates.add_argument("--caucafall-run", type=Path, required=True)
    fall_candidates.add_argument(
        "--benchmark-cases",
        type=Path,
        default=Path("data/processed/v1-m2b/benchmark-cases.json"),
    )
    fall_candidates.add_argument(
        "--policy",
        type=Path,
        default=Path("configs/v1-g4-event-candidate-policy.json"),
    )
    fall_candidates.add_argument("--runs-dir", type=Path, default=Path("runs"))
    fall_candidates.add_argument(
        "--allow-dirty-source",
        action="store_true",
        help="Allow dirty source runs for development only",
    )

    static_home = subparsers.add_parser(
        "benchmark-static-home",
        help=(
            "Stress person detection on the fixed Open Images furniture, pet, "
            "and multi-person still-image set"
        ),
    )
    static_home.add_argument("static_home_cases", type=Path)
    static_home.add_argument("--runs-dir", type=Path, default=Path("runs"))
    static_home.add_argument(
        "--variant",
        action="append",
        choices=(
            "yolo26n-pose",
            "rtmpose-m-humanart",
            "torchvision-keypointrcnn",
        ),
        help="Repeat to select variants; defaults to all three in this order",
    )
    static_home.add_argument(
        "--model-binding-policy",
        type=Path,
        default=Path("configs/v1-m3-pose-models.json"),
    )
    static_home.add_argument(
        "--yolo-model", type=Path, default=Path("models/yolo26n-pose.pt")
    )
    static_home.add_argument("--yolo-device", default="auto")
    static_home.add_argument("--yolo-image-size", type=int, default=640)
    static_home.add_argument("--yolo-confidence", type=float, default=0.35)
    static_home.add_argument(
        "--rtmpose-detector-model",
        type=Path,
        default=Path(
            "models/rtmpose/yolox_m_humanart/yolox_m_humanart.onnx"
        ),
    )
    static_home.add_argument(
        "--rtmpose-pose-model",
        type=Path,
        default=Path(
            "models/rtmpose/rtmpose_m_humanart/rtmpose_m_humanart.onnx"
        ),
    )
    static_home.add_argument("--rtmpose-device", default="auto")
    static_home.add_argument(
        "--rtmpose-detection-confidence", type=float, default=0.05
    )
    static_home.add_argument(
        "--torchvision-model",
        type=Path,
        default=Path(
            "models/torchvision/"
            "keypointrcnn_resnet50_fpn_coco-fc266e95.pth"
        ),
    )
    static_home.add_argument(
        "--torchvision-policy",
        type=Path,
        default=Path("configs/v1-m3-torchvision-pose-model.json"),
    )
    static_home.add_argument("--torchvision-device", default="auto")
    static_home.add_argument(
        "--torchvision-detection-confidence", type=float, default=0.5
    )
    static_home.add_argument("--torchvision-min-size", type=int, default=800)
    static_home.add_argument("--torchvision-max-size", type=int, default=1333)

    speech_benchmark = subparsers.add_parser(
        "benchmark-speech-models",
        help="Compare the FunASR baseline and Whisper small on V1-M2b speech",
    )
    speech_benchmark.add_argument("benchmark_cases", type=Path)
    speech_benchmark.add_argument("--runs-dir", type=Path, default=Path("runs"))
    speech_benchmark.add_argument(
        "--variant",
        action="append",
        choices=("funasr-paraformer", "whisper-small"),
        help="Repeat to select variants; defaults to both in this order",
    )
    speech_benchmark.add_argument("--asr-model", default="paraformer-zh")
    speech_benchmark.add_argument("--vad-model", default="fsmn-vad")
    speech_benchmark.add_argument("--punc-model", default="ct-punc")
    speech_benchmark.add_argument("--funasr-device", default="auto")
    speech_benchmark.add_argument("--language", default="zh")
    speech_benchmark.add_argument("--offline-models", action="store_true")
    speech_benchmark.add_argument(
        "--whisper-model",
        type=Path,
        default=Path("models/whisper/small.pt"),
    )
    speech_benchmark.add_argument("--whisper-device", default="auto")
    speech_benchmark.add_argument("--whisper-beam-size", type=int, default=5)
    whisper_precision = speech_benchmark.add_mutually_exclusive_group()
    whisper_precision.add_argument(
        "--whisper-fp16",
        dest="whisper_fp16",
        action="store_const",
        const=True,
        help="Force FP16 decoding",
    )
    whisper_precision.add_argument(
        "--whisper-fp32",
        dest="whisper_fp16",
        action="store_const",
        const=False,
        help="Force FP32 decoding",
    )
    speech_benchmark.set_defaults(whisper_fp16=None)

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
        "require_audio_track": args.require_audio_track,
        "max_packets_per_stream": args.max_packets_per_stream,
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
                    require_audio_track=args.require_audio_track,
                    packet_scan_limit_per_stream=args.max_packets_per_stream,
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
                        "audio_track_status": (
                            report.container_timing.audio_track_status
                            if report.container_timing
                            else "unknown"
                        ),
                        "video_stream_count": (
                            report.container_timing.video_stream_count
                            if report.container_timing
                            else 0
                        ),
                        "audio_stream_count": (
                            report.container_timing.audio_stream_count
                            if report.container_timing
                            else 0
                        ),
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


def _assess_m2c_capture_command(args: argparse.Namespace) -> int:
    from .m2c_capture import assess_m2c_capture
    from .privacy import sha256_file

    with RunArtifacts(
        args.runs_dir,
        stage="v1-m2c-capture-readiness",
        evidence_level=args.evidence_level,
        configuration={
            "command": "assess-m2c-capture",
            "source_type": args.source_type.value,
            "input_path_persisted": False,
            "max_packets_per_stream": args.max_packets_per_stream,
            "require_ready": args.require_ready,
        },
    ) as run:
        with run.step("assess-m2c-capture") as step:
            assessment = assess_m2c_capture(
                args.manifest,
                policy_path=args.policy,
                evidence_level=args.evidence_level,
                source_type=args.source_type,
                packet_scan_limit_per_stream=args.max_packets_per_stream,
            )
            run.record_asset(assessment.manifest_asset)
            for report in assessment.media_reports:
                run.record_asset(report.asset)
                run.record_observation(report.observation)
            for asset in assessment.sleep_assets:
                run.record_asset(asset)
            for index, report in enumerate(assessment.media_reports):
                output = run.write_report(
                    f"m2c-media-probe-{index:03d}.json",
                    report,
                )
                step.outputs.append(run.relative(output))
            output = run.write_report(
                "m2c-capture-readiness.json",
                assessment.report,
            )
            step.outputs.append(run.relative(output))
            run.manifest.configuration.update(
                {
                    "capture_manifest_sha256": assessment.report.manifest_sha256,
                    "capture_readiness_report_sha256": sha256_file(output),
                }
            )
            run.save_manifest()
    report = assessment.report
    _print_result(
        run,
        {
            "decision": report.decision,
            "quality_status": report.quality_status.value,
            "structurally_usable_clip_count": report.counts[
                "structurally_usable_clip_count"
            ],
            "camera_ready_for_model_retest": (
                report.camera_ready_for_model_retest
            ),
            "camera_matrix_complete": report.camera_matrix_complete,
            "sleep_sample_ready_for_profiling": (
                report.sleep_sample_ready_for_profiling
            ),
            "capture_bundle_ready_for_review": (
                report.capture_bundle_ready_for_review
            ),
        },
    )
    if args.require_ready and not report.capture_bundle_ready_for_review:
        return 2
    return 0


def _assess_event_evaluation_command(args: argparse.Namespace) -> int:
    from .event_evaluation import assess_fall_event_evaluation
    from .privacy import sha256_file

    with RunArtifacts(
        args.runs_dir,
        stage="v1-g4-event-evaluation-readiness",
        evidence_level=args.evidence_level,
        configuration={
            "command": "assess-event-evaluation",
            "source_type": args.source_type.value,
            "input_paths_persisted": False,
            "require_ready": args.require_ready,
        },
    ) as run:
        with run.step("assess-event-evaluation") as step:
            assessment = assess_fall_event_evaluation(
                args.bundle,
                policy_path=args.policy,
                evidence_level=args.evidence_level,
                source_type=args.source_type,
            )
            for asset in assessment.assets:
                run.record_asset(asset)
            output = run.write_report(
                "g4-event-evaluation-readiness.json",
                assessment.report,
            )
            step.outputs.append(run.relative(output))
            run.manifest.configuration.update(
                {
                    "bundle_sha256": assessment.report.bundle_sha256,
                    "policy_sha256": assessment.report.policy_sha256,
                    "capture_manifest_sha256": (
                        assessment.report.capture_manifest_sha256
                    ),
                    "candidate_generator_policy_sha256": (
                        assessment.report.candidate_generator_policy_sha256
                    ),
                    "event_evaluation_report_sha256": sha256_file(output),
                }
            )
            run.save_manifest()
    report = assessment.report
    _print_result(
        run,
        {
            "decision": report.decision,
            "quality_status": report.quality_status.value,
            "annotation_set_count": report.annotation_set_count,
            "agreement_gate_passed": report.agreement_gate_passed,
            "ground_truth_event_count": report.ground_truth_event_count,
            "negative_clip_count": report.negative_clip_count,
            "event_metrics_ready_for_review": (
                report.event_metrics_ready_for_review
            ),
            "variants": [
                {
                    "variant_id": variant.variant_id,
                    "true_positive_count": variant.true_positive_count,
                    "false_positive_count": variant.false_positive_count,
                    "false_negative_count": variant.false_negative_count,
                    "recall": variant.recall,
                    "false_activations_per_hour": (
                        variant.false_activations_per_hour
                    ),
                    "median_detection_delay_ms": (
                        variant.median_detection_delay_ms
                    ),
                }
                for variant in report.variants
            ],
            "risk_assessment_emitted": report.risk_assessment_emitted,
            "alert_emitted": report.alert_emitted,
        },
    )
    if args.require_ready and not report.event_metrics_ready_for_review:
        return 2
    return 0


def _export_fall_candidates_command(args: argparse.Namespace) -> int:
    from .fall_candidate_export import run_fall_candidate_export

    run, prediction, summary = run_fall_candidate_export(
        capture_manifest_path=args.capture_manifest,
        feature_set_path=args.feature_set,
        source_feature_run_manifest_path=args.source_feature_run_manifest,
        policy_path=args.policy,
        runs_dir=args.runs_dir,
        evidence_level=args.evidence_level,
        allow_dirty_source=args.allow_dirty_source,
    )
    _print_result(
        run,
        {
            "variant_id": prediction.variant_id,
            "clip_count": summary.clip_count,
            "input_frame_count": summary.input_frame_count,
            "activated_clip_count": summary.activated_clip_count,
            "candidate_episode_count": summary.candidate_episode_count,
            "prediction": str(
                run.reports_dir / "fall-candidate-predictions.json"
            ),
            "summary": str(
                run.reports_dir / "fall-candidate-export-summary.json"
            ),
            "risk_assessment_emitted": summary.risk_assessment_emitted,
            "alert_emitted": summary.alert_emitted,
        },
    )
    return 0


def _assemble_event_evaluation_bundle_command(args: argparse.Namespace) -> int:
    from .event_bundle import assemble_fall_event_evaluation_bundle

    assembly = assemble_fall_event_evaluation_bundle(
        output_dir=args.output,
        capture_manifest_path=args.capture_manifest,
        capture_readiness_report_path=args.readiness_report,
        capture_assessment_run_manifest_path=args.readiness_run_manifest,
        candidate_policy_path=args.candidate_policy,
        annotation_paths=args.annotation,
        adjudication_path=args.adjudication,
        prediction_sources=[tuple(pair) for pair in args.prediction_source],
        evaluation_policy_path=args.evaluation_policy,
        evidence_level=args.evidence_level,
        source_type=args.source_type,
        evaluation_id=args.evaluation_id,
    )
    print(
        json.dumps(
            {
                "bundle": str(assembly.bundle_path),
                "bundle_sha256": assembly.report.bundle_sha256,
                "preflight": str(assembly.preflight_path),
                "assembly_report": str(assembly.assembly_report_path),
                "variant_ids": assembly.report.variant_ids,
                "preflight_decision": assembly.report.preflight_decision,
                "provenance_gate_passed": (
                    assembly.report.provenance_gate_passed
                ),
                "event_metrics_ready_for_review": (
                    assembly.report.event_metrics_ready_for_review
                ),
                "risk_assessment_emitted": False,
                "alert_emitted": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _capture_fall_features_command(args: argparse.Namespace) -> int:
    from .fall_adl_benchmark import build_fall_adl_pose_backend
    from .fall_feature_capture import run_fall_feature_capture

    def backend_factory(model_policy_path: Path):
        return build_fall_adl_pose_backend(
            args.variant,
            yolo_model=args.yolo_model,
            yolo_device=args.yolo_device,
            yolo_image_size=args.yolo_image_size,
            yolo_confidence=args.yolo_confidence,
            rtmpose_detector_model=args.rtmpose_detector_model,
            rtmpose_pose_model=args.rtmpose_pose_model,
            rtmpose_device=args.rtmpose_device,
            rtmpose_detection_confidence=args.rtmpose_detection_confidence,
            torchvision_model=args.torchvision_model,
            torchvision_policy=model_policy_path,
            torchvision_device=args.torchvision_device,
            torchvision_detection_confidence=(
                args.torchvision_detection_confidence
            ),
            torchvision_min_size=args.torchvision_min_size,
            torchvision_max_size=args.torchvision_max_size,
            track=True,
        )

    run, feature_set, report = run_fall_feature_capture(
        capture_manifest_path=args.capture_manifest,
        readiness_report_path=args.readiness_report,
        readiness_run_manifest_path=args.readiness_run_manifest,
        variant_id=args.variant,
        backend_factory=backend_factory,
        config_path=args.feature_config,
        runs_dir=args.runs_dir,
        evidence_level=args.evidence_level,
        source_type=args.source_type,
        sample_fps=args.sample_fps,
        allow_dirty_readiness=args.allow_dirty_readiness,
    )
    _print_result(
        run,
        {
            "variant_id": report.variant_id,
            "clip_count": report.clip_count,
            "input_frame_count": report.input_frame_count,
            "frames_with_people": sum(
                clip.frames_with_people for clip in report.clips
            ),
            "tracked_frames": sum(clip.tracked_frames for clip in report.clips),
            "feature_set": str(
                run.reports_dir / "fall-feature-capture-set.json"
            ),
            "report": str(
                run.reports_dir / "fall-feature-capture-report.json"
            ),
            "feature_version": feature_set.feature_version,
            "risk_assessment_emitted": report.risk_assessment_emitted,
            "alert_emitted": report.alert_emitted,
        },
    )
    return 0


def _assess_sleep_route_command(args: argparse.Namespace) -> int:
    from .sleep_route import assess_sleep_route

    with RunArtifacts(
        args.runs_dir,
        stage="v1-m3-sleep-field-route",
        evidence_level=args.evidence_level,
        configuration={
            "command": "assess-sleep-route",
            "source_type": args.source_type.value,
            "policy": str(args.policy),
            "mapping_config": str(args.mapping_config),
            "values_persisted": False,
        },
    ) as run:
        with run.step("profile-sleep-fields") as step:
            profile = profile_sleep_export(
                args.path,
                evidence_level=args.evidence_level,
                source_type=args.source_type,
                device_ref=args.device_ref,
                elder_ref=args.elder_ref,
            )
            run.record_asset(profile.asset)
            run.record_observation(profile.observation)
            profile_path = run.write_report("sleep-field-profile.json", profile)
            step.outputs.append(run.relative(profile_path))
        with run.step("assess-sleep-field-route") as step:
            report = assess_sleep_route(
                profile=profile,
                policy_path=args.policy,
                mapping_config_path=args.mapping_config,
            )
            report_path = run.write_report(
                "sleep-route-assessment.json", report
            )
            step.outputs.append(run.relative(report_path))
    _print_result(
        run,
        {
            "decision": report.decision,
            "direct_field_count": report.counts["direct_total"],
            "direct_ready_count": report.counts["direct_ready"],
            "candidate_unconfirmed_count": report.counts.get(
                "direct_candidate_unconfirmed", 0
            ),
            "not_assumed_count": report.counts["not_assumed_total"],
            "derived_enabled_count": report.counts["derived_enabled"],
            "values_persisted": report.values_persisted,
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
    if args.audio_from_video and args.audio is not None:
        raise ValueError(
            "do not provide a separate audio path with --audio-from-video"
        )
    if args.audio_from_video:
        audio_path = args.video
    elif args.audio is not None:
        audio_path = args.audio
    else:
        raise ValueError(
            "provide a PCM WAV audio path or select --audio-from-video"
        )
    same_container_av = args.video.resolve() == audio_path.resolve()
    configuration = {
        "command": "run-multimodal",
        "source_type": args.source_type.value,
        "input_layout": (
            "same_container_pts"
            if same_container_av
            else "separate_files_synthetic_common_zero"
        ),
        "pose_model": _model_manifest_ref(args.pose_model),
        "pose_model_path_persisted": False,
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
            audio_path=audio_path,
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
            "input_layout": report.input_layout,
            "audio_start_offset_ms": report.audio_start_offset_ms,
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


def _model_manifest_ref(model: str | Path) -> str:
    """Return a public model filename without persisting its local directory."""

    name = Path(model).name
    if not name:
        raise ValueError("pose model must have a filename")
    return name


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


def _benchmark_pose_models_command(args: argparse.Namespace) -> int:
    from .pose_benchmark import run_pose_model_comparison

    variants = args.variant or [
        "yolo26n-pose",
        "rtmpose-m-humanart",
        "torchvision-keypointrcnn",
    ]
    run, report = run_pose_model_comparison(
        benchmark_cases_path=args.benchmark_cases,
        runs_dir=args.runs_dir,
        variants=variants,
        yolo_model=args.yolo_model,
        yolo_device=args.yolo_device,
        yolo_image_size=args.yolo_image_size,
        yolo_confidence=args.yolo_confidence,
        rtmpose_detector_model=args.rtmpose_detector_model,
        rtmpose_pose_model=args.rtmpose_pose_model,
        rtmpose_device=args.rtmpose_device,
        rtmpose_detection_confidence=args.rtmpose_detection_confidence,
        torchvision_model=args.torchvision_model,
        torchvision_policy=args.torchvision_policy,
        torchvision_device=args.torchvision_device,
        torchvision_detection_confidence=(
            args.torchvision_detection_confidence
        ),
        torchvision_min_size=args.torchvision_min_size,
        torchvision_max_size=args.torchvision_max_size,
        sample_fps=args.pose_sample_fps,
        max_duration_s=args.max_duration_s,
    )
    summaries = [
        {
            "variant_id": variant.variant_id,
            "pose_frame_coverage": variant.pose_frame_coverage,
            "lying_pose_frame_coverage": variant.by_posture_phase["lying"][
                "pose_frame_coverage"
            ],
            "pose_inference_realtime_factor": variant.realtime_factors[
                "pose_inference"
            ],
        }
        for variant in report.variants
    ]
    _print_result(
        run,
        {
            "benchmark_id": report.benchmark_id,
            "case_count": report.case_count,
            "variants": summaries,
            "comparisons": report.comparisons,
        },
    )
    return 0


def _benchmark_speech_models_command(args: argparse.Namespace) -> int:
    from .speech_benchmark import run_speech_model_comparison

    variants = args.variant or ["funasr-paraformer", "whisper-small"]
    run, report = run_speech_model_comparison(
        benchmark_cases_path=args.benchmark_cases,
        runs_dir=args.runs_dir,
        variants=variants,
        asr_model=args.asr_model,
        vad_model=args.vad_model,
        punc_model=args.punc_model,
        funasr_device=args.funasr_device,
        language=args.language,
        offline_models=args.offline_models,
        whisper_model=args.whisper_model,
        whisper_device=args.whisper_device,
        whisper_beam_size=args.whisper_beam_size,
        whisper_fp16=args.whisper_fp16,
    )
    summaries = [
        {
            "variant_id": variant.variant_id,
            "corpus_character_error_rate": (
                variant.corpus_character_error_rate
            ),
            "transcript_exact_match_count": (
                variant.transcript_exact_match_count
            ),
            "blank_output_count": variant.blank_output_count,
            "speech_inference_realtime_factor": variant.realtime_factors[
                "speech_inference"
            ],
            "silence_probe_passed": variant.silence_probe["passed"],
        }
        for variant in report.variants
    ]
    _print_result(
        run,
        {
            "benchmark_id": report.benchmark_id,
            "case_count": report.case_count,
            "variants": summaries,
            "comparisons": report.comparisons,
        },
    )
    return 0


def _benchmark_fall_features_command(args: argparse.Namespace) -> int:
    from .fall_features import run_fall_feature_benchmark

    run, report = run_fall_feature_benchmark(
        benchmark_cases_path=args.benchmark_cases,
        pose_comparison_report_path=args.pose_comparison_report,
        runs_dir=args.runs_dir,
        variant_id=args.variant,
        config_path=args.config,
        model_binding_policy_path=args.model_binding_policy,
        torchvision_policy_path=args.torchvision_policy,
        allow_dirty_source=args.allow_dirty_source,
    )
    lying = report.by_posture_phase["lying"]
    transition = report.by_posture_phase["falling_transition"]
    adl = report.by_video_class.get("adl")
    _print_result(
        run,
        {
            "benchmark_id": report.benchmark_id,
            "variant_id": report.variant_id,
            "case_count": report.case_count,
            "lying_bbox_horizontal_rate": lying.bbox_horizontal_rate,
            "lying_keypoint_gate_pass_rate": lying.keypoint_gate_pass_rate,
            "lying_box_only_frames": lying.box_only_frames,
            "transition_rapid_descent_rate": transition.rapid_descent_rate,
            "adl_bbox_horizontal_frames": (
                adl.bbox_horizontal_frames if adl is not None else 0
            ),
            "risk_assessment_emitted": report.risk_assessment_emitted,
            "alert_emitted": report.alert_emitted,
        },
    )
    return 0


def _benchmark_fall_adl_command(args: argparse.Namespace) -> int:
    from .fall_adl_benchmark import run_fall_adl_benchmark

    variants = args.variant or [
        "yolo26n-pose",
        "rtmpose-m-humanart",
        "torchvision-keypointrcnn",
    ]
    run, report = run_fall_adl_benchmark(
        fall_adl_cases_path=args.fall_adl_cases,
        runs_dir=args.runs_dir,
        variants=variants,
        config_path=args.config,
        model_binding_policy_path=args.model_binding_policy,
        yolo_model=args.yolo_model,
        yolo_device=args.yolo_device,
        yolo_image_size=args.yolo_image_size,
        yolo_confidence=args.yolo_confidence,
        rtmpose_detector_model=args.rtmpose_detector_model,
        rtmpose_pose_model=args.rtmpose_pose_model,
        rtmpose_device=args.rtmpose_device,
        rtmpose_detection_confidence=args.rtmpose_detection_confidence,
        torchvision_model=args.torchvision_model,
        torchvision_policy=args.torchvision_policy,
        torchvision_device=args.torchvision_device,
        torchvision_detection_confidence=(
            args.torchvision_detection_confidence
        ),
        torchvision_min_size=args.torchvision_min_size,
        torchvision_max_size=args.torchvision_max_size,
        sample_fps=args.pose_sample_fps,
        max_duration_s=args.max_duration_s,
    )
    summaries = []
    for variant in report.variants:
        metrics = variant.overall.fall_feature_metrics
        summaries.append(
            {
                "variant_id": variant.variant_id,
                "pose_frame_coverage": variant.overall.pose_frame_coverage,
                "bbox_horizontal_frames": metrics.bbox_horizontal_frames,
                "maximum_horizontal_duration_ms": (
                    metrics.maximum_horizontal_duration_ms
                ),
                "rapid_descent_frames": metrics.rapid_descent_frames,
                "low_motion_frames": metrics.low_motion_frames,
                "risk_assessment_emitted": variant.risk_assessment_emitted,
                "alert_emitted": variant.alert_emitted,
            }
        )
    _print_result(
        run,
        {
            "suite_id": report.suite_id,
            "case_count": report.case_count,
            "variants": summaries,
            "risk_assessment_emitted": report.risk_assessment_emitted,
            "alert_emitted": report.alert_emitted,
        },
    )
    return 0


def _benchmark_fall_candidates_command(args: argparse.Namespace) -> int:
    from .fall_candidates import run_fall_candidate_public_stress

    run, report = run_fall_candidate_public_stress(
        urfd_run_dirs=args.urfd_run,
        caucafall_run_dir=args.caucafall_run,
        benchmark_cases_path=args.benchmark_cases,
        policy_path=args.policy,
        runs_dir=args.runs_dir,
        allow_dirty_source=args.allow_dirty_source,
    )
    summaries = [
        {
            "variant_id": variant.variant_id,
            "urfd_fall_activated_count": variant.urfd_fall_activated_count,
            "urfd_fall_case_count": variant.urfd_fall_case_count,
            "urfd_adl_false_activation_count": (
                variant.urfd_adl_false_activation_count
            ),
            "caucafall_false_activation_count": (
                variant.caucafall_false_activation_count
            ),
            "negative_episode_count": variant.negative_episode_count,
            "false_activations_per_hour": variant.false_activations_per_hour,
            "risk_assessment_emitted": variant.risk_assessment_emitted,
            "alert_emitted": variant.alert_emitted,
        }
        for variant in report.variants
    ]
    _print_result(
        run,
        {
            "benchmark_id": report.benchmark_id,
            "candidate_policy_id": report.candidate_policy_id,
            "case_evaluation_count": report.case_evaluation_count,
            "variants": summaries,
            "risk_assessment_emitted": report.risk_assessment_emitted,
            "alert_emitted": report.alert_emitted,
        },
    )
    return 0


def _benchmark_static_home_command(args: argparse.Namespace) -> int:
    from .static_home_benchmark import run_static_home_benchmark

    variants = args.variant or [
        "yolo26n-pose",
        "rtmpose-m-humanart",
        "torchvision-keypointrcnn",
    ]
    run, report = run_static_home_benchmark(
        static_home_cases_path=args.static_home_cases,
        runs_dir=args.runs_dir,
        variants=variants,
        model_binding_policy_path=args.model_binding_policy,
        yolo_model=args.yolo_model,
        yolo_device=args.yolo_device,
        yolo_image_size=args.yolo_image_size,
        yolo_confidence=args.yolo_confidence,
        rtmpose_detector_model=args.rtmpose_detector_model,
        rtmpose_pose_model=args.rtmpose_pose_model,
        rtmpose_device=args.rtmpose_device,
        rtmpose_detection_confidence=args.rtmpose_detection_confidence,
        torchvision_model=args.torchvision_model,
        torchvision_policy=args.torchvision_policy,
        torchvision_device=args.torchvision_device,
        torchvision_detection_confidence=(
            args.torchvision_detection_confidence
        ),
        torchvision_min_size=args.torchvision_min_size,
        torchvision_max_size=args.torchvision_max_size,
    )
    summaries = []
    for variant in report.variants:
        metrics = variant.overall
        summaries.append(
            {
                "variant_id": variant.variant_id,
                "person_absent_false_activation_rate": (
                    metrics.person_absent_false_activation_rate
                ),
                "matched_person_count": metrics.matched_person_count,
                "false_positive_count": metrics.false_positive_count,
                "false_negative_count": metrics.false_negative_count,
                "detection_precision": metrics.detection_precision,
                "detection_recall": metrics.detection_recall,
                "multi_all_people_matched_cases": (
                    metrics.multi_all_people_matched_cases
                ),
                "risk_assessment_emitted": variant.risk_assessment_emitted,
                "alert_emitted": variant.alert_emitted,
            }
        )
    _print_result(
        run,
        {
            "suite_id": report.suite_id,
            "case_count": report.case_count,
            "matching_iou_threshold": report.matching_iou_threshold,
            "variants": summaries,
            "risk_assessment_emitted": report.risk_assessment_emitted,
            "alert_emitted": report.alert_emitted,
        },
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "probe-media":
        return _probe_media_command(args)
    if args.command == "assess-m2c-capture":
        return _assess_m2c_capture_command(args)
    if args.command == "assess-event-evaluation":
        return _assess_event_evaluation_command(args)
    if args.command == "assemble-event-evaluation-bundle":
        return _assemble_event_evaluation_bundle_command(args)
    if args.command == "export-fall-candidates":
        return _export_fall_candidates_command(args)
    if args.command == "capture-fall-features":
        return _capture_fall_features_command(args)
    if args.command == "profile-sleep":
        return _profile_sleep_command(args)
    if args.command == "assess-sleep-route":
        return _assess_sleep_route_command(args)
    if args.command == "inspect-ezviz":
        return _inspect_ezviz_command(args)
    if args.command == "run-multimodal":
        return _run_multimodal_command(args)
    if args.command == "benchmark-dataset":
        return _benchmark_dataset_command(args)
    if args.command == "benchmark-pose-models":
        return _benchmark_pose_models_command(args)
    if args.command == "benchmark-fall-features":
        return _benchmark_fall_features_command(args)
    if args.command == "benchmark-fall-adl":
        return _benchmark_fall_adl_command(args)
    if args.command == "benchmark-fall-candidates":
        return _benchmark_fall_candidates_command(args)
    if args.command == "benchmark-static-home":
        return _benchmark_static_home_command(args)
    if args.command == "benchmark-speech-models":
        return _benchmark_speech_models_command(args)
    raise RuntimeError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
