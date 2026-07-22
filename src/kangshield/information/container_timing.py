from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from statistics import median
from typing import Any

from .contracts import (
    ContainerTimingReport,
    MediaStreamTiming,
    QualityIssue,
    Severity,
)


TIMING_VERSION = "container-timing-v0.1.0"
DEFAULT_PACKET_SCAN_LIMIT = 200_000


@dataclass
class _PacketAccumulator:
    packet_count: int = 0
    packets_with_pts: int = 0
    packets_with_dts: int = 0
    missing_pts_count: int = 0
    missing_dts_count: int = 0
    negative_pts_count: int = 0
    pts_backward_step_count: int = 0
    dts_backward_step_count: int = 0
    first_demux_pts: int | None = None
    last_demux_pts: int | None = None
    previous_pts: int | None = None
    previous_dts: int | None = None
    pts_values: list[int] = field(default_factory=list)
    duration_sum: int = 0
    max_end_pts: int | None = None
    scan_truncated: bool = False

    def add(self, packet: Any) -> None:
        self.packet_count += 1
        pts = packet.pts
        dts = packet.dts
        duration = packet.duration

        if pts is None:
            self.missing_pts_count += 1
        else:
            pts = int(pts)
            self.packets_with_pts += 1
            if self.first_demux_pts is None:
                self.first_demux_pts = pts
            self.last_demux_pts = pts
            if pts < 0:
                self.negative_pts_count += 1
            if self.previous_pts is not None and pts < self.previous_pts:
                self.pts_backward_step_count += 1
            self.previous_pts = pts
            self.pts_values.append(pts)
            end_pts = pts + max(0, int(duration or 0))
            if self.max_end_pts is None or end_pts > self.max_end_pts:
                self.max_end_pts = end_pts

        if dts is None:
            self.missing_dts_count += 1
        else:
            dts = int(dts)
            self.packets_with_dts += 1
            if self.previous_dts is not None and dts < self.previous_dts:
                self.dts_backward_step_count += 1
            self.previous_dts = dts

        if duration is not None and int(duration) > 0:
            self.duration_sum += int(duration)


def _fraction_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        fraction = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if fraction.denominator == 0:
        return None
    return f"{fraction.numerator}/{fraction.denominator}"


def _to_ms(value: int | float | None, time_base: Any) -> float | None:
    if value is None or time_base is None:
        return None
    try:
        return round(float(value * time_base) * 1000.0, 6)
    except (TypeError, ValueError, OverflowError):
        return None


def _ratio_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        fraction = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if fraction.denominator == 0:
        return None
    return f"{fraction.numerator}/{fraction.denominator}"


def _stream_technical_metadata(stream: Any) -> dict[str, Any]:
    context = stream.codec_context
    if stream.type == "video":
        return {
            "width": int(context.width) if context.width else None,
            "height": int(context.height) if context.height else None,
            "pixel_format": getattr(context.format, "name", None),
            "average_rate": _ratio_text(getattr(stream, "average_rate", None)),
            "base_rate": _ratio_text(getattr(stream, "base_rate", None)),
            "guessed_rate": _ratio_text(getattr(stream, "guessed_rate", None)),
        }
    layout = getattr(context, "layout", None)
    audio_format = getattr(context, "format", None)
    return {
        "sample_rate_hz": int(context.sample_rate) if context.sample_rate else None,
        "channels": int(context.channels) if context.channels else None,
        "channel_layout": getattr(layout, "name", None),
        "sample_format": getattr(audio_format, "name", None),
    }


def _build_stream_report(stream: Any, accumulator: _PacketAccumulator) -> MediaStreamTiming:
    time_base = stream.time_base
    declared_frames = getattr(stream, "frames", None)
    sorted_pts = sorted(accumulator.pts_values)
    forward_steps = [
        current - previous
        for previous, current in zip(sorted_pts, sorted_pts[1:])
        if current >= previous
    ]
    minimum = sorted_pts[0] if sorted_pts else None
    maximum = sorted_pts[-1] if sorted_pts else None
    min_ms = _to_ms(minimum, time_base)
    max_ms = _to_ms(maximum, time_base)
    end_ms = _to_ms(accumulator.max_end_pts, time_base)
    return MediaStreamTiming(
        stream_index=int(stream.index),
        stream_type=stream.type,
        codec_name=getattr(stream.codec_context, "name", None),
        time_base=_fraction_text(time_base),
        declared_start_pts=(
            int(stream.start_time) if stream.start_time is not None else None
        ),
        declared_start_ms=_to_ms(stream.start_time, time_base),
        declared_duration_pts=(
            int(stream.duration) if stream.duration is not None else None
        ),
        declared_duration_ms=_to_ms(stream.duration, time_base),
        declared_frame_count=(
            int(declared_frames)
            if isinstance(declared_frames, int) and declared_frames > 0
            else None
        ),
        packet_count=accumulator.packet_count,
        packets_with_pts=accumulator.packets_with_pts,
        packets_with_dts=accumulator.packets_with_dts,
        missing_pts_count=accumulator.missing_pts_count,
        missing_dts_count=accumulator.missing_dts_count,
        negative_pts_count=accumulator.negative_pts_count,
        pts_backward_step_count=accumulator.pts_backward_step_count,
        dts_backward_step_count=accumulator.dts_backward_step_count,
        first_demux_pts=accumulator.first_demux_pts,
        last_demux_pts=accumulator.last_demux_pts,
        min_pts=minimum,
        max_pts=maximum,
        min_pts_ms=min_ms,
        max_pts_ms=max_ms,
        end_pts_ms=end_ms,
        pts_span_ms=(
            round(max_ms - min_ms, 6)
            if min_ms is not None and max_ms is not None
            else None
        ),
        packet_duration_sum_ms=_to_ms(accumulator.duration_sum, time_base),
        median_forward_pts_step_ms=(
            _to_ms(median(forward_steps), time_base)
            if forward_steps
            else None
        ),
        max_forward_pts_step_ms=(
            _to_ms(max(forward_steps), time_base) if forward_steps else None
        ),
        scan_truncated=accumulator.scan_truncated,
        technical_metadata=_stream_technical_metadata(stream),
    )


def _first_timed_stream(
    streams: list[MediaStreamTiming], stream_type: str
) -> MediaStreamTiming | None:
    candidates = [stream for stream in streams if stream.stream_type == stream_type]
    candidates.sort(key=lambda item: item.stream_index)
    return candidates[0] if candidates else None


def probe_container_timing(
    path: Path,
    *,
    packet_scan_limit_per_stream: int = DEFAULT_PACKET_SCAN_LIMIT,
) -> tuple[ContainerTimingReport | None, list[QualityIssue]]:
    if packet_scan_limit_per_stream <= 0:
        raise ValueError("packet_scan_limit_per_stream must be positive")
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    try:
        import av
    except ImportError:
        return (
            None,
            [
                QualityIssue(
                    code="pyav_unavailable",
                    severity=Severity.WARNING,
                    message="Install the media extra to inspect container tracks and PTS",
                )
            ],
        )

    try:
        with av.open(str(path), mode="r") as container:
            selected = [
                stream
                for stream in container.streams
                if stream.type in {"video", "audio"}
            ]
            accumulators = {
                int(stream.index): _PacketAccumulator() for stream in selected
            }
            if selected:
                for packet in container.demux(selected):
                    stream_index = int(packet.stream.index)
                    accumulator = accumulators[stream_index]
                    if accumulator.packet_count >= packet_scan_limit_per_stream:
                        for item in accumulators.values():
                            item.scan_truncated = True
                        break
                    if packet.size == 0 and packet.pts is None and packet.dts is None:
                        continue
                    accumulator.add(packet)

            stream_reports = [
                _build_stream_report(stream, accumulators[int(stream.index)])
                for stream in selected
            ]
            video = _first_timed_stream(stream_reports, "video")
            audio = _first_timed_stream(stream_reports, "audio")
            video_start = video.min_pts_ms if video else None
            audio_start = audio.min_pts_ms if audio else None
            video_end = video.end_pts_ms if video else None
            audio_end = audio.end_pts_ms if audio else None
            format_name = getattr(container.format, "name", "") or ""
            bit_rate = container.bit_rate
            report = ContainerTimingReport(
                timing_version=TIMING_VERSION,
                backend_version=str(av.__version__),
                format_names=[item for item in format_name.split(",") if item],
                container_start_ms=(
                    round(container.start_time / av.time_base * 1000.0, 6)
                    if container.start_time is not None
                    else None
                ),
                container_duration_ms=(
                    round(container.duration / av.time_base * 1000.0, 6)
                    if container.duration is not None
                    else None
                ),
                container_bit_rate=(
                    int(bit_rate) if bit_rate is not None and bit_rate >= 0 else None
                ),
                metadata_key_count=len(container.metadata or {}),
                metadata_values_persisted=False,
                source_path_persisted=False,
                stream_count=len(stream_reports),
                video_stream_count=sum(
                    stream.stream_type == "video" for stream in stream_reports
                ),
                audio_stream_count=sum(
                    stream.stream_type == "audio" for stream in stream_reports
                ),
                video_track_status="present" if video else "absent",
                audio_track_status="present" if audio else "absent",
                same_container_av=video is not None and audio is not None,
                can_measure_start_offset=(
                    video_start is not None and audio_start is not None
                ),
                audio_minus_video_start_ms=(
                    round(audio_start - video_start, 6)
                    if audio_start is not None and video_start is not None
                    else None
                ),
                audio_minus_video_end_ms=(
                    round(audio_end - video_end, 6)
                    if audio_end is not None and video_end is not None
                    else None
                ),
                duration_delta_ms=(
                    round((audio_end - audio_start) - (video_end - video_start), 6)
                    if None not in {audio_start, audio_end, video_start, video_end}
                    else None
                ),
                drift_estimate_available=False,
                packet_scan_limit_per_stream=packet_scan_limit_per_stream,
                streams=stream_reports,
                limitations=[
                    "container_pts_does_not_prove_capture_clock_accuracy",
                    "drift_requires_two_cross_modal_sync_events",
                    "pts_backward_steps_can_be_valid_for_reordered_video",
                    "container_metadata_values_are_not_persisted",
                ],
            )
    except Exception as error:
        return (
            None,
            [
                QualityIssue(
                    code="container_timing_probe_failed",
                    severity=Severity.ERROR,
                    message="Container tracks and packet timestamps could not be inspected",
                    details={"error_type": type(error).__name__},
                )
            ],
        )

    issues: list[QualityIssue] = []
    if any(stream.scan_truncated for stream in report.streams):
        issues.append(
            QualityIssue(
                code="container_packet_scan_truncated",
                severity=Severity.WARNING,
                message="Packet timing scan reached the configured per-stream limit",
                details={"packet_scan_limit_per_stream": packet_scan_limit_per_stream},
            )
        )
    return report, issues
