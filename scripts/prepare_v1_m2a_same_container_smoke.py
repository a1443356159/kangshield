#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

from kangshield.information.container_timing import probe_container_timing
from kangshield.information.privacy import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = (
    PROJECT_ROOT / "data" / "raw" / "public-smoke" / "ultralytics-bus-replay.avi"
)
DEFAULT_AUDIO = (
    PROJECT_ROOT / "data" / "raw" / "public-smoke" / "funasr-asr-example-zh.wav"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "public-smoke"
    / "v1-m2a-public-av-offset-250ms.mkv"
)


def _read_pcm16_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as stream:
        if stream.getcomptype() != "NONE":
            raise ValueError("audio input must be uncompressed PCM WAV")
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2:
            raise ValueError("audio input must be mono 16-bit PCM WAV")
        sample_rate_hz = stream.getframerate()
        samples = np.frombuffer(
            stream.readframes(stream.getnframes()),
            dtype="<i2",
        ).copy()
    if sample_rate_hz <= 0 or not samples.size:
        raise ValueError("audio input must contain positive-rate PCM samples")
    return samples, sample_rate_hz


def build_same_container_smoke(
    *,
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    audio_offset_ms: int = 250,
) -> dict[str, object]:
    """Compose public video/WAV inputs into one A/V container with a PTS offset."""

    video_path = Path(video_path)
    audio_path = Path(audio_path)
    output_path = Path(output_path)
    if not video_path.is_file():
        raise FileNotFoundError(video_path)
    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)
    if audio_offset_ms < 0:
        raise ValueError("audio_offset_ms must be non-negative")
    samples, sample_rate_hz = _read_pcm16_mono(audio_path)
    offset_samples = round(audio_offset_ms * sample_rate_hz / 1000.0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".mkv",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        with av.open(str(video_path), mode="r") as source:
            video_streams = list(source.streams.video)
            if len(video_streams) != 1:
                raise ValueError(
                    "video input must contain exactly one video stream; "
                    f"found {len(video_streams)}"
                )
            source_video = video_streams[0]
            rate = source_video.average_rate
            if rate is None:
                raise ValueError("video input must declare an average frame rate")
            rate = Fraction(rate)
            if rate.denominator != 1 or rate.numerator <= 0:
                raise ValueError("smoke composer requires a positive integer video FPS")
            fps = rate.numerator
            if sample_rate_hz % fps:
                raise ValueError("audio sample rate must be divisible by video FPS")
            audio_chunk_size = sample_rate_hz // fps

            with av.open(
                str(temporary),
                mode="w",
                format="matroska",
                container_options={"fflags": "+bitexact"},
            ) as output:
                output.metadata["fixture"] = "public-inputs-engineered-av-offset"
                video = output.add_stream("ffv1", rate=fps)
                video.width = int(source_video.codec_context.width)
                video.height = int(source_video.codec_context.height)
                video.pix_fmt = "yuv420p"
                audio = output.add_stream("pcm_s16le", rate=sample_rate_hz)
                audio.layout = "mono"

                decoded_video = iter(source.decode(source_video))
                video_finished = False
                video_index = 0
                audio_index = 0
                while True:
                    frame = None
                    if not video_finished:
                        try:
                            frame = next(decoded_video)
                        except StopIteration:
                            video_finished = True
                    audio_start = audio_index * audio_chunk_size
                    has_audio = audio_start < samples.size
                    if frame is None and not has_audio:
                        break

                    if frame is not None:
                        normalized = frame.reformat(
                            width=video.width,
                            height=video.height,
                            format="yuv420p",
                        )
                        normalized.pts = video_index
                        normalized.time_base = Fraction(1, fps)
                        for packet in video.encode(normalized):
                            output.mux(packet)
                        video_index += 1

                    if has_audio:
                        chunk = samples[
                            audio_start : audio_start + audio_chunk_size
                        ]
                        audio_frame = av.AudioFrame.from_ndarray(
                            chunk.reshape(1, -1),
                            format="s16",
                            layout="mono",
                        )
                        audio_frame.sample_rate = sample_rate_hz
                        audio_frame.pts = offset_samples + audio_start
                        audio_frame.time_base = Fraction(1, sample_rate_hz)
                        for packet in audio.encode(audio_frame):
                            output.mux(packet)
                        audio_index += 1

                for packet in video.encode():
                    output.mux(packet)
                for packet in audio.encode():
                    output.mux(packet)

        timing, issues = probe_container_timing(temporary)
        if timing is None or issues:
            raise ValueError("composed container did not pass the timing probe")
        if timing.video_stream_count != 1 or timing.audio_stream_count != 1:
            raise ValueError("composed container does not contain one A/V stream pair")
        if timing.audio_minus_video_start_ms != float(audio_offset_ms):
            raise ValueError(
                "container muxer did not preserve the requested audio PTS offset"
            )
        if any(
            stream.missing_pts_count or stream.scan_truncated
            for stream in timing.streams
        ):
            raise ValueError("composed container has incomplete packet timing")
        temporary.replace(output_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return {
        "video_input_sha256": sha256_file(video_path),
        "audio_input_sha256": sha256_file(audio_path),
        "output_sha256": sha256_file(output_path),
        "output_byte_size": output_path.stat().st_size,
        "audio_offset_ms": audio_offset_ms,
        "video_frame_count": video_index,
        "audio_sample_count": int(samples.size),
        "audio_sample_rate_hz": sample_rate_hz,
        "container_format": "matroska",
        "video_codec": "ffv1",
        "audio_codec": "pcm_s16le",
        "bitexact_mux": True,
        "synthetic_alignment": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compose public smoke video/WAV into one PTS-offset A/V container"
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--audio", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audio-offset-ms", type=int, default=250)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    if output.exists() and not args.force:
        raise FileExistsError(f"output already exists; use --force: {output}")
    report = build_same_container_smoke(
        video_path=args.video.resolve(),
        audio_path=args.audio.resolve(),
        output_path=output,
        audio_offset_ms=args.audio_offset_ms,
    )
    print(
        json.dumps(
            {
                "output": str(output),
                **report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
