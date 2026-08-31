from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from kangshield.information.longitudinal.store import LongitudinalStore
from kangshield.information.multidomain import (
    build_snapshot,
    load_policy,
    score_mental_wellbeing,
)
from kangshield.information.product import ProductRuntime, export_product_report


POLICY, POLICY_DIGEST = load_policy()


def _feature_row(day: date, values, *, segments: int = 3, updated_at: str = ""):
    return {
        "local_date": day.isoformat(),
        "eligible_segments": segments,
        "daytime_presence": values[0],
        "activity_level": values[1],
        "speech_interaction": values[2],
        "sleep_regularity": values[3],
        "sleep_confirmed": 1,
        "source_refs_json": "[]",
        "updated_at": updated_at or f"{day.isoformat()}T12:00:00+00:00",
    }


def _variable_baseline(start: date, days: int = 28):
    rows = []
    for offset in range(days):
        variation = (-1, 0, 1, 0)[offset % 4]
        rows.append(
            _feature_row(
                start + timedelta(days=offset),
                (
                    0.5 + variation * 0.03,
                    4.0 + variation * 0.2,
                    2.0 + variation * 0.1,
                    22.5 + variation * 0.1,
                ),
            )
        )
    return rows


def _level_two_day(day: date):
    return _feature_row(day, (0.8, 4.0, 2.0, 22.5))


def _mental_score(rows, day: date):
    return score_mental_wellbeing(
        rows,
        now=datetime.combine(day, time(12), tzinfo=timezone.utc),
        stale=False,
        policy=POLICY,
        policy_digest=POLICY_DIGEST,
    )


def test_level_two_streak_requires_consecutive_calendar_days():
    start = date(2026, 6, 1)
    baseline = _variable_baseline(start)
    first = start + timedelta(days=28)

    consecutive = [*baseline]
    consecutive_scores = []
    for offset in range(3):
        current = first + timedelta(days=offset)
        consecutive.append(_level_two_day(current))
        consecutive_scores.append(_mental_score(consecutive, current).score)
    assert consecutive_scores == [2, 2, 3]

    gapped = [*baseline]
    gapped_scores = []
    for offset in (0, 2, 4):
        current = first + timedelta(days=offset)
        gapped.append(_level_two_day(current))
        result = _mental_score(gapped, current)
        gapped_scores.append(result.score)
    assert gapped_scores == [2, 2, 2]
    assert "level_2_or_higher_for_three_days" not in result.evidence_summary


def test_sixty_day_personal_window_checkin_restart_rollover_and_export(tmp_path):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    today = now.astimezone().date()
    store_root = tmp_path / "store"

    with LongitudinalStore("elder-longitudinal", root=store_root) as store:
        # These 31 large historical values must not affect the current 28-day baseline.
        for age in range(59, 28, -1):
            store.upsert_daily_feature(
                _feature_row(
                    today - timedelta(days=age),
                    (99.0, 99.0, 99.0, 99.0),
                    updated_at=now.isoformat(),
                )
            )
        recent = _variable_baseline(today - timedelta(days=28))
        for row in recent:
            row["updated_at"] = now.isoformat()
            store.upsert_daily_feature(row)
        store.upsert_daily_feature(
            _feature_row(
                today,
                (0.5, 4.0, 2.0, 22.5),
                updated_at=now.isoformat(),
            )
        )
        store.record_analysis_attempt(
            media_digest="1" * 64,
            report_digest="2" * 64,
            run_id="longitudinal-test",
            device_ref="device-longitudinal",
            attempted_at=now.isoformat(),
            captured_start_at=(now - timedelta(minutes=12)).isoformat(),
            captured_end_at=now.isoformat(),
            status="completed",
            pose_quality_seconds=600,
            audio_valid_seconds=600,
        )
        stable = build_snapshot(
            store,
            device_ref="device-longitudinal",
            now=now,
            persist=True,
        )
        mental = next(
            item
            for item in stable.assessments
            if item.domain.value == "mental_wellbeing"
        )
        assert mental.score == 0
        assert mental.status.value == "assessed"
        store.upsert_wellbeing_checkin(
            checkin_month=now.astimezone().strftime("%Y-%m"),
            completed_at=now.astimezone().isoformat(),
            answers=[2, 2, 2, 2, 2],
            raw_score=10,
            percentage_score=40,
            instrument_id="WHO-5",
            instrument_revision="WHO/UCN/MSD/MHE/2024.1",
        )
        attention = build_snapshot(
            store,
            device_ref="device-longitudinal",
            now=now,
            persist=True,
        )
        mental = next(
            item
            for item in attention.assessments
            if item.domain.value == "mental_wellbeing"
        )
        assert mental.score == 2

    runtime = ProductRuntime(
        elder_ref="elder-longitudinal",
        device_ref="device-longitudinal",
        store_root=store_root,
        cloud_playback_provider="none",
    )
    profile = runtime.personal_profile()
    assert profile["ready"] is True
    assert profile["baseline_days"] == 28
    assert all(item["state"] == "stable" for item in profile["features"])

    with LongitudinalStore("elder-longitudinal", root=store_root) as store:
        assert len(store.fetch_daily_features(limit=60)) == 60
        assert len(store.fetch_wellbeing_checkins(limit=12)) == 1
        assert sum(
            row["domain"] == "mental_wellbeing"
            for row in store.fetch_assessment_history(days=28)
        ) == 2
        next_month = (
            now.astimezone().date().replace(day=28) + timedelta(days=4)
        ).replace(day=1) + timedelta(days=2)
        rollover_now = datetime.combine(
            next_month, time(12), tzinfo=now.astimezone().tzinfo
        )
        rollover = build_snapshot(
            store,
            device_ref="device-longitudinal",
            now=rollover_now,
        )
        rollover_mental = next(
            item
            for item in rollover.assessments
            if item.domain.value == "mental_wellbeing"
        )
        assert rollover_mental.score is None
        assert rollover_mental.status.value == "data_stale"
        checkin = runtime._wellbeing_checkin_from_store(
            store, POLICY, rollover_now
        )
        assert checkin["due"] is True

    _, public_json = export_product_report(
        elder_ref="elder-longitudinal",
        device_ref="device-longitudinal",
        visibility="public_evidence",
        output=tmp_path / "public",
        store_root=store_root,
    )
    public_text = public_json.read_text(encoding="utf-8")
    for forbidden in (
        "elder-longitudinal",
        "device-longitudinal",
        "answers_json",
        "percentage_score",
        "wellbeing_checkins",
    ):
        assert forbidden not in public_text
