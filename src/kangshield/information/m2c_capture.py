from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .container_timing import DEFAULT_PACKET_SCAN_LIMIT
from .contracts import (
    EVIDENCE_RANK,
    EvidenceLevel,
    M2cCaptureReadinessReport,
    M2cClipReadiness,
    MediaProbeReport,
    Modality,
    PrivacyLevel,
    QualityIssue,
    QualityStatus,
    Severity,
    SourceAsset,
    SourceType,
    ensure_source_evidence_compatible,
)
from .media_probe import probe_media
from .privacy import safe_local_uri, sha256_file


ASSESSOR_VERSION = "m2c-capture-readiness-v0.1.0"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
ConfigModel = TypeVar("ConfigModel", bound=BaseModel)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _FileReference(_StrictModel):
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    byte_size: int = Field(gt=0)


class _Device(_StrictModel):
    device_ref: str = Field(min_length=3)
    model: str = Field(min_length=1)
    firmware_version: str = Field(min_length=1)
    capability_snapshot: _FileReference
    acquisition_method: Literal[
        "live_recording",
        "playback_export",
        "sdk_export",
        "api_response",
        "app_export",
        "synthetic_fixture",
    ]


class _CameraPlacement(_StrictModel):
    height_cm: float = Field(gt=0, le=500)
    pitch_degrees: float = Field(ge=-90, le=90)
    room_zone: str = Field(min_length=1)
    distance_markers_cm: list[int] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_distances(self) -> "_CameraPlacement":
        if any(distance <= 0 for distance in self.distance_markers_cm):
            raise ValueError("camera distance markers must be positive")
        if len(self.distance_markers_cm) != len(set(self.distance_markers_cm)):
            raise ValueError("camera distance markers must be unique")
        return self


class _ModelPolicyBinding(_StrictModel):
    variant_id: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)


class _HeldOutProtocol(_StrictModel):
    partition: Literal["held_out"]
    assignment_rule: Literal["all_manifest_clips"]
    partition_frozen_at: datetime
    labels_frozen_at: datetime
    first_inference_at: datetime | None = None
    model_policies: list[_ModelPolicyBinding] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_order_and_uniqueness(self) -> "_HeldOutProtocol":
        if self.labels_frozen_at < self.partition_frozen_at:
            raise ValueError("labels cannot be frozen before the partition")
        if (
            self.first_inference_at is not None
            and self.first_inference_at < self.labels_frozen_at
        ):
            raise ValueError("first inference cannot precede frozen labels")
        variants = [binding.variant_id for binding in self.model_policies]
        if len(variants) != len(set(variants)):
            raise ValueError("held-out model variants must be unique")
        return self


class _DeclaredTracks(_StrictModel):
    video_present: bool | None
    audio_present: bool | None
    video_codec: str | None = None
    audio_codec: str | None = None
    video_time_base: str | None = None
    audio_time_base: str | None = None


class _AnnotationWindow(_StrictModel):
    label: Literal[
        "person_present",
        "walking",
        "turning",
        "sit_down",
        "stand_up",
        "bend_pick",
        "bed_lie",
        "bed_rise",
        "furniture_occlusion",
        "simulated_fall",
        "speech",
    ]
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    certainty: Literal["certain", "uncertain"]

    @model_validator(mode="after")
    def validate_window(self) -> "_AnnotationWindow":
        if self.end_ms <= self.start_ms:
            raise ValueError("annotation end must be after start")
        return self


class _SynchronizationEvent(_StrictModel):
    event_id: str = Field(min_length=1)
    position: Literal["start", "end"]
    video_ms: int = Field(ge=0)
    audio_ms: int = Field(ge=0)
    annotation_method: Literal[
        "manual_frame_and_waveform",
        "automatic_fixture",
    ]
    certainty: Literal["certain", "uncertain"]


class _Safety(_StrictModel):
    simulated_fall: bool
    safety_mat: bool
    spotter_present: bool
    area_cleared: bool


class _Clip(_StrictModel):
    scenario_id: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    lighting: Literal["day", "night"]
    night_vision: bool
    distance_band: Literal["near", "mid", "far"]
    occlusion: Literal["none", "furniture_partial"]
    expected_person_presence: Literal["absent", "present"]
    expected_person_count: int = Field(ge=0)
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    byte_size: int = Field(gt=0)
    media_start_at: datetime
    duration_ms: int = Field(gt=0)
    audio_expected: bool
    tracks: _DeclaredTracks
    synchronization_events: list[_SynchronizationEvent] = Field(
        default_factory=list
    )
    annotation_windows: list[_AnnotationWindow] = Field(default_factory=list)
    safety: _Safety
    issues: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_people_windows_and_synchronization(self) -> "_Clip":
        if self.expected_person_presence == "absent":
            if self.expected_person_count != 0:
                raise ValueError("absent clip must expect zero people")
            if self.annotation_windows:
                raise ValueError("absent clip cannot contain person/action windows")
        else:
            if self.expected_person_count < 1:
                raise ValueError("present clip must expect at least one person")
            if "person_present" not in {
                window.label for window in self.annotation_windows
            }:
                raise ValueError("present clip requires a person_present window")
        if any(window.end_ms > self.duration_ms for window in self.annotation_windows):
            raise ValueError("annotation window exceeds clip duration")
        if any(
            max(event.video_ms, event.audio_ms) > self.duration_ms
            for event in self.synchronization_events
        ):
            raise ValueError("synchronization event exceeds clip duration")
        positions = [event.position for event in self.synchronization_events]
        if len(positions) != len(set(positions)):
            raise ValueError("synchronization positions must be unique per clip")
        if self.synchronization_events and set(positions) != {"start", "end"}:
            raise ValueError("synchronization requires both start and end events")
        if self.synchronization_events and not self.audio_expected:
            raise ValueError("synchronization events require expected audio")
        if self.scenario == "simulated_fall":
            if not all(
                (
                    self.safety.simulated_fall,
                    self.safety.safety_mat,
                    self.safety.spotter_present,
                    self.safety.area_cleared,
                )
            ):
                raise ValueError("simulated fall requires every safety control")
        elif self.safety.simulated_fall:
            raise ValueError("non-fall scenario cannot claim simulated fall")
        return self


class _SleepExport(_StrictModel):
    source_kind: Literal["api_response", "sdk_export", "app_export"]
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    byte_size: int = Field(gt=0)
    requested_at: datetime
    covered_start_at: datetime | None = None
    covered_end_at: datetime | None = None
    device_timezone: str = Field(min_length=1)
    documentation_version: str = Field(min_length=1)
    known_units: dict[str, str] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_coverage(self) -> "_SleepExport":
        if (self.covered_start_at is None) != (self.covered_end_at is None):
            raise ValueError("sleep coverage requires both start and end")
        if (
            self.covered_start_at is not None
            and self.covered_end_at is not None
            and self.covered_end_at <= self.covered_start_at
        ):
            raise ValueError("sleep coverage end must be after start")
        return self


class _CaptureManifest(_StrictModel):
    schema_version: Literal["1.1"]
    template_only: bool
    synthetic: bool
    capture_id: str = Field(min_length=3)
    captured_start_at: datetime
    captured_end_at: datetime
    operator_ref: str = Field(min_length=3)
    participant_ref: str = Field(min_length=3)
    consent: _FileReference
    devices: list[_Device] = Field(min_length=1)
    camera_placement: _CameraPlacement
    held_out_protocol: _HeldOutProtocol
    clips: list[_Clip] = Field(min_length=1)
    sleep_exports: list[_SleepExport] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_capture(self) -> "_CaptureManifest":
        if self.captured_end_at <= self.captured_start_at:
            raise ValueError("capture end must be after start")
        datetimes = [
            self.captured_start_at,
            self.captured_end_at,
            self.held_out_protocol.partition_frozen_at,
            self.held_out_protocol.labels_frozen_at,
        ]
        datetimes.extend(clip.media_start_at for clip in self.clips)
        if any(value.utcoffset() is None for value in datetimes):
            raise ValueError("capture datetimes must include an explicit timezone")
        if self.held_out_protocol.partition_frozen_at > self.captured_start_at:
            raise ValueError("held-out partition must be frozen before capture starts")
        if self.held_out_protocol.labels_frozen_at < self.captured_end_at:
            raise ValueError("held-out labels must be frozen after capture ends")
        for clip in self.clips:
            clip_end = clip.media_start_at.timestamp() + clip.duration_ms / 1000
            if clip.media_start_at < self.captured_start_at:
                raise ValueError("clip starts before the capture interval")
            if clip_end > self.captured_end_at.timestamp() + 0.001:
                raise ValueError("clip ends after the capture interval")
        scenario_ids = [clip.scenario_id for clip in self.clips]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario ids must be unique in a capture manifest")
        paths = [clip.relative_path for clip in self.clips]
        if len(paths) != len(set(paths)):
            raise ValueError("clip paths must be unique in a capture manifest")
        device_refs = [device.device_ref for device in self.devices]
        if len(device_refs) != len(set(device_refs)):
            raise ValueError("device refs must be unique")
        return self


class _ScenarioPolicy(_StrictModel):
    scenario_id: str
    scenario: str
    lighting: Literal["day", "night"]
    night_vision: bool
    distance_band: Literal["near", "mid", "far"]
    occlusion: Literal["none", "furniture_partial"]
    expected_person_presence: Literal["absent", "present"]
    required_annotation_labels: list[str] = Field(default_factory=list)
    coverage_tags: list[str] = Field(default_factory=list)


class _RequiredModelPolicy(_StrictModel):
    variant_id: str
    sha256: str = Field(pattern=SHA256_PATTERN)


class _CapturePolicy(_StrictModel):
    schema_version: Literal["1.0"]
    policy_version: str
    target_camera_model: str
    target_sleep_model: str
    minimum_usable_clips_for_model_retest: int = Field(ge=1)
    minimum_model_variants: int = Field(ge=1)
    minimum_synchronized_audio_clips: int = Field(ge=1)
    maximum_duration_difference_ms: int = Field(ge=0)
    required_model_policies: list[_RequiredModelPolicy]
    required_core_coverage_tags: list[str]
    full_matrix_scenario_ids: list[str]
    scenarios: list[_ScenarioPolicy]

    @model_validator(mode="after")
    def validate_policy(self) -> "_CapturePolicy":
        ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("capture policy scenario ids must be unique")
        if not set(self.full_matrix_scenario_ids).issubset(ids):
            raise ValueError("full matrix references unknown scenarios")
        known_tags = {
            tag for scenario in self.scenarios for tag in scenario.coverage_tags
        }
        if not set(self.required_core_coverage_tags).issubset(known_tags):
            raise ValueError("core gate references unknown coverage tags")
        variants = [binding.variant_id for binding in self.required_model_policies]
        if len(variants) != len(set(variants)):
            raise ValueError("required model policy variants must be unique")
        if len(variants) < self.minimum_model_variants:
            raise ValueError("required model policies are below the minimum count")
        return self


@dataclass(frozen=True)
class M2cCaptureAssessment:
    manifest_asset: SourceAsset
    media_reports: list[MediaProbeReport]
    sleep_assets: list[SourceAsset]
    report: M2cCaptureReadinessReport


def _load_json(path: Path, model: type[ConfigModel]) -> ConfigModel:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("capture configuration could not be read as JSON") from error
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise ValueError("capture configuration schema validation failed") from error


def _issue(
    code: str,
    severity: Severity,
    message: str,
    *,
    scope: str | None = None,
) -> QualityIssue:
    details = {"scope": scope} if scope else {}
    return QualityIssue(
        code=code,
        severity=severity,
        message=message,
        details=details,
    )


def _safe_bundle_path(bundle_root: Path, relative_path: str) -> Path:
    pure = PurePosixPath(relative_path)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\\" in relative_path
    ):
        raise ValueError("bundle reference must be a normalized relative path")
    root = bundle_root.resolve()
    resolved = (root / Path(*pure.parts)).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("bundle reference escapes the capture directory")
    return resolved


def _verify_reference(
    bundle_root: Path,
    reference: _FileReference | _ModelPolicyBinding | _SleepExport,
    *,
    scope: str,
) -> tuple[Path | None, list[QualityIssue]]:
    issues: list[QualityIssue] = []
    try:
        path = _safe_bundle_path(bundle_root, reference.relative_path)
    except ValueError:
        return None, [
            _issue(
                "bundle_path_invalid",
                Severity.ERROR,
                "A capture bundle reference is not a safe relative path",
                scope=scope,
            )
        ]
    if not path.is_file():
        return None, [
            _issue(
                "bundle_file_missing",
                Severity.ERROR,
                "A referenced capture bundle file is missing",
                scope=scope,
            )
        ]
    actual_size = path.stat().st_size
    if hasattr(reference, "byte_size") and actual_size != reference.byte_size:
        issues.append(
            _issue(
                "bundle_byte_size_mismatch",
                Severity.ERROR,
                "A referenced file byte size differs from the frozen manifest",
                scope=scope,
            )
        )
    if sha256_file(path) != reference.sha256:
        issues.append(
            _issue(
                "bundle_sha256_mismatch",
                Severity.ERROR,
                "A referenced file digest differs from the frozen manifest",
                scope=scope,
            )
        )
    return path, issues


def _reference_asset(
    path: Path,
    *,
    modality: Modality,
    source_type: SourceType,
    evidence_level: EvidenceLevel,
) -> SourceAsset:
    digest = sha256_file(path)
    return SourceAsset(
        asset_id=f"asset_{digest[:20]}",
        modality=modality,
        source_type=source_type,
        evidence_level=evidence_level,
        uri=safe_local_uri(path, digest),
        sha256=digest,
        byte_size=path.stat().st_size,
        privacy_level=PrivacyLevel.RAW_SENSITIVE,
        metadata={
            "filename_suffix": path.suffix.lower(),
            "source_path_persisted": False,
        },
    )


def _has_fixture_marker(path: Path) -> bool:
    if path.suffix.lower() != ".json":
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return isinstance(payload, dict) and any(
        payload.get(key) is True for key in ("fixture", "synthetic")
    )


def _scenario_issues(
    clip: _Clip,
    policy: _ScenarioPolicy | None,
    *,
    synthetic: bool,
) -> list[QualityIssue]:
    scope = clip.scenario_id
    if policy is None:
        return [
            _issue(
                "scenario_not_in_policy",
                Severity.ERROR,
                "The clip scenario id is not present in the frozen policy",
                scope=scope,
            )
        ]
    issues: list[QualityIssue] = []
    comparisons = {
        "scenario": (clip.scenario, policy.scenario),
        "lighting": (clip.lighting, policy.lighting),
        "night_vision": (clip.night_vision, policy.night_vision),
        "distance_band": (clip.distance_band, policy.distance_band),
        "occlusion": (clip.occlusion, policy.occlusion),
        "expected_person_presence": (
            clip.expected_person_presence,
            policy.expected_person_presence,
        ),
    }
    if any(observed != expected for observed, expected in comparisons.values()):
        issues.append(
            _issue(
                "scenario_contract_mismatch",
                Severity.ERROR,
                "Clip metadata differs from the frozen scenario contract",
                scope=scope,
            )
        )
    labels = {window.label for window in clip.annotation_windows}
    missing_labels = set(policy.required_annotation_labels) - labels
    if missing_labels:
        issues.append(
            _issue(
                "required_annotation_missing",
                Severity.ERROR,
                "The clip is missing one or more required annotation labels",
                scope=scope,
            )
        )
    if not synthetic and any(
        event.annotation_method == "automatic_fixture"
        for event in clip.synchronization_events
    ):
        issues.append(
            _issue(
                "fixture_sync_annotation_on_real_capture",
                Severity.ERROR,
                "A real capture cannot use the synthetic synchronization method",
                scope=scope,
            )
        )
    if clip.tracks.video_present is not True or clip.tracks.audio_present is None:
        issues.append(
            _issue(
                "declared_track_facts_incomplete",
                Severity.ERROR,
                "Post-capture video and audio track facts must be explicit",
                scope=scope,
            )
        )
    if clip.issues:
        issues.append(
            _issue(
                "capture_issue_declared",
                Severity.WARNING,
                "The operator declared one or more acquisition issues",
                scope=scope,
            )
        )
    return issues


def _synchronization_metrics(
    events: list[_SynchronizationEvent],
) -> tuple[float | None, float | None, float | None]:
    if {event.position for event in events} != {"start", "end"}:
        return None, None, None
    by_position = {event.position: event for event in events}
    start = by_position["start"]
    end = by_position["end"]
    start_offset = float(start.audio_ms - start.video_ms)
    end_offset = float(end.audio_ms - end.video_ms)
    elapsed_ms = end.video_ms - start.video_ms
    drift = (
        (end_offset - start_offset) * 60_000 / elapsed_ms
        if elapsed_ms > 0
        else None
    )
    return (
        round(start_offset, 3),
        round(end_offset, 3),
        round(drift, 3) if drift is not None else None,
    )


def _duration_ms(report: MediaProbeReport) -> float | None:
    if report.container_timing is not None:
        value = report.container_timing.container_duration_ms
        if value is not None:
            return value
    value = report.technical_metadata.get("duration_s")
    if isinstance(value, (int, float)):
        return float(value) * 1000
    return None


def assess_m2c_capture(
    manifest_path: Path,
    *,
    policy_path: Path,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.FIXTURE,
    packet_scan_limit_per_stream: int = DEFAULT_PACKET_SCAN_LIMIT,
) -> M2cCaptureAssessment:
    ensure_source_evidence_compatible(source_type, evidence_level)
    if packet_scan_limit_per_stream <= 0:
        raise ValueError("packet scan limit must be positive")
    manifest_path = Path(manifest_path)
    policy_path = Path(policy_path)
    if not manifest_path.is_file():
        raise FileNotFoundError("capture manifest not found")
    if not policy_path.is_file():
        raise FileNotFoundError("capture policy not found")
    manifest = _load_json(manifest_path, _CaptureManifest)
    policy = _load_json(policy_path, _CapturePolicy)
    bundle_root = manifest_path.parent
    manifest_asset = _reference_asset(
        manifest_path,
        modality=Modality.DEVICE_SNAPSHOT,
        source_type=source_type,
        evidence_level=evidence_level,
    )
    policy_sha256 = sha256_file(policy_path)
    capture_ref = f"capture_{manifest_asset.sha256[:16]}"
    issues: list[QualityIssue] = []

    consent_path, consent_issues = _verify_reference(
        bundle_root,
        manifest.consent,
        scope="consent",
    )
    issues.extend(consent_issues)
    consent_verified = consent_path is not None and not consent_issues
    if (
        consent_path is not None
        and not manifest.synthetic
        and _has_fixture_marker(consent_path)
    ):
        issue = _issue(
            "fixture_marker_on_real_capture",
            Severity.ERROR,
            "A capture declared as real references a fixture-marked file",
            scope="consent",
        )
        issues.append(issue)
        consent_verified = False

    devices_by_model: dict[str, list[_Device]] = {}
    verified_device_capabilities: dict[str, bool] = {}
    for device in manifest.devices:
        devices_by_model.setdefault(device.model, []).append(device)
        capability_path, reference_issues = _verify_reference(
            bundle_root,
            device.capability_snapshot,
            scope=f"device:{device.model}",
        )
        if not manifest.synthetic and device.acquisition_method == "synthetic_fixture":
            reference_issues.append(
                _issue(
                    "synthetic_acquisition_on_real_capture",
                    Severity.ERROR,
                    "A capture declared as real uses a synthetic acquisition method",
                    scope=f"device:{device.model}",
                )
            )
        if (
            capability_path is not None
            and not manifest.synthetic
            and _has_fixture_marker(capability_path)
        ):
            reference_issues.append(
                _issue(
                    "fixture_marker_on_real_capture",
                    Severity.ERROR,
                    "A capture declared as real references a fixture-marked file",
                    scope=f"device:{device.model}",
                )
            )
        issues.extend(reference_issues)
        verified_device_capabilities[device.model] = not reference_issues
    for target_model in (policy.target_camera_model, policy.target_sleep_model):
        count = len(devices_by_model.get(target_model, []))
        if count != 1:
            issues.append(
                _issue(
                    "target_device_count_invalid",
                    Severity.ERROR,
                    "The capture must bind exactly one required target device",
                    scope=f"device:{target_model}",
                )
            )

    model_policy_verified = 0
    required_model_policies = {
        binding.variant_id: binding.sha256
        for binding in policy.required_model_policies
    }
    bound_model_policies = {
        binding.variant_id: binding.sha256
        for binding in manifest.held_out_protocol.model_policies
    }
    for binding in manifest.held_out_protocol.model_policies:
        _, reference_issues = _verify_reference(
            bundle_root,
            binding,
            scope=f"model-policy:{binding.variant_id}",
        )
        issues.extend(reference_issues)
        if not reference_issues:
            model_policy_verified += 1
    model_policy_contract_match = (
        required_model_policies.items() <= bound_model_policies.items()
    )
    if not model_policy_contract_match:
        issues.append(
            _issue(
                "required_model_policy_mismatch",
                Severity.ERROR,
                "Held-out model variant ids or policy digests differ from the frozen gate",
            )
        )

    scenario_policies = {
        scenario.scenario_id: scenario for scenario in policy.scenarios
    }
    media_reports: list[MediaProbeReport] = []
    clip_results: list[M2cClipReadiness] = []
    usable_scenarios: set[str] = set()
    covered_tags: set[str] = set()
    annotation_counts: Counter[str] = Counter()
    synchronized_usable_clips = 0
    observed_media_digests: list[str] = []

    for clip in manifest.clips:
        clip_issues = _scenario_issues(
            clip,
            scenario_policies.get(clip.scenario_id),
            synthetic=manifest.synthetic,
        )
        path: Path | None
        try:
            path = _safe_bundle_path(bundle_root, clip.relative_path)
        except ValueError:
            path = None
            clip_issues.append(
                _issue(
                    "bundle_path_invalid",
                    Severity.ERROR,
                    "The media reference is not a safe relative path",
                    scope=clip.scenario_id,
                )
            )
        digest_match = False
        size_match = False
        probe_report: MediaProbeReport | None = None
        if path is None or not path.is_file():
            if path is not None:
                clip_issues.append(
                    _issue(
                        "media_file_missing",
                        Severity.ERROR,
                        "A referenced clip file is missing",
                        scope=clip.scenario_id,
                    )
                )
        else:
            actual_sha256 = sha256_file(path)
            observed_media_digests.append(actual_sha256)
            digest_match = actual_sha256 == clip.sha256
            size_match = path.stat().st_size == clip.byte_size
            if not digest_match:
                clip_issues.append(
                    _issue(
                        "media_sha256_mismatch",
                        Severity.ERROR,
                        "Clip bytes differ from the frozen manifest",
                        scope=clip.scenario_id,
                    )
                )
            if not size_match:
                clip_issues.append(
                    _issue(
                        "media_byte_size_mismatch",
                        Severity.ERROR,
                        "Clip byte size differs from the frozen manifest",
                        scope=clip.scenario_id,
                    )
                )
            try:
                probe_report = probe_media(
                    path,
                    evidence_level=evidence_level,
                    source_type=source_type,
                    require_audio_track=clip.audio_expected,
                    packet_scan_limit_per_stream=packet_scan_limit_per_stream,
                )
                media_reports.append(probe_report)
            except Exception as error:
                clip_issues.append(
                    _issue(
                        "media_probe_failed",
                        Severity.ERROR,
                        "The media probe did not complete",
                        scope=f"{clip.scenario_id}:{type(error).__name__}",
                    )
                )
        video_track_status = "unknown"
        audio_track_status = "unknown"
        probe_quality = QualityStatus.UNKNOWN
        media_asset_id = None
        if probe_report is not None:
            probe_quality = probe_report.observation.quality_status
            media_asset_id = probe_report.asset.asset_id
            if probe_report.container_timing is not None:
                video_track_status = probe_report.container_timing.video_track_status
                audio_track_status = probe_report.container_timing.audio_track_status
            if video_track_status != "present":
                clip_issues.append(
                    _issue(
                        "video_track_missing",
                        Severity.ERROR,
                        "The clip does not have a verified video track",
                        scope=clip.scenario_id,
                    )
                )
            if clip.tracks.video_present != (video_track_status == "present"):
                clip_issues.append(
                    _issue(
                        "declared_video_track_mismatch",
                        Severity.ERROR,
                        "Declared video-track status differs from the media probe",
                        scope=clip.scenario_id,
                    )
                )
            if clip.tracks.audio_present != (audio_track_status == "present"):
                clip_issues.append(
                    _issue(
                        "declared_audio_track_mismatch",
                        Severity.ERROR,
                        "Declared audio-track status differs from the media probe",
                        scope=clip.scenario_id,
                    )
                )
            observed_duration_ms = _duration_ms(probe_report)
            if (
                observed_duration_ms is None
                or abs(observed_duration_ms - clip.duration_ms)
                > policy.maximum_duration_difference_ms
            ):
                clip_issues.append(
                    _issue(
                        "media_duration_mismatch",
                        Severity.ERROR,
                        "Observed media duration is missing or outside policy tolerance",
                        scope=clip.scenario_id,
                    )
                )

        start_offset, end_offset, drift = _synchronization_metrics(
            clip.synchronization_events
        )
        has_errors = any(
            item.severity is Severity.ERROR for item in clip_issues
        )
        usable = (
            not has_errors
            and probe_report is not None
            and probe_quality is QualityStatus.PASS
        )
        labels = sorted({window.label for window in clip.annotation_windows})
        annotation_counts.update(labels)
        if usable:
            usable_scenarios.add(clip.scenario_id)
            scenario_policy = scenario_policies.get(clip.scenario_id)
            if scenario_policy is not None:
                covered_tags.update(scenario_policy.coverage_tags)
            if start_offset is not None and end_offset is not None:
                synchronized_usable_clips += 1
        result = M2cClipReadiness(
            clip_ref=f"clip_{clip.sha256[:16]}",
            scenario_id=clip.scenario_id,
            media_asset_id=media_asset_id,
            manifest_digest_match=digest_match,
            manifest_byte_size_match=size_match,
            probe_quality_status=probe_quality,
            video_track_status=video_track_status,
            audio_track_status=audio_track_status,
            annotation_labels=labels,
            annotation_window_count=len(clip.annotation_windows),
            synchronization_event_count=len(clip.synchronization_events),
            synchronization_offset_start_ms=start_offset,
            synchronization_offset_end_ms=end_offset,
            synchronization_drift_ms_per_minute=drift,
            usable_for_model_retest=usable,
            issues=clip_issues,
        )
        clip_results.append(result)
        issues.extend(clip_issues)

    duplicate_media_count = len(observed_media_digests) - len(
        set(observed_media_digests)
    )
    unique_media_ok = manifest.synthetic or duplicate_media_count == 0
    if not unique_media_ok:
        issues.append(
            _issue(
                "duplicate_media_content",
                Severity.ERROR,
                "A real capture reuses identical media bytes across clip entries",
            )
        )

    sleep_assets: list[SourceAsset] = []
    verified_sleep_exports = 0
    for index, export in enumerate(manifest.sleep_exports):
        path, export_issues = _verify_reference(
            bundle_root,
            export,
            scope=f"sleep-export:{index}",
        )
        if (
            path is not None
            and not manifest.synthetic
            and _has_fixture_marker(path)
        ):
            export_issues.append(
                _issue(
                    "fixture_marker_on_real_capture",
                    Severity.ERROR,
                    "A capture declared as real references a fixture-marked file",
                    scope=f"sleep-export:{index}",
                )
            )
        issues.extend(export_issues)
        if path is not None and not export_issues:
            verified_sleep_exports += 1
            sleep_assets.append(
                _reference_asset(
                    path,
                    modality=Modality.SLEEP,
                    source_type=source_type,
                    evidence_level=evidence_level,
                )
            )

    real_evidence = (
        source_type is not SourceType.FIXTURE
        and EVIDENCE_RANK[evidence_level] >= EVIDENCE_RANK[EvidenceLevel.E2]
        and not manifest.template_only
        and not manifest.synthetic
    )
    held_out_checks: dict[str, bool | int] = {
        "partition_frozen_before_capture": (
            manifest.held_out_protocol.partition_frozen_at
            <= manifest.captured_start_at
        ),
        "labels_frozen_after_capture": (
            manifest.held_out_protocol.labels_frozen_at
            >= manifest.captured_end_at
        ),
        "first_inference_after_labels": (
            manifest.held_out_protocol.first_inference_at is None
            or manifest.held_out_protocol.first_inference_at
            >= manifest.held_out_protocol.labels_frozen_at
        ),
        "model_policy_count": len(manifest.held_out_protocol.model_policies),
        "model_policy_verified_count": model_policy_verified,
        "required_model_policy_contract_match": model_policy_contract_match,
    }
    held_out_ready = (
        model_policy_verified == len(manifest.held_out_protocol.model_policies)
        and model_policy_verified >= policy.minimum_model_variants
        and model_policy_contract_match
        and all(
            bool(held_out_checks[name])
            for name in (
                "partition_frozen_before_capture",
                "labels_frozen_after_capture",
                "first_inference_after_labels",
            )
        )
    )
    missing_core_tags = sorted(
        set(policy.required_core_coverage_tags) - covered_tags
    )
    missing_matrix_scenarios = sorted(
        set(policy.full_matrix_scenario_ids) - usable_scenarios
    )
    target_camera_ready = (
        len(devices_by_model.get(policy.target_camera_model, [])) == 1
        and verified_device_capabilities.get(policy.target_camera_model, False)
    )
    target_sleep_ready = (
        len(devices_by_model.get(policy.target_sleep_model, [])) == 1
        and verified_device_capabilities.get(policy.target_sleep_model, False)
    )
    structural_camera_ready = (
        consent_verified
        and target_camera_ready
        and held_out_ready
        and len(usable_scenarios)
        >= policy.minimum_usable_clips_for_model_retest
        and not missing_core_tags
        and synchronized_usable_clips
        >= policy.minimum_synchronized_audio_clips
        and unique_media_ok
    )
    camera_ready = real_evidence and structural_camera_ready
    camera_matrix_complete = camera_ready and not missing_matrix_scenarios
    sleep_ready = (
        real_evidence
        and consent_verified
        and target_sleep_ready
        and verified_sleep_exports >= 1
    )
    m2c_ready = camera_matrix_complete and sleep_ready

    if not real_evidence:
        decision = "tooling_only" if structural_camera_ready else "not_ready"
    elif m2c_ready:
        decision = "ready_for_review"
    elif camera_ready and sleep_ready:
        decision = "camera_retest_ready_matrix_incomplete"
    elif camera_ready:
        decision = "camera_retest_ready_sleep_pending"
    else:
        decision = "not_ready"
    if m2c_ready:
        quality_status = QualityStatus.PASS
    elif decision == "tooling_only" or camera_ready or sleep_ready:
        quality_status = QualityStatus.PARTIAL
    else:
        quality_status = QualityStatus.FAIL

    report = M2cCaptureReadinessReport(
        assessor_version=ASSESSOR_VERSION,
        capture_ref=capture_ref,
        evidence_level=evidence_level,
        source_type=source_type,
        manifest_asset_id=manifest_asset.asset_id,
        manifest_sha256=manifest_asset.sha256,
        policy_version=policy.policy_version,
        policy_sha256=policy_sha256,
        template_only=manifest.template_only,
        synthetic=manifest.synthetic,
        clips=clip_results,
        counts={
            "declared_clip_count": len(manifest.clips),
            "usable_clip_count": len(usable_scenarios),
            "synchronized_usable_clip_count": synchronized_usable_clips,
            "duplicate_media_content_count": duplicate_media_count,
            "model_policy_count": len(manifest.held_out_protocol.model_policies),
            "model_policy_verified_count": model_policy_verified,
            "declared_sleep_export_count": len(manifest.sleep_exports),
            "verified_sleep_export_count": verified_sleep_exports,
            "error_count": sum(
                item.severity is Severity.ERROR for item in issues
            ),
            "warning_count": sum(
                item.severity is Severity.WARNING for item in issues
            ),
        },
        coverage={
            "usable_scenario_ids": sorted(usable_scenarios),
            "covered_core_tags": sorted(covered_tags),
            "missing_core_tags": missing_core_tags,
            "missing_full_matrix_scenario_ids": missing_matrix_scenarios,
            "annotation_labels": sorted(annotation_counts),
            "minimum_usable_clips": policy.minimum_usable_clips_for_model_retest,
            "minimum_synchronized_audio_clips": (
                policy.minimum_synchronized_audio_clips
            ),
            "unique_media_required_for_real_capture": True,
        },
        held_out_checks=held_out_checks,
        camera_ready_for_model_retest=camera_ready,
        camera_matrix_complete=camera_matrix_complete,
        sleep_sample_ready_for_profiling=sleep_ready,
        m2c_ready_for_review=m2c_ready,
        decision=decision,
        quality_status=quality_status,
        issues=issues,
        limitations=[
            "fixture_or_e1_inputs_can_validate_tooling_but_never_create_device_evidence",
            "annotation_windows_and_identity_references_are_not_copied_to_the_report",
            "manual_sync_events_measure_av_offset_and_drift_but_not_wall_clock_accuracy",
            "capture_readiness_does_not_select_a_pose_or_speech_model",
            "sleep_export_readiness_only_allows_field_profiling_not_medical_semantics",
        ],
    )
    return M2cCaptureAssessment(
        manifest_asset=manifest_asset,
        media_reports=media_reports,
        sleep_assets=sleep_assets,
        report=report,
    )
