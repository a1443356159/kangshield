#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "v1-m3-pose-models.json"
DEFAULT_MODELS_DIR = PROJECT_ROOT / "models" / "rtmpose"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        with destination.open("wb") as stream:
            shutil.copyfileobj(response, stream)


def _extract_onnx(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        candidates = [
            name for name in bundle.namelist() if name.endswith("/end2end.onnx")
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"expected exactly one end2end.onnx in {archive}, got {candidates}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with bundle.open(candidates[0]) as source:
            with destination.open("wb") as target:
                shutil.copyfileobj(source, target)


def prepare_model(
    model: dict,
    *,
    models_dir: Path,
    offline: bool,
) -> dict:
    output = models_dir / model["output_path"]
    if output.is_file() and sha256_file(output) == model["onnx_sha256"]:
        return {
            "model_id": model["model_id"],
            "path": str(output),
            "sha256": model["onnx_sha256"],
            "status": "verified_existing",
        }
    if offline:
        raise FileNotFoundError(
            f"offline validation failed for {model['model_id']}: {output}"
        )

    with tempfile.TemporaryDirectory(prefix="kangshield-v1-m3-model-") as temp:
        archive = Path(temp) / "model.zip"
        _download(model["url"], archive)
        actual_archive_digest = sha256_file(archive)
        if actual_archive_digest != model["archive_sha256"]:
            raise ValueError(
                f"archive digest mismatch for {model['model_id']}: "
                f"{actual_archive_digest}"
            )
        temporary_output = Path(temp) / "end2end.onnx"
        _extract_onnx(archive, temporary_output)
        actual_onnx_digest = sha256_file(temporary_output)
        if actual_onnx_digest != model["onnx_sha256"]:
            raise ValueError(
                f"ONNX digest mismatch for {model['model_id']}: "
                f"{actual_onnx_digest}"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_output.replace(output)
    return {
        "model_id": model["model_id"],
        "path": str(output),
        "sha256": model["onnx_sha256"],
        "status": "downloaded_and_verified",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and verify pinned V1-M3 OpenMMLab ONNX models"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Only validate already prepared models; never access the network",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("schema_version") != "1.0":
        raise ValueError("unsupported V1-M3 model config schema")
    results = [
        prepare_model(model, models_dir=args.models_dir, offline=args.offline)
        for model in config["models"]
    ]
    print(json.dumps({"models": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
