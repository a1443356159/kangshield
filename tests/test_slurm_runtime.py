from __future__ import annotations

import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SLURM_DIR = PROJECT_ROOT / "scripts" / "slurm"
RUNTIME = SLURM_DIR / "runtime.sh"


def _slurm_environment(
    tmp_path: Path,
    *,
    submit_dir: Path = PROJECT_ROOT,
) -> tuple[dict[str, str], Path, Path]:
    output = tmp_path / "slurm-test-123.out"
    output.write_text("runtime test\n", encoding="utf-8")
    output.chmod(0o644)
    runs_dir = tmp_path / "runs"
    environment = os.environ.copy()
    environment.update(
        {
            "SLURM_SUBMIT_DIR": str(submit_dir),
            "SLURM_JOB_ID": "123",
            "SLURM_JOB_NAME": "kangshield-test",
            "KANG_SLURM_OUTPUT_PATH": str(output),
            "KANG_RUNS_DIR": str(runs_dir),
            "KANG_PYTHON": sys.executable,
            "KANG_REQUIRE_CLEAN_CHECKOUT": "0",
        }
    )
    return environment, output, runs_dir


def test_slurm_runtime_binds_checkout_and_permissions(tmp_path):
    environment, output, runs_dir = _slurm_environment(tmp_path)
    command = (
        f"source {shlex.quote(str(RUNTIME))}; "
        "kang_slurm_init; "
        "printf '%s\\n' \"${kang_repo_dir}\" \"${kang_runs_dir}\""
    )

    completed = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "contract=slurm-runtime-v0.1.0" in completed.stdout
    assert "checkout_bound=true owner_only=true" in completed.stdout
    assert str(PROJECT_ROOT) in completed.stdout
    assert str(runs_dir) in completed.stdout
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert stat.S_IMODE(runs_dir.stat().st_mode) == 0o700


def test_slurm_runtime_rejects_non_repository_submit_dir(tmp_path):
    environment, output, _ = _slurm_environment(tmp_path, submit_dir=tmp_path)

    completed = subprocess.run(
        [
            "bash",
            "-c",
            f"source {shlex.quote(str(RUNTIME))}; kang_slurm_init",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "SLURM_SUBMIT_DIR is not a Git checkout" in completed.stderr
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_slurm_runtime_rejects_invalid_clean_checkout_switch(tmp_path):
    environment, output, _ = _slurm_environment(tmp_path)
    environment["KANG_REQUIRE_CLEAN_CHECKOUT"] = "invalid"

    completed = subprocess.run(
        [
            "bash",
            "-c",
            f"source {shlex.quote(str(RUNTIME))}; kang_slurm_init",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "KANG_REQUIRE_CLEAN_CHECKOUT must be 0 or 1" in completed.stderr
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_slurm_runtime_rejects_dirty_checkout_after_restricting_stdout(
    tmp_path,
):
    repository = tmp_path / "repository"
    package = repository / "src" / "kangshield"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (repository / "pyproject.toml").write_text(
        "[build-system]\nrequires = []\n",
        encoding="utf-8",
    )
    (repository / ".gitignore").write_text(
        "runs/\nslurm-*.out\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "KangShield Test"],
        cwd=repository,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"],
        cwd=repository,
        check=True,
    )
    with (repository / "pyproject.toml").open("a", encoding="utf-8") as stream:
        stream.write("# dirty\n")

    environment, output, _ = _slurm_environment(
        repository,
        submit_dir=repository,
    )
    environment.pop("KANG_REQUIRE_CLEAN_CHECKOUT", None)

    completed = subprocess.run(
        [
            "bash",
            "-c",
            f"source {shlex.quote(str(RUNTIME))}; kang_slurm_init",
        ],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "Formal Slurm execution requires a clean checkout" in completed.stderr
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_sbatch_restricts_stdout_before_required_input_failure(tmp_path):
    environment, output, runs_dir = _slurm_environment(tmp_path)
    environment["SLURM_JOB_NAME"] = "kangshield-m3-speech"
    environment.pop("KANG_DATASET_CASES", None)

    completed = subprocess.run(
        ["bash", str(SLURM_DIR / "v1_m3_speech_comparison.sbatch")],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "KANG_DATASET_CASES" in completed.stderr
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert stat.S_IMODE(runs_dir.stat().st_mode) == 0o700


def test_slurm_runtime_rejects_non_dedicated_runs_directory(tmp_path):
    environment, output, _ = _slurm_environment(tmp_path)
    environment["KANG_RUNS_DIR"] = str(PROJECT_ROOT)

    completed = subprocess.run(
        [
            "bash",
            "-c",
            f"source {shlex.quote(str(RUNTIME))}; kang_slurm_init",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "KANG_RUNS_DIR must be a dedicated run directory" in completed.stderr
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_all_sbatch_entries_use_shared_runtime_contract():
    entries = sorted(SLURM_DIR.glob("*.sbatch"))
    assert len(entries) == 8
    expected_cudnn = {
        "v1_g4_fall_adl_benchmark.sbatch",
        "v1_g4_feature_capture_smoke.sbatch",
        "v1_g4_static_home_benchmark.sbatch",
        "v1_m3_pose_comparison.sbatch",
        "v1_multimodal_smoke.sbatch",
        "v1_runtime_preflight.sbatch",
    }
    expected_onnxruntime = expected_cudnn - {"v1_multimodal_smoke.sbatch"}

    for entry in entries:
        text = entry.read_text(encoding="utf-8")
        assert text.count(
            'source "${SLURM_SUBMIT_DIR}/scripts/slurm/runtime.sh"'
        ) == 1
        assert text.count("kang_slurm_init") == 1
        assert "${SLURM_SUBMIT_DIR:-/home/yyy/kangshield}" not in text
        assert "#SBATCH --output=slurm-%x-%j.out" in text
        assert ("kang_slurm_bind_cudnn9" in text) == (
            entry.name in expected_cudnn
        )
        assert ("kang_slurm_verify_onnxruntime_cuda" in text) == (
            entry.name in expected_onnxruntime
        )

    for script in [RUNTIME, *entries]:
        subprocess.run(["bash", "-n", str(script)], check=True)
