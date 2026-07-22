from __future__ import annotations

from fractions import Fraction
import json
import wave

import pytest

from kangshield.information.artifacts import RunArtifacts
from kangshield.information.contracts import EvidenceLevel, ModelBinding
from kangshield.information.multimodal_pipeline import (
    MultimodalPipelineConfig,
    _same_container_audio_offset,
    run_multimodal_pipeline,
)
from kangshield.information.media_probe import probe_media
from kangshield.information.pose_backend import PoseDetection
from kangshield.information.speech_backend import SpeechSegment


class FakePoseBackend:
    @property
    def bindings(self):
        return [
            ModelBinding(
                task="human_pose_tracking",
                backend="fake",
                model_name="synthetic-pose",
                model_version="test",
                license="test-only",
                device="cpu",
            )
        ]

    def infer(self, frame):
        return [
            PoseDetection(
                bbox_xyxy=[1.0, 2.0, 20.0, 40.0],
                keypoints_xyc=[[4.0, 5.0, 0.9], [8.0, 9.0, 0.8]],
                confidence=0.85,
                track_id=7,
            )
        ]


class FakeSpeechBackend:
    def __init__(self):
        self.last_audio = None

    @property
    def bindings(self):
        return [
            ModelBinding(
                task="mandarin_speech_recognition",
                backend="fake",
                model_name="synthetic-asr",
                model_version="test",
                license="test-only",
                device="cpu",
            )
        ]

    def transcribe(self, audio):
        self.last_audio = audio
        return [
            SpeechSegment(
                start_ms=500,
                end_ms=1500,
                text="我摔倒了，救命",
                language="zh",
                confidence=0.9,
            )
        ]


def _write_video(path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10,
        (64, 48),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV video writer unavailable")
    for value in range(20):
        writer.write(np.full((48, 64, 3), value * 4, dtype=np.uint8))
    writer.release()


def _write_audio(path):
    np = pytest.importorskip("numpy")
    samples = (np.sin(np.arange(32000) * 2 * np.pi * 440 / 16000) * 1000).astype(
        "<i2"
    )
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(samples.tobytes())


def _write_av_container(path, *, audio_offset_ms: int = 250, seconds: int = 2):
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    fps = 10
    sample_rate = 8000
    samples_per_frame = sample_rate // fps
    offset_samples = round(audio_offset_ms * sample_rate / 1000)
    with av.open(str(path), "w", format="matroska") as output:
        video = output.add_stream("ffv1", rate=fps)
        video.width = 64
        video.height = 48
        video.pix_fmt = "yuv420p"
        audio = output.add_stream("pcm_s16le", rate=sample_rate)
        audio.layout = "mono"
        for index in range(seconds * fps):
            pixels = np.full((48, 64, 3), index * 4, dtype=np.uint8)
            video_frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            video_frame.pts = index
            video_frame.time_base = Fraction(1, fps)
            for packet in video.encode(video_frame):
                output.mux(packet)

            samples = np.full((1, samples_per_frame), 500, dtype=np.int16)
            audio_frame = av.AudioFrame.from_ndarray(
                samples,
                format="s16",
                layout="mono",
            )
            audio_frame.sample_rate = sample_rate
            audio_frame.pts = index * samples_per_frame + offset_samples
            audio_frame.time_base = Fraction(1, sample_rate)
            for packet in audio.encode(audio_frame):
                output.mux(packet)
        for packet in video.encode():
            output.mux(packet)
        for packet in audio.encode():
            output.mux(packet)


def test_pipeline_aligns_pose_speech_and_language_without_report_text_leak(tmp_path):
    video_path = tmp_path / "video.avi"
    audio_path = tmp_path / "speech.wav"
    _write_video(video_path)
    _write_audio(audio_path)

    with RunArtifacts(
        tmp_path / "runs",
        stage="test-multimodal",
        evidence_level=EvidenceLevel.E1,
        project_dir=tmp_path,
    ) as run:
        report = run_multimodal_pipeline(
            video_path=video_path,
            audio_path=audio_path,
            pose_backend=FakePoseBackend(),
            speech_backend=FakeSpeechBackend(),
            run=run,
            config=MultimodalPipelineConfig(
                video_sample_fps=2.0,
                fusion_window_ms=1000,
                max_duration_s=2.0,
            ),
            model_load_wall_ms=125.0,
        )

    features_text = (run.run_dir / "features.jsonl").read_text(encoding="utf-8")
    windows = [
        json.loads(line)
        for line in (run.run_dir / "multimodal_windows.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    report_text = (
        run.run_dir / "reports" / "multimodal-pipeline-report.json"
    ).read_text(encoding="utf-8")

    assert report.sampled_video_frames == 4
    assert report.pose_detection_count == 4
    assert report.speech_segment_count == 1
    assert report.multimodal_window_count == 2
    assert report.semantic_tag_counts == {"fall_related": 1, "help_request": 1}
    assert report.input_layout == "separate_files_synthetic_common_zero"
    assert report.same_container_av is False
    assert report.audio_start_offset_ms == 0.0
    assert report.timing_ms["model_load_wall"] == 125.0
    assert report.timing_ms["cold_start_total_wall"] > 125.0
    assert report.realtime_factors["processing_end_to_end"] > 0.0
    assert (
        report.realtime_factors["cold_start_end_to_end"]
        > report.realtime_factors["processing_end_to_end"]
    )
    assert "我摔倒了" in features_text
    assert "我摔倒了" not in report_text
    assert windows[0]["track_ids"] == ["7"]
    assert windows[0]["semantic_tags"] == ["fall_related", "help_request"]
    assert windows[1]["semantic_tags"] == ["fall_related", "help_request"]
    assert len(features_text.splitlines()) == 7
    assert len(
        (run.run_dir / "source_assets.jsonl").read_text(encoding="utf-8").splitlines()
    ) == 2


def test_pipeline_decodes_one_container_and_shifts_speech_by_audio_pts(tmp_path):
    container_path = tmp_path / "capture.mkv"
    _write_av_container(container_path, audio_offset_ms=250)
    speech_backend = FakeSpeechBackend()

    with RunArtifacts(
        tmp_path / "runs",
        stage="test-same-container-multimodal",
        evidence_level=EvidenceLevel.E1,
        project_dir=tmp_path,
    ) as run:
        report = run_multimodal_pipeline(
            video_path=container_path,
            audio_path=container_path,
            pose_backend=FakePoseBackend(),
            speech_backend=speech_backend,
            run=run,
            config=MultimodalPipelineConfig(
                video_sample_fps=2.0,
                fusion_window_ms=1000,
                max_duration_s=2.0,
            ),
        )

    features = [
        json.loads(line)
        for line in (run.run_dir / "features.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    speech = next(
        item for item in features if item["feature_type"] == "audio.speech_segment"
    )
    transcript = next(
        item
        for item in features
        if item["feature_type"] == "language.transcript_segment"
    )

    assert report.pipeline_version == "multimodal-replay-v0.3.0"
    assert report.input_layout == "same_container_pts"
    assert report.same_container_av is True
    assert report.audio_start_offset_ms == 250.0
    assert report.video_asset_id == report.audio_asset_id
    assert speech_backend.last_audio.start_ms == 250
    assert speech_backend.last_audio.sample_rate_hz == 16000
    assert speech["time_range"]["start_ms"] == 750
    assert speech["time_range"]["end_ms"] == 1750
    assert transcript["time_range"]["start_ms"] == 750
    assert transcript["time_range"]["end_ms"] == 1750
    assert len(
        (run.run_dir / "source_assets.jsonl").read_text(encoding="utf-8").splitlines()
    ) == 1
    assert len(
        (run.run_dir / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    ) == 1
    assert len(run.manifest.inputs) == 1
    assert (
        run.run_dir / "reports" / "multimodal-container-probe.json"
    ).is_file()
    assert not (run.run_dir / "reports" / "multimodal-audio-probe.json").exists()
    assert "separate_video_and_audio_inputs_assume_a_common_zero_time" not in (
        report.limitations
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("missing_pts_count", 1, "audio_packet_pts_missing"),
        ("scan_truncated", True, "audio_packet_scan_truncated"),
        ("pts_backward_step_count", 1, "audio_packet_pts_not_monotonic"),
    ],
)
def test_same_container_pts_gate_rejects_incomplete_audio_timing(
    tmp_path,
    field,
    value,
    message,
):
    container_path = tmp_path / "capture.mkv"
    _write_av_container(container_path)
    probe = probe_media(container_path, require_audio_track=True)
    assert probe.container_timing is not None
    audio_stream = next(
        stream
        for stream in probe.container_timing.streams
        if stream.stream_type == "audio"
    )
    setattr(audio_stream, field, value)

    with pytest.raises(ValueError, match=message):
        _same_container_audio_offset(probe)
