#!/usr/bin/env bash
#SBATCH --job-name=kangshield-mm-smoke
#SBATCH --partition=hepnodes
#SBATCH --gres=gpu:L40:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:20:00
#SBATCH --output=slurm-%x-%j.out

set -euo pipefail

: "${KANG_VIDEO_INPUT:?Set KANG_VIDEO_INPUT to a local video file}"

kang_audio_arguments=()
case "${KANG_AUDIO_FROM_VIDEO:-0}" in
  0)
    : "${KANG_AUDIO_INPUT:?Set KANG_AUDIO_INPUT or KANG_AUDIO_FROM_VIDEO=1}"
    kang_audio_arguments=("${KANG_AUDIO_INPUT}")
    ;;
  1)
    if [[ -n "${KANG_AUDIO_INPUT:-}" ]]; then
      echo "KANG_AUDIO_INPUT must be unset when KANG_AUDIO_FROM_VIDEO=1" >&2
      exit 2
    fi
    kang_audio_arguments=(--audio-from-video)
    ;;
  *)
    echo "KANG_AUDIO_FROM_VIDEO must be 0 or 1" >&2
    exit 2
    ;;
esac

kang_repo_dir=${SLURM_SUBMIT_DIR:-/home/yyy/kangshield}
kang_python=${KANG_PYTHON:-${kang_repo_dir}/.venv/bin/python}
kang_pose_model=${KANG_POSE_MODEL:-${kang_repo_dir}/models/yolo26n-pose.pt}
kang_runs_dir=${KANG_RUNS_DIR:-${kang_repo_dir}/runs}

umask 077
cd "${kang_repo_dir}"
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
  kang_slurm_output="${kang_repo_dir}/slurm-${SLURM_JOB_NAME}-${SLURM_JOB_ID}.out"
  if [[ ! -f "${kang_slurm_output}" ]]; then
    echo "Slurm output file not found: ${kang_slurm_output}" >&2
    exit 2
  fi
  chmod 600 "${kang_slurm_output}"
fi
export PYTHONUNBUFFERED=1
export PYTHONPATH="${kang_repo_dir}/src${PYTHONPATH:+:${PYTHONPATH}}"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

kang_cudnn_lib=$("${kang_python}" -c \
  'from pathlib import Path; import nvidia.cudnn; print(Path(next(iter(nvidia.cudnn.__path__))) / "lib")')
if [[ ! -f "${kang_cudnn_lib}/libcudnn.so.9" ]]; then
  echo "cuDNN 9 runtime library not found: ${kang_cudnn_lib}" >&2
  exit 2
fi
export LD_LIBRARY_PATH="${kang_cudnn_lib}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

"${kang_python}" -m kangshield.information.cli run-multimodal \
  "${KANG_VIDEO_INPUT}" \
  "${kang_audio_arguments[@]}" \
  --runs-dir "${kang_runs_dir}" \
  --pose-model "${kang_pose_model}" \
  --pose-device 0 \
  --speech-device cuda:0 \
  --offline-models \
  --pose-sample-fps "${KANG_POSE_SAMPLE_FPS:-5}" \
  --fusion-window-ms "${KANG_FUSION_WINDOW_MS:-1000}" \
  --max-duration-s "${KANG_MAX_DURATION_S:-30}" \
  --evidence-level "${KANG_EVIDENCE_LEVEL:-E1}" \
  --source-type "${KANG_SOURCE_TYPE:-local_file}"
