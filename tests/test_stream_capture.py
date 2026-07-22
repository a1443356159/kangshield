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

from kangshield.information.artifacts import RunArtifacts
from kangshield.information.cli import main
from kangshield.information.contracts import (
    EvidenceLevel,
    ModelBinding,
    SourceType,
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
    with pytest.raises(RuntimeError, match="synthetic probe failure"):
        capture_stream(
            endpoint=str(source),
            output_path=output,
            output_artifact="artifacts/stream-capture.mkv",
            source_type=SourceType.FIXTURE,
            config=StreamCaptureConfig(duration_s=1.0),
        )
    assert not output.exists()
