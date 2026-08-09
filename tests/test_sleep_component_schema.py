from __future__ import annotations

from pathlib import Path

from kangshield.information.sleep_profile import profile_sleep_export
from kangshield.information.sleep_route import assess_sleep_route


PROJECT_ROOT = Path(__file__).parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "sleep"
POLICY = PROJECT_ROOT / "configs" / "sleep" / "v1-sleep-route-policy.json"
COMPONENT_MAPPING = (
    PROJECT_ROOT
    / "configs"
    / "sleep"
    / "sdhy1-field-map.component-warehouse.example.json"
)

HUAYI_DAILY_SLEEP = FIXTURE_DIR / "huayi-daily-sleep-stats.synthetic.json"
HUAYI_DAILY_HR = FIXTURE_DIR / "huayi-daily-heart-rate.synthetic.json"
HUAYI_HISTORY = FIXTURE_DIR / "huayi-properties-history.synthetic.json"
WHST_REPORT = FIXTURE_DIR / "whst-sleep-report.synthetic.json"

ALL_COMPONENT_FIXTURES = (
    HUAYI_HISTORY,
    HUAYI_DAILY_HR,
    HUAYI_DAILY_SLEEP,
    WHST_REPORT,
)


def test_properties_history_profile_maps_documented_leaves():
    report = profile_sleep_export(HUAYI_HISTORY)

    assert report.container_path == "$.data"
    assert report.record_count == 3
    candidates = {
        (candidate.canonical_field, candidate.source_path)
        for candidate in report.mapping_candidates
    }
    assert ("heart_rate_bpm", "heartRate") in candidates
    assert ("respiratory_rate_bpm", "breathRate") in candidates
    assert ("measurement_at", "ts") in candidates
    assert "SYNTHETIC-DEVICE-0001" not in report.model_dump_json()


def test_daily_heart_rate_fixture_profiles_minutes_series():
    report = profile_sleep_export(HUAYI_DAILY_HR)

    assert report.container_path == "$.data.minutesList"
    assert report.record_count == 3
    assert any(
        candidate.canonical_field == "measurement_at"
        and candidate.source_path == "ts"
        for candidate in report.mapping_candidates
    )


def test_daily_sleep_fixture_exposes_key_value_item_shape():
    report = profile_sleep_export(HUAYI_DAILY_SLEEP)

    # The profiler takes the largest record list; here it is the
    # name/value indicator list, not the sleep-stage timeline.
    assert report.container_path == "$.data.items"
    assert report.record_count == 4
    assert any(field.path == "value" for field in report.fields)
    # "name" is a sensitive key and must not produce mapping candidates.
    assert not any(
        candidate.source_path == "name"
        for candidate in report.mapping_candidates
    )


def test_whst_report_fixture_profiles_largest_record_list():
    report = profile_sleep_export(WHST_REPORT)

    # timeOutput is the largest record list in the documented response.
    assert report.container_path == "$.data[0].sleepAnalysis.timeOutput"
    assert report.record_count == 5


def test_component_warehouse_route_stays_fail_closed():
    for fixture in ALL_COMPONENT_FIXTURES:
        profile = profile_sleep_export(fixture)

        report = assess_sleep_route(
            profile=profile,
            policy_path=POLICY,
            mapping_config_path=COMPONENT_MAPPING,
        )

        assert report.decision == "interface_only_waiting_for_e2_e3_schema"
        assert report.counts["direct_ready"] == 0
        assert report.counts["derived_enabled"] == 0
        assert report.values_persisted is False
        assert "SYNTHETIC-DEVICE-0001" not in report.model_dump_json()


def test_component_warehouse_route_marks_documented_candidates():
    profile = profile_sleep_export(HUAYI_HISTORY)

    report = assess_sleep_route(
        profile=profile,
        policy_path=POLICY,
        mapping_config_path=COMPONENT_MAPPING,
    )

    by_field = {field.canonical_field: field for field in report.direct_fields}
    assert by_field["heart_rate_bpm"].status == "candidate_unconfirmed"
    assert by_field["respiratory_rate_bpm"].status == "candidate_unconfirmed"
    assert by_field["measurement_at"].status == "candidate_unconfirmed"
    assert report.counts["direct_candidate_unconfirmed"] == 3
