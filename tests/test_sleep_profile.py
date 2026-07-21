from __future__ import annotations

import json
from pathlib import Path

import pytest

from kangshield.information.contracts import EvidenceLevel, SourceType
from kangshield.information.sleep_profile import profile_sleep_export


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "sleep"
    / "sdnl1-export.synthetic.json"
)


def test_sleep_profile_discovers_fields_without_persisting_values():
    report = profile_sleep_export(
        FIXTURE,
        evidence_level=EvidenceLevel.E1,
        source_type=SourceType.FIXTURE,
    )
    serialized = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)

    assert report.record_count == 2
    assert report.container_path == "$.records"
    assert any(field.path == "heart_rate" for field in report.fields)
    assert any(
        candidate.canonical_field == "heart_rate_bpm"
        and candidate.source_path == "heart_rate"
        for candidate in report.mapping_candidates
    )
    assert "Synthetic Person" not in serialized
    assert "SYNTHETIC-SLEEP-0001" not in serialized
    assert "values_persisted_in_report" in serialized


def test_sleep_profile_supports_csv(tmp_path):
    path = tmp_path / "sleep.csv"
    path.write_text(
        "timestamp,heart_rate,respiratory_rate,in_bed\n"
        "2026-07-21T22:00:00+08:00,68,15,true\n",
        encoding="utf-8",
    )

    report = profile_sleep_export(path)

    assert report.record_count == 1
    assert report.asset.metadata["container_type"] == "csv"
    assert {item.canonical_field for item in report.mapping_candidates} >= {
        "heart_rate_bpm",
        "respiratory_rate_bpm",
        "bed_presence",
    }


def test_fixture_cannot_claim_live_evidence():
    with pytest.raises(ValueError, match="at most E1"):
        profile_sleep_export(
            FIXTURE,
            evidence_level=EvidenceLevel.E3,
            source_type=SourceType.FIXTURE,
        )
