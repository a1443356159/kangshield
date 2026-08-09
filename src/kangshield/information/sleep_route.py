from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import (
    EVIDENCE_RANK,
    EvidenceLevel,
    QualityIssue,
    Severity,
    SleepDerivedRouteAssessment,
    SleepFieldRouteAssessment,
    SleepProfileReport,
    SleepRouteAssessmentReport,
    SourceType,
)
from .privacy import sha256_file


ROUTE_VERSION = "sleep-route-assessment-v0.1.0"
ConfigModel = TypeVar("ConfigModel", bound=BaseModel)


class _StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _DirectFieldPolicy(_StrictConfigModel):
    canonical_field: str
    monitoring_indicators: list[str]
    priority: str
    route: Literal["direct_if_exposed"]
    expected_units: list[str]
    required_confirmations: list[str]


class _DerivedIndicatorPolicy(_StrictConfigModel):
    indicator_id: str
    monitoring_indicators: list[str]
    required_canonical_fields: list[str]
    minimum_nights: int = Field(ge=1)
    limitations: list[str] = Field(default_factory=list)


class _NotAssumedFieldPolicy(_StrictConfigModel):
    canonical_field: str
    monitoring_indicators: list[str]
    priority: str
    reason: str


class _SleepRoutePolicy(_StrictConfigModel):
    schema_version: Literal["1.0"]
    policy_version: str
    device_model: str
    source: str
    source_sha256: str = Field(min_length=64, max_length=64)
    direct_fields: list[_DirectFieldPolicy]
    derived_indicators: list[_DerivedIndicatorPolicy]
    not_assumed_fields: list[_NotAssumedFieldPolicy]
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_fields(self) -> "_SleepRoutePolicy":
        direct = [field.canonical_field for field in self.direct_fields]
        not_assumed = [field.canonical_field for field in self.not_assumed_fields]
        derived = [field.indicator_id for field in self.derived_indicators]
        if len(direct) != len(set(direct)):
            raise ValueError("sleep route policy contains duplicate direct fields")
        if len(not_assumed) != len(set(not_assumed)):
            raise ValueError("sleep route policy contains duplicate not-assumed fields")
        if set(direct) & set(not_assumed):
            raise ValueError("direct and not-assumed sleep fields must be disjoint")
        if len(derived) != len(set(derived)):
            raise ValueError("sleep route policy contains duplicate derived indicators")
        unknown_requirements = sorted(
            {
                requirement
                for indicator in self.derived_indicators
                for requirement in indicator.required_canonical_fields
            }
            - set(direct)
        )
        if unknown_requirements:
            raise ValueError(
                "derived sleep indicators reference unknown direct fields: "
                + ", ".join(unknown_requirements)
            )
        return self


class _MappingEntry(_StrictConfigModel):
    source_path: str
    confirmed_unit: str | None = None
    time_source_path: str | None = None
    time_semantics: str | None = None
    value_semantics: str | None = None
    missing_semantics: str | None = None
    status: Literal["candidate", "confirmed", "rejected"]


class _SleepMappingConfig(_StrictConfigModel):
    schema_version: Literal["1.0"]
    fixture_only: bool
    evidence_level: EvidenceLevel
    device_model: str
    note: str
    mappings: dict[str, _MappingEntry]


def _load_config(path: Path, model: type[ConfigModel]) -> ConfigModel:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON config: {path}") from error
    return model.model_validate(payload)


def _full_field_path(profile: SleepProfileReport, relative_path: str) -> str:
    if profile.container_path == "$":
        return f"$.{relative_path}"
    return f"{profile.container_path}[].{relative_path}"


def _profile_paths(profile: SleepProfileReport) -> set[str]:
    return {_full_field_path(profile, field.path) for field in profile.fields}


def _automatic_candidates(
    profile: SleepProfileReport,
) -> dict[str, list[str]]:
    candidates: dict[str, list[str]] = defaultdict(list)
    for candidate in profile.mapping_candidates:
        candidates[candidate.canonical_field].append(
            _full_field_path(profile, candidate.source_path)
        )
    return {
        field: sorted(set(paths))
        for field, paths in candidates.items()
    }


def _is_present(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _missing_confirmations(
    policy: _DirectFieldPolicy,
    mapping: _MappingEntry,
) -> list[str]:
    payload = mapping.model_dump()
    return sorted(
        name
        for name in policy.required_confirmations
        if not _is_present(payload.get(name))
    )


def _evidence_allows_confirmation(
    profile: SleepProfileReport,
    mapping_config: _SleepMappingConfig,
) -> bool:
    return (
        not mapping_config.fixture_only
        and profile.asset.source_type != SourceType.FIXTURE
        and EVIDENCE_RANK[profile.asset.evidence_level]
        >= EVIDENCE_RANK[EvidenceLevel.E2]
        and EVIDENCE_RANK[mapping_config.evidence_level]
        >= EVIDENCE_RANK[EvidenceLevel.E2]
        and EVIDENCE_RANK[mapping_config.evidence_level]
        <= EVIDENCE_RANK[profile.asset.evidence_level]
    )


def _assess_direct_field(
    *,
    field: _DirectFieldPolicy,
    profile: SleepProfileReport,
    mapping_config: _SleepMappingConfig,
    automatic_candidates: dict[str, list[str]],
    available_paths: set[str],
) -> SleepFieldRouteAssessment:
    mapping = mapping_config.mappings.get(field.canonical_field)
    candidate_paths = list(automatic_candidates.get(field.canonical_field, []))
    if mapping is not None:
        candidate_paths.append(mapping.source_path)
    candidate_paths = sorted(set(candidate_paths))
    missing_confirmations: list[str] = []
    limitations = [
        "field_name_similarity_does_not_confirm_unit_or_medical_semantics"
    ]

    if mapping is not None and mapping.status == "rejected":
        status = "mapping_rejected"
    elif mapping is None or mapping.status == "candidate":
        status = "candidate_unconfirmed" if candidate_paths else "not_observed"
    elif mapping.source_path not in available_paths:
        status = "source_path_missing"
    elif not _evidence_allows_confirmation(profile, mapping_config):
        status = "blocked_evidence"
    else:
        missing_confirmations = _missing_confirmations(field, mapping)
        if (
            mapping.time_source_path
            and mapping.time_source_path not in available_paths
        ):
            missing_confirmations.append("time_source_path_not_observed")
        if (
            mapping.confirmed_unit
            and mapping.confirmed_unit.casefold()
            not in {unit.casefold() for unit in field.expected_units}
        ):
            missing_confirmations.append("confirmed_unit_not_in_policy")
        missing_confirmations = sorted(set(missing_confirmations))
        status = (
            "blocked_semantics"
            if missing_confirmations
            else "ready_for_adapter"
        )

    can_standardize = status == "ready_for_adapter"
    if not can_standardize:
        limitations.append("standardized_feature_emission_is_disabled")
    return SleepFieldRouteAssessment(
        canonical_field=field.canonical_field,
        monitoring_indicators=field.monitoring_indicators,
        priority=field.priority,
        route=field.route,
        candidate_source_paths=candidate_paths,
        mapping_status=mapping.status if mapping else None,
        status=status,
        can_standardize=can_standardize,
        required_confirmations=field.required_confirmations,
        missing_confirmations=missing_confirmations,
        limitations=limitations,
    )


def assess_sleep_route(
    *,
    profile: SleepProfileReport,
    policy_path: Path,
    mapping_config_path: Path,
) -> SleepRouteAssessmentReport:
    policy_path = Path(policy_path)
    mapping_config_path = Path(mapping_config_path)
    policy = _load_config(policy_path, _SleepRoutePolicy)
    mapping_config = _load_config(mapping_config_path, _SleepMappingConfig)
    if policy.device_model != mapping_config.device_model:
        raise ValueError("sleep policy and mapping config device models disagree")
    policy_source_path = (policy_path.parent / policy.source).resolve()
    if not policy_source_path.is_file():
        raise FileNotFoundError(
            f"sleep route policy source not found: {policy_source_path}"
        )
    actual_source_digest = sha256_file(policy_source_path)
    if actual_source_digest != policy.source_sha256:
        raise ValueError(
            "sleep route policy source digest changed; review the monitoring "
            "requirements before updating the field policy"
        )

    candidates = _automatic_candidates(profile)
    available_paths = _profile_paths(profile)
    direct_fields = [
        _assess_direct_field(
            field=field,
            profile=profile,
            mapping_config=mapping_config,
            automatic_candidates=candidates,
            available_paths=available_paths,
        )
        for field in policy.direct_fields
    ]
    ready_fields = {
        field.canonical_field for field in direct_fields if field.can_standardize
    }
    not_assumed_fields = [
        SleepFieldRouteAssessment(
            canonical_field=field.canonical_field,
            monitoring_indicators=field.monitoring_indicators,
            priority=field.priority,
            route="not_assumed",
            status="not_assumed",
            can_standardize=False,
            limitations=[
                field.reason,
                "standardized_feature_emission_is_disabled",
            ],
        )
        for field in policy.not_assumed_fields
    ]
    derived_indicators: list[SleepDerivedRouteAssessment] = []
    for indicator in policy.derived_indicators:
        missing = sorted(
            set(indicator.required_canonical_fields) - ready_fields
        )
        derived_indicators.append(
            SleepDerivedRouteAssessment(
                indicator_id=indicator.indicator_id,
                monitoring_indicators=indicator.monitoring_indicators,
                required_canonical_fields=indicator.required_canonical_fields,
                missing_required_fields=missing,
                minimum_nights=indicator.minimum_nights,
                status=(
                    "blocked_source_fields"
                    if missing
                    else "blocked_time_coverage"
                ),
                calculation_enabled=False,
                limitations=[
                    *indicator.limitations,
                    "field_profile_does_not_persist_values_or_prove_"
                    "multi_night_coverage",
                ],
            )
        )

    status_counts: dict[str, int] = defaultdict(int)
    for field in direct_fields:
        status_counts[f"direct_{field.status}"] += 1
    status_counts["direct_total"] = len(direct_fields)
    status_counts["direct_ready"] = len(ready_fields)
    status_counts["not_assumed_total"] = len(not_assumed_fields)
    status_counts["derived_total"] = len(derived_indicators)
    status_counts["derived_enabled"] = sum(
        indicator.calculation_enabled for indicator in derived_indicators
    )

    issues = [
        QualityIssue(
            code="sleep_values_not_emitted",
            severity=Severity.INFO,
            message=(
                "Route assessment records schema readiness only and emits no "
                "standardized sleep or vital-sign values"
            ),
        )
    ]
    if profile.asset.evidence_level in {EvidenceLevel.E0, EvidenceLevel.E1}:
        issues.append(
            QualityIssue(
                code="target_schema_unverified",
                severity=Severity.WARNING,
                message=(
                    "E0/E1 input cannot confirm the CS-EP-SDHY1 developer schema"
                ),
            )
        )
    if any(field.status == "candidate_unconfirmed" for field in direct_fields):
        issues.append(
            QualityIssue(
                code="candidate_fields_require_confirmation",
                severity=Severity.WARNING,
                message=(
                    "Candidate source paths require unit, time, value, and missing "
                    "semantics before adapter implementation"
                ),
            )
        )

    return SleepRouteAssessmentReport(
        route_version=ROUTE_VERSION,
        device_model=policy.device_model,
        evidence_level=profile.asset.evidence_level,
        profile_asset_id=profile.asset.asset_id,
        profile_asset_sha256=profile.asset.sha256,
        policy_version=policy.policy_version,
        policy_sha256=sha256_file(policy_path),
        policy_source_sha256=actual_source_digest,
        mapping_config_sha256=sha256_file(mapping_config_path),
        mapping_config_fixture_only=mapping_config.fixture_only,
        direct_fields=direct_fields,
        not_assumed_fields=not_assumed_fields,
        derived_indicators=derived_indicators,
        counts=dict(sorted(status_counts.items())),
        decision=(
            "confirmed_fields_ready_for_adapter_implementation"
            if ready_fields
            else "interface_only_waiting_for_e2_e3_schema"
        ),
        values_persisted=False,
        issues=issues,
        limitations=[
            *policy.limitations,
            "official_public_marketing_does_not_prove_target_model_api_fields",
            "route_assessment_is_not_sleep_stage_or_vital_sign_accuracy_evidence",
            "derived_indicators_remain_disabled_until_time_coverage_is_audited",
        ],
    )
