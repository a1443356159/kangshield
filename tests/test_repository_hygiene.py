from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def test_local_markdown_links_resolve():
    documents = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    missing = []
    for document in documents:
        for match in MARKDOWN_LINK.finditer(document.read_text(encoding="utf-8")):
            target = match.group(1).strip().split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (document.parent / target).resolve().exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert missing == []


def test_public_dataset_freeze_manifest_matches_policies_and_has_no_local_paths():
    path = ROOT / "artifacts/validation/caucafall-policy-freeze.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    bindings = payload["bindings"]
    expected = {
        "edge_selection_policy": ROOT / "configs/v2-edge-segment-policy.json",
        "fall_feature_policy": ROOT / "configs/v1-g4-fall-features.json",
        "fall_candidate_policy": ROOT
        / "configs/v1-g4-event-candidate-policy.json",
    }
    for name, policy_path in expected.items():
        assert bindings[name]["sha256"] == _digest(policy_path)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "/home/" not in serialized
    assert "/cache/" not in serialized
    assert payload["evaluation_contract"]["holdout_media_state_at_freeze"] == (
        "not_cached_or_evaluated"
    )


def test_frozen_public_dataset_reports_match_manifest_and_have_no_private_paths():
    manifest = json.loads(
        (ROOT / "artifacts/validation/caucafall-policy-freeze.json").read_text(
            encoding="utf-8"
        )
    )
    reports = {
        "dev": {
            "filename": "caucafall-dev.json",
            "sha256": "5c5edaaffcb332696f9fb521c8ae0f6dfc1cd09c8a0e701573715138935c70a0",
            "subjects": [1, 2, 3, 4, 5],
            "gate_passed": True,
        },
        "holdout": {
            "filename": "caucafall-holdout.json",
            "sha256": "1a565ed74e41f116e63bd8ddb0689d09269f2a20c2c2314f189a6adb7529bcea",
            "subjects": [6, 7, 8, 9, 10],
            "gate_passed": False,
        },
    }
    forbidden = (
        "/home/",
        "/cache/",
        "device_ref",
        "elder_ref",
        "transcript",
        "local_path",
        "download_url",
    )

    for split, expected in reports.items():
        path = ROOT / "artifacts/validation" / expected["filename"]
        assert _digest(path) == expected["sha256"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        contract = payload["evaluation_contract"]
        assert contract["split"] == split
        assert contract["subjects"] == expected["subjects"]
        assert len(payload["cases"]) == 50
        assert payload["engineering_gate"]["passed"] is expected["gate_passed"]
        assert payload["status"] == "pilot_unvalidated"
        assert payload["execution"] == {
            "login_node_compute_prohibited": True,
            "surface": "slurm_compute_node",
        }
        for policy_name in (
            "edge_selection_policy",
            "fall_feature_policy",
            "fall_candidate_policy",
        ):
            assert payload["bindings"][policy_name] == manifest["bindings"][policy_name]
        assert payload["bindings"]["pose_model"]["model_digest"] == manifest[
            "bindings"
        ]["pose_model"]["sha256"]
        serialized = json.dumps(payload, ensure_ascii=False)
        assert not any(value in serialized for value in forbidden)


def test_historical_public_domain_freeze_remains_immutable():
    path = ROOT / "artifacts/validation/public-domains-policy-freeze.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "multidomain_policy": "0c495432498e355b28f2e73ec0c37e972bcaf4cbf050c726d9a4f3d4a051b800",
        "multidomain_rule_implementation": "ee2b63e639b06e959a9c1f77049809d701309242bbc2a0c51967341de4031cac",
        "public_domain_validator": "2f2685450fd4c2f162523028dcb7690600c487605a084db6b2cac7a2e200e5cd",
        "slurm_runner": "0e3d5f5d6606741876c34ebd928e80c1f16e65660ae508d2c92ede1191a4e50e",
    }
    for name, digest in expected.items():
        assert payload["bindings"][name]["sha256"] == digest
    contract = payload["evaluation_contract"]
    assert contract["holdout_partition_evaluated_at_freeze"] is False
    assert contract["holdout_runs_allowed"] == 1
    assert payload["development_result"]["fraud"]["gate_passed"] is True
    assert (
        payload["development_result"]["mental_wellbeing"]["gate_passed"]
        is True
    )
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "/home/" not in serialized
    assert "/cache/" not in serialized


def test_longitudinal_health_amendment_matches_current_policy_and_code():
    path = ROOT / "artifacts/validation/longitudinal-health-amendment.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "multidomain_policy": ROOT / "configs/v2-multidomain-risk-policy.json",
        "multidomain_rule_implementation": (
            ROOT / "src/kangshield/information/multidomain.py"
        ),
        "longitudinal_health_test": ROOT / "tests/test_longitudinal_health.py",
    }
    for name, source in expected.items():
        assert payload["bindings"][name]["sha256"] == _digest(source)
    assert payload["change"] == {
        "from_policy_revision": "2026-08-31.1",
        "to_policy_revision": "2026-08-31.2",
        "reason": "level_two_streak_must_use_consecutive_calendar_dates",
        "thresholds_changed": False,
        "features_changed": False,
        "public_holdout_rerun": False,
    }
    assert payload["post_fix_observation"]["gapped_level_two_scores"] == [2, 2, 2]
    assert payload["casas_development_regression"]["engineering_gate_passed"] is True
    boundary = payload["evidence_boundary"]
    assert boundary["current_revision_has_new_independent_holdout"] is False
    assert boundary["holdout_not_reused_for_tuning"] is True
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "/home/" not in serialized
    assert "/cache/" not in serialized


def test_frozen_public_domain_reports_match_freeze_and_hide_raw_records():
    manifest = json.loads(
        (ROOT / "artifacts/validation/public-domains-policy-freeze.json").read_text(
            encoding="utf-8"
        )
    )
    reports = {
        "dev": (
            "public-domains-dev.json",
            "265728ef2cea1c4bc8718a5c61fbd633526c0b9206b742fa0bb56599790faf12",
        ),
        "holdout": (
            "public-domains-holdout.json",
            "997e29cff69ae2817647a8fad27b4675e49490c20dcf5cb866a8ffb13ce97b72",
        ),
    }
    forbidden = (
        "/home/",
        "/cache/",
        "device_ref",
        "elder_ref",
        "transcript",
        "local_path",
        "download_url",
    )
    for split, (filename, digest) in reports.items():
        path = ROOT / "artifacts/validation" / filename
        assert _digest(path) == digest
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["evaluation_contract"]["split"] == split
        assert payload["passed"] is True
        assert all(
            gate["passed"] is True
            for gate in payload["engineering_gates"].values()
        )
        assert payload["bindings"]["multidomain_policy"] == manifest["bindings"][
            "multidomain_policy"
        ]
        assert payload["sources"]["fraud"]["archive_sha256"] == manifest[
            "sources"
        ]["fbs_sms"]["archive_sha256"]
        assert payload["sources"]["fraud"]["raw_text_in_report"] is False
        assert (
            payload["sources"]["mental_wellbeing"]["raw_timestamps_in_report"]
            is False
        )
        assert payload["execution"] == {
            "login_node_compute_prohibited": True,
            "surface": "slurm_compute_node",
        }
        serialized = json.dumps(payload, ensure_ascii=False)
        assert not any(value in serialized for value in forbidden)
