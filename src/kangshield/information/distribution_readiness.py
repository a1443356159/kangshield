from __future__ import annotations

import json
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .contracts import (
    EvidenceLevel,
    Modality,
    PrivacyLevel,
    SourceAsset,
    SourceType,
)
from .privacy import safe_local_uri, sha256_file


ASSESSOR_VERSION = "distribution-readiness-v0.1.0"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _normalized_relative_path(value: str) -> str:
    pure = PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or pure.as_posix() != value
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\\" in value
    ):
        raise ValueError("path must be a normalized repository-relative path")
    return value


class _SourceBinding(_StrictModel):
    relative_path: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    covered_asset_ids: list[str] = Field(min_length=1)

    _validate_path = field_validator("relative_path")(
        _normalized_relative_path
    )


class _RequiredFile(_StrictModel):
    file_id: str = Field(min_length=1)
    relative_path: str
    purpose: str = Field(min_length=1)
    required_for_ready: bool = True
    minimum_byte_size: int = Field(default=1, ge=1)
    expected_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )

    _validate_path = field_validator("relative_path")(
        _normalized_relative_path
    )


class _DistributionDecision(_StrictModel):
    decision_id: str = Field(min_length=1)
    status: Literal["open", "confirmed"]
    value: str | None = None
    evidence_ref: str | None = None
    owner_role: str = Field(min_length=1)
    required_for_ready: bool = True

    @field_validator("evidence_ref")
    @classmethod
    def validate_evidence_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if (
            value.startswith(("/", "~", "file:"))
            or "\\" in value
            or "/home/" in value
        ):
            raise ValueError("decision evidence_ref must not expose a local path")
        return value

    @model_validator(mode="after")
    def validate_confirmation(self) -> "_DistributionDecision":
        if self.status == "confirmed":
            if not self.value or not self.evidence_ref:
                raise ValueError(
                    "confirmed distribution decisions require value and evidence_ref"
                )
        elif self.value is not None or self.evidence_ref is not None:
            raise ValueError(
                "open distribution decisions cannot carry a value or evidence_ref"
            )
        return self


class _DistributionAsset(_StrictModel):
    asset_id: str = Field(min_length=1)
    category: Literal[
        "project_code",
        "software_dependency",
        "model_artifact",
        "evaluation_dataset",
    ]
    name: str = Field(min_length=1)
    version_or_revision: str = Field(min_length=1)
    bundle_action: Literal["include", "exclude", "undecided"]
    clearance_status: Literal[
        "cleared",
        "cleared_with_obligations",
        "blocked_pending_review",
        "blocked_pending_owner_decision",
        "excluded_from_bundle",
    ]
    license_expression: str | None = None
    license_sources: list[str] = Field(default_factory=list)
    obligations: list[str] = Field(default_factory=list)
    open_requirements: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_clearance(self) -> "_DistributionAsset":
        excluded = self.clearance_status == "excluded_from_bundle"
        blocked = self.clearance_status in {
            "blocked_pending_review",
            "blocked_pending_owner_decision",
        }
        cleared = self.clearance_status in {
            "cleared",
            "cleared_with_obligations",
        }
        if (self.bundle_action == "exclude") != excluded:
            raise ValueError(
                "excluded bundle assets must use excluded_from_bundle and vice versa"
            )
        if self.bundle_action == "undecided" and not blocked:
            raise ValueError("undecided assets must remain blocked")
        if blocked and not self.open_requirements:
            raise ValueError("blocked assets require open_requirements")
        if not blocked and self.open_requirements:
            raise ValueError("only blocked assets may carry open_requirements")
        if cleared and (not self.license_expression or not self.license_sources):
            raise ValueError(
                "cleared assets require a license expression and source"
            )
        if (
            self.clearance_status == "cleared_with_obligations"
            and not self.obligations
        ):
            raise ValueError("cleared_with_obligations requires obligations")
        if any(not source.startswith("https://") for source in self.license_sources):
            raise ValueError("license sources must use https URLs")
        return self


class _ReadinessGate(_StrictModel):
    gate_id: str = Field(min_length=1)
    required_file_ids: list[str] = Field(default_factory=list)
    required_decision_ids: list[str] = Field(default_factory=list)
    required_asset_ids: list[str] = Field(default_factory=list)


class _DistributionPolicy(_StrictModel):
    schema_version: Literal["1.0"]
    policy_id: str = Field(min_length=1)
    policy_version: Literal[ASSESSOR_VERSION]
    profile_id: str = Field(min_length=1)
    reviewed_on: date
    legal_review_required: Literal[True] = True
    source_bindings: list[_SourceBinding] = Field(min_length=1)
    required_files: list[_RequiredFile] = Field(min_length=1)
    decisions: list[_DistributionDecision] = Field(min_length=1)
    assets: list[_DistributionAsset] = Field(min_length=1)
    readiness_gates: list[_ReadinessGate] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "_DistributionPolicy":
        def unique(values: list[str], kind: str) -> set[str]:
            result = set(values)
            if len(values) != len(result):
                raise ValueError(f"distribution policy contains duplicate {kind}")
            return result

        asset_ids = unique(
            [asset.asset_id for asset in self.assets], "asset ids"
        )
        source_paths = unique(
            [source.relative_path for source in self.source_bindings],
            "source paths",
        )
        if not source_paths:
            raise ValueError("distribution policy requires source bindings")
        file_ids = unique(
            [item.file_id for item in self.required_files], "required file ids"
        )
        unique(
            [item.relative_path for item in self.required_files],
            "required file paths",
        )
        decision_ids = unique(
            [item.decision_id for item in self.decisions], "decision ids"
        )
        unique([gate.gate_id for gate in self.readiness_gates], "gate ids")

        covered: set[str] = set()
        for source in self.source_bindings:
            unknown = set(source.covered_asset_ids) - asset_ids
            if unknown:
                raise ValueError(
                    "source binding references unknown assets: "
                    + ", ".join(sorted(unknown))
                )
            covered.update(source.covered_asset_ids)
        if covered != asset_ids:
            raise ValueError(
                "assets missing source coverage: "
                + ", ".join(sorted(asset_ids - covered))
            )

        for gate in self.readiness_gates:
            unknown_files = set(gate.required_file_ids) - file_ids
            unknown_decisions = set(gate.required_decision_ids) - decision_ids
            unknown_assets = set(gate.required_asset_ids) - asset_ids
            if unknown_files or unknown_decisions or unknown_assets:
                raise ValueError(
                    f"readiness gate {gate.gate_id} references unknown inputs"
                )
        return self


class DistributionSourceCheck(_StrictModel):
    relative_path: str
    expected_sha256: str = Field(pattern=SHA256_PATTERN)
    actual_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    status: Literal["matched", "missing", "digest_mismatch"]
    covered_asset_ids: list[str]


class DistributionRequiredFileCheck(_StrictModel):
    file_id: str
    relative_path: str
    purpose: str
    required_for_ready: bool
    minimum_byte_size: int = Field(ge=1)
    expected_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    actual_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    byte_size: int | None = Field(default=None, ge=0)
    status: Literal[
        "matched",
        "missing",
        "too_small",
        "digest_unbound",
        "digest_mismatch",
    ]


class DistributionDecisionAssessment(_StrictModel):
    decision_id: str
    status: Literal["open", "confirmed"]
    value: str | None = None
    evidence_ref: str | None = None
    owner_role: str
    required_for_ready: bool
    blocking: bool


class DistributionAssetAssessment(_StrictModel):
    asset_id: str
    category: str
    name: str
    version_or_revision: str
    bundle_action: str
    clearance_status: str
    license_expression: str | None = None
    license_sources: list[str]
    obligations: list[str]
    open_requirements: list[str]
    limitations: list[str]
    source_evidence_ready: bool
    blocking: bool


class DistributionGateAssessment(_StrictModel):
    gate_id: str
    ready: bool
    blocking_inputs: list[str]


class DistributionReadinessReport(_StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    assessor_version: Literal[ASSESSOR_VERSION] = ASSESSOR_VERSION
    policy_id: str
    policy_version: str
    policy_sha256: str = Field(pattern=SHA256_PATTERN)
    profile_id: str
    reviewed_on: date
    legal_review_required: Literal[True] = True
    legal_advice_provided: Literal[False] = False
    source_checks: list[DistributionSourceCheck]
    required_files: list[DistributionRequiredFileCheck]
    decisions: list[DistributionDecisionAssessment]
    assets: list[DistributionAssetAssessment]
    readiness_gates: list[DistributionGateAssessment]
    counts: dict[str, int]
    blocking_reasons: list[str]
    decision: Literal[
        "submission_bundle_ready",
        "blocked_pending_distribution_review",
    ]
    submission_bundle_ready: bool
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str]


def _load_policy(path: Path) -> _DistributionPolicy:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("distribution policy could not be read as JSON") from error
    try:
        return _DistributionPolicy.model_validate(payload)
    except ValidationError as error:
        raise ValueError("distribution policy schema validation failed") from error


def _repository_file(repository_root: Path, relative_path: str) -> Path:
    candidate = (repository_root / relative_path).resolve()
    if not candidate.is_relative_to(repository_root):
        raise ValueError("distribution policy path escapes repository root")
    return candidate


def distribution_policy_asset(policy_path: Path) -> SourceAsset:
    policy_path = Path(policy_path)
    digest = sha256_file(policy_path)
    return SourceAsset(
        asset_id=f"distribution_policy_{digest[:16]}",
        modality=Modality.UNKNOWN,
        source_type=SourceType.LOCAL_FILE,
        evidence_level=EvidenceLevel.E1,
        uri=safe_local_uri(policy_path, digest),
        sha256=digest,
        byte_size=policy_path.stat().st_size,
        privacy_level=PrivacyLevel.AGGREGATE,
        metadata={"kind": "distribution_readiness_policy"},
    )


def assess_distribution_readiness(
    *,
    policy_path: Path,
    repository_root: Path,
) -> DistributionReadinessReport:
    policy_path = Path(policy_path).resolve()
    repository_root = Path(repository_root).resolve()
    if not (repository_root / "pyproject.toml").is_file() or not (
        repository_root / "src" / "kangshield" / "__init__.py"
    ).is_file():
        raise ValueError("repository_root is not a KangShield checkout")

    policy = _load_policy(policy_path)
    policy_sha256 = sha256_file(policy_path)

    source_checks: list[DistributionSourceCheck] = []
    source_status: dict[str, str] = {}
    for source in policy.source_bindings:
        path = _repository_file(repository_root, source.relative_path)
        actual_sha256 = sha256_file(path) if path.is_file() else None
        if actual_sha256 is None:
            status = "missing"
        elif actual_sha256 != source.sha256:
            status = "digest_mismatch"
        else:
            status = "matched"
        source_status[source.relative_path] = status
        source_checks.append(
            DistributionSourceCheck(
                relative_path=source.relative_path,
                expected_sha256=source.sha256,
                actual_sha256=actual_sha256,
                status=status,
                covered_asset_ids=source.covered_asset_ids,
            )
        )

    required_files: list[DistributionRequiredFileCheck] = []
    file_ready: dict[str, bool] = {}
    for item in policy.required_files:
        path = _repository_file(repository_root, item.relative_path)
        byte_size = path.stat().st_size if path.is_file() else None
        actual_sha256 = sha256_file(path) if path.is_file() else None
        if byte_size is None:
            status = "missing"
        elif byte_size < item.minimum_byte_size:
            status = "too_small"
        elif item.expected_sha256 is None:
            status = "digest_unbound"
        elif actual_sha256 != item.expected_sha256:
            status = "digest_mismatch"
        else:
            status = "matched"
        file_ready[item.file_id] = status == "matched"
        required_files.append(
            DistributionRequiredFileCheck(
                file_id=item.file_id,
                relative_path=item.relative_path,
                purpose=item.purpose,
                required_for_ready=item.required_for_ready,
                minimum_byte_size=item.minimum_byte_size,
                expected_sha256=item.expected_sha256,
                actual_sha256=actual_sha256,
                byte_size=byte_size,
                status=status,
            )
        )

    decisions = [
        DistributionDecisionAssessment(
            **item.model_dump(),
            blocking=item.required_for_ready and item.status != "confirmed",
        )
        for item in policy.decisions
    ]
    decision_ready = {
        item.decision_id: item.status == "confirmed" for item in policy.decisions
    }

    asset_source_ready = {item.asset_id: True for item in policy.assets}
    for source in source_checks:
        if source.status != "matched":
            for asset_id in source.covered_asset_ids:
                asset_source_ready[asset_id] = False

    assets: list[DistributionAssetAssessment] = []
    asset_ready: dict[str, bool] = {}
    for item in policy.assets:
        source_evidence_ready = asset_source_ready[item.asset_id]
        blocking = item.bundle_action != "exclude" and (
            item.clearance_status
            not in {
                "cleared",
                "cleared_with_obligations",
            }
            or not source_evidence_ready
        )
        asset_ready[item.asset_id] = not blocking
        assets.append(
            DistributionAssetAssessment(
                **item.model_dump(),
                source_evidence_ready=source_evidence_ready,
                blocking=blocking,
            )
        )

    readiness_gates: list[DistributionGateAssessment] = []
    for gate in policy.readiness_gates:
        blocking_inputs = sorted(
            [
                *(f"file:{item}" for item in gate.required_file_ids if not file_ready[item]),
                *(
                    f"decision:{item}"
                    for item in gate.required_decision_ids
                    if not decision_ready[item]
                ),
                *(
                    f"asset:{item}"
                    for item in gate.required_asset_ids
                    if not asset_ready[item]
                ),
            ]
        )
        readiness_gates.append(
            DistributionGateAssessment(
                gate_id=gate.gate_id,
                ready=not blocking_inputs,
                blocking_inputs=blocking_inputs,
            )
        )

    blocking_reasons = sorted(
        [
            *(
                f"source:{check.relative_path}:{check.status}"
                for check in source_checks
                if check.status != "matched"
            ),
            *(
                f"required_file:{item.file_id}:{item.status}"
                for item in required_files
                if item.required_for_ready and item.status != "matched"
            ),
            *(
                f"decision:{item.decision_id}:open"
                for item in decisions
                if item.blocking
            ),
            *(
                f"asset:{item.asset_id}:{item.clearance_status}"
                for item in assets
                if item.blocking
            ),
        ]
    )
    ready = not blocking_reasons
    counts = {
        "source_total": len(source_checks),
        "source_matched": sum(item.status == "matched" for item in source_checks),
        "source_missing_or_drifted": sum(
            item.status != "matched" for item in source_checks
        ),
        "required_file_total": len(required_files),
        "required_file_present": sum(
            item.status != "missing" for item in required_files
        ),
        "required_file_missing": sum(
            item.status == "missing" for item in required_files
        ),
        "required_file_matched": sum(
            item.status == "matched" for item in required_files
        ),
        "required_file_unbound_or_drifted": sum(
            item.status not in {"matched", "missing"}
            for item in required_files
        ),
        "decision_total": len(decisions),
        "decision_confirmed": sum(item.status == "confirmed" for item in decisions),
        "decision_open": sum(item.status == "open" for item in decisions),
        "asset_total": len(assets),
        "asset_include": sum(item.bundle_action == "include" for item in assets),
        "asset_exclude": sum(item.bundle_action == "exclude" for item in assets),
        "asset_undecided": sum(item.bundle_action == "undecided" for item in assets),
        "asset_blocking": sum(item.blocking for item in assets),
        "gate_total": len(readiness_gates),
        "gate_ready": sum(item.ready for item in readiness_gates),
    }
    return DistributionReadinessReport(
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        policy_sha256=policy_sha256,
        profile_id=policy.profile_id,
        reviewed_on=policy.reviewed_on,
        source_checks=source_checks,
        required_files=required_files,
        decisions=decisions,
        assets=assets,
        readiness_gates=readiness_gates,
        counts=counts,
        blocking_reasons=blocking_reasons,
        decision=(
            "submission_bundle_ready"
            if ready
            else "blocked_pending_distribution_review"
        ),
        submission_bundle_ready=ready,
        limitations=policy.limitations,
    )
