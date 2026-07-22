from __future__ import annotations

import argparse
import json
from pathlib import Path

from kangshield.information.dataset_preparation import prepare_v1_m2b_dataset


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download, verify, and prepare the pinned V1-M2b public suite"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("configs/v1-m2b-datasets.json"),
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=Path("data/raw/v1-m2b/downloads"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/v1-m2b"),
    )
    parser.add_argument(
        "--accept-urfd-noncommercial-license",
        action="store_true",
        help="Confirm that CC-BY-NC-SA-4.0 terms were reviewed and use is non-commercial",
    )
    args = parser.parse_args()
    result = prepare_v1_m2b_dataset(
        manifest_path=args.manifest,
        download_dir=args.download_dir,
        output_dir=args.output_dir,
        accept_urfd_noncommercial_license=args.accept_urfd_noncommercial_license,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
