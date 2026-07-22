#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: scripts/slurm/submit.sh <sbatch-script> [sbatch-arguments...]" >&2
  exit 2
fi
for argument in "$@"; do
  case "${argument}" in
    --export|--export=*)
      echo "Do not override --export; pass KANG_* values in the environment" >&2
      exit 2
      ;;
  esac
done

kang_submit_dir=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "Run the Slurm submit wrapper from a Git checkout" >&2
  exit 2
}
kang_submit_dir=$(realpath -- "${kang_submit_dir}")
if [[ "$(realpath -- "${PWD}")" != "${kang_submit_dir}" ]]; then
  echo "Run the Slurm submit wrapper from the repository root" >&2
  exit 2
fi
if [[ ! -f "${kang_submit_dir}/pyproject.toml" || ! -f "${kang_submit_dir}/src/kangshield/__init__.py" ]]; then
  echo "Current checkout is not KangShield" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "Formal Slurm submission requires a clean checkout" >&2
  exit 2
fi

kang_submit_commit=$(git rev-parse HEAD)
exec sbatch \
  --export="ALL,KANG_SUBMIT_COMMIT=${kang_submit_commit}" \
  "$@"
