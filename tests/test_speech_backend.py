from __future__ import annotations

import pytest

from kangshield.information.speech_backend import (
    WhisperSpeechBackend,
    _model_license,
    _normalize_funasr_result,
    _normalize_whisper_result,
    _resolve_model_reference,
    _snapshot_version,
    _weight_digest,
    tag_transcript,
)


def test_normalize_funasr_timestamp_result():
    segments = _normalize_funasr_result(
        [
            {
                "text": "欢迎使用语音识别模型",
                "timestamp": [[120, 300], [300, 900]],
            }
        ],
        duration_ms=1000,
        language="zh",
    )

    assert len(segments) == 1
    assert segments[0].start_ms == 120
    assert segments[0].end_ms == 900
    assert segments[0].text == "欢迎使用语音识别模型"


def test_normalize_whisper_seconds_and_fallback_text():
    segments = _normalize_whisper_result(
        {
            "text": "不应重复拼接",
            "segments": [
                {"start": 0.12, "end": 0.9, "text": "欢迎使用"},
                {"start": 0.9, "end": 1.5, "text": "语音识别"},
            ],
        },
        duration_ms=1000,
        language="zh",
    )

    assert [(item.start_ms, item.end_ms, item.text) for item in segments] == [
        (120, 900, "欢迎使用"),
        (900, 1000, "语音识别"),
    ]
    fallback = _normalize_whisper_result(
        {"text": "只有汇总文本", "segments": []},
        duration_ms=1000,
        language="zh",
    )
    assert len(fallback) == 1
    assert fallback[0].text == "只有汇总文本"


def test_normalize_whisper_silence_is_empty():
    assert _normalize_whisper_result(
        {"text": "", "segments": []}, duration_ms=2000, language="zh"
    ) == []


def test_whisper_candidate_rejects_unreviewed_checkpoint(tmp_path):
    checkpoint = tmp_path / "candidate.pt"
    checkpoint.write_bytes(b"not-the-pinned-checkpoint")

    with pytest.raises(ValueError, match="checkpoint digest changed"):
        WhisperSpeechBackend(checkpoint, device="cpu", fp16=False)


def test_transcript_tags_are_observational_categories():
    assert tag_transcript("我摔倒了，快来人帮帮我") == [
        "fall_related",
        "help_request",
    ]
    assert tag_transcript("今天天气很好") == []


def test_explicit_local_model_snapshot_is_offline_and_digestible(tmp_path):
    snapshot = tmp_path / "snapshots" / "revision-1"
    snapshot.mkdir(parents=True)
    (snapshot / "config.yaml").write_text("model: fixture\n", encoding="utf-8")
    (snapshot / "model.pt").write_bytes(b"synthetic-weight")

    assert _resolve_model_reference(str(snapshot), offline=True) == str(snapshot)
    assert _snapshot_version(str(snapshot)) == "revision-1"
    assert _weight_digest(str(snapshot)) == (
        "615949a888a3d598f114021095c5c05d4f1a3be27619dce65c50c15f2a2000a8"
    )


def test_known_model_licenses_are_bound_and_custom_models_require_review():
    assert _model_license("paraformer-zh") == "Apache-2.0"
    assert _model_license("fsmn-vad") == "Apache-2.0"
    assert _model_license("ct-punc") == "Apache-2.0"
    assert _model_license("local/custom-model") == "model-license-review-required"
