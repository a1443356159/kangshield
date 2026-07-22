from __future__ import annotations

import argparse
import json
from pathlib import Path

from kangshield.information.dataset_preparation import download_and_verify
from kangshield.information.privacy import sha256_file
from kangshield.information.torchvision_pose_backend import (
    load_torchvision_pose_policy,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "v1-m3-torchvision-pose-model.json"
DEFAULT_MODELS_DIR = PROJECT_ROOT / "models" / "torchvision"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and verify the frozen TorchVision Keypoint R-CNN weight"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Only validate the prepared weight; never access the network",
    )
    args = parser.parse_args()
    policy = load_torchvision_pose_policy(args.config)
    output = args.models_dir / policy["output_path"]
    if args.offline:
        if not output.is_file() or output.stat().st_size != policy["byte_size"]:
            raise FileNotFoundError(
                f"offline TorchVision model validation failed: {output}"
            )
        if sha256_file(output) != policy["sha256"]:
            raise ValueError("offline TorchVision model digest validation failed")
        status = "verified_existing"
    else:
        existed = output.is_file()
        download_and_verify(
            policy["url"],
            output,
            byte_size=policy["byte_size"],
            sha256=policy["sha256"],
        )
        status = "verified_existing" if existed else "downloaded_and_verified"
    print(
        json.dumps(
            {
                "model_id": policy["model_id"],
                "path": str(output),
                "sha256": policy["sha256"],
                "policy_sha256": sha256_file(args.config),
                "status": status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
