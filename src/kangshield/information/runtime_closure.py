from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from collections import deque
from datetime import date
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from packaging.markers import Marker, default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version
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


ASSESSOR_VERSION = "runtime-closure-v0.1.0"
SNAPSHOT_VERSION = "runtime-inventory-v0.1.0"
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


def _canonical_name(value: str) -> str:
    canonical = canonicalize_name(value)
    if not canonical:
        raise ValueError("package name must not be empty")
    return canonical


class RuntimeTarget(_StrictModel):
    python_full_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    implementation_name: str = Field(min_length=1)
    platform_system: str = Field(min_length=1)
    platform_machine: str = Field(min_length=1)
    sys_platform: str = Field(min_length=1)
    os_name: str = Field(min_length=1)

    _normalize_implementation = field_validator("implementation_name")(
        lambda value: value.lower()
    )


class _RepositorySource(_StrictModel):
    relative_path: str
    sha256: str = Field(pattern=SHA256_PATTERN)

    _validate_path = field_validator("relative_path")(
        _normalized_relative_path
    )


class _DirectRequirement(_StrictModel):
    requirement: str = Field(min_length=1)
    purpose: str = Field(min_length=1)

    @field_validator("requirement")
    @classmethod
    def validate_requirement(cls, value: str) -> str:
        try:
            parsed = Requirement(value)
        except InvalidRequirement as error:
            raise ValueError("invalid direct requirement") from error
        if parsed.url is not None or parsed.marker is not None:
            raise ValueError(
                "direct requirements cannot use URLs or environment markers"
            )
        if not parsed.specifier:
            raise ValueError("direct requirements must pin or constrain a version")
        return value


class _RuntimeProfile(_StrictModel):
    schema_version: Literal["1.0"]
    profile_id: str = Field(min_length=1)
    profile_version: Literal[ASSESSOR_VERSION]
    status: Literal["candidate_not_release"]
    reviewed_on: date
    target: RuntimeTarget
    repository_sources: list[_RepositorySource] = Field(min_length=1)
    direct_requirements: list[_DirectRequirement] = Field(min_length=1)
    prohibited_closure_packages: list[str] = Field(default_factory=list)
    allowed_bootstrap_packages: list[str] = Field(default_factory=list)
    allowed_direct_url_packages: list[str] = Field(default_factory=list)
    prohibit_editable_installs: Literal[True] = True
    prohibit_pythonpath: Literal[True] = True
    require_isolated_environment: Literal[True] = True
    require_license_metadata: Literal[True] = True
    final_lock_emission_authorized: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @field_validator(
        "prohibited_closure_packages",
        "allowed_bootstrap_packages",
        "allowed_direct_url_packages",
    )
    @classmethod
    def normalize_package_list(cls, values: list[str]) -> list[str]:
        return [_canonical_name(value) for value in values]

    @model_validator(mode="after")
    def validate_profile(self) -> "_RuntimeProfile":
        source_paths = [item.relative_path for item in self.repository_sources]
        if len(source_paths) != len(set(source_paths)):
            raise ValueError("runtime profile contains duplicate source paths")
        direct_names = [
            canonicalize_name(Requirement(item.requirement).name)
            for item in self.direct_requirements
        ]
        if len(direct_names) != len(set(direct_names)):
            raise ValueError("runtime profile contains duplicate direct packages")
        prohibited = set(self.prohibited_closure_packages)
        if len(prohibited) != len(self.prohibited_closure_packages):
            raise ValueError("runtime profile contains duplicate prohibited packages")
        allowed = set(self.allowed_bootstrap_packages)
        if len(allowed) != len(self.allowed_bootstrap_packages):
            raise ValueError("runtime profile contains duplicate bootstrap packages")
        overlap = prohibited & (set(direct_names) | allowed)
        if overlap:
            raise ValueError(
                "prohibited packages cannot be direct or bootstrap packages"
            )
        direct_url_allowed = set(self.allowed_direct_url_packages)
        if len(direct_url_allowed) != len(self.allowed_direct_url_packages):
            raise ValueError(
                "runtime profile contains duplicate direct URL allowances"
            )
        if direct_url_allowed - set(direct_names):
            raise ValueError(
                "direct URL allowances must refer to direct requirements"
            )
        return self


class RuntimeRequirement(_StrictModel):
    name: str = Field(min_length=1)
    specifier: str = ""
    marker: str | None = None
    extras: list[str] = Field(default_factory=list)
    url_reference: bool = False

    _normalize_name = field_validator("name")(_canonical_name)

    @field_validator("specifier")
    @classmethod
    def validate_specifier(cls, value: str) -> str:
        try:
            Requirement(f"fixture{value}")
        except InvalidRequirement as error:
            raise ValueError("invalid sanitized requirement specifier") from error
        return value

    @field_validator("marker")
    @classmethod
    def validate_marker(cls, value: str | None) -> str | None:
        if value is not None:
            Marker(value)
            if any(token in value for token in ("/", "\\", "file:", "~")):
                raise ValueError("runtime requirement marker is not path-safe")
        return value

    @field_validator("extras")
    @classmethod
    def normalize_extras(cls, values: list[str]) -> list[str]:
        normalized = sorted(canonicalize_name(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("runtime requirement contains duplicate extras")
        return normalized


class RuntimePackage(_StrictModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    installer: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_.-]{1,64}$",
    )
    requested: bool = False
    direct_url_reference: bool = False
    editable_install: bool = False
    requirements: list[RuntimeRequirement] = Field(default_factory=list)
    license_metadata_status: Literal[
        "spdx_expression_present",
        "legacy_field_present",
        "classifier_only",
        "missing",
    ]
    license_expression: str | None = Field(default=None, max_length=512)
    legacy_license_value_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    license_classifiers: list[str] = Field(default_factory=list)

    _normalize_name = field_validator("name")(_canonical_name)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        try:
            Version(value)
        except InvalidVersion as error:
            raise ValueError("runtime package version is invalid") from error
        return value

    @field_validator("license_expression")
    @classmethod
    def validate_license_expression(cls, value: str | None) -> str | None:
        if value is not None and (
            "\n" in value
            or "\r" in value
            or "/home/" in value
            or "file:" in value.lower()
            or "\\" in value
        ):
            raise ValueError("license expression is not safe to persist")
        return value

    @field_validator("license_classifiers")
    @classmethod
    def validate_license_classifiers(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(value) > 256 or any(
                token in value for token in ("\n", "\r", "/home/", "file:", "\\")
            ):
                raise ValueError("license classifier is not safe to persist")
        return values


class RuntimeInventory(_StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    snapshot_version: Literal[SNAPSHOT_VERSION] = SNAPSHOT_VERSION
    python_full_version: str
    implementation_name: str
    platform_system: str
    platform_machine: str
    sys_platform: str
    os_name: str
    pip_version: str
    pythonpath_configured: bool = False
    packages: list[RuntimePackage]
    invalid_requirement_refs: list[str] = Field(default_factory=list)
    local_paths_persisted: Literal[False] = False
    dependency_urls_persisted: Literal[False] = False

    _normalize_implementation = field_validator("implementation_name")(
        lambda value: value.lower()
    )

    @field_validator("pip_version")
    @classmethod
    def validate_pip_version(cls, value: str) -> str:
        try:
            Version(value)
        except InvalidVersion as error:
            raise ValueError("runtime inventory pip version is invalid") from error
        return value

    @model_validator(mode="after")
    def validate_packages(self) -> "RuntimeInventory":
        names = [item.name for item in self.packages]
        if len(names) != len(set(names)):
            raise ValueError("runtime inventory contains duplicate packages")
        if self.invalid_requirement_refs != sorted(
            set(self.invalid_requirement_refs)
        ):
            raise ValueError(
                "invalid requirement references must be unique and sorted"
            )
        return self


class RuntimeSourceCheck(_StrictModel):
    relative_path: str
    expected_sha256: str = Field(pattern=SHA256_PATTERN)
    actual_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    status: Literal["matched", "missing", "digest_mismatch"]


class RuntimeTargetAssessment(_StrictModel):
    expected: RuntimeTarget
    actual: RuntimeTarget
    mismatched_fields: list[str]
    ready: bool


class RuntimeDirectRequirementAssessment(_StrictModel):
    requirement: str
    package_name: str
    purpose: str
    installed_version: str | None = None
    status: Literal["matched", "missing", "version_mismatch"]


class RuntimeDependencyIssue(_StrictModel):
    parent_package: str
    dependency_name: str
    issue: Literal[
        "missing",
        "version_mismatch",
        "invalid_installed_version",
        "url_dependency_requires_review",
        "invalid_requirement_metadata",
    ]
    required_specifier: str | None = None
    installed_version: str | None = None


class RuntimeClosurePackageAssessment(_StrictModel):
    name: str
    version: str
    direct: bool
    requested: bool
    installer: str | None = None
    direct_url_reference: bool
    editable_install: bool
    dependency_names: list[str]
    license_metadata_status: str
    license_expression: str | None = None
    legacy_license_value_sha256: str | None = None
    license_classifiers: list[str]


class RuntimeClosureGate(_StrictModel):
    gate_id: Literal[
        "target-environment-ready",
        "repository-source-ready",
        "direct-requirements-ready",
        "dependency-closure-ready",
        "prohibited-closure-absent",
        "installation-provenance-ready",
        "isolated-environment-ready",
        "license-metadata-ready",
    ]
    ready: bool
    blocking_count: int = Field(ge=0)


class RuntimeClosureReport(_StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    assessor_version: Literal[ASSESSOR_VERSION] = ASSESSOR_VERSION
    profile_id: str
    profile_version: str
    profile_status: Literal["candidate_not_release"]
    profile_sha256: str = Field(pattern=SHA256_PATTERN)
    snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    snapshot_version: str
    target: RuntimeTargetAssessment
    source_checks: list[RuntimeSourceCheck]
    direct_requirements: list[RuntimeDirectRequirementAssessment]
    dependency_issues: list[RuntimeDependencyIssue]
    closure_packages: list[RuntimeClosurePackageAssessment]
    prohibited_in_closure: list[str]
    prohibited_installed_outside_closure: list[str]
    installation_provenance_violations: list[str]
    extraneous_installed_packages: list[str]
    relevant_invalid_requirement_refs: list[str]
    gates: list[RuntimeClosureGate]
    counts: dict[str, int]
    blocking_reasons: list[str]
    decision: Literal[
        "candidate_closure_snapshot_ready",
        "blocked_runtime_closure_review",
    ]
    closure_snapshot_ready: bool
    candidate_only: Literal[True] = True
    competition_lock_emitted: Literal[False] = False
    third_party_notice_emitted: Literal[False] = False
    legal_advice_provided: Literal[False] = False
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str]


def _model_bytes(value: BaseModel) -> bytes:
    payload = json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    )
    return (payload + "\n").encode("utf-8")


def runtime_inventory_sha256(inventory: RuntimeInventory) -> str:
    return sha256(_model_bytes(inventory)).hexdigest()


def _metadata_value(metadata: dict[str, Any], key: str) -> Any:
    return metadata.get(key, metadata.get(key.replace("_", "-")))


def _license_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    expression_value = _metadata_value(metadata, "license_expression")
    expression = (
        str(expression_value).strip()
        if expression_value is not None and str(expression_value).strip()
        else None
    )
    if expression is not None and len(expression) > 512:
        expression = None

    legacy_value = _metadata_value(metadata, "license")
    legacy = (
        str(legacy_value).strip()
        if legacy_value is not None and str(legacy_value).strip()
        else None
    )
    if legacy is not None and legacy.lower() in {
        "unknown",
        "unknown license",
        "n/a",
        "none",
    }:
        legacy = None

    raw_classifiers = _metadata_value(metadata, "classifier") or []
    if isinstance(raw_classifiers, str):
        raw_classifiers = [raw_classifiers]
    classifiers = sorted(
        {
            str(item).strip()
            for item in raw_classifiers
            if str(item).strip().startswith("License ::")
        }
    )

    if expression is not None:
        status = "spdx_expression_present"
    elif legacy is not None:
        status = "legacy_field_present"
    elif classifiers:
        status = "classifier_only"
    else:
        status = "missing"
    return {
        "license_metadata_status": status,
        "license_expression": expression,
        "legacy_license_value_sha256": (
            sha256(legacy.encode("utf-8")).hexdigest()
            if legacy is not None
            else None
        ),
        "license_classifiers": classifiers,
    }


def sanitize_pip_inspect(
    payload: dict[str, Any],
    *,
    runtime: RuntimeTarget,
    pythonpath_configured: bool = False,
) -> RuntimeInventory:
    if payload.get("version") != "1" or not isinstance(
        payload.get("installed"), list
    ):
        raise ValueError("unsupported pip inspect schema")
    pip_version = str(payload.get("pip_version") or "unknown")
    packages: list[RuntimePackage] = []
    invalid_refs: list[str] = []
    for entry in payload["installed"]:
        if not isinstance(entry, dict) or not isinstance(
            entry.get("metadata"), dict
        ):
            raise ValueError("pip inspect contains an invalid installed entry")
        metadata = entry["metadata"]
        name_value = _metadata_value(metadata, "name")
        version_value = _metadata_value(metadata, "version")
        if not name_value or not version_value:
            raise ValueError("pip inspect package metadata lacks name or version")
        name = _canonical_name(str(name_value))
        raw_requirements = _metadata_value(metadata, "requires_dist") or []
        if isinstance(raw_requirements, str):
            raw_requirements = [raw_requirements]
        requirements: list[RuntimeRequirement] = []
        for index, raw_requirement in enumerate(raw_requirements):
            try:
                parsed = Requirement(str(raw_requirement))
            except InvalidRequirement:
                invalid_refs.append(f"{name}:{index}")
                continue
            marker = str(parsed.marker) if parsed.marker else None
            if marker is not None and any(
                token in marker for token in ("/", "\\", "file:", "~")
            ):
                invalid_refs.append(f"{name}:{index}")
                continue
            requirements.append(
                RuntimeRequirement(
                    name=parsed.name,
                    specifier=str(parsed.specifier),
                    marker=marker,
                    extras=sorted(parsed.extras),
                    url_reference=parsed.url is not None,
                )
            )
        installer_value = (
            str(entry["installer"])
            if entry.get("installer") is not None
            else None
        )
        if installer_value is not None and (
            len(installer_value) > 64
            or any(
                not (character.isalnum() or character in "_.-")
                for character in installer_value
            )
        ):
            installer_value = "other"
        direct_url = entry.get("direct_url")
        direct_url_reference = isinstance(direct_url, dict)
        directory_info = (
            direct_url.get("dir_info", {})
            if isinstance(direct_url, dict)
            else {}
        )
        editable_install = bool(
            isinstance(directory_info, dict)
            and directory_info.get("editable", False)
        )
        packages.append(
            RuntimePackage(
                name=name,
                version=str(version_value),
                installer=installer_value,
                requested=bool(entry.get("requested", False)),
                direct_url_reference=direct_url_reference,
                editable_install=editable_install,
                requirements=requirements,
                **_license_metadata(metadata),
            )
        )
    packages.sort(key=lambda item: item.name)
    return RuntimeInventory(
        python_full_version=runtime.python_full_version,
        implementation_name=runtime.implementation_name,
        platform_system=runtime.platform_system,
        platform_machine=runtime.platform_machine,
        sys_platform=runtime.sys_platform,
        os_name=runtime.os_name,
        pip_version=pip_version,
        pythonpath_configured=pythonpath_configured,
        packages=packages,
        invalid_requirement_refs=sorted(set(invalid_refs)),
    )


def current_runtime_target() -> RuntimeTarget:
    return RuntimeTarget(
        python_full_version=platform.python_version(),
        implementation_name=sys.implementation.name,
        platform_system=platform.system(),
        platform_machine=platform.machine(),
        sys_platform=sys.platform,
        os_name=os.name,
    )


def capture_runtime_inventory() -> RuntimeInventory:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "inspect"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(completed.stdout)
    except (
        OSError,
        subprocess.SubprocessError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise RuntimeError("unable to capture pip inspect runtime metadata") from error
    if not isinstance(payload, dict):
        raise RuntimeError("pip inspect did not return a JSON object")
    return sanitize_pip_inspect(
        payload,
        runtime=current_runtime_target(),
        pythonpath_configured=bool(os.environ.get("PYTHONPATH")),
    )


def load_runtime_inventory(path: Path) -> RuntimeInventory:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("runtime inventory could not be read as JSON") from error
    try:
        return RuntimeInventory.model_validate(payload)
    except ValidationError as error:
        raise ValueError("runtime inventory schema validation failed") from error


def _load_profile(path: Path) -> _RuntimeProfile:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("runtime profile could not be read as JSON") from error
    try:
        return _RuntimeProfile.model_validate(payload)
    except ValidationError as error:
        raise ValueError("runtime profile schema validation failed") from error


def runtime_profile_asset(profile_path: Path) -> SourceAsset:
    profile_path = Path(profile_path)
    digest = sha256_file(profile_path)
    return SourceAsset(
        asset_id=f"runtime_profile_{digest[:16]}",
        modality=Modality.UNKNOWN,
        source_type=SourceType.LOCAL_FILE,
        evidence_level=EvidenceLevel.E1,
        uri=safe_local_uri(profile_path, digest),
        sha256=digest,
        byte_size=profile_path.stat().st_size,
        privacy_level=PrivacyLevel.AGGREGATE,
        metadata={"kind": "runtime_closure_profile"},
    )


def runtime_inventory_asset(inventory: RuntimeInventory) -> SourceAsset:
    payload = _model_bytes(inventory)
    digest = sha256(payload).hexdigest()
    return SourceAsset(
        asset_id=f"runtime_inventory_{digest[:16]}",
        modality=Modality.UNKNOWN,
        source_type=SourceType.RUNTIME_SNAPSHOT,
        evidence_level=EvidenceLevel.E1,
        uri=f"urn:kangshield:runtime-inventory:{digest[:16]}",
        sha256=digest,
        byte_size=len(payload),
        privacy_level=PrivacyLevel.AGGREGATE,
        metadata={
            "kind": "sanitized_pip_inspect",
            "local_paths_persisted": False,
            "dependency_urls_persisted": False,
        },
    )


def _repository_file(repository_root: Path, relative_path: str) -> Path:
    candidate = (repository_root / relative_path).resolve()
    if not candidate.is_relative_to(repository_root):
        raise ValueError("runtime profile path escapes repository root")
    return candidate


def _target_from_inventory(inventory: RuntimeInventory) -> RuntimeTarget:
    return RuntimeTarget(
        python_full_version=inventory.python_full_version,
        implementation_name=inventory.implementation_name,
        platform_system=inventory.platform_system,
        platform_machine=inventory.platform_machine,
        sys_platform=inventory.sys_platform,
        os_name=inventory.os_name,
    )


def _marker_environment(target: RuntimeTarget) -> dict[str, str]:
    environment = default_environment()
    version_parts = target.python_full_version.split(".")
    environment.update(
        {
            "implementation_name": target.implementation_name,
            "implementation_version": target.python_full_version,
            "os_name": target.os_name,
            "platform_machine": target.platform_machine,
            "platform_python_implementation": (
                "CPython"
                if target.implementation_name == "cpython"
                else target.implementation_name
            ),
            "platform_system": target.platform_system,
            "python_full_version": target.python_full_version,
            "python_version": ".".join(version_parts[:2]),
            "sys_platform": target.sys_platform,
        }
    )
    return environment


def _requirement_applies(
    requirement: RuntimeRequirement,
    *,
    environment: dict[str, str],
    active_extras: set[str],
) -> bool:
    if requirement.marker is None:
        return True
    marker = Marker(requirement.marker)
    for extra in ["", *sorted(active_extras)]:
        candidate = dict(environment)
        candidate["extra"] = extra
        if marker.evaluate(candidate):
            return True
    return False


def _version_matches(version: str, specifier: str) -> bool:
    try:
        parsed = Version(version)
    except InvalidVersion:
        return False
    return Requirement(f"fixture{specifier}").specifier.contains(
        parsed,
        prereleases=True,
    )


def assess_runtime_closure(
    *,
    profile_path: Path,
    repository_root: Path,
    inventory: RuntimeInventory,
) -> RuntimeClosureReport:
    profile_path = Path(profile_path).resolve()
    repository_root = Path(repository_root).resolve()
    if not (repository_root / "pyproject.toml").is_file() or not (
        repository_root / "src" / "kangshield" / "__init__.py"
    ).is_file():
        raise ValueError("repository_root is not a KangShield checkout")
    profile = _load_profile(profile_path)
    profile_sha256 = sha256_file(profile_path)
    snapshot_sha256 = runtime_inventory_sha256(inventory)

    actual_target = _target_from_inventory(inventory)
    target_fields = list(RuntimeTarget.model_fields)
    mismatched_fields = [
        field
        for field in target_fields
        if getattr(profile.target, field) != getattr(actual_target, field)
    ]
    target_assessment = RuntimeTargetAssessment(
        expected=profile.target,
        actual=actual_target,
        mismatched_fields=mismatched_fields,
        ready=not mismatched_fields,
    )

    source_checks: list[RuntimeSourceCheck] = []
    for source in profile.repository_sources:
        path = _repository_file(repository_root, source.relative_path)
        actual_sha256 = sha256_file(path) if path.is_file() else None
        if actual_sha256 is None:
            status = "missing"
        elif actual_sha256 != source.sha256:
            status = "digest_mismatch"
        else:
            status = "matched"
        source_checks.append(
            RuntimeSourceCheck(
                relative_path=source.relative_path,
                expected_sha256=source.sha256,
                actual_sha256=actual_sha256,
                status=status,
            )
        )

    packages = {item.name: item for item in inventory.packages}
    direct_requirements: list[RuntimeDirectRequirementAssessment] = []
    direct_parsed: dict[str, Requirement] = {}
    for item in profile.direct_requirements:
        requirement = Requirement(item.requirement)
        name = canonicalize_name(requirement.name)
        direct_parsed[name] = requirement
        installed = packages.get(name)
        if installed is None:
            status = "missing"
            installed_version = None
        elif not _version_matches(
            installed.version,
            str(requirement.specifier),
        ):
            status = "version_mismatch"
            installed_version = installed.version
        else:
            status = "matched"
            installed_version = installed.version
        direct_requirements.append(
            RuntimeDirectRequirementAssessment(
                requirement=item.requirement,
                package_name=name,
                purpose=item.purpose,
                installed_version=installed_version,
                status=status,
            )
        )

    environment = _marker_environment(profile.target)
    active_extras: dict[str, set[str]] = {}
    queue: deque[tuple[str, set[str]]] = deque(
        (
            name,
            {canonicalize_name(extra) for extra in requirement.extras},
        )
        for name, requirement in direct_parsed.items()
    )
    closure_names: set[str] = set()
    dependency_issues_by_key: dict[
        tuple[str, str, str, str | None, str | None], RuntimeDependencyIssue
    ] = {}
    dependency_names_by_parent: dict[str, set[str]] = {}

    while queue:
        name, extras = queue.popleft()
        previous = active_extras.setdefault(name, set())
        new_extras = extras - previous
        if name in closure_names and not new_extras:
            continue
        previous.update(extras)
        closure_names.add(name)
        package = packages.get(name)
        if package is None:
            continue
        dependency_names_by_parent.setdefault(name, set())
        for requirement in package.requirements:
            if not _requirement_applies(
                requirement,
                environment=environment,
                active_extras=previous,
            ):
                continue
            dependency_name = requirement.name
            dependency_names_by_parent[name].add(dependency_name)
            installed = packages.get(dependency_name)
            issue: RuntimeDependencyIssue | None = None
            if requirement.url_reference:
                issue = RuntimeDependencyIssue(
                    parent_package=name,
                    dependency_name=dependency_name,
                    issue="url_dependency_requires_review",
                    required_specifier=requirement.specifier or None,
                    installed_version=(installed.version if installed else None),
                )
            elif installed is None:
                issue = RuntimeDependencyIssue(
                    parent_package=name,
                    dependency_name=dependency_name,
                    issue="missing",
                    required_specifier=requirement.specifier or None,
                )
            elif requirement.specifier and not _version_matches(
                installed.version,
                requirement.specifier,
            ):
                try:
                    Version(installed.version)
                except InvalidVersion:
                    issue_name = "invalid_installed_version"
                else:
                    issue_name = "version_mismatch"
                issue = RuntimeDependencyIssue(
                    parent_package=name,
                    dependency_name=dependency_name,
                    issue=issue_name,
                    required_specifier=requirement.specifier,
                    installed_version=installed.version,
                )
            if issue is not None:
                key = (
                    issue.parent_package,
                    issue.dependency_name,
                    issue.issue,
                    issue.required_specifier,
                    issue.installed_version,
                )
                dependency_issues_by_key[key] = issue
            queue.append((dependency_name, set(requirement.extras)))

    relevant_invalid_refs = sorted(
        ref
        for ref in inventory.invalid_requirement_refs
        if ref.split(":", 1)[0] in closure_names
    )
    for ref in relevant_invalid_refs:
        parent = ref.split(":", 1)[0]
        issue = RuntimeDependencyIssue(
            parent_package=parent,
            dependency_name="unknown",
            issue="invalid_requirement_metadata",
        )
        key = (parent, "unknown", issue.issue, None, None)
        dependency_issues_by_key[key] = issue
    dependency_issues = sorted(
        dependency_issues_by_key.values(),
        key=lambda item: (
            item.parent_package,
            item.dependency_name,
            item.issue,
        ),
    )

    closure_packages: list[RuntimeClosurePackageAssessment] = []
    for name in sorted(closure_names & set(packages)):
        package = packages[name]
        closure_packages.append(
            RuntimeClosurePackageAssessment(
                name=name,
                version=package.version,
                direct=name in direct_parsed,
                requested=package.requested,
                installer=package.installer,
                direct_url_reference=package.direct_url_reference,
                editable_install=package.editable_install,
                dependency_names=sorted(
                    dependency_names_by_parent.get(name, set())
                ),
                license_metadata_status=package.license_metadata_status,
                license_expression=package.license_expression,
                legacy_license_value_sha256=(
                    package.legacy_license_value_sha256
                ),
                license_classifiers=package.license_classifiers,
            )
        )

    prohibited = set(profile.prohibited_closure_packages)
    prohibited_in_closure = sorted(prohibited & closure_names)
    prohibited_installed_outside_closure = sorted(
        (prohibited & set(packages)) - closure_names
    )
    allowed_direct_urls = set(profile.allowed_direct_url_packages)
    installation_provenance_violations = sorted(
        [
            *(
                ["runtime:pythonpath_configured"]
                if profile.prohibit_pythonpath
                and inventory.pythonpath_configured
                else []
            ),
            *(
                f"{item.name}:editable_install"
                for item in closure_packages
                if profile.prohibit_editable_installs and item.editable_install
            ),
            *(
                f"{item.name}:unapproved_direct_url"
                for item in closure_packages
                if item.direct_url_reference
                and not item.editable_install
                and item.name not in allowed_direct_urls
            ),
        ]
    )
    bootstrap = set(profile.allowed_bootstrap_packages)
    extraneous = sorted(set(packages) - closure_names - bootstrap)
    license_missing = sorted(
        item.name
        for item in closure_packages
        if item.license_metadata_status == "missing"
    )

    gate_values = {
        "target-environment-ready": target_assessment.ready,
        "repository-source-ready": all(
            item.status == "matched" for item in source_checks
        ),
        "direct-requirements-ready": all(
            item.status == "matched" for item in direct_requirements
        ),
        "dependency-closure-ready": not dependency_issues,
        "prohibited-closure-absent": not prohibited_in_closure,
        "installation-provenance-ready": not installation_provenance_violations,
        "isolated-environment-ready": (
            not extraneous if profile.require_isolated_environment else True
        ),
        "license-metadata-ready": (
            not license_missing if profile.require_license_metadata else True
        ),
    }
    blocking_counts = {
        "target-environment-ready": len(mismatched_fields),
        "repository-source-ready": sum(
            item.status != "matched" for item in source_checks
        ),
        "direct-requirements-ready": sum(
            item.status != "matched" for item in direct_requirements
        ),
        "dependency-closure-ready": len(dependency_issues),
        "prohibited-closure-absent": len(prohibited_in_closure),
        "installation-provenance-ready": len(
            installation_provenance_violations
        ),
        "isolated-environment-ready": (
            len(extraneous) if profile.require_isolated_environment else 0
        ),
        "license-metadata-ready": (
            len(license_missing) if profile.require_license_metadata else 0
        ),
    }
    gates = [
        RuntimeClosureGate(
            gate_id=gate_id,
            ready=ready,
            blocking_count=blocking_counts[gate_id],
        )
        for gate_id, ready in gate_values.items()
    ]
    ready = all(gate_values.values())
    blocking_reasons = sorted(
        [
            *(f"target:{field}:mismatch" for field in mismatched_fields),
            *(
                f"source:{item.relative_path}:{item.status}"
                for item in source_checks
                if item.status != "matched"
            ),
            *(
                f"direct:{item.package_name}:{item.status}"
                for item in direct_requirements
                if item.status != "matched"
            ),
            *(
                f"dependency:{item.parent_package}:{item.dependency_name}:{item.issue}"
                for item in dependency_issues
            ),
            *(f"prohibited:{name}:in_closure" for name in prohibited_in_closure),
            *(
                f"install_provenance:{item}"
                for item in installation_provenance_violations
            ),
            *(
                f"extraneous:{name}"
                for name in extraneous
                if profile.require_isolated_environment
            ),
            *(
                f"license_metadata:{name}:missing"
                for name in license_missing
                if profile.require_license_metadata
            ),
        ]
    )
    counts = {
        "installed_total": len(packages),
        "direct_total": len(direct_requirements),
        "direct_matched": sum(
            item.status == "matched" for item in direct_requirements
        ),
        "closure_package_total": len(closure_packages),
        "dependency_issue_total": len(dependency_issues),
        "prohibited_in_closure_total": len(prohibited_in_closure),
        "prohibited_installed_outside_closure_total": len(
            prohibited_installed_outside_closure
        ),
        "installation_provenance_violation_total": len(
            installation_provenance_violations
        ),
        "extraneous_installed_total": len(extraneous),
        "license_metadata_missing_total": len(license_missing),
        "gate_total": len(gates),
        "gate_ready": sum(item.ready for item in gates),
    }
    return RuntimeClosureReport(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_status=profile.status,
        profile_sha256=profile_sha256,
        snapshot_sha256=snapshot_sha256,
        snapshot_version=inventory.snapshot_version,
        target=target_assessment,
        source_checks=source_checks,
        direct_requirements=direct_requirements,
        dependency_issues=dependency_issues,
        closure_packages=closure_packages,
        prohibited_in_closure=prohibited_in_closure,
        prohibited_installed_outside_closure=(
            prohibited_installed_outside_closure
        ),
        installation_provenance_violations=(
            installation_provenance_violations
        ),
        extraneous_installed_packages=extraneous,
        relevant_invalid_requirement_refs=relevant_invalid_refs,
        gates=gates,
        counts=counts,
        blocking_reasons=blocking_reasons,
        decision=(
            "candidate_closure_snapshot_ready"
            if ready
            else "blocked_runtime_closure_review"
        ),
        closure_snapshot_ready=ready,
        limitations=profile.limitations,
    )
