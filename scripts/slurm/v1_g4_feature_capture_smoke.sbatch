#!/usr/bin/env bash
#SBATCH --job-name=kangshield-g4-capture
#SBATCH --partition=hepnodes
#SBATCH --gres=gpu:L40:1
#SBATCH --cpus-per-task=8
#SBATCH --time=00:30:00
#SBATCH --output=slurm-%x-%j.out

set -euo pipefail

: "${KANG_CAPTURE_MANIFEST:?Set KANG_CAPTURE_MANIFEST to capture-manifest.json}"
: "${KANG_CAPTURE_READINESS:?Set KANG_CAPTURE_READINESS to the readiness report}"
: "${KANG_CAPTURE_READINESS_RUN:?Set KANG_CAPTURE_READINESS_RUN to its run manifest}"

kang_repo_dir=${SLURM_SUBMIT_DIR:-/home/yyy/kangshield}
kang_python=${KANG_PYTHON:-${kang_repo_dir}/.venv/bin/python}
kang_runs_dir=${KANG_RUNS_DIR:-${kang_repo_dir}/runs}
kang_yolo_model=${KANG_YOLO_MODEL:-${kang_repo_dir}/models/yolo26n-pose.pt}
kang_rtmpose_detector=${KANG_RTMPOSE_DETECTOR:-${kang_repo_dir}/models/rtmpose/yolox_m_humanart/yolox_m_humanart.onnx}
kang_rtmpose_pose=${KANG_RTMPOSE_POSE:-${kang_repo_dir}/models/rtmpose/rtmpose_m_humanart/rtmpose_m_humanart.onnx}
kang_torchvision_model=${KANG_TORCHVISION_MODEL:-${kang_repo_dir}/models/torchvision/keypointrcnn_resnet50_fpn_coco-fc266e95.pth}

cd "${kang_repo_dir}"
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

"${kang_python}" scripts/prepare_v1_m3_pose_models.py --offline
"${kang_python}" scripts/prepare_v1_m3_torchvision_pose_model.py --offline
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

variants=(
  yolo26n-pose
  rtmpose-m-humanart
  torchvision-keypointrcnn
)

for variant in "${variants[@]}"; do
  /usr/bin/time -v "${kang_python}" -m kangshield.information.cli \
    capture-fall-features \
    "${KANG_CAPTURE_MANIFEST}" \
    "${KANG_CAPTURE_READINESS}" \
    "${KANG_CAPTURE_READINESS_RUN}" \
    --variant "${variant}" \
    --runs-dir "${kang_runs_dir}" \
    --source-type fixture \
    --evidence-level E1 \
    --sample-fps "${KANG_POSE_SAMPLE_FPS:-5}" \
    --yolo-model "${kang_yolo_model}" \
    --yolo-device 0 \
    --rtmpose-detector-model "${kang_rtmpose_detector}" \
    --rtmpose-pose-model "${kang_rtmpose_pose}" \
    --rtmpose-device cuda:0 \
    --rtmpose-detection-confidence "${KANG_RTMPOSE_CONFIDENCE:-0.05}" \
    --torchvision-model "${kang_torchvision_model}" \
    --torchvision-device cuda:0 \
    --torchvision-detection-confidence "${KANG_TORCHVISION_CONFIDENCE:-0.5}" \
    --torchvision-min-size "${KANG_TORCHVISION_MIN_SIZE:-800}" \
    --torchvision-max-size "${KANG_TORCHVISION_MAX_SIZE:-1333}"
done
