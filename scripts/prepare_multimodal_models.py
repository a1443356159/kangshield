from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


MODELSCOPE_MODELS = {
    "asr": "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "vad": "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "punctuation": "iic/punc_ct-transformer_cn-en-common-vocab471067-large",
}
POSE_MODEL = "yolo26n-pose.pt"
EXPECTED_DIGESTS = {
    POSE_MODEL: "eb3bb8268828aeaf515cec23a4bfafd793944a86fe9af94ba7823609c14522a9",
    MODELSCOPE_MODELS["asr"]: "3d491689244ec5dfbf9170ef3827c358aa10f1f20e42a7c59e15e688647946d1",
    MODELSCOPE_MODELS["vad"]: "b3be75be477f0780277f3bae0fe489f48718f585f3a6e45d7dd1fbb1a4255fc5",
    MODELSCOPE_MODELS["punctuation"]: "7176cae922a872e130e6b88aef9a1153581711baf79c9124c7c95be383cd6f81",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_digest(name: str, path: Path) -> str:
    actual = _sha256(path)
    expected = EXPECTED_DIGESTS[name]
    if actual != expected:
        raise ValueError(
            f"weight digest changed for {name}: expected {expected}, received {actual}; "
            "review the upstream revision before updating the V1 baseline"
        )
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prefetch the V1 multimodal baseline weights on a networked node",
    )
    parser.add_argument("--pose-dir", type=Path, default=Path("models"))
    args = parser.parse_args()

    try:
        from modelscope import snapshot_download
        from ultralytics import YOLO
    except ImportError as error:
        raise RuntimeError(
            "Install requirements/slurm-models.txt before preparing models"
        ) from error

    snapshots: dict[str, dict[str, str]] = {}
    for task, model_id in MODELSCOPE_MODELS.items():
        snapshot_path = Path(
            snapshot_download(
                model_id=model_id,
                revision="master",
            )
        )
        weight_path = snapshot_path / "model.pt"
        if not weight_path.is_file():
            raise FileNotFoundError(f"model weight not found: {weight_path}")
        snapshots[task] = {
            "model_id": model_id,
            "snapshot": str(snapshot_path),
            "model_sha256": _verified_digest(model_id, weight_path),
        }

    args.pose_dir.mkdir(parents=True, exist_ok=True)
    pose_dir = args.pose_dir.resolve()
    previous_directory = Path.cwd()
    try:
        os.chdir(pose_dir)
        YOLO(POSE_MODEL)
    finally:
        os.chdir(previous_directory)
    pose_path = pose_dir / POSE_MODEL
    if not pose_path.is_file():
        raise FileNotFoundError(f"pose weight not found after download: {pose_path}")

    print(
        json.dumps(
            {
                "pose": {
                    "path": str(pose_path),
                    "model_sha256": _verified_digest(POSE_MODEL, pose_path),
                },
                "modelscope": snapshots,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
