#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "v1-g4-posec3d-model.json"
DEFAULT_MODELS_DIR = PROJECT_ROOT / "models"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as response:
        with destination.open("wb") as stream:
            shutil.copyfileobj(response, stream)


def prepare_model(model: dict, *, models_dir: Path, offline: bool) -> dict:
    output = models_dir / model["output_path"]
    pinned = model.get("weight_sha256")
    if pinned and output.is_file() and sha256_file(output) == pinned:
        return {
            "model_id": model["model_id"],
            "path": str(output),
            "sha256": pinned,
            "status": "verified_existing",
        }
    if offline:
        raise FileNotFoundError(
            f"offline validation failed for {model['model_id']}: {output}"
        )
    if not pinned:
        with tempfile.TemporaryDirectory(prefix="kangshield-v1-g4-model-") as temp:
            candidate = Path(temp) / "candidate.pth"
            _download(model["url"], candidate)
            digest = sha256_file(candidate)
        raise ValueError(
            f"{model['model_id']} weight digest is not pinned in the policy; "
            f"downloaded candidate sha256 is {digest} — pin it as weight_sha256 "
            "in the policy config and re-run"
        )
    with tempfile.TemporaryDirectory(prefix="kangshield-v1-g4-model-") as temp:
        candidate = Path(temp) / "candidate.pth"
        _download(model["url"], candidate)
        actual = sha256_file(candidate)
        if actual != pinned:
            raise ValueError(
                f"weight digest mismatch for {model['model_id']}: {actual}"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(candidate), output)
    return {
        "model_id": model["model_id"],
        "path": str(output),
        "sha256": pinned,
        "status": "downloaded_and_verified",
    }


def prepare_label_map(model: dict, *, models_dir: Path, source: Path | None) -> dict:
    label_rel = model.get("label_map")
    pinned = model.get("label_map_sha256")
    if not label_rel or not pinned:
        return {"label_map": None, "status": "not_required"}
    output = models_dir / label_rel
    if not output.is_file():
        if source is None or not Path(source).is_file():
            raise FileNotFoundError(
                f"label map {output} is missing; pass --label-map-source "
                "pointing at the fall-detection models/posec3d/label_map_ntu60.txt"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
    actual = sha256_file(output)
    if actual != pinned:
        raise ValueError(f"label map digest mismatch: {actual}")
    return {"label_map": str(output), "sha256": pinned, "status": "verified"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and verify the pinned V1-G4 PoseC3D checkpoint"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--label-map-source", type=Path, default=None)
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
        raise ValueError("unsupported V1-G4 PoseC3D model config schema")
    results = []
    for model in config["models"]:
        result = prepare_model(model, models_dir=args.models_dir, offline=args.offline)
        result["label_map"] = prepare_label_map(
            model, models_dir=args.models_dir, source=args.label_map_source
        )
        results.append(result)
    print(json.dumps({"models": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
