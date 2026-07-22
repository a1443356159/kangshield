from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from kangshield.information.cli import build_parser, main
from kangshield.information.privacy import sha256_file
from kangshield.information.runtime_closure import (
    RuntimeInventory,
    RuntimePackage,
    RuntimeRequirement,
    RuntimeTarget,
    assess_runtime_closure,
    runtime_inventory_asset,
    sanitize_pip_inspect,
)


PROJECT_ROOT = Path(__file__).parents[1]
CURRENT_PROFILE = (
    PROJECT_ROOT / "configs" / "v1-r1-runtime-profile-rtmpose-funasr.json"
)
TARGET = RuntimeTarget(
    python_full_version="3.13.13",
    implementation_name="cpython",
    platform_system="Linux",
    platform_machine="x86_64",
    sys_platform="linux",
    os_name="posix",
)


def _package(
    name: str,
    version: str,
    *,
    requirements: list[RuntimeRequirement] | None = None,
    license_status: str = "spdx_expression_present",
    direct_url_reference: bool = False,
    editable_install: bool = False,
) -> RuntimePackage:
    return RuntimePackage(
        name=name,
        version=version,
        installer="pip",
        requested=False,
        direct_url_reference=direct_url_reference,
        editable_install=editable_install,
        requirements=requirements or [],
        license_metadata_status=license_status,
        license_expression="MIT" if license_status == "spdx_expression_present" else None,
    )


def _inventory(packages: list[RuntimePackage]) -> RuntimeInventory:
    return RuntimeInventory(
        python_full_version=TARGET.python_full_version,
        implementation_name=TARGET.implementation_name,
        platform_system=TARGET.platform_system,
        platform_machine=TARGET.platform_machine,
        sys_platform=TARGET.sys_platform,
        os_name=TARGET.os_name,
        pip_version="26.0.1",
        packages=sorted(packages, key=lambda item: item.name),
    )


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    (repository / "src" / "kangshield").mkdir(parents=True)
    (repository / "src" / "kangshield" / "__init__.py").write_text(
        "", encoding="utf-8"
    )
    (repository / "pyproject.toml").write_text(
        "[project]\nname='fixture'\nversion='1.0'\n",
        encoding="utf-8",
    )
    return repository


def _profile(
    repository: Path,
    *,
    direct_requirement: str = "fixture-app[gpu]==1.0",
) -> Path:
    payload = {
        "schema_version": "1.0",
        "profile_id": "fixture-runtime-profile",
        "profile_version": "runtime-closure-v0.1.0",
        "status": "candidate_not_release",
        "reviewed_on": "2026-07-23",
        "target": TARGET.model_dump(mode="json"),
        "repository_sources": [
            {
                "relative_path": "pyproject.toml",
                "sha256": sha256_file(repository / "pyproject.toml"),
            }
        ],
        "direct_requirements": [
            {
                "requirement": direct_requirement,
                "purpose": "fixture runtime root",
            }
        ],
        "prohibited_closure_packages": ["blocked-package"],
        "allowed_bootstrap_packages": ["pip"],
        "allowed_direct_url_packages": [],
        "prohibit_editable_installs": True,
        "prohibit_pythonpath": True,
        "require_isolated_environment": True,
        "require_license_metadata": True,
        "final_lock_emission_authorized": False,
        "limitations": ["fixture_only"],
    }
    path = repository / "runtime-profile.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _ready_inventory() -> RuntimeInventory:
    return _inventory(
        [
            _package(
                "fixture-app",
                "1.0",
                requirements=[
                    RuntimeRequirement(name="fixture-dep", specifier=">=2"),
                    RuntimeRequirement(
                        name="fixture-gpu",
                        specifier="==3",
                        marker='extra == "gpu"',
                    ),
                    RuntimeRequirement(
                        name="windows-only",
                        marker='sys_platform == "win32"',
                    ),
                ],
            ),
            _package("fixture-dep", "2.1"),
            _package("fixture-gpu", "3.0"),
            _package("pip", "26.0.1"),
        ]
    )


def test_runtime_closure_can_open_for_an_isolated_resolved_fixture(tmp_path):
    repository = _repository(tmp_path)
    profile = _profile(repository)

    report = assess_runtime_closure(
        profile_path=profile,
        repository_root=repository,
        inventory=_ready_inventory(),
    )

    assert report.closure_snapshot_ready is True
    assert report.decision == "candidate_closure_snapshot_ready"
    assert report.blocking_reasons == []
    assert report.counts == {
        "installed_total": 4,
        "direct_total": 1,
        "direct_matched": 1,
        "closure_package_total": 3,
        "dependency_issue_total": 0,
        "prohibited_in_closure_total": 0,
        "prohibited_installed_outside_closure_total": 0,
        "extraneous_installed_total": 0,
        "license_metadata_missing_total": 0,
        "installation_provenance_violation_total": 0,
        "gate_total": 8,
        "gate_ready": 8,
    }
    assert {item.name for item in report.closure_packages} == {
        "fixture-app",
        "fixture-dep",
        "fixture-gpu",
    }
    assert "windows-only" not in {
        item.name for item in report.closure_packages
    }
    assert report.competition_lock_emitted is False
    assert report.third_party_notice_emitted is False
    assert report.legal_advice_provided is False


def test_runtime_closure_fails_closed_on_each_readiness_family(tmp_path):
    repository = _repository(tmp_path)
    profile = _profile(repository, direct_requirement="fixture-app==1.0")
    inventory = _inventory(
        [
            _package(
                "fixture-app",
                "0.9",
                requirements=[
                    RuntimeRequirement(name="missing-dep", specifier=">=1"),
                    RuntimeRequirement(name="blocked-package"),
                ],
                direct_url_reference=True,
                editable_install=True,
            ),
            _package(
                "blocked-package",
                "1.0",
                license_status="missing",
            ),
            _package("unrelated", "1.0"),
            _package("pip", "26.0.1"),
        ]
    )
    inventory.python_full_version = "3.12.9"
    inventory.pythonpath_configured = True
    (repository / "pyproject.toml").write_text(
        "[project]\nname='drifted'\n", encoding="utf-8"
    )

    report = assess_runtime_closure(
        profile_path=profile,
        repository_root=repository,
        inventory=inventory,
    )

    assert report.closure_snapshot_ready is False
    assert report.decision == "blocked_runtime_closure_review"
    assert report.target.ready is False
    assert report.source_checks[0].status == "digest_mismatch"
    assert report.direct_requirements[0].status == "version_mismatch"
    assert any(item.issue == "missing" for item in report.dependency_issues)
    assert report.prohibited_in_closure == ["blocked-package"]
    assert report.extraneous_installed_packages == ["unrelated"]
    assert "runtime:pythonpath_configured" in (
        report.installation_provenance_violations
    )
    assert "fixture-app:editable_install" in (
        report.installation_provenance_violations
    )
    assert report.counts["license_metadata_missing_total"] == 1
    assert all(not item.ready for item in report.gates)


def test_runtime_closure_tracks_requested_extras_transitively(tmp_path):
    repository = _repository(tmp_path)
    profile = _profile(repository)
    inventory = _ready_inventory()
    inventory.packages = [
        item for item in inventory.packages if item.name != "fixture-gpu"
    ]

    report = assess_runtime_closure(
        profile_path=profile,
        repository_root=repository,
        inventory=inventory,
    )

    assert any(
        item.parent_package == "fixture-app"
        and item.dependency_name == "fixture-gpu"
        and item.issue == "missing"
        for item in report.dependency_issues
    )
    assert next(
        item
        for item in report.gates
        if item.gate_id == "dependency-closure-ready"
    ).ready is False


def test_sanitized_pip_inspect_removes_paths_urls_and_license_text():
    payload = {
        "version": "1",
        "pip_version": "26.0.1",
        "installed": [
            {
                "metadata": {
                    "name": "Secret_Package",
                    "version": "1.0",
                    "license": "private license text",
                    "requires_dist": [
                        "Dependency @ file:///home/private/wheel.whl"
                    ],
                },
                "metadata_location": "/home/private/site-packages/secret.dist-info",
                "direct_url": {"url": "file:///home/private/source"},
                "installer": "pip",
                "requested": True,
            }
        ],
    }

    inventory = sanitize_pip_inspect(payload, runtime=TARGET)
    serialized = inventory.model_dump_json()
    package = inventory.packages[0]

    assert package.name == "secret-package"
    assert package.requirements[0].name == "dependency"
    assert package.requirements[0].url_reference is True
    assert package.direct_url_reference is True
    assert package.editable_install is False
    assert package.legacy_license_value_sha256 is not None
    assert "/home/private" not in serialized
    assert "file:" not in serialized
    assert "private license text" not in serialized
    assert inventory.local_paths_persisted is False
    assert inventory.dependency_urls_persisted is False
    assert inventory.pythonpath_configured is False
    asset = runtime_inventory_asset(inventory)
    assert asset.source_type.value == "runtime_snapshot"
    assert asset.privacy_level.value == "aggregate"
    assert "/home/" not in asset.model_dump_json()


@pytest.mark.parametrize(
    "requirement",
    [
        "fixture @ https://example.invalid/fixture.whl",
        'fixture==1; python_version >= "3.11"',
        "fixture",
    ],
)
def test_runtime_profile_rejects_unfrozen_direct_requirements(
    tmp_path,
    requirement,
):
    repository = _repository(tmp_path)
    profile = _profile(repository, direct_requirement=requirement)

    with pytest.raises(ValueError, match="schema validation failed"):
        assess_runtime_closure(
            profile_path=profile,
            repository_root=repository,
            inventory=_ready_inventory(),
        )


def test_current_runtime_profile_is_source_bound_and_candidate_only():
    empty_inventory = _inventory([])

    report = assess_runtime_closure(
        profile_path=CURRENT_PROFILE,
        repository_root=PROJECT_ROOT,
        inventory=empty_inventory,
    )

    assert report.profile_id == "v1-r1-l40-rtmpose-funasr-candidate"
    assert report.profile_status == "candidate_not_release"
    assert report.source_checks[0].status == "matched"
    assert report.counts["direct_total"] == 8
    assert report.counts["direct_matched"] == 0
    assert report.closure_snapshot_ready is False
    assert report.competition_lock_emitted is False


def test_runtime_closure_cli_replays_sanitized_owner_only_snapshot(
    tmp_path,
    capsys,
):
    repository = _repository(tmp_path)
    profile = _profile(repository)
    inventory = _ready_inventory()
    inventory.packages.append(_package("unrelated", "1.0"))
    inventory.packages.sort(key=lambda item: item.name)
    snapshot = tmp_path / "runtime-inventory.json"
    snapshot.write_text(
        inventory.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    runs = tmp_path / "runs"

    exit_code = main(
        [
            "assess-runtime-closure",
            "--profile",
            str(profile),
            "--snapshot",
            str(snapshot),
            "--repository-root",
            str(repository),
            "--runs-dir",
            str(runs),
            "--require-ready",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    run_dir = Path(output["run_dir"])
    manifest = json.loads(
        (run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assets = [
        json.loads(line)
        for line in (run_dir / "source_assets.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert exit_code == 2
    assert output["closure_snapshot_ready"] is False
    assert manifest["status"] == "completed"
    assert manifest["stage"] == "v1-r1-runtime-closure"
    assert manifest["configuration"]["profile_path_persisted"] is False
    assert manifest["configuration"]["snapshot_path_persisted"] is False
    assert manifest["configuration"]["repository_root_persisted"] is False
    assert manifest["configuration"]["final_lock_emission_authorized"] is False
    assert {item["source_type"] for item in assets} == {
        "local_file",
        "runtime_snapshot",
    }
    assert stat.S_IMODE(runs.stat().st_mode) == 0o700
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((run_dir / "manifest.json").stat().st_mode) == 0o600
    assert (
        stat.S_IMODE(
            (run_dir / "reports" / "runtime-inventory.json").stat().st_mode
        )
        == 0o600
    )
    serialized = json.dumps(manifest)
    assert str(profile) not in serialized
    assert str(snapshot) not in serialized
    assert str(repository) not in serialized


def test_runtime_closure_parser_defaults_to_candidate_profile():
    args = build_parser().parse_args(["assess-runtime-closure"])

    assert args.profile.name == "v1-r1-runtime-profile-rtmpose-funasr.json"
    assert args.snapshot is None
    assert args.repository_root == Path(".")
    assert args.require_ready is False
