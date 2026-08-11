#!/usr/bin/env python3
"""Run the official MMAction2 PoseC3D checkpoint as a local sidecar.

The existing pose process writes a small NPZ window containing COCO-17
keypoints.  This process watches that file, performs skeleton action
recognition on the GPU, and atomically writes a JSON result.  Keeping this in
its own Python 3.10 environment avoids mixing OpenMMLab's runtime constraints
with the newer Ultralytics environment.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import torch
from mmaction.apis import inference_skeleton, init_recognizer
from mmengine import Config


# Synced from fall-detection posec3d_service.py.  Mechanical adaptation only:
# PROJECT_DIR points at the kangshield repository root instead of the
# fall-detection project directory (recorded in SYNC_MANIFEST.json).
PROJECT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = (
    PROJECT_DIR
    / "vendor/mmaction2/configs/skeleton/posec3d/"
    "slowonly_r50_8xb16-u48-240e_ntu60-xsub-keypoint.py"
)
DEFAULT_CHECKPOINT = (
    PROJECT_DIR / "models/posec3d/posec3d-ntu60-xsub-keypoint.pth"
)
DEFAULT_LABELS = PROJECT_DIR / "models/posec3d/label_map_ntu60.txt"
DEFAULT_INPUT = PROJECT_DIR / ".cache/posec3d-input.npz"
DEFAULT_OUTPUT = PROJECT_DIR / ".cache/posec3d-result.json"


def private_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(stat.S_IRWXU)
    content = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
    temporary.replace(path)


def realtime_config(path: Path) -> Config:
    """Use one view per rolling window instead of the 20-view test protocol."""
    config = Config.fromfile(path)
    for transform in config.test_pipeline:
        if transform["type"] == "UniformSampleFrames":
            transform["num_clips"] = 1
        elif transform["type"] == "GeneratePoseTarget":
            transform["double"] = False
    return config


def pose_results(keypoints: np.ndarray, scores: np.ndarray) -> list[dict[str, Any]]:
    return [
        {
            "keypoints": keypoints[index][None].astype(np.float32, copy=False),
            "keypoint_scores": scores[index][None].astype(np.float32, copy=False),
        }
        for index in range(keypoints.shape[0])
    ]


def warmup(model: torch.nn.Module) -> None:
    # A geometrically valid stationary COCO-17 skeleton makes the first real
    # camera window avoid CUDA/kernel initialization latency.
    xy = np.array(
        [
            [1280, 260], [1250, 240], [1310, 240], [1215, 255], [1345, 255],
            [1190, 430], [1370, 430], [1130, 610], [1430, 610], [1100, 780],
            [1460, 780], [1220, 760], [1340, 760], [1210, 1010], [1350, 1010],
            [1200, 1270], [1360, 1270],
        ],
        dtype=np.float32,
    )
    points = np.repeat(xy[None], 48, axis=0)
    scores = np.full((48, 17), 0.95, dtype=np.float32)
    inference_skeleton(model, pose_results(points, scores), (1440, 2560))
    torch.cuda.synchronize()


def parent_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    checkpoint_path = Path(args.checkpoint)
    labels_path = Path(args.labels)
    input_path = Path(args.input_file)
    output_path = Path(args.output_file)
    for required in (config_path, checkpoint_path, labels_path):
        if not required.is_file():
            raise SystemExit(f"required PoseC3D file is missing: {required}")

    labels = [line.strip() for line in labels_path.read_text().splitlines()]
    if len(labels) != 60:
        raise SystemExit(f"expected 60 NTU labels, found {len(labels)}")

    warnings.filterwarnings(
        "ignore", message="Fail to import .*MultiScaleDeformableAttention.*"
    )
    loading_started = time.perf_counter()
    model = init_recognizer(
        realtime_config(config_path), str(checkpoint_path), device=args.device
    )
    warmup(model)
    load_ms = (time.perf_counter() - loading_started) * 1000
    private_json(
        output_path,
        {
            "state": "ready",
            "signal": "collecting",
            "message": "PoseC3D ready; waiting for a 48-frame skeleton window",
            "model": "PoseC3D SlowOnly-R50 / NTU60-XSub keypoint",
            "device": args.device,
            "model_load_ms": round(load_ms, 1),
            "processed_at": time.time(),
        },
    )
    print(
        f"posec3d_ready device={args.device} load_ms={load_ms:.1f} "
        f"gpu_mib={torch.cuda.memory_allocated() / 1024**2:.1f}",
        flush=True,
    )

    last_mtime_ns = -1
    smoothed_scores: np.ndarray | None = None
    staggering_streak = 0
    falling_streak = 0
    while parent_alive(args.parent_pid):
        try:
            stat_result = input_path.stat()
        except FileNotFoundError:
            time.sleep(args.poll_interval)
            continue
        if stat_result.st_mtime_ns == last_mtime_ns:
            time.sleep(args.poll_interval)
            continue
        last_mtime_ns = stat_result.st_mtime_ns

        try:
            with np.load(input_path, allow_pickle=False) as sample:
                keypoints = sample["keypoints"].astype(np.float32)
                scores = sample["scores"].astype(np.float32)
                height = int(sample["height"])
                width = int(sample["width"])
                sequence = int(sample["sequence"])
                submitted_at = float(sample["submitted_at"])
                window_span_s = float(sample["window_span_s"])
            if keypoints.ndim != 3 or keypoints.shape[1:] != (17, 2):
                raise ValueError(f"invalid keypoint shape {keypoints.shape}")
            if scores.shape != keypoints.shape[:2]:
                raise ValueError(f"invalid score shape {scores.shape}")

            torch.cuda.synchronize()
            inference_started = time.perf_counter()
            result = inference_skeleton(
                model, pose_results(keypoints, scores), (height, width)
            )
            torch.cuda.synchronize()
            inference_ms = (time.perf_counter() - inference_started) * 1000
            current_scores = result.pred_score.detach().cpu().numpy()
            if smoothed_scores is None:
                smoothed_scores = current_scores
            else:
                smoothed_scores = (
                    args.ema_alpha * current_scores
                    + (1.0 - args.ema_alpha) * smoothed_scores
                )

            staggering = float(smoothed_scores[41])
            falling = float(smoothed_scores[42])
            staggering_streak = (
                staggering_streak + 1
                if staggering >= args.staggering_threshold
                else 0
            )
            falling_streak = (
                falling_streak + 1 if falling >= args.falling_threshold else 0
            )
            if falling_streak >= args.required_windows:
                signal = "falling_event"
            elif staggering_streak >= args.required_windows:
                signal = "instability_warning"
            else:
                signal = "monitoring"

            top_indices = np.argsort(smoothed_scores)[-5:][::-1]
            private_json(
                output_path,
                {
                    "state": "ready",
                    "signal": signal,
                    "model": "PoseC3D SlowOnly-R50 / NTU60-XSub keypoint",
                    "device": args.device,
                    "sequence": sequence,
                    "window_frames": int(keypoints.shape[0]),
                    "window_span_s": round(window_span_s, 3),
                    "submitted_at": submitted_at,
                    "processed_at": time.time(),
                    "inference_ms": round(inference_ms, 2),
                    "staggering_probability": round(staggering, 6),
                    "falling_probability": round(falling, 6),
                    "raw_staggering_probability": round(
                        float(current_scores[41]), 6
                    ),
                    "raw_falling_probability": round(float(current_scores[42]), 6),
                    "thresholds": {
                        "staggering": args.staggering_threshold,
                        "falling": args.falling_threshold,
                        "required_windows": args.required_windows,
                    },
                    "top_actions": [
                        {
                            "index": int(index),
                            "label": labels[index],
                            "probability": round(float(smoothed_scores[index]), 6),
                        }
                        for index in top_indices
                    ],
                    "gpu_memory_mib": round(
                        torch.cuda.memory_allocated() / 1024**2, 1
                    ),
                    "note": (
                        "NTU60 action probabilities are engineering signals, "
                        "not calibrated clinical fall probabilities."
                    ),
                },
            )
            print(
                f"sequence={sequence} inference_ms={inference_ms:.1f} "
                f"staggering={staggering:.4f} falling={falling:.4f} "
                f"signal={signal}",
                flush=True,
            )
        except Exception as exc:  # Keep the sidecar alive after a partial write.
            private_json(
                output_path,
                {
                    "state": "error",
                    "signal": "unavailable",
                    "message": str(exc)[:500],
                    "processed_at": time.time(),
                },
            )
            print(f"posec3d_error={exc}", flush=True)
            time.sleep(args.poll_interval)
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--config", default=str(DEFAULT_CONFIG))
    value.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    value.add_argument("--labels", default=str(DEFAULT_LABELS))
    value.add_argument("--input-file", default=str(DEFAULT_INPUT))
    value.add_argument("--output-file", default=str(DEFAULT_OUTPUT))
    value.add_argument("--device", default="cuda:0")
    value.add_argument("--parent-pid", type=int, default=0)
    value.add_argument("--poll-interval", type=float, default=0.05)
    value.add_argument("--ema-alpha", type=float, default=0.45)
    value.add_argument("--staggering-threshold", type=float, default=0.35)
    value.add_argument("--falling-threshold", type=float, default=0.50)
    value.add_argument("--required-windows", type=int, default=2)
    return value


if __name__ == "__main__":
    raise SystemExit(run(parser().parse_args()))
