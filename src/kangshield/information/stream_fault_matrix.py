from __future__ import annotations

import socket
import struct
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import isfinite
from pathlib import Path
from time import monotonic, sleep
from typing import Iterator, Literal

from .contracts import (
    STREAM_FAULT_EXPECTED_STATUS,
    STREAM_FAULT_SCENARIO_ORDER,
    EvidenceLevel,
    SourceType,
    StreamCaptureReport,
    StreamFaultCaseResult,
    StreamFaultExpectedStatus,
    StreamFaultMatrixReport,
    StreamFaultScenarioName,
)
from .privacy import sha256_file
from .stream_capture import (
    StreamCaptureConfig,
    StreamCaptureError,
    capture_stream,
    public_stream_capture_failure_code,
)


STREAM_FAULT_MATRIX_VERSION = "stream-fault-matrix-v0.1.0"
_Behavior = Literal[
    "full",
    "jitter",
    "reject",
    "initial_stall",
    "partial_stall",
    "truncate",
    "reset",
]


@dataclass(frozen=True)
class StreamFaultMatrixConfig:
    capture: StreamCaptureConfig = field(
        default_factory=lambda: StreamCaptureConfig(
            duration_s=2.0,
            minimum_duration_s=1.5,
            open_timeout_s=1.0,
            read_timeout_s=1.0,
        )
    )
    stall_duration_s: float = 1.5
    prefix_byte_limit: int = 2 * 1024 * 1024
    jitter_chunk_bytes: int = 256 * 1024
    jitter_delay_min_s: float = 0.005
    jitter_delay_max_s: float = 0.02
    elapsed_limit_s: float | None = None

    def __post_init__(self) -> None:
        if not self.capture.require_audio:
            raise ValueError("fault matrix requires the audio track")
        if self.capture.transport != "auto":
            raise ValueError("loopback HTTP fault matrix requires auto transport")
        for name, value in (
            ("stall_duration_s", self.stall_duration_s),
            ("jitter_delay_min_s", self.jitter_delay_min_s),
            ("jitter_delay_max_s", self.jitter_delay_max_s),
        ):
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.stall_duration_s <= max(
            self.capture.open_timeout_s,
            self.capture.read_timeout_s,
        ):
            raise ValueError("stall_duration_s must exceed both stream timeouts")
        if self.jitter_delay_max_s < self.jitter_delay_min_s:
            raise ValueError("jitter delay maximum cannot be below minimum")
        if self.jitter_delay_max_s <= 0:
            raise ValueError("jitter delay maximum must be positive")
        if self.prefix_byte_limit <= 0:
            raise ValueError("prefix_byte_limit must be positive")
        if self.jitter_chunk_bytes <= 0:
            raise ValueError("jitter_chunk_bytes must be positive")
        if self.elapsed_limit_s is not None and (
            not isfinite(self.elapsed_limit_s) or self.elapsed_limit_s <= 0
        ):
            raise ValueError("elapsed_limit_s must be finite and positive")

    @property
    def effective_elapsed_limit_s(self) -> float:
        if self.elapsed_limit_s is not None:
            return self.elapsed_limit_s
        return (
            self.capture.open_timeout_s
            + self.capture.duration_s
            + self.capture.read_timeout_s
            + 3.0
        )


@dataclass(frozen=True)
class StreamFaultMatrixResult:
    report: StreamFaultMatrixReport
    capture_reports: tuple[StreamCaptureReport, ...]


@dataclass(frozen=True)
class _FaultTelemetry:
    request_count: int
    body_bytes_sent: int
    body_chunk_count: int
    delay_event_count: int
    stall_event_count: int
    rejection_event_count: int
    reset_event_count: int
    early_close_event_count: int


@dataclass(frozen=True)
class _ScenarioSpec:
    name: StreamFaultScenarioName
    behavior: _Behavior
    expected_status: StreamFaultExpectedStatus


_SCENARIOS = tuple(
    _ScenarioSpec(
        name=name,
        behavior=behavior,
        expected_status=STREAM_FAULT_EXPECTED_STATUS[name],
    )
    for name, behavior in zip(
        STREAM_FAULT_SCENARIO_ORDER,
        (
            "full",
            "jitter",
            "reject",
            "initial_stall",
            "partial_stall",
            "truncate",
            "reset",
        ),
        strict=True,
    )
)


class _FaultHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        source_path: Path,
        behavior: _Behavior,
        *,
        body_byte_limit: int | None,
        stall_duration_s: float,
        jitter_chunk_bytes: int,
        jitter_delays_s: tuple[float, float],
    ) -> None:
        self.source_path = source_path
        self.behavior = behavior
        self.body_byte_limit = body_byte_limit
        self.stall_duration_s = stall_duration_s
        self.jitter_chunk_bytes = jitter_chunk_bytes
        self.jitter_delays_s = jitter_delays_s
        self._telemetry_lock = threading.Lock()
        self._telemetry = {
            "request_count": 0,
            "body_bytes_sent": 0,
            "body_chunk_count": 0,
            "delay_event_count": 0,
            "stall_event_count": 0,
            "rejection_event_count": 0,
            "reset_event_count": 0,
            "early_close_event_count": 0,
        }
        super().__init__(("127.0.0.1", 0), _FaultRequestHandler)

    def handle_error(self, request, client_address) -> None:
        return None

    def record(self, **increments: int) -> None:
        with self._telemetry_lock:
            for name, increment in increments.items():
                self._telemetry[name] += increment

    def telemetry(self) -> _FaultTelemetry:
        with self._telemetry_lock:
            return _FaultTelemetry(**self._telemetry)


class _FaultRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def fault_server(self) -> _FaultHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, format, *args) -> None:
        return None

    def do_HEAD(self) -> None:
        self.fault_server.record(request_count=1)
        if self.fault_server.behavior == "reject":
            self._send_rejection()
            return
        self._send_media_headers()

    def do_GET(self) -> None:
        server = self.fault_server
        server.record(request_count=1)
        if server.behavior == "reject":
            self._send_rejection()
            return

        self._send_media_headers()
        if server.behavior == "initial_stall":
            self.wfile.flush()
            server.record(stall_event_count=1)
            sleep(server.stall_duration_s)
            self.close_connection = True
            return

        sent = self._write_media_body()
        if server.behavior == "partial_stall":
            self.wfile.flush()
            server.record(stall_event_count=1)
            sleep(server.stall_duration_s)
            self.close_connection = True
            return
        if server.behavior == "reset":
            self.close_connection = True
            try:
                self.connection.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_LINGER,
                    struct.pack("ii", 1, 0),
                )
                server.record(reset_event_count=1)
                self.connection.close()
            except OSError:
                pass
            return
        if (
            server.behavior == "truncate"
            and sent < self.fault_server.source_path.stat().st_size
        ):
            server.record(early_close_event_count=1)
            self.close_connection = True

    def _send_rejection(self) -> None:
        self.fault_server.record(rejection_event_count=1)
        self.send_response(503)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def _send_media_headers(self) -> None:
        size = self.fault_server.source_path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "video/x-matroska")
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "none")
        self.send_header("Connection", "close")
        self.end_headers()

    def _write_media_body(self) -> int:
        server = self.fault_server
        source_size = server.source_path.stat().st_size
        byte_limit = server.body_byte_limit or source_size
        sent = 0
        delay_index = 0
        with server.source_path.open("rb") as source:
            while sent < byte_limit:
                chunk = source.read(
                    min(server.jitter_chunk_bytes, byte_limit - sent)
                )
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break
                sent += len(chunk)
                server.record(
                    body_bytes_sent=len(chunk),
                    body_chunk_count=1,
                )
                if server.behavior == "jitter" and sent < byte_limit:
                    server.record(delay_event_count=1)
                    sleep(server.jitter_delays_s[delay_index % 2])
                    delay_index += 1
        return sent


@dataclass(frozen=True)
class _FaultEndpoint:
    url: str
    server: _FaultHTTPServer

    def telemetry(self) -> _FaultTelemetry:
        return self.server.telemetry()


@contextmanager
def _fault_http_endpoint(
    source_path: Path,
    behavior: _Behavior,
    *,
    body_byte_limit: int | None,
    config: StreamFaultMatrixConfig,
) -> Iterator[_FaultEndpoint]:
    server = _FaultHTTPServer(
        source_path,
        behavior,
        body_byte_limit=body_byte_limit,
        stall_duration_s=config.stall_duration_s,
        jitter_chunk_bytes=config.jitter_chunk_bytes,
        jitter_delays_s=(
            config.jitter_delay_min_s,
            config.jitter_delay_max_s,
        ),
    )
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    thread.start()
    try:
        yield _FaultEndpoint(
            url=f"http://127.0.0.1:{server.server_port}/fixture.mkv",
            server=server,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _body_limit(
    scenario: StreamFaultScenarioName,
    *,
    source_size: int,
    prefix_byte_limit: int,
) -> int | None:
    if scenario in {"healthy_control", "chunk_delay_jitter"}:
        return None
    if scenario in {"http_rejection", "initial_response_stall"}:
        return 0
    return max(1, min(source_size - 1, source_size // 4, prefix_byte_limit))


def _case_expectation_met(
    expected_status: StreamFaultExpectedStatus,
    actual_status: str,
) -> bool:
    if expected_status == "captured_ready":
        return actual_status == "captured_ready"
    if expected_status == "failed":
        return actual_status == "failed"
    return actual_status != "captured_ready"


def _scenario_exercised(
    scenario: StreamFaultScenarioName,
    telemetry: _FaultTelemetry,
) -> bool:
    if telemetry.request_count <= 0:
        return False
    if scenario == "healthy_control":
        return telemetry.body_bytes_sent > 0
    if scenario == "chunk_delay_jitter":
        return telemetry.body_bytes_sent > 0 and telemetry.delay_event_count > 0
    if scenario == "http_rejection":
        return (
            telemetry.rejection_event_count > 0
            and telemetry.body_bytes_sent == 0
        )
    if scenario == "initial_response_stall":
        return telemetry.stall_event_count > 0 and telemetry.body_bytes_sent == 0
    if scenario == "midstream_stall":
        return telemetry.stall_event_count > 0 and telemetry.body_bytes_sent > 0
    if scenario == "truncated_transfer":
        return (
            telemetry.early_close_event_count > 0
            and telemetry.body_bytes_sent > 0
        )
    return telemetry.reset_event_count > 0 and telemetry.body_bytes_sent > 0


def _telemetry_fields(telemetry: _FaultTelemetry) -> dict[str, int]:
    return {
        "request_count": telemetry.request_count,
        "body_bytes_sent": telemetry.body_bytes_sent,
        "body_chunk_count": telemetry.body_chunk_count,
        "delay_event_count": telemetry.delay_event_count,
        "stall_event_count": telemetry.stall_event_count,
        "rejection_event_count": telemetry.rejection_event_count,
        "reset_event_count": telemetry.reset_event_count,
        "early_close_event_count": telemetry.early_close_event_count,
    }


def exercise_stream_fault_matrix(
    *,
    fixture_path: Path,
    artifacts_dir: Path,
    config: StreamFaultMatrixConfig | None = None,
) -> StreamFaultMatrixResult:
    config = config or StreamFaultMatrixConfig()
    fixture_path = Path(fixture_path)
    artifacts_dir = Path(artifacts_dir)
    if not fixture_path.is_file():
        raise FileNotFoundError(fixture_path)
    if not artifacts_dir.is_dir():
        raise FileNotFoundError(artifacts_dir)
    fixture_size = fixture_path.stat().st_size
    if fixture_size < 2:
        raise ValueError("fault matrix fixture must contain at least two bytes")
    fixture_sha256 = sha256_file(fixture_path)

    elapsed_limit_ms = round(config.effective_elapsed_limit_s * 1000)
    cases: list[StreamFaultCaseResult] = []
    captures: list[StreamCaptureReport] = []

    for case_index, spec in enumerate(_SCENARIOS, start=1):
        stem = f"stream-fault-{case_index:03d}"
        output_artifact = f"artifacts/{stem}.mkv"
        capture_report_artifact = f"reports/{stem}.json"
        output_path = artifacts_dir / f"{stem}.mkv"
        if output_path.exists():
            raise FileExistsError(output_path)
        body_byte_limit = _body_limit(
            spec.name,
            source_size=fixture_size,
            prefix_byte_limit=config.prefix_byte_limit,
        )
        with _fault_http_endpoint(
            fixture_path,
            spec.behavior,
            body_byte_limit=body_byte_limit,
            config=config,
        ) as endpoint:
            started = monotonic()
            try:
                capture = capture_stream(
                    endpoint=endpoint.url,
                    output_path=output_path,
                    output_artifact=output_artifact,
                    evidence_level=EvidenceLevel.E1,
                    source_type=SourceType.FIXTURE,
                    config=config.capture,
                )
            except StreamCaptureError as error:
                elapsed_ms = max(0, round((monotonic() - started) * 1000))
                telemetry = endpoint.telemetry()
                output_path.unlink(missing_ok=True)
                actual_status = "failed"
                cases.append(
                    StreamFaultCaseResult(
                        case_index=case_index,
                        scenario=spec.name,
                        fault_injected=spec.name != "healthy_control",
                        expected_status=spec.expected_status,
                        actual_status=actual_status,
                        elapsed_ms=elapsed_ms,
                        elapsed_limit_ms=elapsed_limit_ms,
                        bounded_completion=elapsed_ms <= elapsed_limit_ms,
                        expectation_met=_case_expectation_met(
                            spec.expected_status,
                            actual_status,
                        ),
                        body_byte_limit=body_byte_limit,
                        stall_duration_ms=(
                            round(config.stall_duration_s * 1000)
                            if spec.behavior
                            in {"initial_stall", "partial_stall"}
                            else None
                        ),
                        chunk_size_bytes=(
                            config.jitter_chunk_bytes
                            if spec.behavior == "jitter"
                            else None
                        ),
                        chunk_delay_min_ms=(
                            round(config.jitter_delay_min_s * 1000)
                            if spec.behavior == "jitter"
                            else None
                        ),
                        chunk_delay_max_ms=(
                            round(config.jitter_delay_max_s * 1000)
                            if spec.behavior == "jitter"
                            else None
                        ),
                        **_telemetry_fields(telemetry),
                        scenario_exercised=_scenario_exercised(
                            spec.name,
                            telemetry,
                        ),
                        failure_code=public_stream_capture_failure_code(
                            error.code
                        ),
                    )
                )
                continue

            elapsed_ms = max(0, round((monotonic() - started) * 1000))
            telemetry = endpoint.telemetry()
            actual_status = (
                "captured_ready"
                if capture.same_container_multimodal_ready
                else "captured_not_ready"
            )
            cases.append(
                StreamFaultCaseResult(
                    case_index=case_index,
                    scenario=spec.name,
                    fault_injected=spec.name != "healthy_control",
                    expected_status=spec.expected_status,
                    actual_status=actual_status,
                    elapsed_ms=elapsed_ms,
                    elapsed_limit_ms=elapsed_limit_ms,
                    bounded_completion=elapsed_ms <= elapsed_limit_ms,
                    expectation_met=_case_expectation_met(
                        spec.expected_status,
                        actual_status,
                    ),
                    body_byte_limit=body_byte_limit,
                    stall_duration_ms=(
                        round(config.stall_duration_s * 1000)
                        if spec.behavior in {"initial_stall", "partial_stall"}
                        else None
                    ),
                    chunk_size_bytes=(
                        config.jitter_chunk_bytes
                        if spec.behavior == "jitter"
                        else None
                    ),
                    chunk_delay_min_ms=(
                        round(config.jitter_delay_min_s * 1000)
                        if spec.behavior == "jitter"
                        else None
                    ),
                    chunk_delay_max_ms=(
                        round(config.jitter_delay_max_s * 1000)
                        if spec.behavior == "jitter"
                        else None
                    ),
                    **_telemetry_fields(telemetry),
                    scenario_exercised=_scenario_exercised(
                        spec.name,
                        telemetry,
                    ),
                    output_artifact=output_artifact,
                    capture_report_artifact=capture_report_artifact,
                    captured_media_span_ms=capture.captured_media_span_ms,
                    termination_reason=capture.termination_reason,
                    capture_artifact_ready=capture.capture_artifact_ready,
                    same_container_multimodal_ready=(
                        capture.same_container_multimodal_ready
                    ),
                )
            )
            captures.append(capture)

    if (
        fixture_path.stat().st_size != fixture_size
        or sha256_file(fixture_path) != fixture_sha256
    ):
        for case in cases:
            if case.output_artifact:
                (artifacts_dir / Path(case.output_artifact).name).unlink(
                    missing_ok=True
                )
        raise RuntimeError("fault matrix fixture changed during execution")

    captured_count = sum(item.actual_status != "failed" for item in cases)
    ready_count = sum(item.actual_status == "captured_ready" for item in cases)
    not_ready_count = sum(
        item.actual_status == "captured_not_ready" for item in cases
    )
    failed_count = sum(item.actual_status == "failed" for item in cases)
    bounded_count = sum(item.bounded_completion for item in cases)
    expectation_count = sum(item.expectation_met for item in cases)
    exercised_count = sum(item.scenario_exercised for item in cases)
    unexpected_ready_count = sum(
        item.actual_status == "captured_ready"
        and item.expected_status != "captured_ready"
        for item in cases
    )
    scenario_count = len(_SCENARIOS)
    all_bounded = bounded_count == scenario_count
    all_expected = expectation_count == scenario_count
    all_exercised = exercised_count == scenario_count
    report = StreamFaultMatrixReport(
        matrix_version=STREAM_FAULT_MATRIX_VERSION,
        fixture_sha256=fixture_sha256,
        fixture_byte_size=fixture_size,
        requested_duration_ms=round(config.capture.duration_s * 1000),
        minimum_duration_ms=round(config.capture.minimum_duration_s * 1000),
        open_timeout_ms=round(config.capture.open_timeout_s * 1000),
        read_timeout_ms=round(config.capture.read_timeout_s * 1000),
        elapsed_limit_ms=elapsed_limit_ms,
        scenario_count=scenario_count,
        cases=cases,
        captured_case_count=captured_count,
        ready_case_count=ready_count,
        not_ready_case_count=not_ready_count,
        failed_case_count=failed_count,
        bounded_case_count=bounded_count,
        expectation_met_case_count=expectation_count,
        scenario_exercised_case_count=exercised_count,
        unexpected_ready_case_count=unexpected_ready_count,
        all_cases_bounded=all_bounded,
        all_expected_outcomes_met=all_expected,
        all_scenarios_exercised=all_exercised,
        controlled_http_fault_matrix_executed=all_exercised,
        fault_detection_gate_ready=bool(
            all_bounded
            and all_expected
            and all_exercised
            and unexpected_ready_count == 0
        ),
        limitations=[
            "loopback_http_faults_do_not_prove_rtsp_or_target_device_behavior",
            "chunk_delay_schedule_is_not_packet_level_jitter_measurement",
            "tcp_transfer_does_not_inject_or_measure_packet_loss",
            "safe_fault_detection_does_not_prove_reconnect_or_tolerance",
            "short_fault_cases_do_not_prove_long_running_stability",
            "fixture_media_cannot_prove_target_device_or_platform_access",
            "raw_media_requires_consent_controlled_storage_and_deletion",
            "this_stage_does_not_emit_risk_assessment_or_alert",
        ],
    )
    return StreamFaultMatrixResult(
        report=report,
        capture_reports=tuple(captures),
    )
