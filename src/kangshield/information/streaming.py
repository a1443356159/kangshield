from __future__ import annotations

import wave
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True)
class VideoFramePacket:
    frame_index: int
    timestamp_ms: int
    frame: Any


@dataclass(frozen=True)
class AudioBuffer:
    samples: Any
    sample_rate_hz: int
    duration_ms: int
    start_ms: int = 0


class OpenCVVideoReplay:
    """Replay a local video as timestamped frames using a stream-like iterator."""

    def __init__(
        self,
        path: Path,
        sample_fps: float = 5.0,
        max_duration_s: float | None = None,
    ) -> None:
        if sample_fps <= 0:
            raise ValueError("sample_fps must be positive")
        if max_duration_s is not None and max_duration_s <= 0:
            raise ValueError("max_duration_s must be positive")
        self.path = Path(path)
        self.sample_fps = float(sample_fps)
        self.max_duration_s = max_duration_s
        self.source_fps: float | None = None
        self.width: int | None = None
        self.height: int | None = None
        self.source_frame_count: int | None = None

    def __iter__(self) -> Iterator[VideoFramePacket]:
        try:
            import cv2
        except ImportError as error:
            raise RuntimeError("OpenCV is required for video replay") from error

        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened():
            raise ValueError(f"cannot open video: {self.path}")

        self.source_fps = float(capture.get(cv2.CAP_PROP_FPS)) or None
        self.width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
        self.height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
        self.source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or None
        sample_period_ms = 1000.0 / self.sample_fps
        next_sample_ms = 0.0
        frame_index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok or frame is None:
                    break
                if self.source_fps:
                    timestamp_ms = frame_index * 1000.0 / self.source_fps
                else:
                    timestamp_ms = float(capture.get(cv2.CAP_PROP_POS_MSEC))
                if self.max_duration_s is not None and (
                    timestamp_ms >= self.max_duration_s * 1000.0
                ):
                    break
                if timestamp_ms + 0.5 >= next_sample_ms:
                    yield VideoFramePacket(
                        frame_index=frame_index,
                        timestamp_ms=max(0, round(timestamp_ms)),
                        frame=frame,
                    )
                    while next_sample_ms <= timestamp_ms + 0.5:
                        next_sample_ms += sample_period_ms
                frame_index += 1
        finally:
            capture.release()


def read_pcm_wav(path: Path, target_sample_rate_hz: int = 16000) -> AudioBuffer:
    """Read PCM WAV without ffmpeg and normalize it to mono float32."""

    if target_sample_rate_hz <= 0:
        raise ValueError("target_sample_rate_hz must be positive")
    try:
        import numpy as np
    except ImportError as error:
        raise RuntimeError("NumPy is required for audio loading") from error

    path = Path(path)
    with wave.open(str(path), "rb") as stream:
        if stream.getcomptype() != "NONE":
            raise ValueError("only uncompressed PCM WAV is supported")
        channels = stream.getnchannels()
        sample_width = stream.getsampwidth()
        source_rate = stream.getframerate()
        frame_count = stream.getnframes()
        raw = stream.readframes(frame_count)

    if channels <= 0 or source_rate <= 0:
        raise ValueError("invalid WAV channel count or sample rate")
    if sample_width == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported PCM sample width: {sample_width * 8} bits")

    if samples.size % channels:
        raise ValueError("WAV payload is not aligned to the channel count")
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1, dtype=np.float32)
    samples = np.ascontiguousarray(samples, dtype=np.float32)

    if source_rate != target_sample_rate_hz and samples.size:
        target_length = max(1, round(samples.size * target_sample_rate_hz / source_rate))
        source_axis = np.arange(samples.size, dtype=np.float64)
        target_axis = np.linspace(0, samples.size - 1, target_length, dtype=np.float64)
        samples = np.interp(target_axis, source_axis, samples).astype(np.float32)

    duration_ms = round(samples.size * 1000 / target_sample_rate_hz)
    return AudioBuffer(
        samples=samples,
        sample_rate_hz=target_sample_rate_hz,
        duration_ms=max(0, duration_ms),
    )


def read_container_audio(
    path: Path,
    *,
    audio_minus_video_start_ms: float,
    target_sample_rate_hz: int = 16000,
    max_duration_s: float | None = None,
) -> AudioBuffer:
    """Decode one container audio track onto the probed video PTS timeline.

    The caller must supply the offset from the container timing probe. This keeps
    media decoding separate from the fail-closed decision about which tracks and
    timestamps are authoritative.
    """

    if target_sample_rate_hz <= 0:
        raise ValueError("target_sample_rate_hz must be positive")
    if max_duration_s is not None and max_duration_s <= 0:
        raise ValueError("max_duration_s must be positive")
    if not isfinite(audio_minus_video_start_ms):
        raise ValueError("audio_minus_video_start_ms must be finite")
    try:
        import av
        import numpy as np
    except ImportError as error:
        raise RuntimeError(
            "PyAV and NumPy are required for container audio loading"
        ) from error

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    offset_samples = round(
        audio_minus_video_start_ms * target_sample_rate_hz / 1000.0
    )
    maximum_timeline_samples = (
        round(max_duration_s * target_sample_rate_hz)
        if max_duration_s is not None
        else None
    )
    source_trim_samples = max(0, -offset_samples)
    source_samples_needed = None
    if maximum_timeline_samples is not None:
        available_timeline_samples = max(
            0,
            maximum_timeline_samples - max(0, offset_samples),
        )
        source_samples_needed = source_trim_samples + available_timeline_samples

    chunks: list[Any] = []
    first_output_position: int | None = None
    cursor = 0
    decoded_frame_count = 0

    def append_resampled(frame: Any) -> None:
        nonlocal cursor, first_output_position
        if frame.pts is None or frame.time_base is None:
            raise ValueError("decoded container audio is missing PTS")
        absolute_position = round(
            float(frame.pts * frame.time_base) * target_sample_rate_hz
        )
        if first_output_position is None:
            first_output_position = absolute_position
        relative_position = absolute_position - first_output_position
        if relative_position < 0:
            raise ValueError("decoded container audio PTS moved before its start")

        values = np.asarray(frame.to_ndarray(), dtype=np.float32)
        if values.ndim != 2 or values.shape[0] != 1:
            raise ValueError("resampled container audio is not mono")
        values = values.reshape(-1)

        if relative_position > cursor:
            gap_end = relative_position
            if source_samples_needed is not None:
                gap_end = min(gap_end, source_samples_needed)
            if gap_end > cursor:
                chunks.append(np.zeros(gap_end - cursor, dtype=np.float32))
                cursor = gap_end
        elif relative_position < cursor:
            overlap = cursor - relative_position
            if overlap >= values.size:
                return
            values = values[overlap:]

        if source_samples_needed is not None:
            remaining = source_samples_needed - cursor
            if remaining <= 0:
                return
            values = values[:remaining]
        if values.size:
            chunks.append(np.ascontiguousarray(values, dtype=np.float32))
            cursor += int(values.size)

    with av.open(str(path), mode="r") as container:
        audio_streams = list(container.streams.audio)
        if len(audio_streams) != 1:
            raise ValueError(
                "same-container replay requires exactly one audio stream; "
                f"found {len(audio_streams)}"
            )
        if source_samples_needed is not None and source_samples_needed <= 0:
            raise ValueError("container audio does not overlap the replay window")

        resampler = av.AudioResampler(
            format="fltp",
            layout="mono",
            rate=target_sample_rate_hz,
        )
        for decoded in container.decode(audio_streams[0]):
            decoded_frame_count += 1
            for output in resampler.resample(decoded):
                append_resampled(output)
            if (
                source_samples_needed is not None
                and cursor >= source_samples_needed
            ):
                break
        for output in resampler.resample(None):
            append_resampled(output)

    if decoded_frame_count == 0 or not chunks:
        raise ValueError("container audio stream produced no decoded samples")
    samples = np.ascontiguousarray(np.concatenate(chunks), dtype=np.float32)
    if source_trim_samples:
        samples = samples[source_trim_samples:]
    timeline_start_samples = max(0, offset_samples)
    if maximum_timeline_samples is not None:
        available = max(0, maximum_timeline_samples - timeline_start_samples)
        samples = samples[:available]
    if not samples.size:
        raise ValueError("container audio does not overlap the replay window")

    return AudioBuffer(
        samples=np.ascontiguousarray(samples, dtype=np.float32),
        sample_rate_hz=target_sample_rate_hz,
        duration_ms=round(samples.size * 1000 / target_sample_rate_hz),
        start_ms=round(timeline_start_samples * 1000 / target_sample_rate_hz),
    )
