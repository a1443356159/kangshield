from __future__ import annotations

import json
import stat

from kangshield.information.artifacts import RunArtifacts
from kangshield.information.contracts import EvidenceLevel, RunStatus, StepStatus


def test_run_artifacts_complete_and_record_step(tmp_path):
    with RunArtifacts(
        tmp_path / "runs",
        stage="test-stage",
        evidence_level=EvidenceLevel.E1,
        configuration={"fixture": True},
        project_dir=tmp_path,
    ) as run:
        with run.step("first-step") as step:
            report = run.write_report("result.json", {"ok": True})
            step.outputs.append(run.relative(report))
        run.log_event({"event": "permission-check"})

    manifest = json.loads(run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == RunStatus.COMPLETED.value
    assert manifest["steps"][0]["status"] == StepStatus.COMPLETED.value
    assert manifest["steps"][0]["outputs"] == ["reports/result.json"]
    assert manifest["artifacts"] == ["reports/result.json"]
    assert stat.S_IMODE(run.runs_dir.stat().st_mode) == 0o700
    for directory in (
        run.run_dir,
        run.reports_dir,
        run.logs_dir,
        run.artifacts_dir,
    ):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for path in (run.manifest_path, report, run.logs_dir / "events.jsonl"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_run_artifacts_mark_failed_on_exception(tmp_path):
    try:
        with RunArtifacts(
            tmp_path / "runs",
            stage="test-failure",
            evidence_level=EvidenceLevel.E1,
            project_dir=tmp_path,
        ) as run:
            with run.step("broken-step"):
                raise RuntimeError("synthetic failure")
    except RuntimeError:
        pass

    manifest = json.loads(run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == RunStatus.FAILED.value
    assert manifest["steps"][0]["status"] == StepStatus.FAILED.value
    assert manifest["issues"][0]["code"] == "step_failed"
