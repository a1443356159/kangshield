#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

from kangshield.information.privacy import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "raw" / "public-smoke" / "v1-m2c-timing.synthetic.avi"
)


def build_fixture(
    output_path: Path,
    *,
    duration_s: int = 3,
    fps: int = 10,
    sample_rate_hz: int = 8000,
) -> None:
    if duration_s <= 0 or fps <= 0 or sample_rate_hz <= 0:
        raise ValueError("duration, fps and sample rate must be positive")
    if sample_rate_hz % fps:
        raise ValueError("sample rate must be divisible by fps for this fixture")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    samples_per_frame = sample_rate_hz // fps
    click_times_s = {0.5, duration_s - 0.5}
    # AVI avoids Matroska's randomly generated SegmentUID, so identical inputs
    # produce a byte-identical fixture suitable for a provenance smoke test.
    with av.open(str(output_path), "w", format="avi") as output:
        output.metadata["title"] = "kangshield-synthetic-av-timing-fixture"
        output.metadata["fixture"] = "synthetic-no-personal-data"
        video = output.add_stream("ffv1", rate=fps)
        video.width = 96
        video.height = 64
        video.pix_fmt = "yuv420p"
        audio = output.add_stream("pcm_s16le", rate=sample_rate_hz)
        audio.layout = "mono"

        for frame_index in range(duration_s * fps):
            start_s = frame_index / fps
            pixels = np.zeros((64, 96, 3), dtype=np.uint8)
            pixels[:, : 8 + (frame_index % 80), 1] = 160
            if any(abs(start_s - click) < 1 / (2 * fps) for click in click_times_s):
                pixels[:, :, :] = 255
            video_frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            video_frame.pts = frame_index
            video_frame.time_base = Fraction(1, fps)
            for packet in video.encode(video_frame):
                output.mux(packet)

            samples = np.zeros((1, samples_per_frame), dtype=np.int16)
            chunk_start = frame_index * samples_per_frame
            for click_s in click_times_s:
                click_sample = round(click_s * sample_rate_hz)
                relative = click_sample - chunk_start
                if 0 <= relative < samples_per_frame:
                    samples[0, relative : min(relative + 16, samples_per_frame)] = 24000
            audio_frame = av.AudioFrame.from_ndarray(
                samples, format="s16", layout="mono"
            )
            audio_frame.sample_rate = sample_rate_hz
            audio_frame.pts = chunk_start
            audio_frame.time_base = Fraction(1, sample_rate_hz)
            for packet in audio.encode(audio_frame):
                output.mux(packet)

        for packet in video.encode():
            output.mux(packet)
        for packet in audio.encode():
            output.mux(packet)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic same-container A/V timing fixture"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--duration-s", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    if output.exists() and not args.force:
        raise FileExistsError(f"output already exists; use --force: {output}")
    build_fixture(output, duration_s=args.duration_s)
    print(
        json.dumps(
            {
                "output": str(output),
                "byte_size": output.stat().st_size,
                "sha256": sha256_file(output),
                "duration_s": args.duration_s,
                "pyav_version": av.__version__,
                "synthetic": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
