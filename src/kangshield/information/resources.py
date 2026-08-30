"""Resolve immutable runtime policies in source and installed layouts."""

from __future__ import annotations

import sys
from pathlib import Path


POLICY_FILENAMES = frozenset(
    {
        "v1-g4-event-candidate-policy.json",
        "v1-g4-fall-features.json",
        "v2-edge-segment-policy.json",
        "v2-multidomain-risk-policy.json",
    }
)


def policy_path(filename: str) -> Path:
    """Return a bundled policy without accepting arbitrary path input."""

    if filename not in POLICY_FILENAMES:
        raise ValueError(f"unknown KangShield policy: {filename}")
    source_checkout = Path(__file__).resolve().parents[3] / "configs" / filename
    installed_data = Path(sys.prefix) / "share" / "kangshield" / "configs" / filename
    for candidate in (source_checkout, installed_data):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"bundled KangShield policy is unavailable: {filename}; reinstall the package"
    )
