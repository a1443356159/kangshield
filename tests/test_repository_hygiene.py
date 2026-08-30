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
