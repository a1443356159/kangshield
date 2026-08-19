from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from kangshield.information.contracts import (
    CandidateReviewStatus,
    DomainCandidate,
    DomainRiskAssessment,
    DomainRiskStatus,
    MultidomainSnapshotReport,
    RiskDomain,
    TimeRange,
)
from kangshield.information.multidomain import (
    classify_fraud_text,
    load_policy,
    score_fall,
    score_fraud,
    score_mental_wellbeing,
)

POLICY, DIGEST = load_policy()
NOW = datetime(2026, 8, 19, 4, 0, tzinfo=timezone.utc)


def _candidate(domain, category, seconds=0, status="pending"):
    return DomainCandidate(
        candidate_id=f"{domain}-{category}-{seconds}",
        domain=domain,
        category=category,
        occurred_at=NOW + timedelta(seconds=seconds),
        evidence_refs=["feature:test"],
        review_status=status,
    )


def _assessment(domain):
    return DomainRiskAssessment(
        domain=domain,
        score=0,
        status="assessed",
        window=TimeRange(start_at=NOW - timedelta(days=1), end_at=NOW),
        policy_revision=POLICY["revision"],
        policy_digest=DIGEST,
        policy_summary=POLICY["policy_summary"][domain.value],
    )


def test_snapshot_contract_requires_exactly_three_domains_and_no_global_score():
    report = MultidomainSnapshotReport(
        report_version="test",
        assessments=[_assessment(domain) for domain in RiskDomain],
    )
    assert report.global_score is None
    with pytest.raises(ValidationError, match="three risk domains"):
        MultidomainSnapshotReport(
            report_version="test",
            assessments=[_assessment(RiskDomain.FALL)] * 3,
        )
    with pytest.raises(ValidationError):
        MultidomainSnapshotReport(
            report_version="test",
            assessments=[_assessment(domain) for domain in RiskDomain],
            global_score=2,
        )


def test_null_score_requires_reason_and_non_assessed_status():
    with pytest.raises(ValidationError, match="limitation"):
        DomainRiskAssessment(
            domain="fall",
            score=None,
            status="insufficient_data",
            window=TimeRange(),
            policy_revision="r1",
            policy_digest="a" * 64,
            policy_summary="summary",
        )


@pytest.mark.parametrize(
    ("candidates", "deviations", "pose", "expected"),
    [
        ([_candidate("fall", "fall_candidate", status="confirmed")], [], 0, 3),
        (
            [
                _candidate("fall", "fall_candidate"),
                _candidate("fall", "help_speech", seconds=10),
            ],
            [],
            0,
            3,
        ),
        ([_candidate("fall", "fall_candidate")], [], 0, 2),
        ([], [{"detected_at": NOW.isoformat(), "score": 2}], 0, 2),
        ([], [{"detected_at": NOW.isoformat(), "score": 1}], 0, 1),
        ([], [], 600, 0),
        ([], [], 599, None),
    ],
)
def test_fall_rule_levels(candidates, deviations, pose, expected):
    result = score_fall(
        candidates,
        deviations=deviations,
        pose_seconds=pose,
        now=NOW,
        stale=False,
        policy=POLICY,
        policy_digest=DIGEST,
    )
    assert result.score == expected


def test_rejected_fall_candidate_is_excluded_and_zero_becomes_stale():
    result = score_fall(
        [_candidate("fall", "fall_candidate", status="rejected")],
        deviations=[],
        pose_seconds=600,
        now=NOW,
        stale=True,
        policy=POLICY,
        policy_digest=DIGEST,
    )
    assert result.score is None
    assert result.status is DomainRiskStatus.DATA_STALE


def _daily(day, values, segments=3, sleep_confirmed=True):
    return {
        "local_date": day,
        "eligible_segments": segments,
        "daytime_presence": values[0],
        "activity_level": values[1],
        "speech_interaction": values[2],
        "sleep_regularity": values[3],
        "sleep_confirmed": int(sleep_confirmed),
    }


def test_mental_baseline_is_fail_closed_then_scores_severe_changes():
    insufficient = score_mental_wellbeing(
        [_daily("2026-08-18", (1, 1, 1, 1))],
        now=NOW,
        stale=False,
        policy=POLICY,
        policy_digest=DIGEST,
    )
    assert insufficient.score is None
    rows = []
    for day in range(10, 18):
        value = 0.9 if day % 2 else 1.1
        rows.append(_daily(f"2026-08-{day:02d}", (value,) * 4))
    rows.append(_daily("2026-08-19", (5, 5, 1, 1)))
    result = score_mental_wellbeing(
        rows,
        now=NOW,
        stale=False,
        policy=POLICY,
        policy_digest=DIGEST,
    )
    assert result.score == 3
    assert result.data_coverage["eligible_distinct_days"] == 9


def test_fraud_hard_negative_and_score_combinations():
    assert classify_fraud_text("反诈宣传提醒：不要转账，不给验证码", POLICY) == ([], True)
    categories, suppressed = classify_fraud_text(
        "我是公安局的，请马上转账到安全账户", POLICY
    )
    assert suppressed is False
    assert {"impersonation", "urgency_secrecy", "transfer_investment"} <= set(categories)
    first = _candidate("fraud", "fraud_language")
    result = score_fraud(
        [first],
        candidate_payload={
            first.candidate_id: {
                "categories": ["transfer_investment", "impersonation"]
            }
        },
        audio_seconds=0,
        now=NOW,
        stale=False,
        policy=POLICY,
        policy_digest=DIGEST,
    )
    assert result.score == 3
    assert "inaudible_other_side" in " ".join(result.limitations)
    zero = score_fraud(
        [],
        candidate_payload={},
        audio_seconds=600,
        now=NOW,
        stale=False,
        policy=POLICY,
        policy_digest=DIGEST,
    )
    assert zero.score == 0
