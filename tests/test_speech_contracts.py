from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from kangshield.information.contracts import SpeechSegment, TimeRange, VoiceCandidate


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VOICE_POLICY = PROJECT_ROOT / "configs" / "v1-g4-voice-candidate-policy.json"


def test_speech_segment_contract_validates_bounds():
    segment = SpeechSegment(start_ms=0, end_ms=600, text="救命", language="zh")
    assert segment.finalized is True
    assert segment.transcript_ref is None
    with pytest.raises(ValidationError):
        SpeechSegment(start_ms=600, end_ms=0, text="x", language="zh")


def test_voice_candidate_never_emits_risk_assessment():
    candidate = VoiceCandidate(
        candidate_id="voice_candidate_test_001",
        category="help_request",
        time_range=TimeRange(start_ms=0, end_ms=600),
        matcher_revision="voice-candidate-matcher-v0.1.0",
    )
    assert candidate.review_status == "pending_review"
    assert candidate.risk_assessment_emitted is False
    with pytest.raises(ValidationError):
        VoiceCandidate(
            candidate_id="voice_candidate_test_003",
            category="help_request",
            matcher_revision="voice-candidate-matcher-v0.1.0",
            risk_assessment_emitted=True,
        )
    with pytest.raises(ValidationError):
        VoiceCandidate(
            candidate_id="voice_candidate_test_002",
            category="fraud_related",
            matcher_revision="voice-candidate-matcher-v0.1.0",
        )


def test_voice_candidate_policy_is_deterministic_and_d1_scoped():
    policy = json.loads(VOICE_POLICY.read_text(encoding="utf-8"))
    assert policy["matcher_type"] == "deterministic_keyword"
    assert policy["llm_allowed"] is False
    assert set(policy["categories"]) == {"help_request", "fall_related"}
    assert policy["output_rules"]["risk_assessment_emitted"] is False
    assert policy["output_rules"]["voice_candidate_alone_never_confirms_fall"] is True
