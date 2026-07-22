#!/usr/bin/env bash
#SBATCH --job-name=kangshield-runtime
#SBATCH --partition=hepnodes
#SBATCH --gres=gpu:L40:1
#SBATCH --cpus-per-task=2
#SBATCH --time=00:05:00
#SBATCH --output=slurm-%x-%j.out

set -euo pipefail

if [[ -z "${SLURM_SUBMIT_DIR:-}" ]]; then
  echo "SLURM_SUBMIT_DIR is required; submit from the repository root" >&2
  exit 2
fi
# shellcheck source=scripts/slurm/runtime.sh
source "${SLURM_SUBMIT_DIR}/scripts/slurm/runtime.sh"
kang_slurm_init
kang_slurm_bind_cudnn9
kang_slurm_verify_onnxruntime_cuda

nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
"${kang_python}" - <<'PY'
import json

import torch

probe = torch.ones(1, device="cuda")
print(
    json.dumps(
        {
            "cuda_available": torch.cuda.is_available(),
            "cuda_device": torch.cuda.get_device_name(0),
            "cuda_probe_sum": probe.sum().item(),
            "torch_version": torch.__version__,
            "risk_assessment_emitted": False,
            "alert_emitted": False,
        },
        ensure_ascii=False,
        indent=2,
    )
)
PY
