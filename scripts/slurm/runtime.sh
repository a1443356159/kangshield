#!/usr/bin/env bash

# Shared fail-closed runtime setup for KangShield's formal Slurm entrypoints.
# This file is sourced by sbatch scripts after Slurm has populated
# SLURM_SUBMIT_DIR, SLURM_JOB_ID, and SLURM_JOB_NAME.

kang_slurm_runtime_version=slurm-runtime-v0.1.0

kang_slurm_init() {
  if [[ -z "${SLURM_SUBMIT_DIR:-}" ]]; then
    echo "SLURM_SUBMIT_DIR is required; submit from the repository root" >&2
    return 2
  fi
  if [[ -z "${SLURM_JOB_ID:-}" || -z "${SLURM_JOB_NAME:-}" ]]; then
    echo "SLURM_JOB_ID and SLURM_JOB_NAME are required" >&2
    return 2
  fi

  umask 077

  local submit_dir
  if ! submit_dir=$(realpath -- "${SLURM_SUBMIT_DIR}"); then
    echo "Cannot resolve SLURM_SUBMIT_DIR" >&2
    return 2
  fi
  cd "${submit_dir}"

  kang_slurm_output=${KANG_SLURM_OUTPUT_PATH:-${submit_dir}/slurm-${SLURM_JOB_NAME}-${SLURM_JOB_ID}.out}
  if [[ ! -f "${kang_slurm_output}" ]]; then
    echo "Slurm output file not found" >&2
    return 2
  fi
  chmod 600 "${kang_slurm_output}"
  if [[ "$(stat -c '%a' "${kang_slurm_output}")" != "600" ]]; then
    echo "Slurm output is not owner-only" >&2
    return 2
  fi

  local repository_root
  if ! repository_root=$(git -C "${submit_dir}" rev-parse --show-toplevel 2>/dev/null); then
    echo "SLURM_SUBMIT_DIR is not a Git checkout" >&2
    return 2
  fi
  repository_root=$(realpath -- "${repository_root}")
  if [[ "${submit_dir}" != "${repository_root}" ]]; then
    echo "Submit from the repository root, not a nested directory" >&2
    return 2
  fi
  if [[ ! -f "${repository_root}/pyproject.toml" || ! -f "${repository_root}/src/kangshield/__init__.py" ]]; then
    echo "SLURM_SUBMIT_DIR is not a KangShield checkout" >&2
    return 2
  fi

  kang_repo_dir=${repository_root}
  kang_python=${KANG_PYTHON:-${kang_repo_dir}/.venv/bin/python}
  kang_runs_dir=${KANG_RUNS_DIR:-${kang_repo_dir}/runs}
  if [[ ! -x "${kang_python}" ]]; then
    echo "KangShield Python is not executable" >&2
    return 2
  fi

  local checkout_status
  if ! checkout_status=$(git -C "${kang_repo_dir}" status --porcelain --untracked-files=normal); then
    echo "Cannot inspect checkout status" >&2
    return 2
  fi
  local checkout_clean=true
  if [[ -n "${checkout_status}" ]]; then
    checkout_clean=false
  fi
  case "${KANG_REQUIRE_CLEAN_CHECKOUT:-1}" in
    0) ;;
    1)
      if [[ "${checkout_clean}" != "true" ]]; then
        echo "Formal Slurm execution requires a clean checkout" >&2
        return 2
      fi
      ;;
    *)
      echo "KANG_REQUIRE_CLEAN_CHECKOUT must be 0 or 1" >&2
      return 2
      ;;
  esac

  cd "${kang_repo_dir}"

  local runs_dir_resolved
  if ! runs_dir_resolved=$(realpath -m -- "${kang_runs_dir}"); then
    echo "Cannot resolve KANG_RUNS_DIR" >&2
    return 2
  fi
  if [[ "${runs_dir_resolved}" == "/" || "${runs_dir_resolved}" == "${kang_repo_dir}" ]]; then
    echo "KANG_RUNS_DIR must be a dedicated run directory" >&2
    return 2
  fi
  install -d -m 700 -- "${runs_dir_resolved}"
  kang_runs_dir=${runs_dir_resolved}

  export PYTHONUNBUFFERED=1
  export PYTHONPATH="${kang_repo_dir}/src${PYTHONPATH:+:${PYTHONPATH}}"
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

  local loaded_package
  if ! loaded_package=$("${kang_python}" -c \
    'from pathlib import Path; import kangshield; print(Path(kangshield.__file__).resolve())'); then
    echo "Cannot import KangShield from the submit checkout" >&2
    return 2
  fi
  if [[ "${loaded_package}" != "$(realpath -- "${kang_repo_dir}/src/kangshield/__init__.py")" ]]; then
    echo "KangShield import did not resolve to the submit checkout" >&2
    return 2
  fi

  kang_code_version=$(git -C "${kang_repo_dir}" rev-parse --short HEAD)
  echo "KangShield Slurm runtime: contract=${kang_slurm_runtime_version} code=${kang_code_version} clean=${checkout_clean} checkout_bound=true owner_only=true"
}

kang_slurm_bind_cudnn9() {
  local cudnn_lib
  if ! cudnn_lib=$("${kang_python}" -c \
    'from pathlib import Path; import nvidia.cudnn; print(Path(next(iter(nvidia.cudnn.__path__))) / "lib")'); then
    echo "Cannot locate the Python cuDNN runtime" >&2
    return 2
  fi
  local cudnn_library=${cudnn_lib}/libcudnn.so.9
  if [[ ! -f "${cudnn_library}" ]]; then
    echo "cuDNN 9 runtime library not found" >&2
    return 2
  fi
  export LD_LIBRARY_PATH="${cudnn_lib}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
  if ! "${kang_python}" - "${cudnn_library}" <<'PY'
import ctypes
import sys

ctypes.CDLL(sys.argv[1])
PY
  then
    echo "cuDNN 9 runtime library is not loadable" >&2
    return 2
  fi
  echo "KangShield Slurm cuDNN: version=9 loadable=true"
}

kang_slurm_verify_onnxruntime_cuda() {
  local provider_library
  if ! provider_library=$("${kang_python}" -c \
    'from pathlib import Path; import onnxruntime as ort; root = Path(ort.__file__).resolve().parent / "capi"; print(root / "libonnxruntime_providers_cuda.so")'); then
    echo "Cannot locate ONNX Runtime" >&2
    return 2
  fi
  if [[ ! -f "${provider_library}" ]]; then
    echo "ONNX Runtime CUDA provider library not found" >&2
    return 2
  fi
  if ! "${kang_python}" - "${provider_library}" <<'PY'
import ctypes
import sys

import onnxruntime as ort

if "CUDAExecutionProvider" not in ort.get_available_providers():
    raise SystemExit("CUDAExecutionProvider is not registered")
ctypes.CDLL(sys.argv[1])
PY
  then
    echo "ONNX Runtime CUDA provider is not loadable" >&2
    return 2
  fi
  echo "KangShield Slurm ONNX Runtime: cuda_registered=true cuda_loadable=true"
}
