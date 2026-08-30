from __future__ import annotations

import json
from datetime import date, timedelta

from kangshield.information.multidomain import load_policy
from kangshield.validation.public_domains import (
    FraudTextCase,
    _controlled_mental_response,
    evaluate_fraud_cases,
    evaluate_fraud_gate,
    evaluate_mental_gate,
    fraud_cases_for_split,
    parse_casas_line,
    read_casas_daily_rows,
)


POLICY, POLICY_DIGEST = load_policy()


def test_fbs_hash_partition_is_deterministic_and_disjoint():
    cases = [
        FraudTextCase(
            case_ref=f"fbs-{index:08x}{0:016x}",
            category="FR:Other" if index % 2 else "AD:Other",
            text=f"message {index}",
        )
        for index in range(100)
    ]

    dev = fraud_cases_for_split(cases, "dev")
    holdout = fraud_cases_for_split(cases, "holdout")

    assert {item.case_ref for item in dev}.isdisjoint(
        item.case_ref for item in holdout
    )
    assert {item.case_ref for item in dev + holdout} == {
        item.case_ref for item in cases
    }


def test_fraud_metrics_use_source_labels_after_rule_matching_and_hide_text():
    cases = [
        FraudTextCase(
            case_ref="fbs-a",
            category="FR:Phishing(Bank)",
            text="我是公安局工作人员，请马上提供银行卡号和验证码",
        ),
        FraudTextCase(
            case_ref="fbs-b",
            category="AD:Retail",
            text="今日普通商品优惠",
        ),
        FraudTextCase(
            case_ref="fbs-c",
            category="FR:Other",
            text="反诈宣传提醒：不要转账，不给验证码",
        ),
    ]

    metrics = evaluate_fraud_cases(cases, POLICY)

    assert metrics["source_fraud_category_recall"] == 0.5
    assert metrics["source_non_fraud_category_flag_rate"] == 0.0
    assert metrics["hard_negative_suppressed_count"] == 1
    serialized = json.dumps(metrics, ensure_ascii=False)
    assert "公安局" not in serialized
    assert "普通商品" not in serialized
    assert evaluate_fraud_gate({})["passed"] is False


def test_casas_line_parser_keeps_only_structured_event_fields():
    event = parse_casas_line(
        "2020-01-02 22:15:00.125 M001 ON Sleep begin"
    )

    assert event is not None
    assert event.sensor == "M001"
    assert event.message == "ON"
    assert event.activity == "Sleep"
    assert event.activity_boundary == "begin"

    csv_event = parse_casas_line(
        '2020-01-02,22:15:00.125,Bedroom,ON,Sleep="begin"'
    )
    assert csv_event is not None
    assert csv_event.sensor == "Bedroom"
    assert csv_event.activity == "Sleep"
    assert csv_event.activity_boundary == "begin"


def test_casas_daily_adapter_builds_three_segment_personal_days(tmp_path):
    import zipfile

    lines = []
    start = date(2020, 1, 1)
    for offset in range(10):
        current = start + timedelta(days=offset)
        for hour in (6, 10, 14):
            lines.append(f"{current} {hour:02d}:05:00 M001 ON")
        lines.append(f"{current} 22:15:00 M002 ON Sleep begin")
    archive = tmp_path / "casas.zip"
    with zipfile.ZipFile(archive, mode="w") as output:
        output.writestr("labeled/hh101.txt", "\n".join(lines))

    rows, parse = read_casas_daily_rows(archive, "hh101")

    assert len(rows) == 10
    assert all(item["eligible_segments"] == 3 for item in rows)
    assert all(item["sleep_confirmed"] == 1 for item in rows)
    assert parse == {"total_lines": 40, "invalid_lines": 0}


def test_controlled_personal_baseline_checks_all_frozen_levels():
    start = date(2020, 1, 1)
    rows = []
    for offset in range(28):
        variation = (-1, 0, 1, 0)[offset % 4]
        rows.append(
            {
                "local_date": (start + timedelta(days=offset)).isoformat(),
                "eligible_segments": 3,
                "daytime_presence": 0.5 + variation * 0.03,
                "activity_level": 4.0 + variation * 0.2,
                "speech_interaction": None,
                "sleep_regularity": 22.5 + variation * 0.1,
                "sleep_confirmed": 1,
            }
        )

    result = _controlled_mental_response(rows, POLICY, POLICY_DIGEST)

    assert result["available"] is True
    assert result["expected_levels_observed"] is True, result
    assert result["observed_levels"] == {
        "one_mild": 1,
        "one_severe": 2,
        "two_severe": 3,
        "three_day_level_two": 3,
    }
    assert evaluate_mental_gate({})["passed"] is False
