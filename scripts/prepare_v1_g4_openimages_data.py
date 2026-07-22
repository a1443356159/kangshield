from __future__ import annotations

import argparse
import json
from pathlib import Path

from kangshield.information.static_home_preparation import (
    prepare_v1_g4_openimages_data,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download, verify, and prepare the pinned V1-G4 Open Images "
            "static home-negative set"
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("configs/v1-g4-openimages-static-home-negative.json"),
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=Path("data/raw/v1-g4-openimages-static-home/downloads"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/v1-g4-openimages-static-home"),
    )
    args = parser.parse_args()
    result = prepare_v1_g4_openimages_data(
        manifest_path=args.manifest,
        download_dir=args.download_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
