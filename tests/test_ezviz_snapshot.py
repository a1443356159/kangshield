from __future__ import annotations

import json
from pathlib import Path

from kangshield.information.contracts import EvidenceLevel
from kangshield.information.ezviz_snapshot import inspect_ezviz_snapshot


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "ezviz"
    / "device-list.synthetic.json"
)


def test_ezviz_snapshot_finds_models_and_redacts_secrets(monkeypatch):
    monkeypatch.setenv("KANGSHIELD_REF_SALT", "test-only-salt")

    report = inspect_ezviz_snapshot(FIXTURE, evidence_level=EvidenceLevel.E1)
    serialized = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)

    assert len(report.devices) == 2
    assert report.target_models_found == [
        "CS-C6c-V101-1J4WF",
        "CS-EP-SDHY1",
    ]
    assert report.checklist["live_preview"] == "requires_functional_test"
    assert report.sensitive_keys_redacted >= 5
    assert "SYNTHETIC_TOKEN_MUST_BE_REDACTED" not in serialized
    assert "SYNTHETIC-C6C-0001" not in serialized
    assert "Synthetic living room camera" not in serialized
    assert not any(issue.code == "unsalted_device_ref" for issue in report.issues)


def test_ezviz_snapshot_warns_when_ref_salt_is_missing(monkeypatch):
    monkeypatch.delenv("KANGSHIELD_REF_SALT", raising=False)

    report = inspect_ezviz_snapshot(FIXTURE)

    assert any(issue.code == "unsalted_device_ref" for issue in report.issues)
    assert any(issue.code == "fixture_not_device_evidence" for issue in report.issues)
