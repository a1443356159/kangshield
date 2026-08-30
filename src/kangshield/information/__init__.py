"""KangShield continuous, per-person multidomain risk product."""

from .contracts import (
    DomainCandidate,
    DomainRiskAssessment,
    MultidomainSnapshotReport,
    RiskDomain,
)

__all__ = [
    "DomainCandidate",
    "DomainRiskAssessment",
    "MultidomainSnapshotReport",
    "RiskDomain",
]
