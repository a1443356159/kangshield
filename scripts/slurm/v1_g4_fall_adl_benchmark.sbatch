#!/usr/bin/env bash
#SBATCH --job-name=kangshield-g4-adl
#SBATCH --partition=hepnodes
#SBATCH --gres=gpu:L40:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:45:00
#SBATCH --output=slurm-%x-%j.out

set -euo pipefail

: "${KANG_FALL_ADL_CASES:?Set KANG_FALL_ADL_CASES to fall-adl-cases.json}"

kang_repo_dir=${SLURM_SUBMIT_DIR:-/home/yyy/kangshield}
kang_python=${KANG_PYTHON:-${kang_repo_dir}/.venv/bin/python}
kang_runs_dir=${KANG_RUNS_DIR:-${kang_repo_dir}/runs}
kang_yolo_model=${KANG_YOLO_MODEL:-${kang_repo_dir}/models/yolo26n-pose.pt}
kang_rtmpose_detector=${KANG_RTMPOSE_DETECTOR:-${kang_repo_dir}/models/rtmpose/yolox_m_humanart/yolox_m_humanart.onnx}
kang_rtmpose_pose=${KANG_RTMPOSE_POSE:-${kang_repo_dir}/models/rtmpose/rtmpose_m_humanart/rtmpose_m_humanart.onnx}

cd "${kang_repo_dir}"
export PYTHONUNBUFFERED=1
export PYTHONPATH="${kang_repo_dir}/src${PYTHONPATH:+:${PYTHONPATH}}"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

"${kang_python}" scripts/prepare_v1_m3_pose_models.py --offline
test -f "${kang_yolo_model}"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

/usr/bin/time -v "${kang_python}" -m kangshield.information.cli \
  benchmark-fall-adl "${KANG_FALL_ADL_CASES}" \
  --runs-dir "${kang_runs_dir}" \
  --yolo-model "${kang_yolo_model}" \
  --yolo-device 0 \
  --rtmpose-detector-model "${kang_rtmpose_detector}" \
  --rtmpose-pose-model "${kang_rtmpose_pose}" \
  --rtmpose-device cuda:0 \
  --rtmpose-detection-confidence "${KANG_RTMPOSE_CONFIDENCE:-0.05}" \
  --pose-sample-fps "${KANG_POSE_SAMPLE_FPS:-5}" \
  --max-duration-s "${KANG_MAX_DURATION_S:-30}"
