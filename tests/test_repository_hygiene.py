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
