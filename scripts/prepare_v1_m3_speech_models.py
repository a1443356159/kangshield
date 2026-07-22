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
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "v1-m3-speech-models.json"
DEFAULT_WHISPER_DIR = PROJECT_ROOT / "models" / "whisper"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_weight(path: Path, expected: str, label: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"model weight not found for {label}: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"weight digest mismatch for {label}: expected {expected}, "
            f"received {actual}"
        )
    return actual


def prepare_whisper(
    model: dict,
    *,
    models_dir: Path,
    offline: bool,
) -> dict[str, str | int]:
    output = models_dir / model["output_path"]
    if output.is_file():
        actual = sha256_file(output)
        if actual == model["sha256"] and output.stat().st_size == model["byte_size"]:
            return {
                "model_id": model["model_id"],
                "path": str(output),
                "byte_size": output.stat().st_size,
                "sha256": actual,
                "status": "verified_existing",
            }
        if offline:
            raise ValueError(
                f"offline Whisper validation failed for {output}: "
                "digest or size mismatch"
            )
    elif offline:
        raise FileNotFoundError(
            f"offline Whisper validation failed; checkpoint not found: {output}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="kangshield-v1-m3-whisper-", dir=output.parent
    ) as temporary_directory:
        temporary = Path(temporary_directory) / output.name
        with urllib.request.urlopen(model["url"], timeout=180) as response:
            with temporary.open("wb") as stream:
                shutil.copyfileobj(response, stream)
        if temporary.stat().st_size != model["byte_size"]:
            raise ValueError(
                f"Whisper checkpoint size mismatch: {temporary.stat().st_size}"
            )
        digest = _verified_weight(
            temporary, model["sha256"], model["model_id"]
        )
        temporary.replace(output)
    return {
        "model_id": model["model_id"],
        "path": str(output),
        "byte_size": output.stat().st_size,
        "sha256": digest,
        "status": "downloaded_and_verified",
    }


def prepare_funasr(models: list[dict], *, offline: bool) -> list[dict[str, str]]:
    if offline:
        from kangshield.information.speech_backend import _resolve_model_reference

        snapshots = {
            model["alias"]: Path(
                _resolve_model_reference(model["alias"], offline=True)
            )
            for model in models
        }
    else:
        try:
            from modelscope import snapshot_download
        except ImportError as error:
            raise RuntimeError(
                "Install requirements/slurm-models.txt before preparing FunASR models"
            ) from error
        snapshots = {
            model["alias"]: Path(
                snapshot_download(
                    model_id=model["model_id"],
                    revision=model["revision"],
                )
            )
            for model in models
        }

    results: list[dict[str, str]] = []
    for model in models:
        snapshot = snapshots[model["alias"]]
        weight = snapshot / "model.pt"
        digest = _verified_weight(
            weight, model["weight_sha256"], model["model_id"]
        )
        results.append(
            {
                "alias": model["alias"],
                "model_id": model["model_id"],
                "snapshot": str(snapshot),
                "model_sha256": digest,
                "status": "verified_existing" if offline else "downloaded_or_verified",
            }
        )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and verify pinned V1-M3 speech models"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--whisper-dir", type=Path, default=DEFAULT_WHISPER_DIR
    )
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
        raise ValueError("unsupported V1-M3 speech model config schema")
    whisper = prepare_whisper(
        config["whisper"], models_dir=args.whisper_dir, offline=args.offline
    )
    funasr = prepare_funasr(config["funasr"], offline=args.offline)
    print(
        json.dumps(
            {"whisper": whisper, "funasr": funasr},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
