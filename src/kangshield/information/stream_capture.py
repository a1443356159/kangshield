from __future__ import annotations

import os
from dataclasses import dataclass
from math import isfinite
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from .contracts import (
    EVIDENCE_RANK,
    EvidenceLevel,
    QualityStatus,
    SourceType,
    StreamCaptureReport,
    StreamCaptureTrack,
    ensure_source_evidence_compatible,
)
from .media_probe import probe_media


STREAM_CAPTURE_VERSION = "stream-capture-v0.1.0"
NETWORK_SCHEMES = frozenset({"rtsp", "rtsps", "http", "https"})
FIXTURE_SCHEMES = NETWORK_SCHEMES | {"file", "local"}
Transport = Literal["auto", "tcp", "udp"]
TerminationReason = Literal[
    "duration_limit",
    "end_of_stream",
    "packet_limit",
    "wall_time_limit",
]


class StreamCaptureError(RuntimeError):
    """A deliberately sanitized stream capture failure."""


@dataclass(frozen=True)
class StreamCaptureConfig:
    duration_s: float = 10.0
    minimum_duration_s: float = 1.0
    open_timeout_s: float = 10.0
    read_timeout_s: float = 5.0
    max_packets: int = 200_000
    packet_scan_limit_per_stream: int = 200_000
    transport: Transport = "auto"
    require_audio: bool = True

    def __post_init__(self) -> None:
        for name, value in (
            ("duration_s", self.duration_s),
            ("minimum_duration_s", self.minimum_duration_s),
            ("open_timeout_s", self.open_timeout_s),
            ("read_timeout_s", self.read_timeout_s),
        ):
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.minimum_duration_s > self.duration_s:
            raise ValueError("minimum_duration_s cannot exceed duration_s")
        if self.max_packets <= 0:
            raise ValueError("max_packets must be positive")
        if self.packet_scan_limit_per_stream <= 0:
            raise ValueError("packet_scan_limit_per_stream must be positive")
        if self.transport not in {"auto", "tcp", "udp"}:
            raise ValueError("transport must be auto, tcp or udp")


@dataclass(frozen=True)
class _TrackStats:
    stream_type: Literal["video", "audio"]
    source_stream_index: int
    codec_name: str | None
    copied_packet_count: int
    missing_timestamp_count: int


@dataclass(frozen=True)
class _CaptureStats:
    termination_reason: TerminationReason
    inspected_packet_count: int
    copied_packet_count: int
    first_video_packet_keyframe: bool
    tracks: tuple[_TrackStats, ...]


def endpoint_from_environment(variable_name: str) -> str:
    if not variable_name or any(character.isspace() for character in variable_name):
        raise ValueError("endpoint environment variable name is invalid")
    endpoint = os.environ.get(variable_name)
    if endpoint is None or not endpoint.strip():
        raise ValueError("stream endpoint environment variable is missing or empty")
    return endpoint.strip()


def _endpoint_scheme(endpoint: str) -> str:
    if "\x00" in endpoint or "\r" in endpoint or "\n" in endpoint:
        raise ValueError("stream endpoint contains invalid control characters")
    parsed = urlsplit(endpoint)
    scheme = parsed.scheme.lower()
    if not scheme:
        return "local"
    if scheme in NETWORK_SCHEMES | {"file"}:
        return scheme
    raise ValueError("stream endpoint protocol is not supported")


def _validate_endpoint_evidence(
    *,
    endpoint_scheme: str,
    evidence_level: EvidenceLevel,
    source_type: SourceType,
    device_ref: str | None,
) -> None:
    ensure_source_evidence_compatible(source_type, evidence_level)
    if source_type not in {SourceType.FIXTURE, SourceType.NETWORK_STREAM}:
        raise ValueError(
            "stream capture source_type must be fixture or network_stream"
        )
    if source_type is SourceType.NETWORK_STREAM:
        if endpoint_scheme not in NETWORK_SCHEMES:
            raise ValueError(
                "network_stream evidence requires an RTSP or HTTP(S) endpoint"
            )
        if (
            EVIDENCE_RANK[evidence_level] >= EVIDENCE_RANK[EvidenceLevel.E2]
            and not device_ref
        ):
            raise ValueError("E2 network_stream evidence requires device_ref")
    elif endpoint_scheme not in FIXTURE_SCHEMES:
        raise ValueError("fixture stream endpoint protocol is not supported")


def _load_av() -> Any:
    try:
        import av
    except ImportError as error:
        raise RuntimeError("PyAV is required for bounded stream capture") from error
    return av


def _open_input(
    av_module: Any,
    endpoint: str,
    *,
    endpoint_scheme: str,
    config: StreamCaptureConfig,
) -> Any:
    options: dict[str, str] = {}
    if endpoint_scheme in {"rtsp", "rtsps"} and config.transport != "auto":
        options["rtsp_transport"] = config.transport
    return av_module.open(
        endpoint,
        mode="r",
        options=options,
        timeout=(config.open_timeout_s, config.read_timeout_s),
    )


def _packet_time_seconds(packet: Any, source_stream: Any) -> float | None:
    value = packet.dts if packet.dts is not None else packet.pts
    time_base = packet.time_base or source_stream.time_base
    if value is None or time_base is None:
        return None
    try:
        result = float(value * time_base)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _capture_packets(
    *,
    endpoint: str,
    endpoint_scheme: str,
    output_path: Path,
    config: StreamCaptureConfig,
) -> _CaptureStats:
    av_module = _load_av()
    temporary = output_path.with_name(
        f".{output_path.name}.{uuid4().hex}.partial"
    )
    phase = "open"
    inspected_packet_count = 0
    copied_packet_count = 0
    first_video_packet_keyframe = False
    termination_reason: TerminationReason = "end_of_stream"
    track_counts: dict[int, int] = {}
    missing_timestamp_counts: dict[int, int] = {}
    source_streams: dict[int, Any] = {}
    source_stream_types: dict[int, Literal["video", "audio"]] = {}
    source_codec_names: dict[int, str | None] = {}
    capture_wall_started = monotonic()
    media_origin_seconds: float | None = None
    log_capture = av_module.logging.Capture(local=False)

    log_capture.__enter__()
    try:
        with _open_input(
            av_module,
            endpoint,
            endpoint_scheme=endpoint_scheme,
            config=config,
        ) as input_container:
            videos = list(input_container.streams.video)
            audios = list(input_container.streams.audio)
            if len(videos) != 1:
                raise StreamCaptureError(
                    "stream must expose exactly one video track"
                )
            if len(audios) > 1:
                raise StreamCaptureError(
                    "stream must expose at most one audio track"
                )
            if config.require_audio and len(audios) != 1:
                raise StreamCaptureError(
                    "stream does not expose the required single audio track"
                )

            selected = [videos[0], *audios]
            source_streams = {int(stream.index): stream for stream in selected}
            source_stream_types = {
                int(stream.index): stream.type for stream in selected
            }
            source_codec_names = {
                int(stream.index): getattr(stream.codec_context, "name", None)
                for stream in selected
            }
            track_counts = {stream_index: 0 for stream_index in source_streams}
            missing_timestamp_counts = {
                stream_index: 0 for stream_index in source_streams
            }
            video_stream_index = int(videos[0].index)

            phase = "remux"
            with av_module.open(
                str(temporary),
                mode="w",
                format="matroska",
            ) as output_container:
                output_container.metadata.clear()
                output_streams: dict[int, Any] = {}
                for source_stream in selected:
                    output_stream = output_container.add_stream_from_template(
                        source_stream
                    )
                    output_stream.metadata.clear()
                    output_streams[int(source_stream.index)] = output_stream

                for packet in input_container.demux(selected):
                    if packet.size == 0 and packet.pts is None and packet.dts is None:
                        continue
                    inspected_packet_count += 1
                    if inspected_packet_count > config.max_packets:
                        termination_reason = "packet_limit"
                        break
                    if (
                        monotonic() - capture_wall_started
                        > config.duration_s + config.read_timeout_s + 2.0
                    ):
                        termination_reason = "wall_time_limit"
                        break

                    source_index = int(packet.stream.index)
                    source_stream = source_streams[source_index]
                    packet_time = _packet_time_seconds(packet, source_stream)
                    if packet_time is None:
                        missing_timestamp_counts[source_index] += 1
                        raise StreamCaptureError(
                            "selected stream packet is missing a usable timestamp"
                        )

                    if media_origin_seconds is None:
                        if source_index != video_stream_index:
                            continue
                        if not packet.is_keyframe:
                            continue
                        first_video_packet_keyframe = True
                        media_origin_seconds = packet_time

                    if packet_time - media_origin_seconds >= config.duration_s:
                        termination_reason = "duration_limit"
                        break

                    packet.stream = output_streams[source_index]
                    output_container.mux(packet)
                    track_counts[source_index] += 1
                    copied_packet_count += 1

        if not first_video_packet_keyframe or media_origin_seconds is None:
            raise StreamCaptureError(
                "stream ended before a decodable video keyframe was captured"
            )
        if track_counts.get(video_stream_index, 0) <= 0:
            raise StreamCaptureError("stream capture produced no video packets")
        if config.require_audio:
            audio_packet_count = sum(
                track_counts[index]
                for index, stream_type in source_stream_types.items()
                if stream_type == "audio"
            )
            if audio_packet_count <= 0:
                raise StreamCaptureError("stream capture produced no audio packets")
        if copied_packet_count <= 0 or not temporary.is_file():
            raise StreamCaptureError("stream capture produced no media artifact")

        temporary.chmod(0o600)
        temporary.replace(output_path)
        output_path.chmod(0o600)
    except StreamCaptureError:
        temporary.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        raise
    except Exception as error:
        temporary.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        error_type = type(error).__name__
        raise StreamCaptureError(
            f"stream capture failed during {phase} ({error_type})"
        ) from None
    finally:
        log_capture.__exit__(None, None, None)

    tracks = tuple(
        _TrackStats(
            stream_type=source_stream_types[index],
            source_stream_index=index,
            codec_name=source_codec_names[index],
            copied_packet_count=track_counts[index],
            missing_timestamp_count=missing_timestamp_counts[index],
        )
        for index in sorted(source_streams)
    )
    return _CaptureStats(
        termination_reason=termination_reason,
        inspected_packet_count=inspected_packet_count,
        copied_packet_count=copied_packet_count,
        first_video_packet_keyframe=first_video_packet_keyframe,
        tracks=tracks,
    )


def _captured_media_span_ms(media_probe: Any) -> int:
    timing = media_probe.container_timing
    if timing is None:
        return 0
    starts = [
        stream.min_pts_ms
        for stream in timing.streams
        if stream.min_pts_ms is not None
    ]
    ends = [
        stream.end_pts_ms
        for stream in timing.streams
        if stream.end_pts_ms is not None
    ]
    if not starts or not ends:
        return 0
    return max(0, round(max(ends) - min(starts)))


def _capture_readiness(
    *,
    media_probe: Any,
    captured_media_span_ms: int,
    minimum_duration_ms: int,
    termination_reason: TerminationReason,
    first_video_packet_keyframe: bool,
) -> tuple[bool, bool]:
    timing = media_probe.container_timing
    clean_termination = termination_reason in {"duration_limit", "end_of_stream"}
    timing_streams_clean = bool(timing) and all(
        stream.packet_count > 0
        and stream.missing_pts_count == 0
        and not stream.scan_truncated
        for stream in timing.streams
    )
    artifact_ready = bool(
        media_probe.observation.quality_status is QualityStatus.PASS
        and timing is not None
        and timing.video_stream_count == 1
        and first_video_packet_keyframe
        and captured_media_span_ms >= minimum_duration_ms
        and clean_termination
        and timing_streams_clean
    )
    multimodal_ready = bool(
        artifact_ready
        and timing is not None
        and timing.audio_stream_count == 1
        and timing.same_container_av
        and timing.can_measure_start_offset
        and timing.audio_minus_video_start_ms is not None
        and isfinite(timing.audio_minus_video_start_ms)
        and all(
            stream.pts_backward_step_count == 0
            for stream in timing.streams
            if stream.stream_type == "audio"
        )
    )
    return artifact_ready, multimodal_ready


def capture_stream(
    *,
    endpoint: str,
    output_path: Path,
    output_artifact: str,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.NETWORK_STREAM,
    device_ref: str | None = None,
    elder_ref: str | None = None,
    config: StreamCaptureConfig | None = None,
) -> StreamCaptureReport:
    config = config or StreamCaptureConfig()
    output_path = Path(output_path)
    pure_artifact = PurePosixPath(output_artifact)
    if (
        pure_artifact.is_absolute()
        or len(pure_artifact.parts) != 2
        or pure_artifact.parts[0] != "artifacts"
        or pure_artifact.suffix != ".mkv"
        or any(part in {"", ".", ".."} for part in pure_artifact.parts)
        or "\\" in output_artifact
    ):
        raise ValueError("output_artifact must be a normalized artifacts/*.mkv path")
    if output_path.name != pure_artifact.name:
        raise ValueError("output_path name must match output_artifact")
    if not output_path.parent.is_dir():
        raise FileNotFoundError(output_path.parent)
    if output_path.exists():
        raise FileExistsError(output_path)

    endpoint_scheme = _endpoint_scheme(endpoint)
    if config.transport != "auto" and endpoint_scheme not in {"rtsp", "rtsps"}:
        raise ValueError("tcp/udp transport selection is only valid for RTSP")
    _validate_endpoint_evidence(
        endpoint_scheme=endpoint_scheme,
        evidence_level=evidence_level,
        source_type=source_type,
        device_ref=device_ref,
    )
    stats = _capture_packets(
        endpoint=endpoint,
        endpoint_scheme=endpoint_scheme,
        output_path=output_path,
        config=config,
    )
    try:
        media_probe = probe_media(
            output_path,
            evidence_level=evidence_level,
            source_type=source_type,
            device_ref=device_ref,
            elder_ref=elder_ref,
            require_audio_track=config.require_audio,
            packet_scan_limit_per_stream=config.packet_scan_limit_per_stream,
        )
        captured_media_span_ms = _captured_media_span_ms(media_probe)
        minimum_duration_ms = round(config.minimum_duration_s * 1000)
        artifact_ready, multimodal_ready = _capture_readiness(
            media_probe=media_probe,
            captured_media_span_ms=captured_media_span_ms,
            minimum_duration_ms=minimum_duration_ms,
            termination_reason=stats.termination_reason,
            first_video_packet_keyframe=stats.first_video_packet_keyframe,
        )
        report = StreamCaptureReport(
            capture_version=STREAM_CAPTURE_VERSION,
            evidence_level=evidence_level,
            source_type=source_type,
            endpoint_scheme=endpoint_scheme,
            transport=config.transport,
            requested_duration_ms=round(config.duration_s * 1000),
            minimum_duration_ms=minimum_duration_ms,
            captured_media_span_ms=captured_media_span_ms,
            open_timeout_ms=round(config.open_timeout_s * 1000),
            read_timeout_ms=round(config.read_timeout_s * 1000),
            packet_limit=config.max_packets,
            inspected_packet_count=stats.inspected_packet_count,
            copied_packet_count=stats.copied_packet_count,
            termination_reason=stats.termination_reason,
            audio_required=config.require_audio,
            first_video_packet_keyframe=stats.first_video_packet_keyframe,
            tracks=[
                StreamCaptureTrack(
                    stream_type=track.stream_type,
                    source_stream_index=track.source_stream_index,
                    codec_name=track.codec_name,
                    copied_packet_count=track.copied_packet_count,
                    missing_timestamp_count=track.missing_timestamp_count,
                )
                for track in stats.tracks
            ],
            output_artifact=output_artifact,
            media_probe=media_probe,
            capture_artifact_ready=artifact_ready,
            same_container_multimodal_ready=multimodal_ready,
            limitations=[
                "bounded_capture_does_not_prove_stream_stability_or_reconnect_behavior",
                "received_wall_time_is_not_device_event_time",
                "container_pts_does_not_prove_capture_clock_accuracy_or_drift",
                "fixture_capture_cannot_prove_target_device_or_platform_access",
                "raw_media_requires_consent_controlled_storage_and_deletion",
                "this_stage_does_not_emit_risk_assessment_or_alert",
            ],
        )
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return report
