from __future__ import annotations

import json
import stat
import threading
from contextlib import contextmanager
from fractions import Fraction
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from pydantic import ValidationError

from kangshield.information.artifacts import RunArtifacts
from kangshield.information.cli import main
from kangshield.information.contracts import (
    EvidenceLevel,
    ModelBinding,
    SourceType,
    StreamFaultMatrixReport,
    StreamQualificationReport,
)
from kangshield.information.multimodal_pipeline import (
    MultimodalPipelineConfig,
    run_multimodal_pipeline,
)
from kangshield.information.stream_capture import (
    StreamCaptureConfig,
    StreamCaptureError,
    capture_stream,
)
from kangshield.information.stream_fault_matrix import (
    StreamFaultMatrixConfig,
    exercise_stream_fault_matrix,
)
from kangshield.information.stream_qualification import (
    StreamQualificationConfig,
    qualify_stream,
)


class _NoopPoseBackend:
    @property
    def bindings(self):
        return [
            ModelBinding(
                task="human_pose_tracking",
                backend="fixture",
                model_name="noop-pose",
                model_version="test",
                license="test-only",
                device="cpu",
            )
        ]

    def infer(self, frame):
        return []


class _NoopSpeechBackend:
    @property
    def bindings(self):
        return [
            ModelBinding(
                task="mandarin_speech_recognition",
                backend="fixture",
                model_name="noop-speech",
                model_version="test",
                license="test-only",
                device="cpu",
            )
        ]

    def transcribe(self, audio):
        return []


def _write_av_container(
    path: Path,
    *,
    seconds: int = 3,
    include_audio: bool = True,
    metadata_value: str = "fixture-private-metadata",
) -> None:
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    fps = 10
    sample_rate = 8000
    samples_per_frame = sample_rate // fps
    with av.open(str(path), "w", format="matroska") as output:
        output.metadata["title"] = metadata_value
        video = output.add_stream("ffv1", rate=fps)
        video.width = 64
        video.height = 48
        video.pix_fmt = "yuv420p"
        audio = None
        if include_audio:
            audio = output.add_stream("pcm_s16le", rate=sample_rate)
            audio.layout = "mono"
            audio.metadata["comment"] = metadata_value
        for index in range(seconds * fps):
            pixels = np.full((48, 64, 3), index * 3, dtype=np.uint8)
            video_frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            video_frame.pts = index
            video_frame.time_base = Fraction(1, fps)
            for packet in video.encode(video_frame):
                output.mux(packet)
            if audio is not None:
                samples = np.full((1, samples_per_frame), 100, dtype=np.int16)
                audio_frame = av.AudioFrame.from_ndarray(
                    samples,
                    format="s16",
                    layout="mono",
                )
                audio_frame.sample_rate = sample_rate
                audio_frame.pts = index * samples_per_frame
                audio_frame.time_base = Fraction(1, sample_rate)
                for packet in audio.encode(audio_frame):
                    output.mux(packet)
        for packet in video.encode():
            output.mux(packet)
        if audio is not None:
            for packet in audio.encode():
                output.mux(packet)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return None


@contextmanager
def _http_endpoint(directory: Path, filename: str):
    handler = partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{filename}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_stream_capture_is_bounded_private_and_pipeline_replayable(tmp_path):
    source = tmp_path / "private-source-name.mkv"
    output = tmp_path / "artifacts" / "stream-capture.mkv"
    output.parent.mkdir(mode=0o700)
    secret_metadata = "private-title-must-not-propagate"
    _write_av_container(source, metadata_value=secret_metadata)

    with _http_endpoint(tmp_path, source.name) as endpoint:
        report = capture_stream(
            endpoint=endpoint,
            output_path=output,
            output_artifact="artifacts/stream-capture.mkv",
            evidence_level=EvidenceLevel.E1,
            source_type=SourceType.FIXTURE,
            config=StreamCaptureConfig(
                duration_s=1.5,
                minimum_duration_s=1.0,
                open_timeout_s=2.0,
                read_timeout_s=2.0,
            ),
        )

    serialized = report.model_dump_json()
    assert report.endpoint_scheme == "http"
    assert report.endpoint_log_messages_persisted is False
    assert report.termination_reason == "duration_limit"
    assert report.capture_artifact_ready is True
    assert report.same_container_multimodal_ready is True
    assert report.device_platform_integration_proven is False
    assert report.captured_media_span_ms >= 1000
    assert report.media_probe.container_timing is not None
    assert report.media_probe.container_timing.video_stream_count == 1
    assert report.media_probe.container_timing.audio_stream_count == 1
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert endpoint not in serialized
    assert source.name not in serialized
    assert secret_metadata not in serialized

    av = pytest.importorskip("av")
    with av.open(str(output), mode="r") as captured:
        assert secret_metadata not in json.dumps(captured.metadata)
        assert all(
            secret_metadata not in json.dumps(stream.metadata)
            for stream in captured.streams
        )

    with RunArtifacts(
        tmp_path / "pipeline-runs",
        stage="test-stream-to-multimodal",
        evidence_level=EvidenceLevel.E1,
        project_dir=tmp_path,
    ) as run:
        pipeline = run_multimodal_pipeline(
            video_path=output,
            audio_path=output,
            pose_backend=_NoopPoseBackend(),
            speech_backend=_NoopSpeechBackend(),
            run=run,
            config=MultimodalPipelineConfig(
                video_sample_fps=2.0,
                fusion_window_ms=1000,
                max_duration_s=1.0,
            ),
            evidence_level=EvidenceLevel.E1,
            source_type=SourceType.FIXTURE,
        )
    assert pipeline.same_container_av is True
    assert pipeline.input_layout == "same_container_pts"
    assert pipeline.sampled_video_frames == 2


def test_capture_stream_cli_uses_environment_and_owner_only_artifacts(
    tmp_path,
    monkeypatch,
    capsys,
):
    source = tmp_path / "input.mkv"
    _write_av_container(source, seconds=2)
    monkeypatch.setenv("PRIVATE_CAPTURE_ENDPOINT", str(source))

    exit_code = main(
        [
            "capture-stream",
            "--endpoint-env",
            "PRIVATE_CAPTURE_ENDPOINT",
            "--source-type",
            "fixture",
            "--duration-s",
            "1.2",
            "--minimum-duration-s",
            "0.8",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--require-ready",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    run_dir = Path(output["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads(
        (run_dir / "reports" / "stream-capture.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert output["same_container_multimodal_ready"] is True
    assert manifest["status"] == "completed"
    assert manifest["configuration"]["endpoint_value_persisted"] is False
    assert manifest["configuration"]["endpoint_log_messages_persisted"] is False
    assert "PRIVATE_CAPTURE_ENDPOINT" not in json.dumps(manifest)
    assert str(source) not in json.dumps(manifest)
    assert report["endpoint_scheme"] == "local"
    assert report["endpoint_value_persisted"] is False
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    for path in run_dir.rglob("*"):
        expected = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(path.stat().st_mode) == expected


def test_capture_stream_require_ready_returns_two_after_short_report(
    tmp_path,
    monkeypatch,
    capsys,
):
    source = tmp_path / "short-input.mkv"
    _write_av_container(source, seconds=1)
    monkeypatch.setenv("KANG_SHORT_ENDPOINT", str(source))

    exit_code = main(
        [
            "capture-stream",
            "--endpoint-env",
            "KANG_SHORT_ENDPOINT",
            "--source-type",
            "fixture",
            "--duration-s",
            "2",
            "--minimum-duration-s",
            "1.5",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--require-ready",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    report_path = Path(output["run_dir"]) / "reports" / "stream-capture.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 2
    assert output["termination_reason"] == "end_of_stream"
    assert output["same_container_multimodal_ready"] is False
    assert report["captured_media_span_ms"] < report["minimum_duration_ms"]
    assert json.loads(
        (report_path.parents[1] / "manifest.json").read_text(encoding="utf-8")
    )["status"] == "completed"


def test_capture_stream_rejects_missing_audio_and_false_evidence(tmp_path):
    source = tmp_path / "video-only.mkv"
    output = tmp_path / "artifacts" / "stream-capture.mkv"
    output.parent.mkdir(mode=0o700)
    _write_av_container(source, include_audio=False)

    with pytest.raises(StreamCaptureError, match="required single audio"):
        capture_stream(
            endpoint=str(source),
            output_path=output,
            output_artifact="artifacts/stream-capture.mkv",
            source_type=SourceType.FIXTURE,
            config=StreamCaptureConfig(duration_s=1.0),
        )
    assert not output.exists()

    with pytest.raises(ValueError, match="requires an RTSP or HTTP"):
        capture_stream(
            endpoint=str(source),
            output_path=output,
            output_artifact="artifacts/stream-capture.mkv",
            source_type=SourceType.NETWORK_STREAM,
            config=StreamCaptureConfig(duration_s=1.0),
        )
    with pytest.raises(ValueError, match="at most E1"):
        capture_stream(
            endpoint=str(source),
            output_path=output,
            output_artifact="artifacts/stream-capture.mkv",
            evidence_level=EvidenceLevel.E2,
            source_type=SourceType.FIXTURE,
            config=StreamCaptureConfig(duration_s=1.0),
        )
    with pytest.raises(ValueError, match="requires device_ref"):
        capture_stream(
            endpoint="rtsp://127.0.0.1/example",
            output_path=output,
            output_artifact="artifacts/stream-capture.mkv",
            evidence_level=EvidenceLevel.E2,
            source_type=SourceType.NETWORK_STREAM,
            config=StreamCaptureConfig(duration_s=1.0),
        )


def test_capture_failure_never_persists_endpoint_credentials(
    tmp_path,
    monkeypatch,
):
    from kangshield.information import stream_capture

    endpoint = "rtsp://private-user:private-password@127.0.0.1/live?token=secret"
    monkeypatch.setenv("KANG_SECRET_ENDPOINT", endpoint)

    def fail_with_endpoint(*args, **kwargs):
        raise RuntimeError(f"cannot open {endpoint}")

    monkeypatch.setattr(stream_capture, "_open_input", fail_with_endpoint)
    with pytest.raises(StreamCaptureError, match="failed during open") as caught:
        main(
            [
                "capture-stream",
                "--endpoint-env",
                "KANG_SECRET_ENDPOINT",
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )

    assert caught.value.code == "open_failed"
    run_dirs = list((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    run_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in run_dirs[0].rglob("*.json*")
    )
    assert endpoint not in str(caught.value)
    assert endpoint not in run_text
    assert "private-password" not in run_text
    assert "token=secret" not in run_text
    assert json.loads(
        (run_dirs[0] / "manifest.json").read_text(encoding="utf-8")
    )["status"] == "failed"


def test_post_capture_probe_failure_removes_unregistered_raw_media(
    tmp_path,
    monkeypatch,
):
    from kangshield.information import stream_capture

    source = tmp_path / "source.mkv"
    output = tmp_path / "artifacts" / "stream-capture.mkv"
    output.parent.mkdir(mode=0o700)
    _write_av_container(source, seconds=2)

    def fail_probe(*args, **kwargs):
        raise RuntimeError("synthetic probe failure")

    monkeypatch.setattr(stream_capture, "probe_media", fail_probe)
    with pytest.raises(
        StreamCaptureError,
        match="failed during output verification",
    ) as caught:
        capture_stream(
            endpoint=str(source),
            output_path=output,
            output_artifact="artifacts/stream-capture.mkv",
            source_type=SourceType.FIXTURE,
            config=StreamCaptureConfig(duration_s=1.0),
        )
    assert caught.value.code == "output_verification_failed"
    assert "synthetic probe failure" not in str(caught.value)
    assert not output.exists()


def test_stream_qualification_reopens_and_gates_stable_ready_captures(tmp_path):
    source = tmp_path / "private-qualification-source.mkv"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(mode=0o700)
    secret_metadata = "qualification-private-metadata"
    _write_av_container(source, seconds=3, metadata_value=secret_metadata)

    with _http_endpoint(tmp_path, source.name) as endpoint:
        result = qualify_stream(
            endpoint=endpoint,
            artifacts_dir=artifacts,
            evidence_level=EvidenceLevel.E1,
            source_type=SourceType.FIXTURE,
            config=StreamQualificationConfig(
                attempt_count=3,
                capture=StreamCaptureConfig(
                    duration_s=0.8,
                    minimum_duration_s=0.5,
                    open_timeout_s=2.0,
                    read_timeout_s=2.0,
                ),
            ),
        )

    report = result.report
    serialized = report.model_dump_json()
    assert report.attempt_count == 3
    assert report.captured_attempt_count == 3
    assert report.ready_attempt_count == 3
    assert report.not_ready_attempt_count == 0
    assert report.failed_attempt_count == 0
    assert report.unique_track_signature_count == 1
    assert report.track_signatures_consistent is True
    assert report.scheduled_reopen_sequence_proven is True
    assert report.repeated_capture_gate_ready is True
    assert report.involuntary_disconnect_recovery_proven is False
    assert report.long_running_stability_proven is False
    assert report.network_impairment_tolerance_proven is False
    assert report.device_platform_integration_proven is False
    assert len(result.capture_reports) == 3
    assert endpoint not in serialized
    assert source.name not in serialized
    assert secret_metadata not in serialized
    for index, attempt in enumerate(report.attempts, start=1):
        assert attempt.attempt_index == index
        assert attempt.status == "captured_ready"
        assert attempt.capture_artifact_ready is True
        assert attempt.same_container_multimodal_ready is True
        assert attempt.output_artifact == f"artifacts/stream-capture-{index:03d}.mkv"
        assert attempt.capture_report_artifact == (
            f"reports/stream-capture-{index:03d}.json"
        )
        video_signature, audio_signature = attempt.track_signature
        assert video_signature.stream_type == "video"
        assert video_signature.width_px == 64
        assert video_signature.height_px == 48
        assert video_signature.pixel_format == "yuv420p"
        assert video_signature.average_rate == "10/1"
        assert audio_signature.stream_type == "audio"
        assert audio_signature.sample_rate_hz == 8000
        assert audio_signature.channels == 1
        artifact = artifacts / f"stream-capture-{index:03d}.mkv"
        assert artifact.is_file()
        assert stat.S_IMODE(artifact.stat().st_mode) == 0o600

    inconsistent_count = report.model_dump(mode="json")
    inconsistent_count["ready_attempt_count"] = 2
    with pytest.raises(ValidationError, match="attempt counts are inconsistent"):
        StreamQualificationReport.model_validate(inconsistent_count)

    false_gate = report.model_dump(mode="json")
    false_gate["repeated_capture_gate_ready"] = False
    with pytest.raises(ValidationError, match="capture gate is inconsistent"):
        StreamQualificationReport.model_validate(false_gate)

    path_traversal = report.model_dump(mode="json")
    path_traversal["attempts"][0]["output_artifact"] = "../private.mkv"
    with pytest.raises(ValidationError, match=r"artifacts/\*\.mkv"):
        StreamQualificationReport.model_validate(path_traversal)


def test_stream_qualification_keeps_scheduled_reopen_distinct_from_stability(
    tmp_path,
    monkeypatch,
):
    from kangshield.information import stream_qualification

    source = tmp_path / "source.mkv"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(mode=0o700)
    _write_av_container(source, seconds=2)
    original_capture = stream_qualification.capture_stream
    call_count = 0

    def capture_with_changed_signature(**kwargs):
        nonlocal call_count
        call_count += 1
        report = original_capture(**kwargs)
        if call_count == 2:
            report = report.model_copy(deep=True)
            assert report.media_probe.container_timing is not None
            report.media_probe.container_timing.streams[0].codec_name = "changed-codec"
        return report

    monkeypatch.setattr(
        stream_qualification,
        "capture_stream",
        capture_with_changed_signature,
    )
    result = qualify_stream(
        endpoint=str(source),
        artifacts_dir=artifacts,
        source_type=SourceType.FIXTURE,
        config=StreamQualificationConfig(
            attempt_count=2,
            capture=StreamCaptureConfig(
                duration_s=0.8,
                minimum_duration_s=0.5,
            ),
        ),
    )

    assert result.report.ready_attempt_count == 2
    assert result.report.unique_track_signature_count == 2
    assert result.report.track_signatures_consistent is False
    assert result.report.scheduled_reopen_sequence_proven is True
    assert result.report.repeated_capture_gate_ready is False
    assert result.report.involuntary_disconnect_recovery_proven is False


def test_stream_qualification_continues_after_sanitized_attempt_failure(
    tmp_path,
    monkeypatch,
):
    from kangshield.information import stream_qualification

    source = tmp_path / "source.mkv"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(mode=0o700)
    _write_av_container(source, seconds=2)
    endpoint = str(source)
    original_capture = stream_qualification.capture_stream
    call_count = 0

    def fail_once_with_private_code(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise StreamCaptureError(
                f"private failure at {endpoint}",
                code=f"private:{endpoint}",
            )
        return original_capture(**kwargs)

    monkeypatch.setattr(
        stream_qualification,
        "capture_stream",
        fail_once_with_private_code,
    )
    result = qualify_stream(
        endpoint=endpoint,
        artifacts_dir=artifacts,
        source_type=SourceType.FIXTURE,
        config=StreamQualificationConfig(
            attempt_count=2,
            capture=StreamCaptureConfig(
                duration_s=0.8,
                minimum_duration_s=0.5,
            ),
        ),
    )

    serialized = result.report.model_dump_json()
    assert result.report.failed_attempt_count == 1
    assert result.report.ready_attempt_count == 1
    assert result.report.repeated_capture_gate_ready is False
    assert result.report.attempts[0].failure_code == "stream_capture_failed"
    assert result.report.attempts[1].status == "captured_ready"
    assert len(result.capture_reports) == 1
    assert endpoint not in serialized
    assert not (artifacts / "stream-capture-001.mkv").exists()
    assert (artifacts / "stream-capture-002.mkv").is_file()


def test_qualify_stream_cli_records_owner_only_attempts_and_fail_closed_gate(
    tmp_path,
    monkeypatch,
    capsys,
):
    source = tmp_path / "video-only.mkv"
    _write_av_container(source, seconds=2, include_audio=False)
    monkeypatch.setenv("PRIVATE_QUALIFICATION_ENDPOINT", str(source))

    exit_code = main(
        [
            "qualify-stream",
            "--endpoint-env",
            "PRIVATE_QUALIFICATION_ENDPOINT",
            "--source-type",
            "fixture",
            "--attempt-count",
            "2",
            "--duration-s",
            "0.8",
            "--minimum-duration-s",
            "0.5",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--require-ready",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    run_dir = Path(output["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads(
        (run_dir / "reports" / "stream-qualification.json").read_text(
            encoding="utf-8"
        )
    )

    assert exit_code == 2
    assert output["failed_attempt_count"] == 2
    assert output["repeated_capture_gate_ready"] is False
    assert manifest["status"] == "completed"
    assert manifest["configuration"]["attempt_count"] == 2
    assert "PRIVATE_QUALIFICATION_ENDPOINT" not in json.dumps(manifest)
    assert str(source) not in json.dumps(manifest)
    assert report["captured_attempt_count"] == 0
    assert report["failed_attempt_count"] == 2
    assert report["scheduled_reopen_sequence_proven"] is False
    assert {item["failure_code"] for item in report["attempts"]} == {
        "required_audio_track_missing"
    }
    assert not list((run_dir / "artifacts").glob("*.mkv"))
    for path in run_dir.rglob("*"):
        expected = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(path.stat().st_mode) == expected


def test_qualify_stream_cli_writes_parent_child_reports_and_ledgers(
    tmp_path,
    monkeypatch,
    capsys,
):
    source = tmp_path / "input.mkv"
    _write_av_container(source, seconds=2)
    monkeypatch.setenv("KANG_QUALIFICATION_ENDPOINT", str(source))

    exit_code = main(
        [
            "qualify-stream",
            "--endpoint-env",
            "KANG_QUALIFICATION_ENDPOINT",
            "--source-type",
            "fixture",
            "--attempt-count",
            "2",
            "--duration-s",
            "0.8",
            "--minimum-duration-s",
            "0.5",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--require-ready",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    run_dir = Path(output["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    parent = json.loads(
        (run_dir / "reports" / "stream-qualification.json").read_text(
            encoding="utf-8"
        )
    )

    assert exit_code == 0
    assert output["ready_attempt_count"] == 2
    assert output["repeated_capture_gate_ready"] is True
    assert manifest["status"] == "completed"
    asset_rows = [
        json.loads(line)
        for line in (run_dir / "source_assets.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(asset_rows) == 2
    assert set(manifest["inputs"]) == {row["asset_id"] for row in asset_rows}
    assert len(
        (run_dir / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    ) == 2
    assert parent["captured_attempt_count"] == 2
    assert parent["ready_attempt_count"] == 2
    assert parent["unique_track_signature_count"] == 1
    assert parent["repeated_capture_gate_ready"] is True
    expected_artifacts = {
        "artifacts/stream-capture-001.mkv",
        "artifacts/stream-capture-002.mkv",
        "reports/stream-capture-001.json",
        "reports/stream-capture-002.json",
        "reports/stream-qualification.json",
    }
    assert set(manifest["artifacts"]) == expected_artifacts
    assert "KANG_QUALIFICATION_ENDPOINT" not in json.dumps(manifest)
    assert str(source) not in json.dumps(manifest)
    for relative in expected_artifacts:
        assert (run_dir / relative).is_file()
    for path in run_dir.rglob("*"):
        expected = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(path.stat().st_mode) == expected


def _fast_fault_matrix_config() -> StreamFaultMatrixConfig:
    return StreamFaultMatrixConfig(
        capture=StreamCaptureConfig(
            duration_s=0.8,
            minimum_duration_s=0.5,
            open_timeout_s=0.25,
            read_timeout_s=0.25,
        ),
        stall_duration_s=0.45,
        prefix_byte_limit=64 * 1024,
        jitter_chunk_bytes=16 * 1024,
        jitter_delay_min_s=0.001,
        jitter_delay_max_s=0.003,
        elapsed_limit_s=2.0,
    )


def test_stream_fault_matrix_rejects_non_faulting_or_video_only_config():
    with pytest.raises(ValueError, match="must exceed both stream timeouts"):
        StreamFaultMatrixConfig(
            capture=StreamCaptureConfig(
                open_timeout_s=0.5,
                read_timeout_s=0.5,
            ),
            stall_duration_s=0.5,
        )
    with pytest.raises(ValueError, match="jitter delay maximum must be positive"):
        StreamFaultMatrixConfig(
            jitter_delay_min_s=0.0,
            jitter_delay_max_s=0.0,
        )
    with pytest.raises(ValueError, match="requires the audio track"):
        StreamFaultMatrixConfig(
            capture=StreamCaptureConfig(require_audio=False),
        )


def test_stream_fault_matrix_detects_controlled_failures_without_false_ready(
    tmp_path,
):
    source = tmp_path / "private-fault-source.mkv"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(mode=0o700)
    secret_metadata = "fault-private-metadata"
    _write_av_container(source, seconds=2, metadata_value=secret_metadata)

    result = exercise_stream_fault_matrix(
        fixture_path=source,
        artifacts_dir=artifacts,
        config=_fast_fault_matrix_config(),
    )

    report = result.report
    serialized = report.model_dump_json()
    assert report.scenario_count == 7
    assert [item.scenario for item in report.cases] == [
        "healthy_control",
        "chunk_delay_jitter",
        "http_rejection",
        "initial_response_stall",
        "midstream_stall",
        "truncated_transfer",
        "connection_reset",
    ]
    assert report.cases[0].actual_status == "captured_ready"
    assert report.cases[1].actual_status == "captured_ready"
    assert report.cases[2].actual_status == "failed"
    assert report.cases[2].failure_code == "open_failed"
    assert report.cases[3].actual_status == "failed"
    assert report.cases[3].failure_code == "open_failed"
    assert all(
        item.actual_status != "captured_ready" for item in report.cases[2:]
    )
    assert all(item.bounded_completion for item in report.cases)
    assert all(item.expectation_met for item in report.cases)
    assert all(item.scenario_exercised for item in report.cases)
    assert report.cases[0].body_bytes_sent > 0
    assert report.cases[1].delay_event_count > 0
    assert report.cases[2].rejection_event_count > 0
    assert report.cases[3].stall_event_count > 0
    assert report.cases[4].stall_event_count > 0
    assert report.cases[5].early_close_event_count > 0
    assert report.cases[6].reset_event_count > 0
    assert report.unexpected_ready_case_count == 0
    assert report.all_cases_bounded is True
    assert report.all_expected_outcomes_met is True
    assert report.all_scenarios_exercised is True
    assert report.fault_detection_gate_ready is True
    assert report.controlled_http_fault_matrix_executed is True
    assert report.packet_loss_injected is False
    assert report.rtsp_transport_tested is False
    assert report.reconnect_attempted is False
    assert report.involuntary_disconnect_recovery_proven is False
    assert report.network_impairment_tolerance_proven is False
    assert report.long_running_stability_proven is False
    assert report.device_platform_integration_proven is False
    assert source.name not in serialized
    assert secret_metadata not in serialized
    assert "127.0.0.1" not in serialized
    assert len(result.capture_reports) == report.captured_case_count
    for case in report.cases:
        artifact = artifacts / f"stream-fault-{case.case_index:03d}.mkv"
        if case.actual_status == "failed":
            assert not artifact.exists()
        else:
            assert artifact.is_file()
            assert stat.S_IMODE(artifact.stat().st_mode) == 0o600

    inconsistent_count = report.model_dump(mode="json")
    inconsistent_count["failed_case_count"] += 1
    with pytest.raises(ValidationError, match="counts are inconsistent"):
        StreamFaultMatrixReport.model_validate(inconsistent_count)

    false_gate = report.model_dump(mode="json")
    false_gate["fault_detection_gate_ready"] = False
    with pytest.raises(ValidationError, match="fault detection gate"):
        StreamFaultMatrixReport.model_validate(false_gate)

    wrong_order = report.model_dump(mode="json")
    wrong_order["cases"][0], wrong_order["cases"][1] = (
        wrong_order["cases"][1],
        wrong_order["cases"][0],
    )
    with pytest.raises(ValidationError, match="indexes must be contiguous"):
        StreamFaultMatrixReport.model_validate(wrong_order)

    path_traversal = report.model_dump(mode="json")
    captured_index = next(
        index
        for index, case in enumerate(path_traversal["cases"])
        if case["actual_status"] != "failed"
    )
    path_traversal["cases"][captured_index]["output_artifact"] = "../raw.mkv"
    with pytest.raises(ValidationError, match=r"artifacts/\*\.mkv"):
        StreamFaultMatrixReport.model_validate(path_traversal)

    false_telemetry = report.model_dump(mode="json")
    false_telemetry["cases"][1]["delay_event_count"] = 0
    with pytest.raises(ValidationError, match="execution telemetry"):
        StreamFaultMatrixReport.model_validate(false_telemetry)

    private_failure_code = report.model_dump(mode="json")
    failed_index = next(
        index
        for index, case in enumerate(private_failure_code["cases"])
        if case["actual_status"] == "failed"
    )
    private_failure_code["cases"][failed_index]["failure_code"] = (
        "private_path_failure"
    )
    with pytest.raises(ValidationError, match="failure_code"):
        StreamFaultMatrixReport.model_validate(private_failure_code)


def test_stream_fault_matrix_cli_writes_private_parent_child_ledger(
    tmp_path,
    capsys,
):
    source = tmp_path / "private-cli-fault-source.mkv"
    _write_av_container(source, seconds=2)

    exit_code = main(
        [
            "exercise-stream-faults",
            str(source),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--duration-s",
            "0.8",
            "--minimum-duration-s",
            "0.5",
            "--open-timeout-s",
            "0.25",
            "--read-timeout-s",
            "0.25",
            "--stall-duration-s",
            "0.45",
            "--prefix-byte-limit",
            str(64 * 1024),
            "--jitter-chunk-bytes",
            str(16 * 1024),
            "--jitter-delay-min-ms",
            "1",
            "--jitter-delay-max-ms",
            "3",
            "--elapsed-limit-s",
            "2",
            "--require-ready",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    run_dir = Path(output["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    parent = json.loads(
        (run_dir / "reports" / "stream-fault-matrix.json").read_text(
            encoding="utf-8"
        )
    )

    assert exit_code == 0
    assert output["scenario_count"] == 7
    assert output["fault_detection_gate_ready"] is True
    assert output["scenario_exercised_case_count"] == 7
    assert output["unexpected_ready_case_count"] == 0
    assert output["network_impairment_tolerance_proven"] is False
    assert manifest["status"] == "completed"
    assert manifest["configuration"]["fixture_path_persisted"] is False
    assert manifest["configuration"]["endpoint_value_persisted"] is False
    assert manifest["configuration"]["packet_loss_injected"] is False
    assert source.name not in json.dumps(manifest)
    assert str(source) not in json.dumps(manifest)
    assert parent["fault_detection_gate_ready"] is True
    captured_cases = [
        item for item in parent["cases"] if item["actual_status"] != "failed"
    ]
    asset_rows = (
        (run_dir / "source_assets.jsonl").read_text(encoding="utf-8").splitlines()
    )
    observation_rows = (
        (run_dir / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(asset_rows) == len(captured_cases)
    assert len(observation_rows) == len(captured_cases)
    assert len(manifest["inputs"]) == len(captured_cases)
    expected_artifacts = {"reports/stream-fault-matrix.json"}
    for case in captured_cases:
        expected_artifacts.add(case["output_artifact"])
        expected_artifacts.add(case["capture_report_artifact"])
    assert set(manifest["artifacts"]) == expected_artifacts
    run_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in run_dir.rglob("*.json*")
    )
    assert source.name not in run_text
    assert str(source) not in run_text
    assert "127.0.0.1" not in run_text
    for path in run_dir.rglob("*"):
        expected = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(path.stat().st_mode) == expected
