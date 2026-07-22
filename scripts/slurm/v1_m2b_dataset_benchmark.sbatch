#!/usr/bin/env bash
#SBATCH --job-name=kangshield-m2b-public
#SBATCH --partition=hepnodes
#SBATCH --gres=gpu:L40:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:30:00
#SBATCH --output=slurm-%x-%j.out

set -euo pipefail

: "${KANG_DATASET_CASES:?Set KANG_DATASET_CASES to benchmark-cases.json}"

kang_repo_dir=${SLURM_SUBMIT_DIR:-/home/yyy/kangshield}
kang_python=${KANG_PYTHON:-${kang_repo_dir}/.venv/bin/python}
kang_pose_model=${KANG_POSE_MODEL:-${kang_repo_dir}/models/yolo26n-pose.pt}
kang_runs_dir=${KANG_RUNS_DIR:-${kang_repo_dir}/runs}

cd "${kang_repo_dir}"
export PYTHONUNBUFFERED=1
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

"${kang_python}" -m kangshield.information.cli benchmark-dataset \
  "${KANG_DATASET_CASES}" \
  --runs-dir "${kang_runs_dir}" \
  --pose-model "${kang_pose_model}" \
  --pose-device 0 \
  --speech-device cuda:0 \
  --offline-models \
  --pose-sample-fps "${KANG_POSE_SAMPLE_FPS:-5}" \
  --fusion-window-ms "${KANG_FUSION_WINDOW_MS:-1000}" \
  --max-duration-s "${KANG_MAX_DURATION_S:-30}"
