from __future__ import annotations

import json
from pathlib import Path

import pytest

from kangshield.information.contracts import EvidenceLevel, SourceType
from kangshield.information.sleep_profile import profile_sleep_export
from kangshield.information.sleep_route import assess_sleep_route


PROJECT_ROOT = Path(__file__).parents[1]
FIXTURE = PROJECT_ROOT / "tests/fixtures/sleep/sdhy1-export.synthetic.json"
POLICY = PROJECT_ROOT / "configs/sleep/v1-sleep-route-policy.json"
EXAMPLE_MAPPING = (
    PROJECT_ROOT / "configs/sleep/sdhy1-field-map.example.json"
)


def _confirmed_mapping(*, fixture_only: bool, evidence_level: str) -> dict:
    return {
        "schema_version": "1.0",
        "fixture_only": fixture_only,
        "evidence_level": evidence_level,
        "device_model": "CS-EP-SDHY1",
        "note": "test mapping",
        "mappings": {
            "heart_rate_bpm": {
                "source_path": "$.records[].heart_rate",
                "confirmed_unit": "bpm",
                "time_source_path": "$.records[].timestamp",
                "time_semantics": "sample timestamp with explicit timezone",
                "value_semantics": "instantaneous device estimate",
                "missing_semantics": "null means missing measurement",
                "status": "confirmed",
            }
        },
    }


def test_synthetic_route_is_fail_closed_and_covers_monitoring_policy():
    profile = profile_sleep_export(FIXTURE)

    report = assess_sleep_route(
        profile=profile,
        policy_path=POLICY,
        mapping_config_path=EXAMPLE_MAPPING,
    )

    by_field = {field.canonical_field: field for field in report.direct_fields}
    assert report.decision == "interface_only_waiting_for_e2_e3_schema"
    assert report.counts["direct_total"] == 9
    assert report.counts["direct_ready"] == 0
    assert report.counts["direct_candidate_unconfirmed"] == 4
    assert report.counts["not_assumed_total"] == 11
    assert report.counts["derived_total"] == 0
    assert report.counts["derived_enabled"] == 0
    assert by_field["heart_rate_bpm"].status == "candidate_unconfirmed"
    assert by_field["measurement_at"].status == "candidate_unconfirmed"
    assert by_field["total_sleep_duration"].status == "not_observed"
    assert all(
        not indicator.calculation_enabled
        for indicator in report.derived_indicators
    )
    assert report.values_persisted is False
    serialized = report.model_dump_json()
    assert "Synthetic Person" not in serialized
    assert "SYNTHETIC-SLEEP-0001" not in serialized


def test_confirmed_mapping_cannot_bypass_fixture_evidence_gate(tmp_path):
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps(_confirmed_mapping(fixture_only=True, evidence_level="E1")),
        encoding="utf-8",
    )
    profile = profile_sleep_export(FIXTURE)

    report = assess_sleep_route(
        profile=profile,
        policy_path=POLICY,
        mapping_config_path=mapping_path,
    )
    heart_rate = next(
        field
        for field in report.direct_fields
        if field.canonical_field == "heart_rate_bpm"
    )

    assert heart_rate.status == "blocked_evidence"
    assert heart_rate.can_standardize is False


def test_e2_confirmed_mapping_only_opens_named_field_adapter_gate(tmp_path):
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps(_confirmed_mapping(fixture_only=False, evidence_level="E2")),
        encoding="utf-8",
    )
    profile = profile_sleep_export(
        FIXTURE,
        evidence_level=EvidenceLevel.E2,
        source_type=SourceType.SDK_EXPORT,
    )

    report = assess_sleep_route(
        profile=profile,
        policy_path=POLICY,
        mapping_config_path=mapping_path,
    )
    ready = [field for field in report.direct_fields if field.can_standardize]

    assert [field.canonical_field for field in ready] == ["heart_rate_bpm"]
    assert report.decision == "confirmed_fields_ready_for_adapter_implementation"
    assert report.counts["direct_ready"] == 1
    assert report.counts["derived_enabled"] == 0
    assert report.values_persisted is False


def test_monitoring_policy_source_digest_is_enforced(tmp_path):
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    policy["source"] = str(FIXTURE)
    policy["source_sha256"] = "0" * 64
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    profile = profile_sleep_export(FIXTURE)

    with pytest.raises(ValueError, match="policy source digest changed"):
        assess_sleep_route(
            profile=profile,
            policy_path=policy_path,
            mapping_config_path=EXAMPLE_MAPPING,
        )
