from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import stat
import threading

import pytest

from kangshield.information.contracts import (
    EdgeSegmentAudit,
    EvidenceLevel,
    ModelBinding,
    SourceType,
    SpeechSegment,
)
from kangshield.information.edge_monitor import (
    BufferedVideoFrame,
    EdgeModelAnalyzer,
    EdgeMonitor,
    EdgeMonitorError,
    EdgeSelectionPolicy,
    EdgeAnalysisOutcome,
    InMemoryEdgeSegment,
    LightweightSegmentSelector,
    SegmentSelection,
    capture_in_memory_segment,
)
from kangshield.information.longitudinal.store import LongitudinalStore
from kangshield.information.segment_analysis import AnalysisResult
from kangshield.information.speech_backend import AudioBuffer


def _segment(*, seconds=10, moving=True, speaking=True):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    frames = []
    for index in range(seconds * 5):
        pixels = np.zeros((90, 160, 3), dtype=np.uint8)
        if moving and seconds <= index < seconds * 3:
            offset = (index * 3) % 110
            pixels[:, offset : offset + 30] = 220
        ok, encoded = cv2.imencode(".jpg", pixels)
        assert ok
        frames.append(BufferedVideoFrame(index * 200, encoded.tobytes()))
    samples = np.zeros(seconds * 16000, dtype=np.float32)
    if speaking:
        samples[2 * 16000 : min(seconds, 7) * 16000] = 0.05
    started = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
    return InMemoryEdgeSegment(
        segment_id="edge-test-1",
        device_ref="target",
        started_at=started,
        ended_at=started + timedelta(seconds=seconds),
        duration_ms=seconds * 1000,
        frames=tuple(frames),
        audio=AudioBuffer(
            samples=samples,
            sample_rate_hz=16000,
            duration_ms=seconds * 1000,
        ),
        frame_width=160,
        frame_height=90,
        cloud_recording_ref="cloud-recording:test",
    )


class _PoseBackend:
    calls = 0

    @property
    def bindings(self):
        return [
            ModelBinding(
                task="human_pose_tracking",
                backend="fake",
                model_name="fake-pose",
                license="test-only",
                device="cpu",
            )
        ]

    def reset(self):
        return None

    def infer(self, frame):
        self.calls += 1
        return []


class _SpeechBackend:
    calls = 0

    @property
    def bindings(self):
        return [
            ModelBinding(
                task="voice_activity_detection",
                backend="fake",
                model_name="fake-vad",
                license="test-only",
                device="cpu",
            ),
            ModelBinding(
                task="mandarin_speech_recognition",
                backend="fake",
                model_name="fake-asr",
                license="test-only",
                device="cpu",
            ),
        ]

    def transcribe(self, audio):
        self.calls += 1
        return [
            SpeechSegment(
                start_ms=0,
                end_ms=audio.duration_ms,
                text="请立即转账并且保密",
                language="zh",
            )
        ]


def test_lightweight_selector_caps_heavy_inputs_and_keeps_key_windows():
    segment = _segment()
    policy = EdgeSelectionPolicy.load()
    assert policy.archive_enabled is True
    assert policy.archive_retention_days == 30
    assert policy.archive_maximum_total_bytes == 2 * 1024**3
    selection = LightweightSegmentSelector(policy).select(segment)

    assert 0 < len(selection.video_frames) <= len(segment.frames) / 2
    assert 0 < selection.selected_audio_seconds <= segment.audio.duration_ms / 2000
    assert any("motion" in window.reasons for window in selection.key_windows)
    assert any("audio_activity" in window.reasons for window in selection.key_windows)
    assert all(window.end_ms <= segment.duration_ms for window in selection.key_windows)


def test_video_selection_ratio_is_a_hard_cap_for_odd_frame_counts():
    segment = _segment(seconds=11)
    policy = EdgeSelectionPolicy.load()

    selection = LightweightSegmentSelector(policy).select(segment)

    assert len(segment.frames) == 55
    assert len(selection.video_frames) <= 27


def test_selected_windows_only_are_sent_to_heavy_models():
    pose = _PoseBackend()
    speech = _SpeechBackend()
    analyzer = EdgeModelAnalyzer(
        selection_policy=EdgeSelectionPolicy.load(),
        pose_backend=pose,
        speech_backend=speech,
    )
    segment = _segment()

    outcome = analyzer.analyze(segment, receipt_digest="a" * 64)

    assert 0 < pose.calls < len(segment.frames)
    assert speech.calls >= 1
    assert outcome.result.audio_valid_seconds < segment.audio.duration_ms / 1000
    assert len(outcome.result.candidates) == 1
    candidate, payload = outcome.result.candidates[0]
    assert candidate.domain.value == "fraud"
    assert payload["transcript_excerpt"] == "请立即转账并且保密"


def test_pose_model_path_is_external_and_environment_configurable(monkeypatch):
    model = "/cache/models/kangshield-pose.pt"
    monkeypatch.setenv("KANGSHIELD_POSE_MODEL", model)

    analyzer = EdgeModelAnalyzer(selection_policy=EdgeSelectionPolicy.load())

    assert analyzer.pose_model_path.as_posix() == model


def test_pose_model_digest_mismatch_fails_before_model_loading(tmp_path):
    model = tmp_path / "pose.pt"
    model.write_bytes(b"not-the-frozen-model")
    analyzer = EdgeModelAnalyzer(
        selection_policy=EdgeSelectionPolicy.load(),
        pose_model_path=model,
    )

    with pytest.raises(EdgeMonitorError, match="digest mismatch"):
        analyzer._ensure_pose()


def test_edge_audit_contract_forbids_local_raw_media():
    started = datetime(2026, 8, 30, tzinfo=timezone.utc)
    common = dict(
        segment_id="edge-1",
        device_ref="target",
        segment_started_at=started,
        segment_ended_at=started + timedelta(seconds=60),
        status="completed",
        cloud_recording_ref="cloud-recording:test",
        selector_revision="r1",
        selector_digest="a" * 64,
    )
    audit = EdgeSegmentAudit(**common)
    assert audit.raw_video_persisted is False
    assert audit.raw_audio_persisted is False
    with pytest.raises(Exception):
        EdgeSegmentAudit(**common, raw_video_persisted=True)
    archived = EdgeSegmentAudit(
        **common,
        candidate_count=1,
        anomaly_archive_enabled=True,
        archived_candidate_count=1,
        derived_anomaly_media_persisted=True,
    )
    assert archived.raw_video_persisted is False
    assert archived.derived_anomaly_media_persisted is True
    with pytest.raises(Exception):
        EdgeSegmentAudit(
            **common,
            candidate_count=1,
            anomaly_archive_enabled=True,
            archived_candidate_count=1,
            derived_anomaly_media_persisted=False,
        )


def test_monitor_persists_path_free_audit_candidate_and_model_coverage(tmp_path):
    pose = _PoseBackend()
    speech = _SpeechBackend()
    analyzer = EdgeModelAnalyzer(
        selection_policy=EdgeSelectionPolicy.load(),
        pose_backend=pose,
        speech_backend=speech,
    )
    monitor = EdgeMonitor(
        elder_ref="elder_a",
        device_ref="target",
        endpoint_provider=lambda: "memory://secret-endpoint",
        store_root=tmp_path / "store",
        segment_source=lambda endpoint: _segment(),
        analyzer=analyzer,
    )

    audit = monitor.process_once()

    assert audit.status == "completed"
    assert audit.raw_video_persisted is False
    with LongitudinalStore("elder_a", root=tmp_path / "store") as store:
        row = store.fetch_edge_segments()[0]
        store.record_edge_segment(dict(row))
        assert len(store.fetch_edge_segments()) == 1
        serialized = " ".join(str(value) for value in row)
        assert "memory://" not in serialized
        assert row["raw_media_persisted"] == 0
        assert row["selected_asr_seconds"] < row["screened_audio_seconds"]
        candidate = store.fetch_domain_candidates()[0]
        assert "cloud-recording:test" in candidate["payload_json"]
        archive = store.fetch_candidate_media_archive(candidate["candidate_id"])
        assert archive is not None
        archive_path = store.elder_dir / archive["relative_path"]
        assert archive_path.is_file()
        assert stat.S_IMODE(archive_path.stat().st_mode) == 0o600
        assert audit.archived_candidate_count == 1
        assert audit.derived_anomaly_media_persisted is True
        av = pytest.importorskip("av")
        with av.open(str(archive_path)) as container:
            assert len(container.streams.video) == 1
            assert len(container.streams.audio) == 1
        coverage = store.coverage_since(
            "2026-08-30T00:00:00+00:00", "target"
        )
        assert coverage["audio_seconds"] == row["selected_asr_seconds"]


def test_anomaly_archive_can_be_explicitly_disabled(tmp_path):
    analyzer = EdgeModelAnalyzer(
        selection_policy=EdgeSelectionPolicy.load(),
        pose_backend=_PoseBackend(),
        speech_backend=_SpeechBackend(),
    )
    monitor = EdgeMonitor(
        elder_ref="elder_a",
        device_ref="target",
        endpoint_provider=lambda: "memory://stream",
        store_root=tmp_path / "store",
        segment_source=lambda endpoint: _segment(),
        analyzer=analyzer,
        archive_anomaly_clips=False,
    )

    audit = monitor.process_once()

    assert audit.status == "completed"
    assert audit.anomaly_archive_enabled is False
    assert audit.archived_candidate_count == 0
    with LongitudinalStore("elder_a", root=tmp_path / "store") as store:
        assert len(store.fetch_domain_candidates()) == 1
        assert store.fetch_media_archives() == []


def test_archive_failure_is_audited_without_losing_risk_candidate(
    tmp_path, monkeypatch
):
    from kangshield.information import media_archive

    def fail_archive(*args, **kwargs):
        raise media_archive.MediaArchiveError("synthetic encoder failure")

    monkeypatch.setattr(media_archive, "archive_candidate_clip", fail_archive)
    monitor = EdgeMonitor(
        elder_ref="elder_a",
        device_ref="target",
        endpoint_provider=lambda: "memory://stream",
        store_root=tmp_path / "store",
        segment_source=lambda endpoint: _segment(),
        analyzer=EdgeModelAnalyzer(
            selection_policy=EdgeSelectionPolicy.load(),
            pose_backend=_PoseBackend(),
            speech_backend=_SpeechBackend(),
        ),
    )

    audit = monitor.process_once()

    assert audit.status == "partial"
    assert audit.failure_code == "media_archive_failed"
    assert audit.archive_failure_count == 1
    with LongitudinalStore("elder_a", root=tmp_path / "store") as store:
        assert len(store.fetch_domain_candidates()) == 1
        assert store.fetch_media_archives() == []


def test_monitor_failure_is_sanitized_and_does_not_persist_endpoint(tmp_path):
    def fail(_endpoint):
        raise EdgeMonitorError("secret endpoint detail", code="stream_open_failed")

    monitor = EdgeMonitor(
        elder_ref="elder_a",
        device_ref="target",
        endpoint_provider=lambda: "https://secret.example/live?token=private",
        store_root=tmp_path / "store",
        segment_source=fail,
    )

    audit = monitor.process_once()

    assert audit.status == "failed"
    assert audit.failure_code == "stream_open_failed"
    with LongitudinalStore("elder_a", root=tmp_path / "store") as store:
        row = store.fetch_edge_segments()[0]
        serialized = " ".join(str(value) for value in row)
        assert "secret.example" not in serialized
        assert "private" not in serialized


def test_live_fixture_is_decoded_in_memory_without_media_artifact(tmp_path):
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    fixture = tmp_path / "source.mkv"
    with av.open(str(fixture), "w", format="matroska") as output:
        video = output.add_stream("ffv1", rate=10)
        video.width = 160
        video.height = 90
        video.pix_fmt = "yuv420p"
        audio = output.add_stream("pcm_s16le", rate=16000)
        audio.layout = "mono"
        for index in range(20):
            pixels = np.full((90, 160, 3), index * 5, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts = index
            frame.time_base = Fraction(1, 10)
            for packet in video.encode(frame):
                output.mux(packet)
            samples = np.full((1, 1600), 500, dtype=np.int16)
            audio_frame = av.AudioFrame.from_ndarray(
                samples, format="s16", layout="mono"
            )
            audio_frame.sample_rate = 16000
            audio_frame.pts = index * 1600
            audio_frame.time_base = Fraction(1, 16000)
            for packet in audio.encode(audio_frame):
                output.mux(packet)
        for packet in video.encode():
            output.mux(packet)
        for packet in audio.encode():
            output.mux(packet)

    policy = replace(
        EdgeSelectionPolicy.load(),
        segment_duration_seconds=1.5,
        minimum_segment_seconds=1.0,
    )
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    segment = capture_in_memory_segment(
        str(fixture),
        device_ref="fixture",
        policy=policy,
        evidence_level=EvidenceLevel.E1,
        source_type=SourceType.FIXTURE,
    )
    after = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    assert segment.duration_ms == 1500
    assert segment.frames
    assert segment.audio.duration_ms == 1500
    assert after == before


def test_ezviz_provider_caches_only_in_memory_and_invalidates(monkeypatch):
    from kangshield.information import ezviz_live

    calls = []

    def fetch(serial):
        calls.append(serial)
        return f"https://stream.example/{len(calls)}"

    monkeypatch.setattr(ezviz_live, "fetch_live_endpoint", fetch)
    provider = ezviz_live.EzvizEndpointProvider("private-serial", refresh_seconds=60)

    assert provider() == "https://stream.example/1"
    assert provider() == "https://stream.example/1"
    provider.invalidate()
    assert provider() == "https://stream.example/2"
    assert calls == ["private-serial", "private-serial"]


def test_ezviz_cloud_playback_uses_bounded_time_and_never_returns_token(monkeypatch):
    from kangshield.information import ezviz_live

    monkeypatch.setenv("YS7_APP_KEY", "private-app-key")
    monkeypatch.setenv("YS7_APP_SECRET", "private-app-secret")
    calls = []

    def post(path, fields):
        calls.append((path, dict(fields)))
        if path.endswith("token/get"):
            return {"data": {"accessToken": "private-access-token"}}
        return {"data": {"url": "https://open.ys7.com/event/cloud.m3u8?sig=x"}}

    monkeypatch.setattr(ezviz_live, "_post", post)
    started = datetime(2026, 8, 30, 0, 0, tzinfo=timezone.utc)
    endpoint = ezviz_live.fetch_playback_endpoint(
        "private-serial",
        started_at=started,
        ended_at=started + timedelta(seconds=30),
    )

    assert endpoint == "https://open.ys7.com/event/cloud.m3u8?sig=x"
    fields = calls[1][1]
    assert fields["type"] == "3"
    assert fields["protocol"] == "3"
    assert fields["supportH265"] == "0"
    assert fields["startTime"] == "2026-08-30 08:00:00"
    assert fields["stopTime"] == "2026-08-30 08:00:30"
    assert "private-access-token" not in endpoint


def test_capture_producer_continues_while_single_model_worker_is_busy(tmp_path):
    second_captured = threading.Event()
    source_calls = []

    def source(_endpoint):
        index = len(source_calls) + 1
        source_calls.append(index)
        if index == 2:
            second_captured.set()
        segment = _segment(moving=False, speaking=False)
        return replace(
            segment,
            segment_id=f"edge-{index}",
            started_at=segment.started_at + timedelta(seconds=index),
            ended_at=segment.ended_at + timedelta(seconds=index),
        )

    class Analyzer:
        calls = 0

        def analyze(self, segment, *, receipt_digest):
            self.calls += 1
            if self.calls == 1:
                assert second_captured.wait(timeout=2)
            return EdgeAnalysisOutcome(
                result=AnalysisResult(),
                selection=SegmentSelection(
                    video_frames=(),
                    audio_windows_ms=(),
                    key_windows=(),
                    motion_threshold=0.01,
                    audio_threshold=0.01,
                ),
            )

    monitor = EdgeMonitor(
        elder_ref="elder_a",
        device_ref="target",
        endpoint_provider=lambda: "memory://stream",
        store_root=tmp_path / "store",
        segment_source=source,
        analyzer=Analyzer(),
    )

    counts = monitor.run(max_segments=2, queue_size=2)

    assert counts == {"attempted": 2, "completed": 2, "partial": 0, "failed": 0}
    assert source_calls == [1, 2]
