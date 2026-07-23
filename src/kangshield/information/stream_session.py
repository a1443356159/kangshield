from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from time import monotonic, sleep
from typing import Callable, ContextManager

from .contracts import (
    EvidenceLevel,
    SourceType,
    StreamCaptureReport,
    StreamRecoveryExerciseReport,
    StreamRecoveryInjectionResult,
    StreamSessionRecoveryEvent,
    StreamSessionReport,
    StreamSessionSegment,
)
from .privacy import sha256_file
from .stream_capture import (
    StreamCaptureConfig,
    StreamCaptureError,
    capture_stream,
    public_stream_capture_failure_code,
    validate_stream_capture_request,
)
from .stream_fault_matrix import (
    StreamFaultMatrixConfig,
    controlled_http_stream_endpoint,
)
from .stream_qualification import stream_signature_key, stream_track_signature


STREAM_SESSION_VERSION = "stream-session-v0.1.0"
STREAM_RECOVERY_EXERCISE_VERSION = "stream-recovery-exercise-v0.1.0"
LONG_RUNNING_SESSION_THRESHOLD_S = 30 * 60
_RECOVERY_BEHAVIORS = ("full", "reject", "full")


@dataclass(frozen=True)
class StreamSessionConfig:
    segment_count: int = 3
    failure_backoff_s: float = 1.0
    minimum_session_wall_s: float = 0.0
    capture: StreamCaptureConfig = field(default_factory=StreamCaptureConfig)

    def __post_init__(self) -> None:
        if not 2 <= self.segment_count <= 1000:
            raise ValueError("segment_count must be between 2 and 1000")
        if not isfinite(self.failure_backoff_s) or not (
            0 <= self.failure_backoff_s <= 3600
        ):
            raise ValueError(
                "failure_backoff_s must be finite and between 0 and 3600"
            )
        if not isfinite(self.minimum_session_wall_s) or not (
            0 <= self.minimum_session_wall_s <= 7 * 24 * 3600
        ):
            raise ValueError(
                "minimum_session_wall_s must be finite and at most seven days"
            )


@dataclass(frozen=True)
class StreamSessionResult:
    report: StreamSessionReport
    capture_reports: tuple[StreamCaptureReport, ...]


@dataclass(frozen=True)
class StreamRecoveryExerciseConfig:
    session: StreamSessionConfig = field(
        default_factory=lambda: StreamSessionConfig(
            segment_count=3,
            failure_backoff_s=0.1,
            capture=StreamCaptureConfig(
                duration_s=2.0,
                minimum_duration_s=1.5,
                open_timeout_s=1.0,
                read_timeout_s=1.0,
            ),
        )
    )

    def __post_init__(self) -> None:
        if self.session.segment_count != 3:
            raise ValueError("recovery exercise requires exactly three segments")
        if not self.session.capture.require_audio:
            raise ValueError("recovery exercise requires the audio track")
        if self.session.capture.transport != "auto":
            raise ValueError("loopback HTTP recovery exercise requires auto transport")


@dataclass(frozen=True)
class StreamRecoveryExerciseResult:
    report: StreamRecoveryExerciseReport
    capture_reports: tuple[StreamCaptureReport, ...]


EndpointContextFactory = Callable[[int], ContextManager[str]]


def _timing_offsets(
    session_started: float,
    segment_started: float,
    segment_finished: float,
) -> tuple[int, int, int]:
    started_ms = max(0, round((segment_started - session_started) * 1000))
    finished_ms = max(
        started_ms,
        round((segment_finished - session_started) * 1000),
    )
    return started_ms, finished_ms, finished_ms - started_ms


def _recovery_events(
    segments: list[StreamSessionSegment],
) -> list[StreamSessionRecoveryEvent]:
    events: list[StreamSessionRecoveryEvent] = []
    streak_start: int | None = None
    streak_end: int | None = None
    for segment in segments:
        if segment.status != "captured_ready":
            if streak_start is None:
                streak_start = segment.segment_index
            streak_end = segment.segment_index
            continue
        if streak_start is None or streak_end is None:
            continue
        first_interrupted = segments[streak_start - 1]
        last_interrupted = segments[streak_end - 1]
        events.append(
            StreamSessionRecoveryEvent(
                interruption_start_segment_index=streak_start,
                interruption_end_segment_index=streak_end,
                recovered_segment_index=segment.segment_index,
                interrupted_segment_count=streak_end - streak_start + 1,
                reopen_delay_ms=(
                    segment.started_offset_ms
                    - last_interrupted.finished_offset_ms
                ),
                interruption_to_ready_artifact_ms=(
                    segment.finished_offset_ms
                    - first_interrupted.finished_offset_ms
                ),
            )
        )
        streak_start = None
        streak_end = None
    return events


def _longest_interruption_streak(
    segments: list[StreamSessionSegment],
) -> int:
    longest = 0
    current = 0
    for segment in segments:
        if segment.status == "captured_ready":
            current = 0
            continue
        current += 1
        longest = max(longest, current)
    return longest


def run_stream_session(
    *,
    artifacts_dir: Path,
    endpoint: str | None = None,
    endpoint_context_factory: EndpointContextFactory | None = None,
    endpoint_supplied_via_environment: bool = False,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.NETWORK_STREAM,
    device_ref: str | None = None,
    elder_ref: str | None = None,
    config: StreamSessionConfig | None = None,
) -> StreamSessionResult:
    config = config or StreamSessionConfig()
    artifacts_dir = Path(artifacts_dir)
    if not artifacts_dir.is_dir():
        raise FileNotFoundError(artifacts_dir)
    if (endpoint is None) == (endpoint_context_factory is None):
        raise ValueError(
            "provide exactly one of endpoint or endpoint_context_factory"
        )

    endpoint_scheme: str | None = None
    if endpoint is not None:
        endpoint_scheme = validate_stream_capture_request(
            endpoint=endpoint,
            evidence_level=evidence_level,
            source_type=source_type,
            device_ref=device_ref,
            config=config.capture,
        )

    segments: list[StreamSessionSegment] = []
    captures: list[StreamCaptureReport] = []
    signature_keys: set[tuple[tuple[tuple[str, object], ...], ...]] = set()
    session_started = monotonic()

    for segment_index in range(1, config.segment_count + 1):
        if segments and segments[-1].status != "captured_ready":
            sleep(config.failure_backoff_s)
        stem = f"stream-session-{segment_index:03d}"
        output_artifact = f"artifacts/{stem}.mkv"
        capture_report_artifact = f"reports/{stem}.json"
        output_path = artifacts_dir / f"{stem}.mkv"
        if output_path.exists():
            raise FileExistsError(output_path)

        segment_started = monotonic()
        endpoint_context: ContextManager[str]
        if endpoint_context_factory is None:
            endpoint_context = nullcontext(endpoint)
        else:
            endpoint_context = endpoint_context_factory(segment_index)
        try:
            with endpoint_context as segment_endpoint:
                segment_scheme = validate_stream_capture_request(
                    endpoint=segment_endpoint,
                    evidence_level=evidence_level,
                    source_type=source_type,
                    device_ref=device_ref,
                    config=config.capture,
                )
                if endpoint_scheme is None:
                    endpoint_scheme = segment_scheme
                elif segment_scheme != endpoint_scheme:
                    raise ValueError(
                        "all session segments must use the same endpoint scheme"
                    )
                capture = capture_stream(
                    endpoint=segment_endpoint,
                    output_path=output_path,
                    output_artifact=output_artifact,
                    evidence_level=evidence_level,
                    source_type=source_type,
                    device_ref=device_ref,
                    elder_ref=elder_ref,
                    config=config.capture,
                )
        except StreamCaptureError as error:
            segment_finished = monotonic()
            output_path.unlink(missing_ok=True)
            started_ms, finished_ms, elapsed_ms = _timing_offsets(
                session_started,
                segment_started,
                segment_finished,
            )
            gap_before_ms = (
                started_ms - segments[-1].finished_offset_ms
                if segments
                else started_ms
            )
            segments.append(
                StreamSessionSegment(
                    segment_index=segment_index,
                    status="failed",
                    started_offset_ms=started_ms,
                    finished_offset_ms=finished_ms,
                    elapsed_ms=elapsed_ms,
                    gap_before_ms=gap_before_ms,
                    failure_code=public_stream_capture_failure_code(error.code),
                )
            )
            continue

        segment_finished = monotonic()
        started_ms, finished_ms, elapsed_ms = _timing_offsets(
            session_started,
            segment_started,
            segment_finished,
        )
        gap_before_ms = (
            started_ms - segments[-1].finished_offset_ms
            if segments
            else started_ms
        )
        signature = stream_track_signature(capture)
        if signature:
            signature_keys.add(stream_signature_key(signature))
        requested_ready = (
            capture.same_container_multimodal_ready
            if config.capture.require_audio
            else capture.capture_artifact_ready
        )
        timing = capture.media_probe.container_timing
        segments.append(
            StreamSessionSegment(
                segment_index=segment_index,
                status=(
                    "captured_ready" if requested_ready else "captured_not_ready"
                ),
                started_offset_ms=started_ms,
                finished_offset_ms=finished_ms,
                elapsed_ms=elapsed_ms,
                gap_before_ms=gap_before_ms,
                output_artifact=output_artifact,
                capture_report_artifact=capture_report_artifact,
                captured_media_span_ms=capture.captured_media_span_ms,
                termination_reason=capture.termination_reason,
                capture_artifact_ready=capture.capture_artifact_ready,
                same_container_multimodal_ready=(
                    capture.same_container_multimodal_ready
                ),
                track_signature=signature,
                audio_minus_video_start_ms=(
                    timing.audio_minus_video_start_ms if timing else None
                ),
            )
        )
        captures.append(capture)

    if endpoint_scheme is None:
        raise RuntimeError("session did not resolve an endpoint scheme")
    captured_count = sum(item.status != "failed" for item in segments)
    ready_count = sum(item.status == "captured_ready" for item in segments)
    not_ready_count = sum(
        item.status == "captured_not_ready" for item in segments
    )
    failed_count = sum(item.status == "failed" for item in segments)
    signature_count = len(signature_keys)
    signatures_consistent = bool(
        captured_count > 0
        and sum(bool(item.track_signature) for item in segments) == captured_count
        and signature_count == 1
    )
    artifact_paths = [
        item.output_artifact for item in segments if item.output_artifact
    ]
    independent_artifacts = bool(
        captured_count > 0 and len(artifact_paths) == len(set(artifact_paths))
    )
    recovery_events = _recovery_events(segments)
    reopen_attempted = any(
        item.status != "captured_ready" and item.segment_index < config.segment_count
        for item in segments
    )
    all_capture_ready = bool(
        ready_count == config.segment_count
        and not_ready_count == 0
        and failed_count == 0
        and independent_artifacts
        and signatures_consistent
        and signature_count == 1
    )
    session_elapsed_ms = segments[-1].finished_offset_ms
    minimum_session_wall_ms = round(config.minimum_session_wall_s * 1000)
    duration_ready = session_elapsed_ms >= minimum_session_wall_ms
    session_ready = all_capture_ready and duration_ready
    long_run_threshold_ms = LONG_RUNNING_SESSION_THRESHOLD_S * 1000
    long_running = bool(
        session_ready
        and minimum_session_wall_ms >= long_run_threshold_ms
        and session_elapsed_ms >= long_run_threshold_ms
    )
    report = StreamSessionReport(
        session_version=STREAM_SESSION_VERSION,
        evidence_level=evidence_level,
        source_type=source_type,
        endpoint_scheme=endpoint_scheme,
        endpoint_supplied_via_environment=endpoint_supplied_via_environment,
        transport=config.capture.transport,
        segment_count=config.segment_count,
        requested_duration_ms_per_segment=round(config.capture.duration_s * 1000),
        minimum_duration_ms_per_segment=round(
            config.capture.minimum_duration_s * 1000
        ),
        open_timeout_ms=round(config.capture.open_timeout_s * 1000),
        read_timeout_ms=round(config.capture.read_timeout_s * 1000),
        audio_required=config.capture.require_audio,
        failure_backoff_ms=round(config.failure_backoff_s * 1000),
        minimum_session_wall_ms=minimum_session_wall_ms,
        session_elapsed_ms=session_elapsed_ms,
        segments=segments,
        recovery_events=recovery_events,
        captured_segment_count=captured_count,
        ready_segment_count=ready_count,
        not_ready_segment_count=not_ready_count,
        failed_segment_count=failed_count,
        longest_interruption_streak=_longest_interruption_streak(segments),
        unique_track_signature_count=signature_count,
        track_signatures_consistent=signatures_consistent,
        independent_segment_artifacts_proven=independent_artifacts,
        supervisor_reopen_attempted=reopen_attempted,
        supervisor_reopen_recovery_observed=bool(recovery_events),
        all_segment_capture_gate_ready=all_capture_ready,
        session_duration_gate_ready=duration_ready,
        session_gate_ready=session_ready,
        segmented_session_long_running_stability_proven=long_running,
        limitations=[
            "segments_are_independent_artifacts_and_are_never_silently_concatenated",
            "supervisor_reopen_observation_is_not_same_connection_reconnect_proof",
            "unknown_failure_cause_cannot_prove_involuntary_disconnect_recovery",
            "thirty_minute_declared_and_observed_wall_time_is_required_for_long_run_proof",
            "no_network_impairment_is_injected_or_measured_by_this_command",
            "container_pts_does_not_prove_capture_clock_accuracy_or_drift",
            "fixture_sessions_cannot_prove_target_device_or_platform_access",
            "raw_media_requires_consent_controlled_storage_and_deletion",
            "this_stage_does_not_emit_risk_assessment_or_alert",
        ],
    )
    return StreamSessionResult(report=report, capture_reports=tuple(captures))


def _telemetry_delta(before, after) -> dict[str, int]:
    return {
        name: getattr(after, name) - getattr(before, name)
        for name in (
            "request_count",
            "body_bytes_sent",
            "body_chunk_count",
            "rejection_event_count",
        )
    }


def exercise_stream_recovery(
    *,
    fixture_path: Path,
    artifacts_dir: Path,
    config: StreamRecoveryExerciseConfig | None = None,
) -> StreamRecoveryExerciseResult:
    config = config or StreamRecoveryExerciseConfig()
    fixture_path = Path(fixture_path)
    artifacts_dir = Path(artifacts_dir)
    if not fixture_path.is_file():
        raise FileNotFoundError(fixture_path)
    if not artifacts_dir.is_dir():
        raise FileNotFoundError(artifacts_dir)
    fixture_size = fixture_path.stat().st_size
    if fixture_size <= 0:
        raise ValueError("recovery exercise fixture must not be empty")
    fixture_sha256 = sha256_file(fixture_path)
    server_config = StreamFaultMatrixConfig(
        capture=config.session.capture,
        stall_duration_s=max(
            config.session.capture.open_timeout_s,
            config.session.capture.read_timeout_s,
        )
        + 1.0,
    )
    telemetry_by_segment: dict[int, dict[str, int]] = {}

    with controlled_http_stream_endpoint(
        fixture_path,
        "full",
        body_byte_limit=None,
        config=server_config,
    ) as controlled_endpoint:

        def endpoint_context_factory(segment_index: int) -> ContextManager[str]:
            @contextmanager
            def configured_endpoint():
                behavior = _RECOVERY_BEHAVIORS[segment_index - 1]
                controlled_endpoint.set_behavior(behavior)
                before = controlled_endpoint.telemetry()
                try:
                    yield controlled_endpoint.url
                finally:
                    after = controlled_endpoint.telemetry()
                    telemetry_by_segment[segment_index] = _telemetry_delta(
                        before,
                        after,
                    )

            return configured_endpoint()

        session_result = run_stream_session(
            artifacts_dir=artifacts_dir,
            endpoint_context_factory=endpoint_context_factory,
            endpoint_supplied_via_environment=False,
            evidence_level=EvidenceLevel.E1,
            source_type=SourceType.FIXTURE,
            config=config.session,
        )

    if (
        fixture_path.stat().st_size != fixture_size
        or sha256_file(fixture_path) != fixture_sha256
    ):
        for segment in session_result.report.segments:
            if segment.output_artifact:
                (artifacts_dir / Path(segment.output_artifact).name).unlink(
                    missing_ok=True
                )
        raise RuntimeError("recovery exercise fixture changed during execution")

    injections: list[StreamRecoveryInjectionResult] = []
    for segment_index, behavior in enumerate(_RECOVERY_BEHAVIORS, start=1):
        telemetry = telemetry_by_segment[segment_index]
        exercised = bool(
            telemetry["request_count"] > 0
            and (
                (
                    behavior == "full"
                    and telemetry["body_bytes_sent"] > 0
                    and telemetry["rejection_event_count"] == 0
                )
                or (
                    behavior == "reject"
                    and telemetry["body_bytes_sent"] == 0
                    and telemetry["rejection_event_count"] > 0
                )
            )
        )
        injections.append(
            StreamRecoveryInjectionResult(
                segment_index=segment_index,
                behavior=behavior,
                **telemetry,
                scenario_exercised=exercised,
            )
        )

    all_exercised = all(item.scenario_exercised for item in injections)
    session = session_result.report
    statuses = [item.status for item in session.segments]
    gate = bool(
        all_exercised
        and statuses == ["captured_ready", "failed", "captured_ready"]
        and session.segments[1].failure_code == "open_failed"
        and session.unique_track_signature_count == 1
        and session.track_signatures_consistent
        and session.independent_segment_artifacts_proven
        and session.supervisor_reopen_attempted
        and session.supervisor_reopen_recovery_observed
        and len(session.recovery_events) == 1
    )
    report = StreamRecoveryExerciseReport(
        exercise_version=STREAM_RECOVERY_EXERCISE_VERSION,
        fixture_sha256=fixture_sha256,
        fixture_byte_size=fixture_size,
        injections=injections,
        all_injections_exercised=all_exercised,
        session=session,
        controlled_supervisor_recovery_gate_ready=gate,
        limitations=[
            "http_503_is_a_controlled_rejection_not_an_involuntary_disconnect",
            "fixture_endpoint_does_not_prove_rtsp_or_target_device_behavior",
            "supervisor_reopen_creates_a_new_artifact_and_never_joins_raw_media",
            "controlled_recovery_does_not_prove_packet_loss_or_network_tolerance",
            "short_three_segment_exercise_does_not_prove_long_running_stability",
            "raw_media_requires_consent_controlled_storage_and_deletion",
            "this_stage_does_not_emit_risk_assessment_or_alert",
        ],
    )
    return StreamRecoveryExerciseResult(
        report=report,
        capture_reports=session_result.capture_reports,
    )
