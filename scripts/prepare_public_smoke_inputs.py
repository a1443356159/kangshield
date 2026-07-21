from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path


BUS_IMAGE_URL = "https://ultralytics.com/images/bus.jpg"
MANDARIN_WAV_URL = (
    "https://isv-data.oss-cn-hangzhou.aliyuncs.com/ics/MaaS/ASR/"
    "test_audio/asr_example_zh.wav"
)


def _download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        urllib.request.urlretrieve(url, temporary)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _make_video(image_path: Path, video_path: Path) -> None:
    try:
        import cv2
        import numpy as np
    except ImportError as error:
        raise RuntimeError("OpenCV and NumPy are required") from error

    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"cannot decode downloaded image: {image_path}")
    height, width = image.shape[:2]
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (width, height),
    )
    if not writer.isOpened():
        raise RuntimeError("OpenCV MJPG video writer is unavailable")
    try:
        for frame_index in range(50):
            shift = round(4 * np.sin(frame_index / 8.0))
            frame = np.roll(image, shift=shift, axis=1)
            writer.write(frame)
    finally:
        writer.release()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/public-smoke"),
    )
    args = parser.parse_args()
    image_path = args.output_dir / "ultralytics-bus.jpg"
    audio_path = args.output_dir / "funasr-asr-example-zh.wav"
    video_path = args.output_dir / "ultralytics-bus-replay.avi"
    _download(BUS_IMAGE_URL, image_path)
    _download(MANDARIN_WAV_URL, audio_path)
    _make_video(image_path, video_path)
    print(
        json.dumps(
            {
                "video": str(video_path),
                "video_sha256": _sha256(video_path),
                "audio": str(audio_path),
                "audio_sha256": _sha256(audio_path),
                "sources": {
                    "image": BUS_IMAGE_URL,
                    "audio": MANDARIN_WAV_URL,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
