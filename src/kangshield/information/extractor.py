from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .contracts import FeatureEvent, Observation


class FeatureExtractor(Protocol):
    """Boundary implemented by future pose, audio and sleep extractors."""

    name: str
    version: str

    def extract(self, observation: Observation) -> Iterable[FeatureEvent]:
        """Extract versioned features without writing storage directly."""
