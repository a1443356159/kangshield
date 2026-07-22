from __future__ import annotations

import hashlib

from kangshield.information.contracts import SpeechBenchmarkCaseEvaluation
from kangshield.information.speech_backend import SpeechSegment
from kangshield.information.speech_benchmark import (
    _union_segment_duration_ms,
    aggregate_speech_cases,
)
from scripts.prepare_v1_m3_speech_models import prepare_whisper


def _case(
    *,
    case_id: str,
    gender: str,
    reference_chars: int,
    hypothesis_chars: int,
    edits: int,
    exact: bool,
) -> SpeechBenchmarkCaseEvaluation:
    return SpeechBenchmarkCaseEvaluation(
        case_id=case_id,
        variant_id="fixture-asr",
        run_id=f"run-{case_id}",
        audio_sample=f"{case_id}.wav",
        audio_gender=gender,
        audio_duration_ms=1000,
        segment_count=1,
        speech_duration_ms=800,
        speech_coverage=0.8,
        reference_char_count=reference_chars,
        hypothesis_char_count=hypothesis_chars,
        edit_distance=edits,
        character_error_rate=round(edits / reference_chars, 6),
        transcript_exact_match=exact,
        blank_output=hypothesis_chars == 0,
        timing_ms={"speech_inference": 100.0},
        realtime_factor=0.1,
    )


def test_speech_case_aggregate_uses_corpus_cer_and_omits_text_fields():
    cases = [
        _case(
            case_id="female-1",
            gender="female",
            reference_chars=100,
            hypothesis_chars=96,
            edits=6,
            exact=False,
        ),
        _case(
            case_id="male-1",
            gender="male",
            reference_chars=37,
            hypothesis_chars=35,
            edits=3,
            exact=False,
        ),
    ]

    aggregate = aggregate_speech_cases(cases)

    assert aggregate["total_reference_chars"] == 137
    assert aggregate["total_edit_distance"] == 9
    assert aggregate["corpus_character_error_rate"] == 0.065693
    assert aggregate["speech_coverage"] == 0.8
    assert aggregate["by_gender"]["female"]["corpus_character_error_rate"] == 0.06
    serialized = cases[0].model_dump_json()
    assert "reference_transcript" not in serialized
    assert "hypothesis_text" not in serialized


def test_union_segment_duration_merges_overlap_and_clamps_to_audio():
    segments = [
        SpeechSegment(0, 600, "甲", "zh"),
        SpeechSegment(500, 900, "乙", "zh"),
        SpeechSegment(950, 1200, "丙", "zh"),
    ]
    assert _union_segment_duration_ms(segments, 1000) == 950


def test_prepare_whisper_offline_verifies_existing_file(tmp_path):
    payload = b"fixture-whisper-weight"
    digest = hashlib.sha256(payload).hexdigest()
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "small.pt").write_bytes(payload)

    result = prepare_whisper(
        {
            "model_id": "small-fixture",
            "output_path": "small.pt",
            "url": "https://invalid.example/never-used",
            "byte_size": len(payload),
            "sha256": digest,
        },
        models_dir=model_dir,
        offline=True,
    )

    assert result["status"] == "verified_existing"
    assert result["sha256"] == digest
