#!/usr/bin/env bash
#SBATCH --job-name=kangshield-m3-speech
#SBATCH --partition=hepnodes
#SBATCH --gres=gpu:L40:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:30:00
#SBATCH --output=slurm-%x-%j.out

set -euo pipefail

: "${KANG_DATASET_CASES:?Set KANG_DATASET_CASES to benchmark-cases.json}"

kang_repo_dir=${SLURM_SUBMIT_DIR:-/home/yyy/kangshield}
kang_python=${KANG_PYTHON:-${kang_repo_dir}/.venv/bin/python}
kang_runs_dir=${KANG_RUNS_DIR:-${kang_repo_dir}/runs}
kang_whisper_model=${KANG_WHISPER_MODEL:-${kang_repo_dir}/models/whisper/small.pt}

cd "${kang_repo_dir}"
export PYTHONUNBUFFERED=1
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

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
