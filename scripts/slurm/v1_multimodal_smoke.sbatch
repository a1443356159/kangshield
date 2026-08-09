#!/usr/bin/env bash
#SBATCH --job-name=kangshield-mm-smoke
#SBATCH --partition=hepnodes
#SBATCH --gres=gpu:L40:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:20:00
#SBATCH --output=logs/slurm/slurm-%x-%j.out

set -euo pipefail

if [[ -z "${SLURM_SUBMIT_DIR:-}" ]]; then
  echo "SLURM_SUBMIT_DIR is required; submit from the repository root" >&2
  exit 2
fi
# shellcheck source=scripts/slurm/runtime.sh
source "${SLURM_SUBMIT_DIR}/scripts/slurm/runtime.sh"
kang_slurm_init
kang_slurm_bind_cudnn9

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

kang_pose_model=${KANG_POSE_MODEL:-${kang_repo_dir}/models/yolo26n-pose.pt}

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
