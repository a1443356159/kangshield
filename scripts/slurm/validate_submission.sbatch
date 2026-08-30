#!/usr/bin/env bash
#SBATCH --job-name=kangshield-seal
#SBATCH --partition=hepnodes
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=00:15:00

set -euo pipefail

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    echo "Submission validation must run inside a Slurm allocation." >&2
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

export PYTHONUNBUFFERED=1
cd "$repo_root"

.venv/bin/python -m compileall -q src tests
.venv/bin/python -m pytest -q

bash -n scripts/run_product.sh
bash -n scripts/slurm/benchmark_caucafall.sbatch
bash -n scripts/slurm/benchmark_public_domains.sbatch
bash -n scripts/slurm/smoke_installed_demo.sbatch
bash -n scripts/slurm/validate_submission.sbatch
git diff --check

tracked_assets="$(
    git ls-files | rg -i \
        '(^|/)(data|models|runs|logs|secrets)/|\.(mp4|mkv|avi|mov|wav|mp3|flac|pt|pth|onnx|sqlite|sqlite3|db)$' \
        || true
)"
if [[ -n "$tracked_assets" ]]; then
    echo "Tracked private or large assets:" >&2
    echo "$tracked_assets" >&2
    exit 1
fi

scan_roots=(README.md docs configs src tests scripts deploy artifacts)
if rg -n --fixed-strings "/home/${USER}" "${scan_roots[@]}"; then
    echo "User-specific home path found in submission." >&2
    exit 1
fi
if rg -n --fixed-strings "/cache/DeepLearning/${USER}" "${scan_roots[@]}"; then
    echo "User-specific cache path found in submission." >&2
    exit 1
fi
if rg -n 'YS7_APP_(KEY|SECRET)=[[:alnum:]_-]{12,}|KANG_DEVICE_SERIAL=[[:alnum:]_-]{6,}' \
    "${scan_roots[@]}"; then
    echo "Credential-like literal found in submission." >&2
    exit 1
fi

echo "KangShield submission validation passed on ${SLURMD_NODENAME:-unknown-node}."
