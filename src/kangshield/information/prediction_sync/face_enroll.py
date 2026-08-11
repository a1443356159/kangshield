#!/usr/bin/env python3
"""Build the local face whitelist gallery from authorized enrollment photos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .face_recognition import FaceGallery, FaceXLibRetinaArcBackend


PROJECT_DIR = Path(__file__).resolve().parent


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--whitelist-dir", type=Path, default=PROJECT_DIR / "whitelist")
    value.add_argument(
        "--gallery", type=Path, default=PROJECT_DIR / "data/face/gallery.npz"
    )
    value.add_argument("--models-dir", type=Path, default=PROJECT_DIR / "models/face")
    value.add_argument("--device", default="auto")
    value.add_argument("--detection-threshold", type=float, default=0.7)
    value.add_argument("--detector-max-side", type=int, default=1280)
    value.add_argument("--min-face-size", type=int, default=64)
    value.add_argument("--min-blur-variance", type=float, default=30.0)
    return value


def main() -> int:
    args = parser().parse_args()
    backend = FaceXLibRetinaArcBackend(
        args.models_dir,
        device=args.device,
        detection_threshold=args.detection_threshold,
        detector_max_side=args.detector_max_side,
    )
    gallery, report = FaceGallery.enroll_directory(
        args.whitelist_dir,
        backend,
        min_face_size=args.min_face_size,
        min_blur_variance=args.min_blur_variance,
    )
    gallery.save(args.gallery)
    payload = {
        "gallery": str(args.gallery),
        "backend": backend.metadata,
        **report,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
