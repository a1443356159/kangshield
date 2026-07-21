from __future__ import annotations

import json
import wave

import pytest

from kangshield.information.artifacts import RunArtifacts
from kangshield.information.contracts import EvidenceLevel, ModelBinding
from kangshield.information.multimodal_pipeline import (
    MultimodalPipelineConfig,
    run_multimodal_pipeline,
)
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
