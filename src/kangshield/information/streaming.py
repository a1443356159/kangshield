from __future__ import annotations

import wave
from dataclasses import dataclass
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
