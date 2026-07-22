from __future__ import annotations

import os
import platform
import socket
from collections import Counter
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from .artifacts import RunArtifacts
from .contracts import (
    EvidenceLevel,
    FeatureEvent,
    MediaProbeReport,
    MultimodalPipelineReport,
    MultimodalWindow,
    PrivacyLevel,
    QualityStatus,
    SourceType,
    TimeRange,
)
from .media_probe import probe_media
from .pose_backend import PoseBackend, PoseDetection
from .speech_backend import SpeechBackend, tag_transcript
from .streaming import (
    AudioBuffer,
    OpenCVVideoReplay,
    read_container_audio,
    read_pcm_wav,
)


PIPELINE_VERSION = "multimodal-replay-v0.3.0"


@dataclass(frozen=True)
class MultimodalPipelineConfig:
    video_sample_fps: float = 5.0
    fusion_window_ms: int = 2000
    max_duration_s: float | None = 30.0

    def __post_init__(self) -> None:
        if self.video_sample_fps <= 0:
            raise ValueError("video_sample_fps must be positive")
        if self.fusion_window_ms <= 0:
            raise ValueError("fusion_window_ms must be positive")
        if self.max_duration_s is not None and self.max_duration_s <= 0:
            raise ValueError("max_duration_s must be positive")


def run_multimodal_pipeline(
    *,
    video_path: Path,
    audio_path: Path,
    pose_backend: PoseBackend,
    speech_backend: SpeechBackend,
    run: RunArtifacts,
    config: MultimodalPipelineConfig,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.LOCAL_FILE,
    device_ref: str | None = None,
    elder_ref: str | None = None,
    model_load_wall_ms: float | None = None,
) -> MultimodalPipelineReport:
    processing_started = perf_counter()
    same_container_av = _same_resolved_path(video_path, audio_path)
    audio_start_offset_ms = 0.0
    with run.step("probe-multimodal-inputs") as step:
        video_probe = probe_media(
            video_path,
            evidence_level=evidence_level,
            device_ref=device_ref,
            elder_ref=elder_ref,
            source_type=source_type,
            require_audio_track=same_container_av,
        )
        run.record_asset(video_probe.asset)
        run.record_observation(video_probe.observation)
        if same_container_av:
            audio_start_offset_ms = _same_container_audio_offset(video_probe)
            audio_probe = video_probe
            probe_path = run.write_report(
                "multimodal-container-probe.json",
                video_probe,
            )
            step.outputs.append(run.relative(probe_path))
        else:
            audio_probe = probe_media(
                audio_path,
                evidence_level=evidence_level,
                device_ref=device_ref,
                elder_ref=elder_ref,
                source_type=source_type,
            )
            run.record_asset(audio_probe.asset)
            run.record_observation(audio_probe.observation)
            video_probe_path = run.write_report(
                "multimodal-video-probe.json",
                video_probe,
            )
            audio_probe_path = run.write_report(
                "multimodal-audio-probe.json",
                audio_probe,
            )
            step.outputs.extend(
                [run.relative(video_probe_path), run.relative(audio_probe_path)]
            )

    pose_events: list[FeatureEvent] = []
    pose_latencies_ms: list[float] = []
    pose_detection_count = 0
    pose_frames_with_people = 0
    last_video_timestamp_ms = 0
    video_started = perf_counter()
    replay = OpenCVVideoReplay(
        video_path,
        sample_fps=config.video_sample_fps,
        max_duration_s=config.max_duration_s,
    )
    with run.step("extract-video-pose") as step:
        for sequence, packet in enumerate(replay):
            inference_started = perf_counter()
            detections = pose_backend.infer(packet.frame)
            pose_latencies_ms.append((perf_counter() - inference_started) * 1000.0)
            pose_detection_count += len(detections)
            pose_frames_with_people += int(bool(detections))
            last_video_timestamp_ms = max(last_video_timestamp_ms, packet.timestamp_ms)
            event = _pose_feature(
                run_id=run.run_id,
                sequence=sequence,
                timestamp_ms=packet.timestamp_ms,
                sample_fps=config.video_sample_fps,
                observation_id=video_probe.observation.observation_id,
                detections=detections,
                model_digest=_first_digest(pose_backend.bindings),
                extractor_version=_first_version(pose_backend.bindings),
            )
            run.record_feature(event)
            pose_events.append(event)
        step.outputs.append("features.jsonl")
    video_wall_ms = (perf_counter() - video_started) * 1000.0

    with run.step("load-audio-stream"):
        if same_container_av:
            audio = read_container_audio(
                audio_path,
                audio_minus_video_start_ms=audio_start_offset_ms,
                target_sample_rate_hz=16000,
                max_duration_s=config.max_duration_s,
            )
        else:
            audio = read_pcm_wav(audio_path, target_sample_rate_hz=16000)
            audio = _limit_audio(audio, config.max_duration_s)

    speech_started = perf_counter()
    with run.step("extract-speech-language") as step:
        segments = speech_backend.transcribe(audio)
        speech_events, transcript_events, semantic_events = _speech_features(
            run_id=run.run_id,
            observation_id=audio_probe.observation.observation_id,
            segments=segments,
            bindings=speech_backend.bindings,
            timeline_offset_ms=audio.start_ms,
        )
        for event in [*speech_events, *transcript_events, *semantic_events]:
            run.record_feature(event)
        step.outputs.append("features.jsonl")
    speech_wall_ms = (perf_counter() - speech_started) * 1000.0

    video_duration_ms = _video_duration_ms(
        video_probe.technical_metadata,
        last_video_timestamp_ms,
        config.video_sample_fps,
        config.max_duration_s,
    )
    duration_ms = max(video_duration_ms, audio.start_ms + audio.duration_ms)
    all_events = [
        *pose_events,
        *speech_events,
        *transcript_events,
        *semantic_events,
    ]
    with run.step("align-multimodal-windows") as step:
        windows = _build_windows(
            run_id=run.run_id,
            duration_ms=duration_ms,
            window_ms=config.fusion_window_ms,
            video_observation_id=video_probe.observation.observation_id,
            audio_observation_id=audio_probe.observation.observation_id,
            events=all_events,
        )
        for window in windows:
            run.record_multimodal_window(window)
        step.outputs.append("multimodal_windows.jsonl")

    semantic_tag_counts = Counter(
        tag
        for event in semantic_events
        for tag in event.value.get("tags", [])
    )
    processing_wall_ms = (perf_counter() - processing_started) * 1000.0
    bindings = [*pose_backend.bindings, *speech_backend.bindings]
    timing_ms = {
        "processing_total_wall": round(processing_wall_ms, 3),
        "video_pose_wall": round(video_wall_ms, 3),
        "speech_language_wall": round(speech_wall_ms, 3),
        "pose_inference_mean": _rounded_mean(pose_latencies_ms),
        "pose_inference_first": _first_or_zero(pose_latencies_ms),
        "pose_inference_steady_mean": _rounded_mean(pose_latencies_ms[1:]),
        "pose_inference_p95": _percentile(pose_latencies_ms, 0.95),
        "pose_inference_max": _max_or_zero(pose_latencies_ms),
    }
    realtime_factors = {
        "processing_end_to_end": _realtime_factor(processing_wall_ms, duration_ms),
        "video_pose": _realtime_factor(video_wall_ms, video_duration_ms),
        "speech_language": _realtime_factor(speech_wall_ms, audio.duration_ms),
    }
    if model_load_wall_ms is not None:
        cold_start_wall_ms = model_load_wall_ms + processing_wall_ms
        timing_ms["model_load_wall"] = round(model_load_wall_ms, 3)
        timing_ms["cold_start_total_wall"] = round(cold_start_wall_ms, 3)
        realtime_factors["cold_start_end_to_end"] = _realtime_factor(
            cold_start_wall_ms,
            duration_ms,
        )
    report = MultimodalPipelineReport(
        pipeline_version=PIPELINE_VERSION,
        video_asset_id=video_probe.asset.asset_id,
        audio_asset_id=audio_probe.asset.asset_id,
        model_bindings=bindings,
        duration_ms=duration_ms,
        sampled_video_frames=len(pose_events),
        pose_frames_with_people=pose_frames_with_people,
        pose_detection_count=pose_detection_count,
        speech_segment_count=len(speech_events),
        transcript_segment_count=len(transcript_events),
        multimodal_window_count=len(windows),
        semantic_tag_counts=dict(sorted(semantic_tag_counts.items())),
        runtime_environment=_runtime_environment(),
        timing_ms=timing_ms,
        realtime_factors=realtime_factors,
        input_layout=(
            "same_container_pts"
            if same_container_av
            else "separate_files_synthetic_common_zero"
        ),
        same_container_av=same_container_av,
        audio_start_offset_ms=audio_start_offset_ms,
        limitations=[
            "offline_replay_is_not_live_transport_latency",
            *(
                [
                    "container_pts_does_not_prove_capture_clock_accuracy",
                    "single_start_offset_does_not_measure_clock_drift",
                ]
                if same_container_av
                else [
                    "separate_video_and_audio_inputs_assume_a_common_zero_time"
                ]
            ),
            "pose_coordinates_are_uncalibrated_image_coordinates",
            "transcript_features_are_sensitive_and_runs_must_remain_controlled",
            "semantic_tags_are_lexical_observations_not_risk_diagnoses",
        ],
    )
    with run.step("write-multimodal-report") as step:
        report_path = run.write_report("multimodal-pipeline-report.json", report)
        step.outputs.append(run.relative(report_path))
    return report


def _pose_feature(
    *,
    run_id: str,
    sequence: int,
    timestamp_ms: int,
    sample_fps: float,
    observation_id: str,
    detections: list[PoseDetection],
    model_digest: str | None,
    extractor_version: str | None,
) -> FeatureEvent:
    confidences = [item.confidence for item in detections if item.confidence is not None]
    point_confidences = [
        point[2]
        for detection in detections
        for point in detection.keypoints_xyc
        if len(point) >= 3
    ]
    visible_ratio = (
        sum(value >= 0.5 for value in point_confidences) / len(point_confidences)
        if point_confidences
        else None
    )
    end_ms = timestamp_ms + max(1, round(1000.0 / sample_fps))
    return FeatureEvent(
        feature_id=f"feature_{run_id}_pose_{sequence:06d}",
        observation_id=observation_id,
        feature_type="video.pose_frame",
        time_range=TimeRange(start_ms=timestamp_ms, end_ms=end_ms),
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
        quality=round(visible_ratio, 6) if visible_ratio is not None else None,
        extractor_name="ultralytics-pose-adapter",
        extractor_version=extractor_version or "unknown",
        model_digest=model_digest,
        privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
        limitations=["uncalibrated_image_coordinates", "coco_17_keypoints"],
    )


def _speech_features(
    *,
    run_id: str,
    observation_id: str,
    segments: list[Any],
    bindings: list[Any],
    timeline_offset_ms: int = 0,
) -> tuple[list[FeatureEvent], list[FeatureEvent], list[FeatureEvent]]:
    if timeline_offset_ms < 0:
        raise ValueError("timeline_offset_ms must be non-negative")
    speech_events: list[FeatureEvent] = []
    transcript_events: list[FeatureEvent] = []
    semantic_events: list[FeatureEvent] = []
    vad_binding = _binding_for_task(bindings, "voice_activity_detection")
    asr_binding = _binding_for_task(bindings, "mandarin_speech_recognition")
    vad_version = _backend_version(vad_binding)
    asr_version = _backend_version(asr_binding)
    for sequence, segment in enumerate(segments):
        time_range = TimeRange(
            start_ms=timeline_offset_ms + segment.start_ms,
            end_ms=timeline_offset_ms + segment.end_ms,
        )
        speech_id = f"feature_{run_id}_speech_{sequence:04d}"
        transcript_id = f"feature_{run_id}_transcript_{sequence:04d}"
        speech_event = FeatureEvent(
            feature_id=speech_id,
            observation_id=observation_id,
            feature_type="audio.speech_segment",
            time_range=time_range,
            value={"speech_detected": True},
            confidence=segment.confidence,
            extractor_name="funasr-vad-adapter",
            extractor_version=vad_version,
            model_digest=vad_binding.model_digest if vad_binding else None,
            privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
        )
        transcript_event = FeatureEvent(
            feature_id=transcript_id,
            observation_id=observation_id,
            feature_type="language.transcript_segment",
            time_range=time_range,
            value={"text": segment.text, "language": segment.language},
            confidence=segment.confidence,
            extractor_name="funasr-asr-adapter",
            extractor_version=asr_version,
            model_digest=asr_binding.model_digest if asr_binding else None,
            privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
            source_feature_refs=[speech_id],
            limitations=["automatic_transcript_requires_human_review"],
        )
        speech_events.append(speech_event)
        transcript_events.append(transcript_event)
        tags = tag_transcript(segment.text)
        if tags:
            semantic_events.append(
                FeatureEvent(
                    feature_id=f"feature_{run_id}_semantic_{sequence:04d}",
                    observation_id=observation_id,
                    feature_type="language.lexical_tags",
                    time_range=time_range,
                    value={"tags": tags},
                    extractor_name="kangshield-keyword-rules",
                    extractor_version="0.1.0",
                    privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
                    source_feature_refs=[transcript_id],
                    limitations=[
                        "keyword_match_is_not_intent_or_risk_classification"
                    ],
                )
            )
    return speech_events, transcript_events, semantic_events


def _build_windows(
    *,
    run_id: str,
    duration_ms: int,
    window_ms: int,
    video_observation_id: str,
    audio_observation_id: str,
    events: list[FeatureEvent],
) -> list[MultimodalWindow]:
    windows: list[MultimodalWindow] = []
    for index, start_ms in enumerate(range(0, max(duration_ms, 1), window_ms)):
        end_ms = min(duration_ms, start_ms + window_ms)
        if end_ms <= start_ms:
            end_ms = start_ms + window_ms
        matching = [
            event
            for event in events
            if _overlaps(event.time_range, start_ms, end_ms)
        ]
        poses = [event for event in matching if event.feature_type == "video.pose_frame"]
        speech = [
            event for event in matching if event.feature_type == "audio.speech_segment"
        ]
        transcripts = [
            event
            for event in matching
            if event.feature_type == "language.transcript_segment"
        ]
        semantics = [
            event for event in matching if event.feature_type == "language.lexical_tags"
        ]
        track_ids = sorted(
            {
                str(detection["track_id"])
                for event in poses
                for detection in event.value.get("detections", [])
                if detection.get("track_id") is not None
            }
        )
        semantic_tags = sorted(
            {
                tag
                for event in semantics
                for tag in event.value.get("tags", [])
            }
        )
        windows.append(
            MultimodalWindow(
                window_id=f"window_{run_id}_{index:05d}",
                time_range=TimeRange(start_ms=start_ms, end_ms=end_ms),
                video_observation_id=video_observation_id,
                audio_observation_id=audio_observation_id,
                source_feature_refs=[event.feature_id for event in matching],
                pose_frame_count=len(poses),
                max_person_count=max(
                    (event.value.get("person_count", 0) for event in poses),
                    default=0,
                ),
                track_ids=track_ids,
                speech_segment_count=len(speech),
                transcript_feature_refs=[event.feature_id for event in transcripts],
                semantic_tags=semantic_tags,
                stream_available={"video": True, "audio": True, "language": True},
                quality_status=QualityStatus.PASS,
            )
        )
    return windows


def _overlaps(time_range: TimeRange, start_ms: int, end_ms: int) -> bool:
    event_start = time_range.start_ms or 0
    event_end = time_range.end_ms if time_range.end_ms is not None else event_start + 1
    return event_start < end_ms and event_end > start_ms


def _limit_audio(audio: AudioBuffer, max_duration_s: float | None) -> AudioBuffer:
    if max_duration_s is None:
        return audio
    maximum_timeline_ms = round(max_duration_s * 1000.0)
    if audio.start_ms >= maximum_timeline_ms:
        raise ValueError("audio does not overlap the replay window")
    if audio.start_ms + audio.duration_ms <= maximum_timeline_ms:
        return audio
    available_ms = maximum_timeline_ms - audio.start_ms
    sample_count = round(available_ms * audio.sample_rate_hz / 1000.0)
    samples = audio.samples[:sample_count]
    return AudioBuffer(
        samples=samples,
        sample_rate_hz=audio.sample_rate_hz,
        duration_ms=round(len(samples) * 1000 / audio.sample_rate_hz),
        start_ms=audio.start_ms,
    )


def _same_resolved_path(first: Path, second: Path) -> bool:
    return Path(first).resolve() == Path(second).resolve()


def _same_container_audio_offset(probe: MediaProbeReport) -> float:
    timing = probe.container_timing
    failures: list[str] = []
    if probe.observation.quality_status is QualityStatus.FAIL:
        failures.append("media_probe_failed")
    if timing is None:
        failures.append("container_timing_unavailable")
    else:
        if timing.video_stream_count != 1:
            failures.append("video_stream_count_must_equal_one")
        if timing.audio_stream_count != 1:
            failures.append("audio_stream_count_must_equal_one")
        if not timing.same_container_av:
            failures.append("audio_video_tracks_not_verified")
        if not timing.can_measure_start_offset:
            failures.append("audio_video_start_offset_unavailable")
        if (
            timing.audio_minus_video_start_ms is None
            or not isfinite(timing.audio_minus_video_start_ms)
        ):
            failures.append("audio_video_start_offset_invalid")
        for stream in timing.streams:
            if stream.stream_type not in {"video", "audio"}:
                continue
            if stream.packet_count <= 0:
                failures.append(f"{stream.stream_type}_packets_missing")
            if stream.missing_pts_count:
                failures.append(f"{stream.stream_type}_packet_pts_missing")
            if stream.scan_truncated:
                failures.append(f"{stream.stream_type}_packet_scan_truncated")
            if stream.stream_type == "audio" and stream.pts_backward_step_count:
                failures.append("audio_packet_pts_not_monotonic")
    if failures:
        raise ValueError(
            "same-container PTS gate failed: " + ", ".join(sorted(set(failures)))
        )
    assert timing is not None
    assert timing.audio_minus_video_start_ms is not None
    return float(timing.audio_minus_video_start_ms)


def _video_duration_ms(
    metadata: dict[str, Any],
    last_timestamp_ms: int,
    sample_fps: float,
    max_duration_s: float | None,
) -> int:
    duration = metadata.get("duration_s")
    if isinstance(duration, (int, float)) and duration >= 0:
        duration_ms = round(float(duration) * 1000.0)
    else:
        duration_ms = last_timestamp_ms + round(1000.0 / sample_fps)
    if max_duration_s is not None:
        duration_ms = min(duration_ms, round(max_duration_s * 1000.0))
    return max(0, duration_ms)


def _first_digest(bindings: list[Any]) -> str | None:
    return next(
        (binding.model_digest for binding in bindings if binding.model_digest),
        None,
    )


def _first_version(bindings: list[Any]) -> str | None:
    return next(
        (binding.model_version for binding in bindings if binding.model_version),
        None,
    )


def _binding_for_task(bindings: list[Any], task: str) -> Any | None:
    return next((binding for binding in bindings if binding.task == task), None)


def _backend_version(binding: Any | None) -> str:
    if binding is None:
        return "unknown"
    configured = binding.configuration.get("funasr_version")
    return str(configured or binding.model_version or "unknown")


def _rounded_mean(values: list[float]) -> float:
    return round(mean(values), 3) if values else 0.0


def _first_or_zero(values: list[float]) -> float:
    return round(values[0], 3) if values else 0.0


def _max_or_zero(values: list[float]) -> float:
    return round(max(values), 3) if values else 0.0


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def _realtime_factor(wall_ms: float, media_ms: int) -> float:
    return round(wall_ms / media_ms, 6) if media_ms > 0 else 0.0


def _runtime_environment() -> dict[str, Any]:
    environment: dict[str, Any] = {
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
    }
    try:
        import torch
    except ImportError:
        environment["torch"] = "unavailable"
        return environment
    environment.update(
        {
            "torch": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
        }
    )
    if torch.cuda.is_available():
        environment.update(
            {
                "cuda_device": torch.cuda.get_device_name(0),
                "cuda_memory_allocated_mb": round(
                    torch.cuda.memory_allocated(0) / 1024**2,
                    3,
                ),
                "cuda_memory_reserved_mb": round(
                    torch.cuda.memory_reserved(0) / 1024**2,
                    3,
                ),
                "cuda_peak_memory_allocated_mb": round(
                    torch.cuda.max_memory_allocated(0) / 1024**2,
                    3,
                ),
            }
        )
    return environment
