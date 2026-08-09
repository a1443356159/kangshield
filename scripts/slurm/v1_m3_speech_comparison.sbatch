#!/usr/bin/env bash
#SBATCH --job-name=kangshield-m3-speech
#SBATCH --partition=hepnodes
#SBATCH --gres=gpu:L40:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:30:00
#SBATCH --output=logs/slurm/slurm-%x-%j.out

set -euo pipefail

if [[ -z "${SLURM_SUBMIT_DIR:-}" ]]; then
  echo "SLURM_SUBMIT_DIR is required; submit from the repository root" >&2
  exit 2
fi
# shellcheck source=scripts/slurm/runtime.sh
source "${SLURM_SUBMIT_DIR}/scripts/slurm/runtime.sh"
kang_slurm_init

: "${KANG_DATASET_CASES:?Set KANG_DATASET_CASES to benchmark-cases.json}"

kang_whisper_model=${KANG_WHISPER_MODEL:-${kang_repo_dir}/models/whisper/small.pt}

"${kang_python}" scripts/prepare_v1_m3_speech_models.py --offline
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

/usr/bin/time -v "${kang_python}" -m kangshield.information.cli \
  benchmark-speech-models "${KANG_DATASET_CASES}" \
  --runs-dir "${kang_runs_dir}" \
  --offline-models \
  --funasr-device cuda:0 \
  --whisper-model "${kang_whisper_model}" \
  --whisper-device cuda:0 \
  --whisper-beam-size "${KANG_WHISPER_BEAM_SIZE:-5}" \
  --whisper-fp16
