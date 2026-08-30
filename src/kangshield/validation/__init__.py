"""Reproducible, product-external validation utilities."""

from .caucafall import (
    CAUCAFALL_DEV_SUBJECTS,
    CAUCAFALL_HOLDOUT_SUBJECTS,
    CaucafallCase,
    aggregate_metrics,
    cases_for_split,
)

__all__ = [
    "CAUCAFALL_DEV_SUBJECTS",
    "CAUCAFALL_HOLDOUT_SUBJECTS",
    "CaucafallCase",
    "aggregate_metrics",
    "cases_for_split",
]
