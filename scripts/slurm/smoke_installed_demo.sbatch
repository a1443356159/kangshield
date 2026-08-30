#!/usr/bin/env bash
#SBATCH --job-name=kangshield-wheel
#SBATCH --partition=hepnodes
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=00:20:00

set -euo pipefail

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    echo "Installed-demo smoke test must run inside a Slurm allocation." >&2
    exit 2
fi

repo_root="${KANGSHIELD_REPO_ROOT:-${SLURM_SUBMIT_DIR:-}}"
if [[ -z "$repo_root" || ! -f "$repo_root/pyproject.toml" ]]; then
    echo "Submit from the KangShield repository or set KANGSHIELD_REPO_ROOT." >&2
    exit 2
fi
if [[ ! -x "$repo_root/.venv/bin/python" ]]; then
    echo "KangShield build environment is unavailable: $repo_root/.venv" >&2
    exit 2
fi

smoke_base="${KANGSHIELD_SMOKE_ROOT:-/cache/DeepLearning/${USER}/kangshield-validation/fresh-install}"
if [[ "$smoke_base" != /cache/* ]]; then
    echo "KANGSHIELD_SMOKE_ROOT must be an explicit /cache path." >&2
    exit 2
fi
wheelhouse="${KANGSHIELD_WHEELHOUSE:-/cache/DeepLearning/${USER}/kangshield-validation/wheelhouse}"
if [[ "$wheelhouse" != /cache/* || ! -d "$wheelhouse" ]]; then
    echo "KANGSHIELD_WHEELHOUSE must name a prepared /cache directory; see README validation steps." >&2
    exit 2
fi
job_root="$smoke_base/job-${SLURM_JOB_ID}"
if [[ -e "$job_root" ]]; then
    echo "Smoke-test directory already exists: $job_root" >&2
    exit 2
fi

mkdir -p "$job_root/wheel" "$job_root/runtime" "$smoke_base/pip-cache"
export PIP_CACHE_DIR="$smoke_base/pip-cache"
export PYTHONUNBUFFERED=1

"$repo_root/.venv/bin/python" -m pip wheel \
    --disable-pip-version-check \
    --no-deps \
    --no-build-isolation \
    --wheel-dir "$job_root/wheel" \
    "$repo_root"

mapfile -t wheels < <(find "$job_root/wheel" -maxdepth 1 -type f -name 'kangshield-*.whl')
if [[ "${#wheels[@]}" -ne 1 ]]; then
    echo "Expected exactly one KangShield wheel, found ${#wheels[@]}." >&2
    exit 1
fi
wheel_path="${wheels[0]}"

python3 -m venv "$job_root/venv"
"$job_root/venv/bin/python" -m pip install \
    --disable-pip-version-check \
    --no-index \
    --find-links "$wheelhouse" \
    --only-binary=:all: \
    --require-hashes \
    --requirement "$repo_root/requirements-demo.lock"
"$job_root/venv/bin/python" -m pip install \
    --disable-pip-version-check \
    --no-index \
    --no-deps \
    "$wheel_path"
"$job_root/venv/bin/python" -m pip check

cd "$job_root/runtime"
port=$((18000 + SLURM_JOB_ID % 1000))
base_url="http://127.0.0.1:${port}"
server_log="$job_root/server.log"
"$job_root/venv/bin/kangshield-info" serve-product \
    --elder-ref demo-install \
    --device-ref demo-install-c6c \
    --host 127.0.0.1 \
    --port "$port" \
    --store-root "$job_root/store" \
    --demo >"$server_log" 2>&1 &
server_pid=$!

cleanup() {
    if kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid"
        wait "$server_pid" || true
    fi
}
trap cleanup EXIT

ready=0
for _ in {1..30}; do
    if curl -fsS "$base_url/api/health" >"$job_root/health.json" 2>/dev/null; then
        ready=1
        break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
        break
    fi
    sleep 1
done
if [[ "$ready" -ne 1 ]]; then
    echo "Installed demo did not become healthy." >&2
    sed -n '1,160p' "$server_log" >&2
    exit 1
fi

curl -fsS "$base_url/api/snapshot" >"$job_root/snapshot.json"
curl -fsS "$base_url/docs" >"$job_root/docs.html"
curl -fsS "$base_url/" >"$job_root/dashboard.html"

"$job_root/venv/bin/kangshield-info" export-product-report \
    --elder-ref demo-install \
    --device-ref demo-install-c6c \
    --visibility owner_only \
    --store-root "$job_root/store" \
    --output "$job_root/owner-report"
"$job_root/venv/bin/kangshield-info" export-product-report \
    --elder-ref demo-install \
    --device-ref demo-install-c6c \
    --visibility public_evidence \
    --store-root "$job_root/store" \
    --output "$job_root/public-report"

"$job_root/venv/bin/python" - "$job_root" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
health = json.loads((root / "health.json").read_text(encoding="utf-8"))
snapshot = json.loads((root / "snapshot.json").read_text(encoding="utf-8"))
assert health["status"] == "ok"
assert health["local_only"] is True
assert health["global_score"] is None
assert snapshot["global_score"] is None
assert {item["domain"] for item in snapshot["assessments"]} == {
    "fall",
    "mental_wellbeing",
    "fraud",
}
assert "服务条款" in (root / "docs.html").read_text(encoding="utf-8")
assert "康盾" in (root / "dashboard.html").read_text(encoding="utf-8")
public_text = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted((root / "public-report").iterdir())
    if path.is_file()
)
for forbidden in (
    "demo-install",
    "demo-install-c6c",
    "transcript_excerpt",
    "owner_note",
    "local_path",
):
    assert forbidden not in public_text
PY

cleanup
trap - EXIT
sha256sum "$wheel_path"
echo "Fresh non-editable wheel demo passed on ${SLURMD_NODENAME:-unknown-node}."
echo "Evidence directory: $job_root"
