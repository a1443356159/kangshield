from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

from .contracts import (
    EvidenceLevel,
    SourceType,
    StreamCaptureReport,
    StreamQualificationAttempt,
    StreamQualificationReport,
    StreamQualificationTrackSignature,
)
from .stream_capture import (
    StreamCaptureConfig,
    StreamCaptureError,
    capture_stream,
    validate_stream_capture_request,
)


STREAM_QUALIFICATION_VERSION = "stream-qualification-v0.1.0"
_PUBLIC_FAILURE_CODES = frozenset(
    {
        "open_failed",
        "remux_failed",
        "video_track_layout_invalid",
        "audio_track_layout_invalid",
        "required_audio_track_missing",
        "packet_timestamp_missing",
        "video_keyframe_missing",
        "video_packets_missing",
        "audio_packets_missing",
        "media_artifact_missing",
        "output_verification_failed",
    }
)


@dataclass(frozen=True)
class StreamQualificationConfig:
    attempt_count: int = 3
    capture: StreamCaptureConfig = field(default_factory=StreamCaptureConfig)

    def __post_init__(self) -> None:
        if not 2 <= self.attempt_count <= 20:
            raise ValueError("attempt_count must be between 2 and 20")


@dataclass(frozen=True)
class StreamQualificationResult:
    report: StreamQualificationReport
    capture_reports: tuple[StreamCaptureReport, ...]


def _track_signature(
    report: StreamCaptureReport,
) -> list[StreamQualificationTrackSignature]:
    timing = report.media_probe.container_timing
    if timing is None:
        return []
    order = {"video": 0, "audio": 1}
    return [
        StreamQualificationTrackSignature(
            stream_type=stream.stream_type,
            codec_name=stream.codec_name,
            time_base=stream.time_base,
            width_px=(
                stream.technical_metadata.get("width")
                if stream.stream_type == "video"
                else None
            ),
            height_px=(
                stream.technical_metadata.get("height")
                if stream.stream_type == "video"
                else None
            ),
            pixel_format=(
                stream.technical_metadata.get("pixel_format")
                if stream.stream_type == "video"
                else None
            ),
            average_rate=(
                stream.technical_metadata.get("average_rate")
                if stream.stream_type == "video"
                else None
            ),
            sample_rate_hz=(
                stream.technical_metadata.get("sample_rate_hz")
                if stream.stream_type == "audio"
                else None
            ),
            channels=(
                stream.technical_metadata.get("channels")
                if stream.stream_type == "audio"
                else None
            ),
            channel_layout=(
                stream.technical_metadata.get("channel_layout")
                if stream.stream_type == "audio"
                else None
            ),
        )
        for stream in sorted(
            timing.streams,
            key=lambda item: (order[item.stream_type], item.stream_index),
        )
    ]


def _signature_key(
    signature: list[StreamQualificationTrackSignature],
) -> tuple[tuple[tuple[str, object], ...], ...]:
    return tuple(
        tuple(sorted(item.model_dump(mode="json").items())) for item in signature
    )


def qualify_stream(
    *,
    endpoint: str,
    artifacts_dir: Path,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.NETWORK_STREAM,
    device_ref: str | None = None,
    elder_ref: str | None = None,
    config: StreamQualificationConfig | None = None,
) -> StreamQualificationResult:
    config = config or StreamQualificationConfig()
    artifacts_dir = Path(artifacts_dir)
    if not artifacts_dir.is_dir():
        raise FileNotFoundError(artifacts_dir)
    endpoint_scheme = validate_stream_capture_request(
        endpoint=endpoint,
        evidence_level=evidence_level,
        source_type=source_type,
        device_ref=device_ref,
        config=config.capture,
    )

    attempts: list[StreamQualificationAttempt] = []
    captures: list[StreamCaptureReport] = []
    signature_keys: set[tuple[tuple[tuple[str, object], ...], ...]] = set()

    for attempt_index in range(1, config.attempt_count + 1):
        stem = f"stream-capture-{attempt_index:03d}"
        output_artifact = f"artifacts/{stem}.mkv"
        capture_report_artifact = f"reports/{stem}.json"
        output_path = artifacts_dir / f"{stem}.mkv"
        if output_path.exists():
            raise FileExistsError(output_path)
        started = monotonic()
        try:
            capture = capture_stream(
                endpoint=endpoint,
                output_path=output_path,
                output_artifact=output_artifact,
                evidence_level=evidence_level,
                source_type=source_type,
                device_ref=device_ref,
                elder_ref=elder_ref,
                config=config.capture,
            )
        except StreamCaptureError as error:
            output_path.unlink(missing_ok=True)
            failure_code = (
                error.code
                if error.code in _PUBLIC_FAILURE_CODES
                else "stream_capture_failed"
            )
            attempts.append(
                StreamQualificationAttempt(
                    attempt_index=attempt_index,
                    status="failed",
                    elapsed_ms=max(0, round((monotonic() - started) * 1000)),
                    failure_code=failure_code,
                )
            )
            continue

        signature = _track_signature(capture)
        if signature:
            signature_keys.add(_signature_key(signature))
        requested_ready = (
            capture.same_container_multimodal_ready
            if config.capture.require_audio
            else capture.capture_artifact_ready
        )
        timing = capture.media_probe.container_timing
        attempts.append(
            StreamQualificationAttempt(
                attempt_index=attempt_index,
                status=(
                    "captured_ready" if requested_ready else "captured_not_ready"
                ),
                elapsed_ms=max(0, round((monotonic() - started) * 1000)),
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

    captured_count = sum(item.status != "failed" for item in attempts)
    ready_count = sum(item.status == "captured_ready" for item in attempts)
    not_ready_count = sum(
        item.status == "captured_not_ready" for item in attempts
    )
    failed_count = sum(item.status == "failed" for item in attempts)
    unique_signature_count = len(signature_keys)
    signatures_consistent = bool(
        captured_count > 0
        and sum(bool(item.track_signature) for item in attempts) == captured_count
        and unique_signature_count == 1
    )
    repeated_ready = bool(
        ready_count == config.attempt_count
        and failed_count == 0
        and not_ready_count == 0
        and signatures_consistent
        and unique_signature_count == 1
    )
    report = StreamQualificationReport(
        qualification_version=STREAM_QUALIFICATION_VERSION,
        evidence_level=evidence_level,
        source_type=source_type,
        endpoint_scheme=endpoint_scheme,
        transport=config.capture.transport,
        attempt_count=config.attempt_count,
        requested_duration_ms_per_attempt=round(
            config.capture.duration_s * 1000
        ),
        minimum_duration_ms_per_attempt=round(
            config.capture.minimum_duration_s * 1000
        ),
        audio_required=config.capture.require_audio,
        attempts=attempts,
        captured_attempt_count=captured_count,
        ready_attempt_count=ready_count,
        not_ready_attempt_count=not_ready_count,
        failed_attempt_count=failed_count,
        unique_track_signature_count=unique_signature_count,
        track_signatures_consistent=signatures_consistent,
        scheduled_reopen_sequence_proven=ready_count >= 2,
        repeated_capture_gate_ready=repeated_ready,
        limitations=[
            "scheduled_reopen_is_not_involuntary_disconnect_recovery",
            "short_repeated_captures_do_not_prove_long_running_stability",
            "no_network_impairment_is_injected_or_measured_by_this_command",
            "container_pts_does_not_prove_capture_clock_accuracy_or_drift",
            "fixture_qualification_cannot_prove_target_device_or_platform_access",
            "raw_media_requires_consent_controlled_storage_and_deletion",
            "this_stage_does_not_emit_risk_assessment_or_alert",
        ],
    )
    return StreamQualificationResult(
        report=report,
        capture_reports=tuple(captures),
    )
