from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from kangshield.information.cli import build_parser, main
from kangshield.information.distribution_readiness import (
    assess_distribution_readiness,
    distribution_policy_asset,
)
from kangshield.information.privacy import sha256_file


PROJECT_ROOT = Path(__file__).parents[1]
POLICY = PROJECT_ROOT / "configs" / "v1-r1-distribution-readiness.json"


def _load_policy() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_current_distribution_policy_is_complete_and_fail_closed():
    report = assess_distribution_readiness(
        policy_path=POLICY,
        repository_root=PROJECT_ROOT,
    )

    assert report.submission_bundle_ready is False
    assert report.decision == "blocked_pending_distribution_review"
    assert report.counts == {
        "source_total": 8,
        "source_matched": 8,
        "source_missing_or_drifted": 0,
        "required_file_total": 3,
        "required_file_present": 0,
        "required_file_missing": 3,
        "required_file_matched": 0,
        "required_file_unbound_or_drifted": 0,
        "decision_total": 5,
        "decision_confirmed": 0,
        "decision_open": 5,
        "asset_total": 13,
        "asset_include": 2,
        "asset_exclude": 7,
        "asset_undecided": 4,
        "asset_blocking": 6,
        "gate_total": 5,
        "gate_ready": 0,
    }
    assert {item.relative_path for item in report.required_files if item.status == "missing"} == {
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "requirements/competition.lock",
    }
    assert all(check.status == "matched" for check in report.source_checks)
    assert all(not gate.ready for gate in report.readiness_gates)
    assets = {asset.asset_id: asset for asset in report.assets}
    assert assets["ultralytics-runtime"].blocking is False
    assert assets["yolo26n-pose-weight"].bundle_action == "exclude"
    assert assets["yolox-m-humanart-weight"].blocking is True
    assert assets["rtmpose-m-humanart-weight"].blocking is True
    assert assets["torchvision-keypointrcnn-coco-v1-weight"].blocking is True
    assert assets["funasr-mandarin-model-stack"].blocking is True
    assert assets["whisper-small-weight"].blocking is False
    assert all(
        not asset.blocking
        for asset in report.assets
        if asset.category == "evaluation_dataset"
    )
    assert report.legal_advice_provided is False
    assert report.risk_assessment_emitted is False
    assert report.alert_emitted is False
    serialized = report.model_dump_json()
    assert str(PROJECT_ROOT) not in serialized
    assert "models/yolo26n-pose.pt" not in serialized


def test_distribution_source_digest_drift_blocks_readiness(tmp_path):
    payload = _load_policy()
    payload["source_bindings"][0]["sha256"] = "0" * 64
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(payload), encoding="utf-8")

    report = assess_distribution_readiness(
        policy_path=policy,
        repository_root=PROJECT_ROOT,
    )

    check = report.source_checks[0]
    assert check.relative_path == "pyproject.toml"
    assert check.status == "digest_mismatch"
    assert report.counts["source_missing_or_drifted"] == 1
    assert "source:pyproject.toml:digest_mismatch" in report.blocking_reasons
    assert report.submission_bundle_ready is False


def test_distribution_policy_rejects_incomplete_asset_coverage(tmp_path):
    payload = _load_policy()
    payload["source_bindings"][0]["covered_asset_ids"].remove(
        "kangshield-project-code"
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="schema validation failed"):
        assess_distribution_readiness(
            policy_path=policy,
            repository_root=PROJECT_ROOT,
        )


def test_distribution_policy_can_open_after_every_input_is_confirmed(tmp_path):
    repository = tmp_path / "repository"
    (repository / "src" / "kangshield").mkdir(parents=True)
    (repository / "requirements").mkdir()
    (repository / "src" / "kangshield" / "__init__.py").write_text(
        "", encoding="utf-8"
    )
    (repository / "pyproject.toml").write_text(
        "[project]\nname='fixture'\n", encoding="utf-8"
    )
    (repository / "LICENSE").write_text("fixture license\n", encoding="utf-8")
    (repository / "THIRD_PARTY_NOTICES.md").write_text(
        "fixture notices\n", encoding="utf-8"
    )
    (repository / "requirements" / "competition.lock").write_text(
        "fixture==1\n", encoding="utf-8"
    )
    evidence = repository / "asset-evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    payload = {
        "schema_version": "1.0",
        "policy_id": "ready-fixture",
        "policy_version": "distribution-readiness-v0.1.0",
        "profile_id": "ready-fixture-profile",
        "reviewed_on": "2026-07-23",
        "legal_review_required": True,
        "source_bindings": [
            {
                "relative_path": "asset-evidence.json",
                "sha256": sha256_file(evidence),
                "covered_asset_ids": ["fixture-asset"],
            }
        ],
        "required_files": [
            {
                "file_id": "license",
                "relative_path": "LICENSE",
                "purpose": "fixture",
                "required_for_ready": True,
                "expected_sha256": sha256_file(repository / "LICENSE"),
            },
            {
                "file_id": "notices",
                "relative_path": "THIRD_PARTY_NOTICES.md",
                "purpose": "fixture",
                "required_for_ready": True,
                "expected_sha256": sha256_file(
                    repository / "THIRD_PARTY_NOTICES.md"
                ),
            },
            {
                "file_id": "lock",
                "relative_path": "requirements/competition.lock",
                "purpose": "fixture",
                "required_for_ready": True,
                "expected_sha256": sha256_file(
                    repository / "requirements" / "competition.lock"
                ),
            },
        ],
        "decisions": [
            {
                "decision_id": "owner-decision",
                "status": "confirmed",
                "value": "approved",
                "evidence_ref": "review-001",
                "owner_role": "fixture-owner",
                "required_for_ready": True,
            }
        ],
        "assets": [
            {
                "asset_id": "fixture-asset",
                "category": "project_code",
                "name": "Fixture",
                "version_or_revision": "1",
                "bundle_action": "include",
                "clearance_status": "cleared_with_obligations",
                "license_expression": "MIT",
                "license_sources": ["https://example.invalid/license"],
                "obligations": ["retain_notice"],
                "open_requirements": [],
                "limitations": [],
            }
        ],
        "readiness_gates": [
            {
                "gate_id": "ready",
                "required_file_ids": ["license", "notices", "lock"],
                "required_decision_ids": ["owner-decision"],
                "required_asset_ids": ["fixture-asset"],
            }
        ],
        "limitations": ["fixture_only"],
    }
    policy = repository / "policy.json"
    policy.write_text(json.dumps(payload), encoding="utf-8")

    report = assess_distribution_readiness(
        policy_path=policy,
        repository_root=repository,
    )

    assert report.submission_bundle_ready is True
    assert report.decision == "submission_bundle_ready"
    assert report.blocking_reasons == []
    assert report.counts["gate_ready"] == 1
    assert report.readiness_gates[0].ready is True

    evidence.write_text('{"changed": true}\n', encoding="utf-8")
    drifted = assess_distribution_readiness(
        policy_path=policy,
        repository_root=repository,
    )
    assert drifted.submission_bundle_ready is False
    assert drifted.source_checks[0].status == "digest_mismatch"
    assert drifted.assets[0].source_evidence_ready is False
    assert drifted.assets[0].blocking is True
    assert drifted.readiness_gates[0].ready is False


def test_distribution_policy_asset_is_aggregate_and_path_opaque():
    asset = distribution_policy_asset(POLICY)

    assert asset.privacy_level.value == "aggregate"
    assert asset.evidence_level.value == "E1"
    assert asset.source_type.value == "local_file"
    assert str(PROJECT_ROOT) not in asset.uri
    assert POLICY.name not in asset.uri


def test_distribution_cli_writes_owner_only_completed_run(tmp_path, capsys):
    runs = tmp_path / "runs"
    exit_code = main(
        [
            "assess-distribution-readiness",
            "--policy",
            str(POLICY),
            "--repository-root",
            str(PROJECT_ROOT),
            "--runs-dir",
            str(runs),
        ]
    )
    output = json.loads(capsys.readouterr().out)
    run_dir = Path(output["run_dir"])
    manifest = json.loads(
        (run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (run_dir / "reports" / "distribution-readiness.json").read_text(
            encoding="utf-8"
        )
    )

    assert exit_code == 0
    assert output["submission_bundle_ready"] is False
    assert output["source_matched"] == 8
    assert output["source_total"] == 8
    assert output["required_file_missing"] == 3
    assert output["decision_open"] == 5
    assert output["asset_blocking"] == 6
    assert manifest["status"] == "completed"
    assert manifest["stage"] == "v1-r1-distribution-readiness"
    assert manifest["configuration"]["policy_path_persisted"] is False
    assert manifest["configuration"]["repository_root_persisted"] is False
    assert report["submission_bundle_ready"] is False
    assert stat.S_IMODE(runs.stat().st_mode) == 0o700
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((run_dir / "manifest.json").stat().st_mode) == 0o600
    assert (
        stat.S_IMODE(
            (run_dir / "reports" / "distribution-readiness.json").stat().st_mode
        )
        == 0o600
    )
    serialized = json.dumps(manifest)
    assert str(POLICY) not in serialized
    assert str(PROJECT_ROOT) not in serialized


def test_distribution_cli_require_ready_returns_two_but_keeps_completed_run(
    tmp_path,
    capsys,
):
    exit_code = main(
        [
            "assess-distribution-readiness",
            "--policy",
            str(POLICY),
            "--repository-root",
            str(PROJECT_ROOT),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--require-ready",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    manifest = json.loads(
        Path(output["manifest"]).read_text(encoding="utf-8")
    )

    assert exit_code == 2
    assert output["submission_bundle_ready"] is False
    assert manifest["status"] == "completed"
    assert manifest["configuration"]["require_ready"] is True


def test_distribution_parser_defaults_to_frozen_policy_and_fail_closed_gate():
    args = build_parser().parse_args(["assess-distribution-readiness"])

    assert args.policy.name == "v1-r1-distribution-readiness.json"
    assert args.repository_root == Path(".")
    assert args.require_ready is False
