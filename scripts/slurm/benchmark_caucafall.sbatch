#!/usr/bin/env bash
#SBATCH --job-name=kangshield-cauca
#SBATCH --partition=hepnodes
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:45:00

set -euo pipefail

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    echo "This benchmark must run inside a Slurm allocation." >&2
    exit 2
fi

repo_root="${KANGSHIELD_REPO_ROOT:-${SLURM_SUBMIT_DIR:-}}"
if [[ -z "$repo_root" || ! -f "$repo_root/pyproject.toml" ]]; then
    echo "Submit from the KangShield repository or set KANGSHIELD_REPO_ROOT." >&2
    exit 2
fi
if [[ ! -x "$repo_root/.venv/bin/python" ]]; then
    echo "KangShield virtual environment is unavailable: $repo_root/.venv" >&2
    exit 2
fi

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export PYTHONUNBUFFERED=1

cd "$repo_root"
exec .venv/bin/python scripts/benchmark_caucafall.py "$@"
