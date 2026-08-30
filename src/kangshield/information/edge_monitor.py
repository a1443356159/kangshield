"""Continuous in-memory monitoring with bounded anomaly-only local archives."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
from statistics import median
from time import monotonic
from typing import Any, Callable
from urllib.parse import urlsplit
from uuid import uuid4

from .contracts import (
    EVIDENCE_RANK,
    EdgeKeyWindow,
    EdgeSegmentAudit,
    EvidenceLevel,
    SourceType,
    ensure_source_evidence_compatible,
)
from .longitudinal.store import DEFAULT_STORE_ROOT, LongitudinalStore, dumps_compact
from .multidomain import DEFAULT_POLICY_PATH, build_snapshot, insert_candidate, load_policy
from .segment_analysis import (
    AnalysisResult,
    SegmentResultSummarizer,
    merge_daily_feature,
    pose_feature,
    speech_features,
)
from .speech_backend import AudioBuffer


EDGE_MONITOR_VERSION = "edge-monitor-v0.2.0"
DEFAULT_EDGE_POLICY_PATH = Path("configs/v2-edge-segment-policy.json")
_PUBLIC_FAILURE_CODES = frozenset(
    {
        "endpoint_unavailable",
        "stream_open_failed",
        "video_track_invalid",
        "audio_track_invalid",
        "packet_timestamp_missing",
        "segment_too_short",
        "decode_failed",
        "selector_failed",
        "pose_model_failed",
        "speech_model_failed",
        "pose_and_speech_models_failed",
        "analysis_backpressure",
        "store_write_failed",
        "media_archive_failed",
    }
)


class EdgeMonitorError(RuntimeError):
    """A sanitized continuous-monitor failure safe to persist."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code if code in _PUBLIC_FAILURE_CODES else "decode_failed"


@dataclass(frozen=True)
class EdgeSelectionPolicy:
    revision: str
    digest: str
    segment_duration_seconds: float
    minimum_segment_seconds: float
    video_sample_fps: float
    video_buffer_width_px: int
    jpeg_quality: int
    motion_thumbnail_width_px: int
    motion_min_score: float
    motion_mad_multiplier: float
    motion_pre_seconds: float
    motion_post_seconds: float
    baseline_interval_seconds: float
    maximum_selected_video_ratio: float
    audio_sample_rate_hz: int
    audio_gate_window_ms: int
    audio_min_rms: float
    audio_noise_multiplier: float
    audio_activity_override_rms: float
    audio_pad_seconds: float
    audio_merge_gap_seconds: float
    maximum_asr_window_seconds: float
    maximum_selected_audio_ratio: float
    archive_enabled: bool
    archive_event_pre_seconds: float
    archive_event_post_seconds: float
    archive_retention_days: int
    archive_maximum_total_bytes: int
    archive_container: str
    archive_video_codec: str
    archive_audio_codec: str
    limitations: tuple[str, ...]

    @classmethod
    def load(cls, path: Path = DEFAULT_EDGE_POLICY_PATH) -> "EdgeSelectionPolicy":
        raw = Path(path).read_bytes()
        payload = json.loads(raw)
        archive = payload.get("anomaly_archive", {})
        policy = cls(
            revision=str(payload["revision"]),
            digest=hashlib.sha256(raw).hexdigest(),
            segment_duration_seconds=float(payload["segment_duration_seconds"]),
            minimum_segment_seconds=float(payload["minimum_segment_seconds"]),
            video_sample_fps=float(payload["video_sample_fps"]),
            video_buffer_width_px=int(payload["video_buffer_width_px"]),
            jpeg_quality=int(payload["jpeg_quality"]),
            motion_thumbnail_width_px=int(payload["motion_thumbnail_width_px"]),
            motion_min_score=float(payload["motion_min_score"]),
            motion_mad_multiplier=float(payload["motion_mad_multiplier"]),
            motion_pre_seconds=float(payload["motion_pre_seconds"]),
            motion_post_seconds=float(payload["motion_post_seconds"]),
            baseline_interval_seconds=float(payload["baseline_interval_seconds"]),
            maximum_selected_video_ratio=float(
                payload["maximum_selected_video_ratio"]
            ),
            audio_sample_rate_hz=int(payload["audio_sample_rate_hz"]),
            audio_gate_window_ms=int(payload["audio_gate_window_ms"]),
            audio_min_rms=float(payload["audio_min_rms"]),
            audio_noise_multiplier=float(payload["audio_noise_multiplier"]),
            audio_activity_override_rms=float(
                payload["audio_activity_override_rms"]
            ),
            audio_pad_seconds=float(payload["audio_pad_seconds"]),
            audio_merge_gap_seconds=float(payload["audio_merge_gap_seconds"]),
            maximum_asr_window_seconds=float(
                payload["maximum_asr_window_seconds"]
            ),
            maximum_selected_audio_ratio=float(
                payload["maximum_selected_audio_ratio"]
            ),
            archive_enabled=bool(archive.get("enabled", False)),
            archive_event_pre_seconds=float(archive.get("event_pre_seconds", 10)),
            archive_event_post_seconds=float(archive.get("event_post_seconds", 20)),
            archive_retention_days=int(archive.get("retention_days", 30)),
            archive_maximum_total_bytes=int(
                archive.get("maximum_total_bytes", 2_147_483_648)
            ),
            archive_container=str(archive.get("container", "mp4")),
            archive_video_codec=str(archive.get("video_codec", "libx264")),
            archive_audio_codec=str(archive.get("audio_codec", "aac")),
            limitations=tuple(str(item) for item in payload.get("limitations", [])),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        positive = {
            "segment_duration_seconds": self.segment_duration_seconds,
            "minimum_segment_seconds": self.minimum_segment_seconds,
            "video_sample_fps": self.video_sample_fps,
            "motion_mad_multiplier": self.motion_mad_multiplier,
            "motion_pre_seconds": self.motion_pre_seconds,
            "motion_post_seconds": self.motion_post_seconds,
            "baseline_interval_seconds": self.baseline_interval_seconds,
            "audio_noise_multiplier": self.audio_noise_multiplier,
            "audio_pad_seconds": self.audio_pad_seconds,
            "maximum_asr_window_seconds": self.maximum_asr_window_seconds,
        }
        if any(not isfinite(value) or value <= 0 for value in positive.values()):
            raise ValueError("edge selection durations and rates must be positive")
        if self.minimum_segment_seconds > self.segment_duration_seconds:
            raise ValueError("minimum edge segment exceeds requested duration")
        for value in (
            self.motion_min_score,
            self.maximum_selected_video_ratio,
            self.audio_min_rms,
            self.audio_activity_override_rms,
            self.maximum_selected_audio_ratio,
        ):
            if not isfinite(value) or not 0 < value <= 1:
                raise ValueError("edge selection ratios and thresholds must be in (0, 1]")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")
        if min(
            self.video_buffer_width_px,
            self.motion_thumbnail_width_px,
            self.audio_sample_rate_hz,
            self.audio_gate_window_ms,
        ) <= 0:
            raise ValueError("edge selection dimensions must be positive")
        if (
            not isfinite(self.archive_event_pre_seconds)
            or self.archive_event_pre_seconds < 0
            or not isfinite(self.archive_event_post_seconds)
            or self.archive_event_post_seconds <= 0
        ):
            raise ValueError("anomaly archive window is invalid")
        if self.archive_retention_days <= 0:
            raise ValueError("anomaly archive retention days must be positive")
        if self.archive_maximum_total_bytes <= 0:
            raise ValueError("anomaly archive byte limit must be positive")
        if (
            self.archive_container,
            self.archive_video_codec,
            self.archive_audio_codec,
        ) != ("mp4", "libx264", "aac"):
            raise ValueError("anomaly archive must use MP4 with H.264/AAC")


@dataclass(frozen=True)
class BufferedVideoFrame:
    timestamp_ms: int
    jpeg_bytes: bytes


@dataclass(frozen=True)
class InMemoryEdgeSegment:
    segment_id: str
    device_ref: str
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    frames: tuple[BufferedVideoFrame, ...]
    audio: AudioBuffer
    frame_width: int
    frame_height: int
    cloud_recording_ref: str


@dataclass(frozen=True)
class SegmentSelection:
    video_frames: tuple[BufferedVideoFrame, ...]
    audio_windows_ms: tuple[tuple[int, int], ...]
    key_windows: tuple[EdgeKeyWindow, ...]
    motion_threshold: float
    audio_threshold: float

    @property
    def selected_audio_seconds(self) -> float:
        return sum(end - start for start, end in self.audio_windows_ms) / 1000.0


@dataclass(frozen=True)
class EdgeAnalysisOutcome:
    result: AnalysisResult
    selection: SegmentSelection
    failure_codes: tuple[str, ...] = ()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cloud_recording_ref(device_ref: str, started_at: datetime, ended_at: datetime) -> str:
    digest = hashlib.sha256(
        f"cloud|{device_ref}|{started_at.isoformat()}|{ended_at.isoformat()}".encode()
    ).hexdigest()[:32]
    return f"cloud-recording:{digest}"


def _receipt_digest(segment: InMemoryEdgeSegment, selector_digest: str) -> str:
    payload = {
        "segment_id": segment.segment_id,
        "device_ref": segment.device_ref,
        "started_at": segment.started_at.isoformat(),
        "ended_at": segment.ended_at.isoformat(),
        "cloud_recording_ref": segment.cloud_recording_ref,
        "selector_digest": selector_digest,
        "raw_media_persisted": False,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class LightweightSegmentSelector:
    """Motion/energy gate that never emits a risk result by itself."""

    def __init__(self, policy: EdgeSelectionPolicy) -> None:
        self.policy = policy

    def select(self, segment: InMemoryEdgeSegment) -> SegmentSelection:
        try:
            video_frames, video_windows, motion_threshold = self._select_video(segment)
            audio_windows, audio_key_windows, audio_threshold = self._select_audio(segment)
        except EdgeMonitorError:
            raise
        except Exception as error:
            raise EdgeMonitorError(
                "lightweight selector failed", code="selector_failed"
            ) from error
        key_windows = _combine_key_windows(
            [*video_windows, *audio_key_windows], segment.duration_ms
        )
        return SegmentSelection(
            video_frames=tuple(video_frames),
            audio_windows_ms=tuple(audio_windows),
            key_windows=tuple(key_windows),
            motion_threshold=motion_threshold,
            audio_threshold=audio_threshold,
        )

    def _select_video(
        self, segment: InMemoryEdgeSegment
    ) -> tuple[list[BufferedVideoFrame], list[EdgeKeyWindow], float]:
        import cv2
        import numpy as np

        frames = list(segment.frames)
        if not frames:
            return [], [], self.policy.motion_min_score
        grays: list[Any] = []
        for item in frames:
            encoded = np.frombuffer(item.jpeg_bytes, dtype=np.uint8)
            gray = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                raise EdgeMonitorError("buffered frame decode failed", code="selector_failed")
            target_height = max(
                1,
                round(gray.shape[0] * self.policy.motion_thumbnail_width_px / gray.shape[1]),
            )
            grays.append(
                cv2.resize(
                    gray,
                    (self.policy.motion_thumbnail_width_px, target_height),
                    interpolation=cv2.INTER_AREA,
                )
            )
        scores = [0.0]
        for previous, current in zip(grays, grays[1:]):
            score = float(np.mean(cv2.absdiff(previous, current)) / 255.0)
            scores.append(max(0.0, min(score, 1.0)))
        center = median(scores)
        mad = median(abs(value - center) for value in scores)
        threshold = max(
            self.policy.motion_min_score,
            center + self.policy.motion_mad_multiplier * mad,
        )
        pre_ms = round(self.policy.motion_pre_seconds * 1000)
        post_ms = round(self.policy.motion_post_seconds * 1000)
        motion_intervals: list[tuple[int, int, float]] = []
        for item, score in zip(frames, scores):
            if score < threshold:
                continue
            motion_intervals.append(
                (
                    max(0, item.timestamp_ms - pre_ms),
                    min(segment.duration_ms, item.timestamp_ms + post_ms),
                    score,
                )
            )
        motion_intervals = _merge_scored_intervals(motion_intervals, gap_ms=500)

        baseline_indices: set[int] = set()
        baseline_step = round(self.policy.baseline_interval_seconds * 1000)
        for target in range(0, max(segment.duration_ms, 1), baseline_step):
            index = min(
                range(len(frames)),
                key=lambda candidate: abs(frames[candidate].timestamp_ms - target),
            )
            baseline_indices.add(index)
        motion_indices = {
            index
            for index, item in enumerate(frames)
            if any(start <= item.timestamp_ms < end for start, end, _ in motion_intervals)
        }
        maximum = max(
            len(baseline_indices),
            round(len(frames) * self.policy.maximum_selected_video_ratio),
        )
        selected_indices = set(baseline_indices)
        remaining = maximum - len(selected_indices)
        motion_only = sorted(motion_indices - selected_indices)
        if remaining > 0 and len(motion_only) > remaining:
            positions = np.linspace(0, len(motion_only) - 1, remaining, dtype=int)
            selected_indices.update(motion_only[int(position)] for position in positions)
        else:
            selected_indices.update(motion_only[: max(0, remaining)])

        selected = [frames[index] for index in sorted(selected_indices)]
        frame_span_ms = max(1, round(1000 / self.policy.video_sample_fps))
        windows: list[EdgeKeyWindow] = []
        for index in sorted(selected_indices):
            item = frames[index]
            reasons: list[str] = []
            if index in baseline_indices:
                reasons.append("baseline")
            matching = [
                score
                for start, end, score in motion_intervals
                if start <= item.timestamp_ms < end
            ]
            if matching:
                reasons.append("motion")
            windows.append(
                EdgeKeyWindow(
                    start_ms=item.timestamp_ms,
                    end_ms=min(segment.duration_ms, item.timestamp_ms + frame_span_ms),
                    modalities=["video"],
                    reasons=reasons or ["baseline"],
                    peak_motion_score=max(matching) if matching else None,
                )
            )
        return selected, windows, round(min(threshold, 1.0), 6)

    def _select_audio(
        self, segment: InMemoryEdgeSegment
    ) -> tuple[list[tuple[int, int]], list[EdgeKeyWindow], float]:
        import numpy as np

        samples = np.asarray(segment.audio.samples, dtype=np.float32)
        rate = segment.audio.sample_rate_hz
        frame_samples = max(1, round(rate * self.policy.audio_gate_window_ms / 1000))
        values: list[tuple[int, int, float]] = []
        for start in range(0, len(samples), frame_samples):
            chunk = samples[start : start + frame_samples]
            if not chunk.size:
                continue
            rms = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64))))
            start_ms = round(start * 1000 / rate)
            end_ms = min(segment.duration_ms, round((start + len(chunk)) * 1000 / rate))
            values.append((start_ms, end_ms, max(0.0, min(rms, 1.0))))
        if not values:
            return [], [], self.policy.audio_min_rms
        ordered = sorted(value for _, _, value in values)
        noise = ordered[max(0, round((len(ordered) - 1) * 0.2))]
        threshold = min(
            self.policy.audio_activity_override_rms,
            max(self.policy.audio_min_rms, noise * self.policy.audio_noise_multiplier),
        )
        pad_ms = round(self.policy.audio_pad_seconds * 1000)
        intervals = [
            (
                max(0, start - pad_ms),
                min(segment.duration_ms, end + pad_ms),
                rms,
            )
            for start, end, rms in values
            if rms >= threshold
        ]
        intervals = _merge_scored_intervals(
            intervals, gap_ms=round(self.policy.audio_merge_gap_seconds * 1000)
        )
        intervals = _split_scored_intervals(
            intervals, round(self.policy.maximum_asr_window_seconds * 1000)
        )
        budget = round(segment.duration_ms * self.policy.maximum_selected_audio_ratio)
        retained: list[tuple[int, int, float]] = []
        for start, end, peak in sorted(intervals, key=lambda item: item[2], reverse=True):
            remaining = budget - sum(item[1] - item[0] for item in retained)
            if remaining <= 0:
                break
            retained.append((start, min(end, start + remaining), peak))
        retained.sort()
        windows = [
            EdgeKeyWindow(
                start_ms=start,
                end_ms=end,
                modalities=["audio"],
                reasons=["audio_activity"],
                peak_audio_rms=peak,
            )
            for start, end, peak in retained
            if end > start
        ]
        return (
            [(item.start_ms, item.end_ms) for item in windows],
            windows,
            round(threshold, 6),
        )


def _merge_scored_intervals(
    intervals: list[tuple[int, int, float]], *, gap_ms: int
) -> list[tuple[int, int, float]]:
    merged: list[tuple[int, int, float]] = []
    for start, end, score in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + gap_ms:
            previous = merged[-1]
            merged[-1] = (previous[0], max(previous[1], end), max(previous[2], score))
        else:
            merged.append((start, end, score))
    return merged


def _split_scored_intervals(
    intervals: list[tuple[int, int, float]], maximum_ms: int
) -> list[tuple[int, int, float]]:
    result: list[tuple[int, int, float]] = []
    for start, end, score in intervals:
        cursor = start
        while cursor < end:
            piece_end = min(end, cursor + maximum_ms)
            result.append((cursor, piece_end, score))
            cursor = piece_end
    return result


def _combine_key_windows(
    windows: list[EdgeKeyWindow], duration_ms: int
) -> list[EdgeKeyWindow]:
    combined: list[EdgeKeyWindow] = []
    for window in sorted(windows, key=lambda item: (item.start_ms, item.end_ms)):
        if combined and window.start_ms <= combined[-1].end_ms + 500:
            previous = combined[-1]
            combined[-1] = EdgeKeyWindow(
                start_ms=previous.start_ms,
                end_ms=min(duration_ms, max(previous.end_ms, window.end_ms)),
                modalities=sorted(set(previous.modalities + window.modalities)),
                reasons=sorted(set(previous.reasons + window.reasons)),
                peak_motion_score=max(
                    value
                    for value in (previous.peak_motion_score, window.peak_motion_score)
                    if value is not None
                )
                if previous.peak_motion_score is not None
                or window.peak_motion_score is not None
                else None,
                peak_audio_rms=max(
                    value
                    for value in (previous.peak_audio_rms, window.peak_audio_rms)
                    if value is not None
                )
                if previous.peak_audio_rms is not None or window.peak_audio_rms is not None
                else None,
            )
        else:
            combined.append(window)
    return combined


def _packet_time_seconds(packet: Any, stream: Any) -> float | None:
    value = packet.dts if packet.dts is not None else packet.pts
    time_base = packet.time_base or stream.time_base
    if value is None or time_base is None:
        return None
    try:
        result = float(value * time_base)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _validate_stream_endpoint(
    endpoint: str,
    *,
    evidence_level: EvidenceLevel,
    source_type: SourceType,
    device_ref: str,
    transport: str,
) -> str:
    if "\x00" in endpoint or "\r" in endpoint or "\n" in endpoint:
        raise ValueError("stream endpoint contains invalid control characters")
    parsed = urlsplit(endpoint)
    scheme = parsed.scheme.lower() or "local"
    network_schemes = {"rtsp", "rtsps", "http", "https"}
    ensure_source_evidence_compatible(source_type, evidence_level)
    if source_type is SourceType.NETWORK_STREAM:
        if scheme not in network_schemes:
            raise ValueError("network stream requires an RTSP or HTTP(S) endpoint")
        if (
            EVIDENCE_RANK[evidence_level] >= EVIDENCE_RANK[EvidenceLevel.E2]
            and not device_ref
        ):
            raise ValueError("E2 network stream requires device_ref")
    elif source_type is SourceType.FIXTURE:
        if scheme not in network_schemes | {"file", "local"}:
            raise ValueError("fixture stream endpoint protocol is not supported")
    else:
        raise ValueError("edge stream source must be fixture or network_stream")
    if transport not in {"auto", "tcp", "udp"}:
        raise ValueError("transport must be auto, tcp, or udp")
    if transport != "auto" and scheme not in {"rtsp", "rtsps"}:
        raise ValueError("tcp/udp transport selection is only valid for RTSP")
    return scheme


def _buffer_video_frame(frame: Any, timestamp_ms: int, policy: EdgeSelectionPolicy):
    import cv2

    width = min(int(frame.width), policy.video_buffer_width_px)
    height = max(1, round(int(frame.height) * width / int(frame.width)))
    resized = frame.reformat(width=width, height=height, format="bgr24")
    array = resized.to_ndarray(format="bgr24")
    ok, encoded = cv2.imencode(
        ".jpg", array, [int(cv2.IMWRITE_JPEG_QUALITY), policy.jpeg_quality]
    )
    if not ok:
        raise EdgeMonitorError("video frame compression failed", code="decode_failed")
    return (
        BufferedVideoFrame(timestamp_ms=timestamp_ms, jpeg_bytes=encoded.tobytes()),
        width,
        height,
    )


def capture_in_memory_segment(
    endpoint: str,
    *,
    device_ref: str,
    policy: EdgeSelectionPolicy,
    evidence_level: EvidenceLevel = EvidenceLevel.E2,
    source_type: SourceType = SourceType.NETWORK_STREAM,
    open_timeout_s: float = 10.0,
    read_timeout_s: float = 5.0,
    transport: str = "auto",
) -> InMemoryEdgeSegment:
    """Decode one live segment into bounded memory and never create a media file."""

    if any(
        not isfinite(value) or value <= 0
        for value in (open_timeout_s, read_timeout_s)
    ):
        raise ValueError("stream open and read timeouts must be positive")
    endpoint_scheme = _validate_stream_endpoint(
        endpoint,
        evidence_level=evidence_level,
        source_type=source_type,
        device_ref=device_ref,
        transport=transport,
    )
    try:
        import av
        import numpy as np
    except ImportError as error:
        raise EdgeMonitorError("media dependencies unavailable", code="decode_failed") from error

    options: dict[str, str] = {}
    if endpoint_scheme in {"rtsp", "rtsps"} and transport != "auto":
        options["rtsp_transport"] = transport
    started_at = datetime.now(timezone.utc)
    segment_id = f"edge_{started_at.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4().hex[:8]}"
    frames: list[BufferedVideoFrame] = []
    audio_chunks: list[Any] = []
    frame_width = 0
    frame_height = 0
    media_origin: float | None = None
    video_last_ms = 0
    next_video_ms = 0.0
    audio_samples = 0
    capture_wall_started = monotonic()
    resampler = None
    log_capture = av.logging.Capture(local=False)
    log_capture.__enter__()
    try:
        try:
            container = av.open(
                endpoint,
                mode="r",
                options=options,
                timeout=(open_timeout_s, read_timeout_s),
            )
        except Exception as error:
            raise EdgeMonitorError("stream open failed", code="stream_open_failed") from error
        with container:
            videos = list(container.streams.video)
            audios = list(container.streams.audio)
            if len(videos) != 1:
                raise EdgeMonitorError("video track layout invalid", code="video_track_invalid")
            if len(audios) != 1:
                raise EdgeMonitorError("audio track layout invalid", code="audio_track_invalid")
            selected = [videos[0], audios[0]]
            video_index = int(videos[0].index)
            resampler = av.AudioResampler(
                format="fltp", layout="mono", rate=policy.audio_sample_rate_hz
            )
            for packet in container.demux(selected):
                if monotonic() - capture_wall_started > (
                    policy.segment_duration_seconds + read_timeout_s + 2.0
                ):
                    break
                stream = packet.stream
                packet_time = _packet_time_seconds(packet, stream)
                if packet_time is None:
                    raise EdgeMonitorError(
                        "stream packet timestamp missing", code="packet_timestamp_missing"
                    )
                if media_origin is None:
                    if int(stream.index) != video_index or not packet.is_keyframe:
                        continue
                    media_origin = packet_time
                relative_s = packet_time - media_origin
                if relative_s < 0:
                    continue
                if relative_s >= policy.segment_duration_seconds:
                    break
                try:
                    decoded_frames = packet.decode()
                except Exception as error:
                    raise EdgeMonitorError("packet decode failed", code="decode_failed") from error
                if stream.type == "video":
                    for decoded in decoded_frames:
                        frame_time = _packet_time_seconds(decoded, stream)
                        frame_relative_s = (
                            frame_time - media_origin if frame_time is not None else relative_s
                        )
                        if frame_relative_s < 0:
                            continue
                        timestamp_ms = round(frame_relative_s * 1000)
                        if timestamp_ms + 0.5 < next_video_ms:
                            continue
                        item, frame_width, frame_height = _buffer_video_frame(
                            decoded, timestamp_ms, policy
                        )
                        frames.append(item)
                        video_last_ms = max(
                            video_last_ms,
                            timestamp_ms + round(1000 / policy.video_sample_fps),
                        )
                        while next_video_ms <= timestamp_ms + 0.5:
                            next_video_ms += 1000 / policy.video_sample_fps
                else:
                    for decoded in decoded_frames:
                        for output in resampler.resample(decoded):
                            values = np.asarray(output.to_ndarray(), dtype=np.float32)
                            if values.ndim != 2 or values.shape[0] != 1:
                                raise EdgeMonitorError(
                                    "resampled audio layout invalid", code="decode_failed"
                                )
                            flattened = np.ascontiguousarray(values.reshape(-1))
                            audio_chunks.append(flattened)
                            audio_samples += int(flattened.size)
            if resampler is not None:
                for output in resampler.resample(None):
                    values = np.asarray(output.to_ndarray(), dtype=np.float32).reshape(-1)
                    audio_chunks.append(np.ascontiguousarray(values))
                    audio_samples += int(values.size)
    finally:
        log_capture.__exit__(None, None, None)

    maximum_samples = round(
        policy.segment_duration_seconds * policy.audio_sample_rate_hz
    )
    samples = (
        np.ascontiguousarray(np.concatenate(audio_chunks)[:maximum_samples], dtype=np.float32)
        if audio_chunks
        else np.zeros(0, dtype=np.float32)
    )
    audio_duration_ms = round(len(samples) * 1000 / policy.audio_sample_rate_hz)
    duration_ms = min(video_last_ms, audio_duration_ms)
    if duration_ms < round(policy.minimum_segment_seconds * 1000):
        raise EdgeMonitorError("in-memory segment too short", code="segment_too_short")
    samples = samples[: round(duration_ms * policy.audio_sample_rate_hz / 1000)]
    ended_at = max(
        datetime.now(timezone.utc), started_at + timedelta(milliseconds=duration_ms)
    )
    return InMemoryEdgeSegment(
        segment_id=segment_id,
        device_ref=device_ref,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        frames=tuple(item for item in frames if item.timestamp_ms < duration_ms),
        audio=AudioBuffer(
            samples=samples,
            sample_rate_hz=policy.audio_sample_rate_hz,
            duration_ms=duration_ms,
        ),
        frame_width=frame_width,
        frame_height=frame_height,
        cloud_recording_ref=_cloud_recording_ref(device_ref, started_at, ended_at),
    )


class EdgeModelAnalyzer:
    """Run retained heavy models only over lightweight-selected in-memory data."""

    def __init__(
        self,
        *,
        selection_policy: EdgeSelectionPolicy,
        risk_policy_path: Path = DEFAULT_POLICY_PATH,
        pose_backend: Any | None = None,
        speech_backend: Any | None = None,
    ) -> None:
        self.selection_policy = selection_policy
        self.selector = LightweightSegmentSelector(selection_policy)
        self.risk_policy_path = Path(risk_policy_path)
        self._pose_backend = pose_backend
        self._speech_backend = speech_backend
        self._summarizer = SegmentResultSummarizer(self.risk_policy_path)

    def _ensure_pose(self) -> Any:
        if self._pose_backend is None:
            model = Path("models/yolo26n-pose.pt")
            if not model.is_file():
                raise EdgeMonitorError("pose model unavailable", code="pose_model_failed")
            from .pose_backend import UltralyticsPoseBackend

            self._pose_backend = UltralyticsPoseBackend(
                model=model, device="auto", image_size=640, confidence=0.35, track=True
            )
        return self._pose_backend

    def _ensure_speech(self) -> Any:
        if self._speech_backend is None:
            from .speech_backend import FunASRSpeechBackend

            self._speech_backend = FunASRSpeechBackend(
                model="paraformer-zh",
                vad_model="fsmn-vad",
                punc_model="ct-punc",
                device="auto",
                language="zh",
                offline=True,
            )
        return self._speech_backend

    def analyze(
        self, segment: InMemoryEdgeSegment, *, receipt_digest: str
    ) -> EdgeAnalysisOutcome:
        import cv2
        import numpy as np

        selection = self.selector.select(segment)
        features: list[dict[str, Any]] = []
        failure_codes: list[str] = []
        pose_frames_with_people = 0
        sampled_pose_frames = 0
        if selection.video_frames:
            try:
                pose = self._ensure_pose()
                reset = getattr(pose, "reset", None)
                if callable(reset):
                    reset()
                for sequence, item in enumerate(selection.video_frames):
                    frame = cv2.imdecode(
                        np.frombuffer(item.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
                    )
                    if frame is None:
                        raise EdgeMonitorError(
                            "selected frame decode failed", code="pose_model_failed"
                        )
                    detections = pose.infer(frame)
                    pose_frames_with_people += int(bool(detections))
                    sampled_pose_frames += 1
                    event = pose_feature(
                        run_id=segment.segment_id,
                        sequence=sequence,
                        timestamp_ms=item.timestamp_ms,
                        sample_fps=self.selection_policy.video_sample_fps,
                        observation_id=f"{segment.segment_id}_video",
                        detections=detections,
                        model_digest=_first_binding_value(pose, "model_digest"),
                        extractor_version=_first_binding_value(pose, "model_version"),
                    )
                    features.append(event.model_dump(mode="json"))
            except Exception:
                failure_codes.append("pose_model_failed")
                features = [
                    item for item in features if item.get("feature_type") != "video.pose_frame"
                ]
                pose_frames_with_people = 0
                sampled_pose_frames = 0

        speech_segment_count = 0
        if selection.audio_windows_ms:
            try:
                speech = self._ensure_speech()
                for window_index, (start_ms, end_ms) in enumerate(
                    selection.audio_windows_ms
                ):
                    start_sample = round(
                        start_ms * segment.audio.sample_rate_hz / 1000
                    )
                    end_sample = round(end_ms * segment.audio.sample_rate_hz / 1000)
                    samples = np.ascontiguousarray(
                        segment.audio.samples[start_sample:end_sample], dtype=np.float32
                    )
                    audio = AudioBuffer(
                        samples=samples,
                        sample_rate_hz=segment.audio.sample_rate_hz,
                        duration_ms=end_ms - start_ms,
                    )
                    segments = speech.transcribe(audio)
                    speech_segment_count += len(segments)
                    speech_events, transcripts, semantics = speech_features(
                        run_id=f"{segment.segment_id}_w{window_index:03d}",
                        observation_id=f"{segment.segment_id}_audio",
                        segments=segments,
                        bindings=speech.bindings,
                        timeline_offset_ms=start_ms,
                    )
                    features.extend(
                        event.model_dump(mode="json")
                        for event in [*speech_events, *transcripts, *semantics]
                    )
            except Exception:
                failure_codes.append("speech_model_failed")
                features = [
                    item
                    for item in features
                    if item.get("feature_type")
                    not in {
                        "audio.speech_segment",
                        "language.transcript_segment",
                        "language.lexical_tags",
                    }
                ]
                speech_segment_count = 0

        result = self._summarizer.summarize(
            features,
            duration_ms=segment.duration_ms,
            sampled_video_frames=sampled_pose_frames,
            pose_frames_with_people=pose_frames_with_people,
            speech_segment_count=speech_segment_count,
            capture_started_at=segment.started_at,
            media_digest=receipt_digest,
            frame_width=segment.frame_width,
            frame_height=segment.frame_height,
        )
        result.audio_valid_seconds = (
            selection.selected_audio_seconds
            if "speech_model_failed" not in failure_codes
            else 0.0
        )
        return EdgeAnalysisOutcome(
            result=result,
            selection=selection,
            failure_codes=tuple(sorted(set(failure_codes))),
        )


def _first_binding_value(backend: Any, name: str) -> str | None:
    bindings = list(getattr(backend, "bindings", []))
    if not bindings:
        return None
    value = getattr(bindings[0], name, None)
    return str(value) if value is not None else None


class EdgeMonitor:
    """Near-continuous segment supervisor with path-free SQLite receipts."""

    def __init__(
        self,
        *,
        elder_ref: str,
        device_ref: str,
        endpoint_provider: Callable[[], str],
        store_root: Path = DEFAULT_STORE_ROOT,
        risk_policy_path: Path = DEFAULT_POLICY_PATH,
        selection_policy_path: Path = DEFAULT_EDGE_POLICY_PATH,
        evidence_level: EvidenceLevel = EvidenceLevel.E2,
        source_type: SourceType = SourceType.NETWORK_STREAM,
        open_timeout_s: float = 10.0,
        read_timeout_s: float = 5.0,
        transport: str = "auto",
        failure_backoff_s: float = 2.0,
        segment_source: Callable[[str], InMemoryEdgeSegment] | None = None,
        analyzer: EdgeModelAnalyzer | None = None,
        stop_event: threading.Event | None = None,
        archive_anomaly_clips: bool | None = None,
    ) -> None:
        if failure_backoff_s < 0 or not isfinite(failure_backoff_s):
            raise ValueError("failure_backoff_s must be finite and non-negative")
        self.elder_ref = elder_ref
        self.device_ref = device_ref
        self.endpoint_provider = endpoint_provider
        self.store_root = Path(store_root)
        self.risk_policy_path = Path(risk_policy_path)
        self.selection_policy = EdgeSelectionPolicy.load(selection_policy_path)
        self.archive_anomaly_clips = (
            self.selection_policy.archive_enabled
            if archive_anomaly_clips is None
            else bool(archive_anomaly_clips)
        )
        self.risk_policy, _ = load_policy(self.risk_policy_path)
        self.evidence_level = evidence_level
        self.source_type = source_type
        self.failure_backoff_s = failure_backoff_s
        self.stop_event = stop_event or threading.Event()
        self.segment_source = segment_source or (
            lambda endpoint: capture_in_memory_segment(
                endpoint,
                device_ref=self.device_ref,
                policy=self.selection_policy,
                evidence_level=self.evidence_level,
                source_type=self.source_type,
                open_timeout_s=open_timeout_s,
                read_timeout_s=read_timeout_s,
                transport=transport,
            )
        )
        self.analyzer = analyzer or EdgeModelAnalyzer(
            selection_policy=self.selection_policy,
            risk_policy_path=self.risk_policy_path,
        )

    def _capture_once(self) -> InMemoryEdgeSegment | EdgeSegmentAudit:
        attempt_started = datetime.now(timezone.utc)
        try:
            endpoint = self.endpoint_provider().strip()
            if not endpoint:
                raise EdgeMonitorError(
                    "stream endpoint is unavailable", code="endpoint_unavailable"
                )
            segment = self.segment_source(endpoint)
        except Exception as error:
            code = error.code if isinstance(error, EdgeMonitorError) else "endpoint_unavailable"
            invalidate = getattr(self.endpoint_provider, "invalidate", None)
            if code == "stream_open_failed" and callable(invalidate):
                invalidate()
            audit = self._failed_audit(attempt_started, code)
            self._persist_audit(audit)
            return audit
        return segment

    def process_once(self) -> EdgeSegmentAudit:
        captured = self._capture_once()
        if isinstance(captured, EdgeSegmentAudit):
            return captured
        return self._process_segment(captured)

    def _process_segment(self, segment: InMemoryEdgeSegment) -> EdgeSegmentAudit:
        receipt_digest = _receipt_digest(segment, self.selection_policy.digest)
        try:
            outcome = self.analyzer.analyze(segment, receipt_digest=receipt_digest)
        except Exception as error:
            code = error.code if isinstance(error, EdgeMonitorError) else "selector_failed"
            audit = self._failed_audit(
                segment.started_at,
                code,
                ended_at=segment.ended_at,
                segment_id=segment.segment_id,
                cloud_ref=segment.cloud_recording_ref,
                screened_video_seconds=segment.duration_ms / 1000,
                screened_audio_seconds=segment.audio.duration_ms / 1000,
                screened_frame_count=len(segment.frames),
            )
            self._persist_audit(audit)
            return audit

        failure_code = None
        status = "completed"
        if outcome.failure_codes:
            status = "partial"
            failure_code = (
                "pose_and_speech_models_failed"
                if set(outcome.failure_codes)
                == {"pose_model_failed", "speech_model_failed"}
                else outcome.failure_codes[0]
            )
        archived_candidate_count = 0
        archive_failure_count = 0
        archive_maintenance_failed = False
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            if self.archive_anomaly_clips:
                try:
                    from .media_archive import prune_candidate_archives

                    prune_candidate_archives(
                        store,
                        now=segment.ended_at,
                        maximum_total_bytes=(
                            self.selection_policy.archive_maximum_total_bytes
                        ),
                    )
                except Exception:
                    archive_maintenance_failed = True
            for candidate, payload in outcome.result.candidates:
                enriched = {
                    **payload,
                    "segment_id": segment.segment_id,
                    "cloud_recording_ref": segment.cloud_recording_ref,
                    "raw_media_persisted": False,
                }
                insert_candidate(
                    store, candidate, device_ref=self.device_ref, payload=enriched
                )
                if self.archive_anomaly_clips:
                    try:
                        from .media_archive import archive_candidate_clip

                        archive_candidate_clip(
                            store,
                            segment=segment,
                            candidate=candidate,
                            pre_seconds=self.selection_policy.archive_event_pre_seconds,
                            post_seconds=self.selection_policy.archive_event_post_seconds,
                            retention_days=self.selection_policy.archive_retention_days,
                            maximum_total_bytes=(
                                self.selection_policy.archive_maximum_total_bytes
                            ),
                            video_fps=self.selection_policy.video_sample_fps,
                        )
                        archived_candidate_count += 1
                    except Exception:
                        archive_failure_count += 1
            if (
                archive_failure_count or archive_maintenance_failed
            ) and status == "completed":
                status = "partial"
                failure_code = "media_archive_failed"
            limitations = list(self.selection_policy.limitations)
            if archive_failure_count:
                limitations.append("one_or_more_candidate_archives_failed")
            if archive_maintenance_failed:
                limitations.append("candidate_archive_retention_maintenance_failed")
            audit = EdgeSegmentAudit(
                segment_id=segment.segment_id,
                device_ref=self.device_ref,
                segment_started_at=segment.started_at,
                segment_ended_at=segment.ended_at,
                status=status,
                failure_code=failure_code,
                cloud_recording_ref=segment.cloud_recording_ref,
                selector_revision=self.selection_policy.revision,
                selector_digest=self.selection_policy.digest,
                screened_video_seconds=round(segment.duration_ms / 1000, 3),
                screened_audio_seconds=round(segment.audio.duration_ms / 1000, 3),
                selected_pose_seconds=round(outcome.result.pose_quality_seconds, 3),
                selected_asr_seconds=round(outcome.result.audio_valid_seconds, 3),
                screened_frame_count=len(segment.frames),
                selected_frame_count=len(outcome.selection.video_frames),
                candidate_count=len(outcome.result.candidates),
                anomaly_archive_enabled=self.archive_anomaly_clips,
                archived_candidate_count=archived_candidate_count,
                archive_failure_count=archive_failure_count,
                derived_anomaly_media_persisted=bool(archived_candidate_count),
                key_windows=list(outcome.selection.key_windows),
                limitations=limitations,
            )
            merge_daily_feature(
                store,
                started=segment.started_at,
                result=outcome.result,
                source_ref=receipt_digest,
                now=segment.ended_at,
                policy=self.risk_policy,
            )
            store.record_edge_segment(_audit_row(audit))
            build_snapshot(
                store,
                device_ref=self.device_ref,
                policy_path=self.risk_policy_path,
                now=segment.ended_at,
                persist=True,
            )
        return audit

    def run(
        self,
        *,
        max_segments: int = 0,
        on_audit: Callable[[EdgeSegmentAudit], None] | None = None,
        queue_size: int = 2,
    ) -> dict[str, int]:
        if max_segments < 0:
            raise ValueError("max_segments must be zero or positive")
        if queue_size <= 0:
            raise ValueError("edge analysis queue_size must be positive")
        counts = {"attempted": 0, "completed": 0, "partial": 0, "failed": 0}
        lock = threading.Lock()
        pending: queue.Queue[InMemoryEdgeSegment] = queue.Queue(maxsize=queue_size)
        producer_done = threading.Event()

        def observe(audit: EdgeSegmentAudit) -> None:
            with lock:
                counts[audit.status] += 1
            if on_audit is not None:
                on_audit(audit)

        def produce() -> None:
            produced = 0
            try:
                while not self.stop_event.is_set() and (
                    max_segments == 0 or produced < max_segments
                ):
                    captured = self._capture_once()
                    produced += 1
                    with lock:
                        counts["attempted"] += 1
                    if isinstance(captured, EdgeSegmentAudit):
                        observe(captured)
                        if self.stop_event.wait(self.failure_backoff_s):
                            break
                        continue
                    try:
                        pending.put(captured, timeout=0.05)
                    except queue.Full:
                        audit = self._failed_audit(
                            captured.started_at,
                            "analysis_backpressure",
                            ended_at=captured.ended_at,
                            segment_id=captured.segment_id,
                            cloud_ref=captured.cloud_recording_ref,
                            screened_video_seconds=captured.duration_ms / 1000,
                            screened_audio_seconds=captured.audio.duration_ms / 1000,
                            screened_frame_count=len(captured.frames),
                        )
                        self._persist_audit(audit)
                        observe(audit)
            finally:
                producer_done.set()

        producer = threading.Thread(
            target=produce, name="kangshield-edge-capture", daemon=True
        )
        producer.start()
        while not producer_done.is_set() or not pending.empty():
            if self.stop_event.is_set() and pending.empty():
                break
            try:
                segment = pending.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                audit = self._process_segment(segment)
                observe(audit)
            finally:
                pending.task_done()
        producer.join(timeout=5)
        return counts

    def _failed_audit(
        self,
        started_at: datetime,
        code: str,
        *,
        ended_at: datetime | None = None,
        segment_id: str | None = None,
        cloud_ref: str | None = None,
        screened_video_seconds: float = 0.0,
        screened_audio_seconds: float = 0.0,
        screened_frame_count: int = 0,
    ) -> EdgeSegmentAudit:
        started_at = _aware_utc(started_at)
        ended_at = _aware_utc(ended_at or (started_at + timedelta(milliseconds=1)))
        if ended_at <= started_at:
            ended_at = started_at + timedelta(milliseconds=1)
        segment_id = segment_id or (
            f"edge_failed_{started_at.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4().hex[:8]}"
        )
        cloud_ref = cloud_ref or _cloud_recording_ref(
            self.device_ref, started_at, ended_at
        )
        return EdgeSegmentAudit(
            segment_id=segment_id,
            device_ref=self.device_ref,
            segment_started_at=started_at,
            segment_ended_at=ended_at,
            status="failed",
            failure_code=code if code in _PUBLIC_FAILURE_CODES else "decode_failed",
            cloud_recording_ref=cloud_ref,
            selector_revision=self.selection_policy.revision,
            selector_digest=self.selection_policy.digest,
            screened_video_seconds=screened_video_seconds,
            screened_audio_seconds=screened_audio_seconds,
            screened_frame_count=screened_frame_count,
            anomaly_archive_enabled=self.archive_anomaly_clips,
            limitations=list(self.selection_policy.limitations),
        )

    def _persist_audit(self, audit: EdgeSegmentAudit) -> None:
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            store.record_edge_segment(_audit_row(audit))
            if self.archive_anomaly_clips:
                try:
                    from .media_archive import prune_candidate_archives

                    prune_candidate_archives(
                        store,
                        now=audit.segment_ended_at,
                        maximum_total_bytes=(
                            self.selection_policy.archive_maximum_total_bytes
                        ),
                    )
                except Exception:
                    pass


def endpoint_provider_from_environment(variable_name: str) -> Callable[[], str]:
    if not variable_name or any(character.isspace() for character in variable_name):
        raise ValueError("endpoint environment variable name is invalid")

    def provider() -> str:
        value = os.environ.get(variable_name)
        if value is None or not value.strip():
            raise EdgeMonitorError(
                "stream endpoint is unavailable", code="endpoint_unavailable"
            )
        return value.strip()

    return provider


def ezviz_provider_from_environment(
    variable_name: str = "KANG_DEVICE_SERIAL", *, refresh_seconds: float = 1800
) -> Callable[[], str]:
    from .ezviz_live import provider_from_environment

    return provider_from_environment(
        variable_name, refresh_seconds=refresh_seconds
    )


def _audit_row(audit: EdgeSegmentAudit) -> dict[str, Any]:
    payload = audit.model_dump(mode="json")
    return {
        "segment_id": audit.segment_id,
        "device_ref": audit.device_ref,
        "segment_started_at": str(payload["segment_started_at"]),
        "segment_ended_at": str(payload["segment_ended_at"]),
        "status": audit.status,
        "failure_code": audit.failure_code,
        "cloud_recording_ref": audit.cloud_recording_ref,
        "selector_revision": audit.selector_revision,
        "selector_digest": audit.selector_digest,
        "raw_media_persisted": 0,
        "endpoint_value_persisted": 0,
        "screened_video_seconds": audit.screened_video_seconds,
        "screened_audio_seconds": audit.screened_audio_seconds,
        "selected_pose_seconds": audit.selected_pose_seconds,
        "selected_asr_seconds": audit.selected_asr_seconds,
        "screened_frame_count": audit.screened_frame_count,
        "selected_frame_count": audit.selected_frame_count,
        "candidate_count": audit.candidate_count,
        "anomaly_archive_enabled": int(audit.anomaly_archive_enabled),
        "archived_candidate_count": audit.archived_candidate_count,
        "archive_failure_count": audit.archive_failure_count,
        "derived_anomaly_media_persisted": int(
            audit.derived_anomaly_media_persisted
        ),
        "key_windows_json": dumps_compact(payload["key_windows"]),
        "limitations_json": dumps_compact(audit.limitations),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
