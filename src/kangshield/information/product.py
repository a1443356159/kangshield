"""Local-only multidomain dashboard, review API, and offline reports."""

from __future__ import annotations

import json
import os
import secrets
import stat
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median
from time import monotonic
from typing import Any, Callable
from urllib.parse import urlsplit

from .contracts import CandidateReviewDecision, WellbeingCheckinSubmission
from .longitudinal.store import DEFAULT_STORE_ROOT, LongitudinalStore
from .multidomain import (
    build_snapshot,
    candidate_from_row,
    load_policy,
)
from .resources import policy_path as bundled_policy_path
from .product_ui import dashboard_html, documentation_html, offline_report_html

PRODUCT_VERSION = "multidomain-product-v0.7.0"
WHO5_QUESTIONS = [
    "我感觉快乐、心情舒畅",
    "我感觉宁静和放松",
    "我感觉充满活力、精力充沛",
    "我醒来时感到清醒、精力充沛",
    "我的日常生活中充满了我感兴趣的事情",
]
WHO5_OPTIONS = [
    {"value": 5, "label": "所有时间"},
    {"value": 4, "label": "大多数时间"},
    {"value": 3, "label": "超过一半时间"},
    {"value": 2, "label": "少于一半时间"},
    {"value": 1, "label": "有些时候"},
    {"value": 0, "label": "没有过"},
]


def _atomic_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        stream.write(value)
        temporary = Path(stream.name)
    temporary.replace(path)


class ProductRuntime:
    def __init__(
        self,
        *,
        elder_ref: str,
        device_ref: str,
        store_root: Path = DEFAULT_STORE_ROOT,
        policy_path: Path = bundled_policy_path("v2-multidomain-risk-policy.json"),
        continuous: bool = False,
        edge_endpoint_env: str = "KANG_STREAM_ENDPOINT",
        edge_provider: str = "endpoint_env",
        edge_device_serial_env: str = "KANG_DEVICE_SERIAL",
        edge_endpoint_refresh_seconds: float = 1800.0,
        edge_policy_path: Path = bundled_policy_path("v2-edge-segment-policy.json"),
        edge_pose_model_path: Path | None = None,
        edge_failure_backoff_s: float = 2.0,
        archive_anomaly_clips: bool | None = None,
        cloud_playback_provider: str = "auto",
        playback_provider: Callable[[datetime, datetime], str] | None = None,
    ) -> None:
        self.elder_ref = elder_ref
        self.device_ref = device_ref
        self.store_root = Path(store_root)
        self.policy_path = Path(policy_path)
        self.csrf_token = secrets.token_urlsafe(32)
        self.stop_event = threading.Event()
        self.mutation_lock = threading.RLock()
        self.media_token_lock = threading.Lock()
        self.media_tokens: dict[str, tuple[str, float]] = {}
        self.edge_worker: threading.Thread | None = None
        self.last_edge_segment: dict[str, object] = {
            "status": "disabled" if not continuous else "not_started"
        }
        self.edge_monitor: Any | None = None
        from .edge_monitor import EdgeSelectionPolicy

        self.local_archive_policy = EdgeSelectionPolicy.load(edge_policy_path)
        self.archive_anomaly_clips = (
            self.local_archive_policy.archive_enabled
            if archive_anomaly_clips is None
            else bool(archive_anomaly_clips)
        )
        try:
            from .media_archive import prune_candidate_archives

            with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
                prune_candidate_archives(
                    store,
                    now=datetime.now(timezone.utc),
                    maximum_total_bytes=(
                        self.local_archive_policy.archive_maximum_total_bytes
                    ),
                )
        except Exception:
            self.last_edge_segment = {
                **self.last_edge_segment,
                "archive_maintenance": "failed",
            }
        if cloud_playback_provider not in {"auto", "none", "ezviz"}:
            raise ValueError("cloud_playback_provider must be auto, none, or ezviz")
        self.playback_provider = playback_provider
        if continuous:
            from .edge_monitor import (
                EdgeMonitor,
                endpoint_provider_from_environment,
                ezviz_provider_from_environment,
            )

            if edge_provider not in {"endpoint_env", "ezviz"}:
                raise ValueError("edge_provider must be endpoint_env or ezviz")
            provider = (
                ezviz_provider_from_environment(
                    edge_device_serial_env,
                    refresh_seconds=edge_endpoint_refresh_seconds,
                )
                if edge_provider == "ezviz"
                else endpoint_provider_from_environment(edge_endpoint_env)
            )
            self.edge_monitor = EdgeMonitor(
                elder_ref=elder_ref,
                device_ref=device_ref,
                endpoint_provider=provider,
                store_root=self.store_root,
                risk_policy_path=self.policy_path,
                selection_policy_path=edge_policy_path,
                pose_model_path=edge_pose_model_path,
                failure_backoff_s=edge_failure_backoff_s,
                stop_event=self.stop_event,
                archive_anomaly_clips=self.archive_anomaly_clips,
            )
        should_enable_ezviz_playback = cloud_playback_provider == "ezviz" or (
            cloud_playback_provider == "auto"
            and continuous
            and edge_provider == "ezviz"
        )
        if self.playback_provider is None and should_enable_ezviz_playback:
            from .ezviz_live import playback_provider_from_environment

            self.playback_provider = playback_provider_from_environment(
                edge_device_serial_env
            )

    def start(self) -> None:
        if self.edge_worker is not None or self.edge_monitor is None:
            return
        self.edge_worker = threading.Thread(
            target=self._edge_loop,
            name="kangshield-edge-monitor",
            daemon=True,
        )
        self.edge_worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        with self.media_token_lock:
            self.media_tokens.clear()
        if self.edge_worker is not None:
            self.edge_worker.join(timeout=5)

    def _edge_loop(self) -> None:
        assert self.edge_monitor is not None
        self.edge_monitor.run(on_audit=self._observe_edge_audit)

    def _observe_edge_audit(self, audit: Any) -> None:
        self.last_edge_segment = {
            "status": audit.status,
            "failure_code": audit.failure_code,
            "segment_ended_at": audit.segment_ended_at.isoformat(),
            "screened_video_seconds": audit.screened_video_seconds,
            "screened_audio_seconds": audit.screened_audio_seconds,
            "selected_pose_seconds": audit.selected_pose_seconds,
            "selected_asr_seconds": audit.selected_asr_seconds,
            "raw_media_persisted": False,
            "archived_candidate_count": audit.archived_candidate_count,
            "archive_failure_count": audit.archive_failure_count,
            "derived_anomaly_media_persisted": (
                audit.derived_anomaly_media_persisted
            ),
        }

    def snapshot(self):
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            return build_snapshot(
                store,
                device_ref=self.device_ref,
                policy_path=self.policy_path,
            )

    def candidates(self) -> list[dict[str, object]]:
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            return self._candidates_from_store(store)

    def _candidates_from_store(
        self, store: LongitudinalStore
    ) -> list[dict[str, object]]:
        reviews_by_candidate: dict[str, list[dict[str, object]]] = {}
        for review in store.fetch_candidate_reviews():
            reviews_by_candidate.setdefault(str(review["candidate_id"]), []).append(
                dict(review)
            )
        result: list[dict[str, object]] = []
        archive_rows = {
            str(row["candidate_id"]): row for row in store.fetch_media_archives()
        }
        from .media_archive import candidate_archive_available

        for row in store.fetch_domain_candidates():
            candidate_id = str(row["candidate_id"])
            item = candidate_from_row(row).model_dump(mode="json")
            payload = json.loads(row["payload_json"])
            transcript_excerpt = payload.get("transcript_excerpt")
            if isinstance(transcript_excerpt, str) and transcript_excerpt.strip():
                item["transcript_excerpt"] = transcript_excerpt.strip()[:120]
            archive = archive_rows.get(candidate_id)
            local_available = bool(
                archive is not None
                and archive["device_ref"] == self.device_ref
                and candidate_archive_available(store, archive)
            )
            cloud_available = bool(
                self.playback_provider is not None and payload.get("segment_id")
            )
            item["playback_available"] = local_available or cloud_available
            item["playback_source"] = (
                "local_archive"
                if local_available
                else "cloud"
                if cloud_available
                else None
            )
            item["archived_locally"] = local_available
            item["reviews"] = reviews_by_candidate.get(candidate_id, [])
            result.append(item)
        return result

    def event_playback(self, candidate_id: str) -> dict[str, object]:
        """Prefer a local owner archive, then fall back to ephemeral cloud media."""

        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            candidate = store.fetch_domain_candidate(candidate_id)
            if candidate is None or candidate["device_ref"] != self.device_ref:
                raise KeyError(candidate_id)
            archive = store.fetch_candidate_media_archive(candidate_id)
            if archive is not None and archive["device_ref"] == self.device_ref:
                from .media_archive import candidate_archive_verified

                if candidate_archive_verified(store, archive):
                    token = self._issue_media_token(str(archive["archive_id"]))
                    return {
                        "candidate_id": candidate_id,
                        "started_at": str(archive["started_at"]),
                        "ended_at": str(archive["ended_at"]),
                        "url": f"/api/media/{token}",
                        "source": "local_archive",
                        "ephemeral": True,
                        "locally_persisted": True,
                    }
            payload = json.loads(candidate["payload_json"])
            segment_id = payload.get("segment_id")
            if not isinstance(segment_id, str) or not segment_id:
                raise LookupError("candidate has no playable segment")
            segment = store.fetch_edge_segment(segment_id)
            if segment is None or segment["device_ref"] != self.device_ref:
                raise LookupError("candidate cloud segment is unavailable")
            occurred_at = datetime.fromisoformat(str(candidate["occurred_at"]))
            segment_start = datetime.fromisoformat(str(segment["segment_started_at"]))
            segment_end = datetime.fromisoformat(str(segment["segment_ended_at"]))
        if any(
            value.tzinfo is None
            for value in (occurred_at, segment_start, segment_end)
        ):
            raise LookupError("candidate cloud timing is invalid")
        if not segment_start <= occurred_at <= segment_end:
            raise LookupError("candidate falls outside its audited cloud segment")
        started_at = max(segment_start, occurred_at - timedelta(seconds=10))
        ended_at = min(segment_end, occurred_at + timedelta(seconds=20))
        if ended_at <= started_at:
            raise LookupError("candidate cloud window is unavailable")
        if self.playback_provider is None:
            raise LookupError("cloud playback is not configured")
        try:
            url = self.playback_provider(started_at, ended_at)
        except Exception as error:
            raise LookupError("cloud playback provider is unavailable") from error
        parsed = urlsplit(url) if isinstance(url, str) else None
        if (
            parsed is None
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise LookupError("cloud playback provider returned an invalid URL")
        return {
            "candidate_id": candidate_id,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "url": url,
            "source": "cloud",
            "ephemeral": True,
            "locally_persisted": False,
        }

    def cloud_playback(self, candidate_id: str) -> dict[str, object]:
        """Compatibility wrapper for the event playback API."""

        return self.event_playback(candidate_id)

    def _issue_media_token(self, archive_id: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.media_token_lock:
            now = monotonic()
            self.media_tokens = {
                key: value for key, value in self.media_tokens.items() if value[1] > now
            }
            self.media_tokens[token] = (archive_id, now + 600)
        return token

    def resolve_media_token(self, token: str) -> dict[str, object]:
        with self.media_token_lock:
            now = monotonic()
            record = self.media_tokens.get(token)
            if record is None or record[1] <= now:
                self.media_tokens.pop(token, None)
                raise KeyError(token)
            archive_id = record[0]
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            row = store.fetch_media_archive(archive_id)
            if row is None or row["device_ref"] != self.device_ref:
                raise KeyError(token)
            from .media_archive import (
                candidate_archive_path,
                candidate_archive_verified,
            )

            if not candidate_archive_verified(store, row):
                raise KeyError(token)
            path = candidate_archive_path(store, row)
            return {
                "path": path,
                "mime_type": str(row["mime_type"]),
                "byte_size": int(row["byte_size"]),
            }

    def trends(self) -> list[dict[str, object]]:
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            return self._trends_from_store(store)

    @staticmethod
    def _trends_from_store(store: LongitudinalStore) -> list[dict[str, object]]:
        return [
            {
                "assessed_at": row["assessed_at"],
                "domain": row["domain"],
                "score": row["score"],
                "status": row["status"],
            }
            for row in store.fetch_assessment_history(days=28)
        ]

    def personal_profile(self) -> dict[str, object]:
        policy, _ = load_policy(self.policy_path)
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            snapshot = build_snapshot(
                store,
                device_ref=self.device_ref,
                policy_path=self.policy_path,
            )
            return self._personal_profile_from_store(store, snapshot, policy)

    @staticmethod
    def _personal_profile_from_store(
        store: LongitudinalStore,
        snapshot: Any,
        policy: dict[str, Any],
    ) -> dict[str, object]:
        spec = policy["mental_wellbeing"]
        rows = [dict(row) for row in store.fetch_daily_features(limit=60)]
        eligible = sorted(
            (
                row
                for row in rows
                if int(row["eligible_segments"])
                >= int(spec["minimum_segments_per_day"])
            ),
            key=lambda row: str(row["local_date"]),
        )
        required = int(spec["minimum_baseline_days"])
        window_days = int(spec["baseline_window_days"])
        if not eligible:
            return {
                "ready": False,
                "comparison_label": f"与过去 {window_days} 天的自己相比",
                "observed_days": 0,
                "required_days": required,
                "latest_date": None,
                "summary": "还需要更多日常记录，才能建立个人基线。",
                "features": [],
            }
        current = eligible[-1]
        current_day = date.fromisoformat(str(current["local_date"]))
        baseline_start = current_day - timedelta(days=window_days)
        baseline = [
            row
            for row in eligible[:-1]
            if date.fromisoformat(str(row["local_date"])) >= baseline_start
        ]
        baseline_days = len({str(row["local_date"]) for row in baseline})
        ready = baseline_days >= required
        mental = next(
            item
            for item in snapshot.assessments
            if item.domain.value == "mental_wellbeing"
        )
        evidence = set(mental.evidence_summary)
        feature_labels = {
            "daytime_presence": "日间活动规律",
            "activity_level": "日常活动量",
            "speech_interaction": "语言互动",
            "sleep_regularity": "睡眠规律",
        }
        features: list[dict[str, str]] = []
        for feature in spec["features"]:
            if feature == "sleep_regularity" and not bool(current["sleep_confirmed"]):
                features.append(
                    {
                        "key": feature,
                        "label": feature_labels[feature],
                        "state": "unavailable",
                        "direction": "unknown",
                    }
                )
                continue
            values = [
                float(row[feature])
                for row in baseline
                if row.get(feature) is not None
                and (feature != "sleep_regularity" or bool(row["sleep_confirmed"]))
            ]
            value = current.get(feature)
            if not ready or value is None or len(values) < required:
                state, direction = "unavailable", "unknown"
            else:
                severe = f"{feature}:severe_personal_baseline_change" in evidence
                mild = f"{feature}:mild_personal_baseline_change" in evidence
                state = (
                    "significant_change"
                    if severe
                    else "slight_change"
                    if mild
                    else "stable"
                )
                center = median(values)
                direction = (
                    "higher"
                    if float(value) > center
                    else "lower"
                    if float(value) < center
                    else "stable"
                )
            features.append(
                {
                    "key": feature,
                    "label": feature_labels[feature],
                    "state": state,
                    "direction": direction,
                }
            )
        return {
            "ready": ready,
            "comparison_label": f"与过去 {window_days} 天的自己相比",
            "observed_days": len({str(row["local_date"]) for row in eligible}),
            "baseline_days": baseline_days,
            "required_days": required,
            "latest_date": str(current["local_date"]),
            "summary": (
                f"已用 {baseline_days} 个有效日期建立个人日常基线。"
                if ready
                else f"已记录 {baseline_days} 天，还需至少 {required} 天建立个人基线。"
            ),
            "features": features,
        }

    def wellbeing_checkin(self) -> dict[str, object]:
        policy, _ = load_policy(self.policy_path)
        now = datetime.now().astimezone()
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            return self._wellbeing_checkin_from_store(store, policy, now)

    @staticmethod
    def _wellbeing_checkin_from_store(
        store: LongitudinalStore,
        policy: dict[str, Any],
        now: datetime,
    ) -> dict[str, object]:
        spec = policy["mental_wellbeing"]["monthly_wellbeing_checkin"]
        current_month = now.strftime("%Y-%m")
        rows = [dict(row) for row in store.fetch_wellbeing_checkins(limit=12)]
        current = next(
            (row for row in rows if row["checkin_month"] == current_month), None
        )
        next_month = (now.date().replace(day=28) + timedelta(days=4)).replace(day=1)
        threshold = int(spec["low_wellbeing_raw_score_below"])
        history = [
            {
                "month": row["checkin_month"],
                "completed_at": row["completed_at"],
                "percentage_score": int(row["percentage_score"]),
                "needs_attention": int(row["raw_score"]) < threshold,
            }
            for row in rows
        ]
        current_payload = None
        if current is not None:
            current_payload = {
                "month": current["checkin_month"],
                "completed_at": current["completed_at"],
                "answers": json.loads(current["answers_json"]),
                "raw_score": int(current["raw_score"]),
                "percentage_score": int(current["percentage_score"]),
                "needs_attention": int(current["raw_score"]) < threshold,
            }
        return {
            "instrument": {
                "id": spec["instrument_id"],
                "revision": spec["instrument_revision"],
                "timeframe": "过去两个星期",
                "questions": WHO5_QUESTIONS,
                "options": WHO5_OPTIONS,
                "screening_threshold_raw_below": threshold,
                "attribution": "世界卫生组织 WHO-5，2024，CC BY-NC-SA 3.0 IGO",
            },
            "due": current is None,
            "due_month": current_month,
            "next_reminder_date": (
                now.date().isoformat() if current is None else next_month.isoformat()
            ),
            "current": current_payload,
            "history": history,
            "affects_mental_risk": True,
            "disclaimer": "自评结果会参与心理健康风险规则，但不是临床诊断。",
        }

    def dashboard(self) -> dict[str, object]:
        """Build the complete dashboard from one SQLite connection and snapshot."""

        policy, _ = load_policy(self.policy_path)
        now_utc = datetime.now(timezone.utc)
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            snapshot = build_snapshot(
                store,
                device_ref=self.device_ref,
                policy_path=self.policy_path,
                now=now_utc,
            )
            return {
                "schema_version": "2.0",
                "generated_at": now_utc.isoformat(),
                "snapshot": snapshot.model_dump(mode="json"),
                "candidates": self._candidates_from_store(store),
                "trends": self._trends_from_store(store),
                "profile": self._personal_profile_from_store(
                    store, snapshot, policy
                ),
                "wellbeing_checkin": self._wellbeing_checkin_from_store(
                    store, policy, now_utc.astimezone()
                ),
                "monitor": {
                    "mode": (
                        "continuous_in_memory"
                        if self.edge_monitor is not None
                        else "database_only"
                    ),
                    "last_segment": self.last_edge_segment,
                    "raw_media_persisted": False,
                    "local_anomaly_archive_count": len(
                        store.fetch_media_archives()
                    ),
                    "local_anomaly_archive_enabled": (
                        self.archive_anomaly_clips
                    ),
                },
            }

    def save_wellbeing_checkin(
        self, submission: WellbeingCheckinSubmission
    ) -> dict[str, object]:
        policy, _ = load_policy(self.policy_path)
        spec = policy["mental_wellbeing"]["monthly_wellbeing_checkin"]
        now = datetime.now().astimezone()
        raw_score = sum(submission.answers)
        with self.mutation_lock:
            with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
                store.upsert_wellbeing_checkin(
                    checkin_month=now.strftime("%Y-%m"),
                    completed_at=now.isoformat(),
                    answers=submission.answers,
                    raw_score=raw_score,
                    percentage_score=raw_score * 4,
                    instrument_id=str(spec["instrument_id"]),
                    instrument_revision=str(spec["instrument_revision"]),
                )
                snapshot = build_snapshot(
                    store,
                    device_ref=self.device_ref,
                    policy_path=self.policy_path,
                    persist=True,
                )
                checkin = self._wellbeing_checkin_from_store(store, policy, now)
        return {
            "checkin": checkin,
            "snapshot": snapshot.model_dump(mode="json"),
        }

    def delete_current_wellbeing_checkin(self) -> dict[str, object]:
        policy, _ = load_policy(self.policy_path)
        now = datetime.now().astimezone()
        current_month = now.strftime("%Y-%m")
        with self.mutation_lock:
            with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
                if not store.delete_wellbeing_checkin(current_month):
                    raise KeyError(current_month)
                snapshot = build_snapshot(
                    store,
                    device_ref=self.device_ref,
                    policy_path=self.policy_path,
                    persist=True,
                )
                checkin = self._wellbeing_checkin_from_store(store, policy, now)
        return {
            "checkin": checkin,
            "snapshot": snapshot.model_dump(mode="json"),
        }

    def review(self, decision: CandidateReviewDecision) -> dict[str, object]:
        with self.mutation_lock:
            with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
                store.review_candidate(
                    candidate_id=decision.candidate_id,
                    decision=decision.decision.value,
                    decided_at=decision.decided_at.isoformat(),
                    operator=decision.operator,
                    owner_note=decision.owner_note,
                )
                snapshot = build_snapshot(
                    store,
                    device_ref=self.device_ref,
                    policy_path=self.policy_path,
                    persist=True,
                )
        return snapshot.model_dump(mode="json")


def make_product_handler(runtime: ProductRuntime, *, host: str, port: int):
    expected_origin = f"http://{host}:{port}"

    class ProductHandler(BaseHTTPRequestHandler):
        server_version = "KangShieldLocal/0.6"

        def log_message(self, format: str, *args: object) -> None:
            return None

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            parts = path.strip("/").split("/")
            is_media = len(parts) == 3 and parts[:2] == ["api", "media"]
            if is_media:
                self._send_media(parts[2])
            elif path == "/":
                self._send_html(_dashboard_html(runtime.csrf_token))
            elif path == "/docs":
                self._send_html(_documentation_html())
            elif path == "/api/health":
                self._send_json(
                    {
                        "status": "ok",
                        "product_version": PRODUCT_VERSION,
                        "local_only": True,
                        "global_score": None,
                        "last_edge_segment": runtime.last_edge_segment,
                    }
                )
            elif path == "/api/dashboard":
                self._send_json(runtime.dashboard())
            elif path == "/api/snapshot":
                self._send_json(runtime.snapshot().model_dump(mode="json"))
            elif path == "/api/candidates":
                self._send_json({"candidates": runtime.candidates()})
            elif path == "/api/trends":
                self._send_json({"trends": runtime.trends()})
            elif path == "/api/profile":
                self._send_json(runtime.personal_profile())
            elif path == "/api/wellbeing-checkin":
                self._send_json(runtime.wellbeing_checkin())
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            parts = path.strip("/").split("/")
            is_review = (
                len(parts) == 4
                and parts[:2] == ["api", "candidates"]
                and parts[3] == "review"
            )
            is_checkin = path == "/api/wellbeing-checkin"
            is_playback = (
                len(parts) == 4
                and parts[:2] == ["api", "candidates"]
                and parts[3] == "playback"
            )
            if not is_review and not is_checkin and not is_playback:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not self._authorize_json_mutation(expected_origin, runtime.csrf_token):
                return
            try:
                payload = self._read_json()
                if is_review:
                    payload["candidate_id"] = parts[2]
                    decision = CandidateReviewDecision.model_validate(payload)
                    result = {"snapshot": runtime.review(decision)}
                elif is_playback:
                    result = runtime.event_playback(parts[2])
                else:
                    submission = WellbeingCheckinSubmission.model_validate(payload)
                    result = runtime.save_wellbeing_checkin(submission)
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            except LookupError:
                self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
                return
            except Exception:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            self._send_json(result)

        def do_DELETE(self) -> None:
            path = urlsplit(self.path).path
            if path != "/api/wellbeing-checkin":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not self._authorize_mutation(expected_origin, runtime.csrf_token):
                return
            try:
                result = runtime.delete_current_wellbeing_checkin()
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._send_json(result)

        def _authorize_mutation(self, origin: str, csrf_token: str) -> bool:
            if not self._valid_same_origin(origin):
                self.send_error(HTTPStatus.FORBIDDEN)
                return False
            if not secrets.compare_digest(
                self.headers.get("X-CSRF-Token", ""), csrf_token
            ):
                self.send_error(HTTPStatus.FORBIDDEN)
                return False
            return True

        def _authorize_json_mutation(self, origin: str, csrf_token: str) -> bool:
            if not self._authorize_mutation(origin, csrf_token):
                return False
            if not self.headers.get("Content-Type", "").lower().startswith(
                "application/json"
            ):
                self.send_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return False
            return True

        def _read_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16_384:
                raise ValueError("invalid request length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            return payload

        def _valid_same_origin(self, origin: str) -> bool:
            return (
                self.headers.get("Origin") == origin
                and self.headers.get("Host") == origin.removeprefix("http://")
            )

        def _send_json(self, payload: object, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
            )
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_media(self, token: str) -> None:
            fetch_site = self.headers.get("Sec-Fetch-Site")
            if fetch_site not in (None, "same-origin"):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            try:
                media = runtime.resolve_media_token(token)
            except (KeyError, LookupError):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            path = media["path"]
            size = int(media["byte_size"])
            start = 0
            end = size - 1
            status = HTTPStatus.OK
            range_header = self.headers.get("Range")
            if range_header:
                if not range_header.startswith("bytes=") or "," in range_header:
                    self._send_range_error(size)
                    return
                raw_start, separator, raw_end = range_header[6:].partition("-")
                if not separator:
                    self._send_range_error(size)
                    return
                try:
                    if raw_start:
                        start = int(raw_start)
                        end = int(raw_end) if raw_end else size - 1
                    elif raw_end:
                        suffix = int(raw_end)
                        if suffix <= 0:
                            raise ValueError
                        start = max(0, size - suffix)
                    else:
                        raise ValueError
                except ValueError:
                    self._send_range_error(size)
                    return
                if start < 0 or start >= size or end < start:
                    self._send_range_error(size)
                    return
                end = min(end, size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
            length = end - start + 1
            try:
                descriptor = os.open(
                    Path(path),
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                )
                details = os.fstat(descriptor)
                if not stat.S_ISREG(details.st_mode) or details.st_size != size:
                    os.close(descriptor)
                    raise OSError("candidate archive changed before playback")
            except OSError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(status)
            self.send_header("Content-Type", str(media["mime_type"]))
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Disposition", "inline")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.end_headers()
            with os.fdopen(descriptor, "rb") as stream:
                stream.seek(start)
                remaining = length
                while remaining:
                    chunk = stream.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def _send_range_error(self, size: int) -> None:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _send_html(self, body_text: str) -> None:
            body = body_text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
            )
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline';"
                " style-src 'self' 'unsafe-inline'; connect-src 'self';"
                " media-src 'self' https:;"
                " frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ProductHandler


def serve_product(
    *,
    elder_ref: str,
    device_ref: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    store_root: Path = DEFAULT_STORE_ROOT,
    policy_path: Path = bundled_policy_path("v2-multidomain-risk-policy.json"),
    demo: bool = False,
    continuous: bool = False,
    edge_endpoint_env: str = "KANG_STREAM_ENDPOINT",
    edge_provider: str = "endpoint_env",
    edge_device_serial_env: str = "KANG_DEVICE_SERIAL",
    edge_endpoint_refresh_seconds: float = 1800.0,
    edge_policy_path: Path = bundled_policy_path("v2-edge-segment-policy.json"),
    edge_pose_model_path: Path | None = None,
    edge_failure_backoff_s: float = 2.0,
    archive_anomaly_clips: bool | None = None,
    cloud_playback_provider: str = "auto",
) -> None:
    if host != "127.0.0.1":
        raise ValueError("serve-product only permits host 127.0.0.1")
    if not 1 <= port <= 65535:
        raise ValueError("port must be 1..65535")
    if demo and continuous:
        raise ValueError("demo mode cannot open a continuous live stream")
    if demo:
        from .product_demo import seed_product_demo

        seed_product_demo(
            elder_ref=elder_ref,
            device_ref=device_ref,
            store_root=store_root,
            policy_path=policy_path,
            edge_policy_path=edge_policy_path,
        )
    runtime = ProductRuntime(
        elder_ref=elder_ref,
        device_ref=device_ref,
        store_root=store_root,
        policy_path=policy_path,
        continuous=continuous,
        edge_endpoint_env=edge_endpoint_env,
        edge_provider=edge_provider,
        edge_device_serial_env=edge_device_serial_env,
        edge_endpoint_refresh_seconds=edge_endpoint_refresh_seconds,
        edge_policy_path=edge_policy_path,
        edge_pose_model_path=edge_pose_model_path,
        edge_failure_backoff_s=edge_failure_backoff_s,
        archive_anomaly_clips=archive_anomaly_clips,
        cloud_playback_provider=cloud_playback_provider,
    )
    server = ThreadingHTTPServer((host, port), make_product_handler(runtime, host=host, port=port))
    runtime.start()
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.shutdown()
        server.server_close()
        runtime.stop()


def export_product_report(
    *,
    elder_ref: str,
    device_ref: str | None,
    visibility: str,
    output: Path,
    store_root: Path = DEFAULT_STORE_ROOT,
    policy_path: Path = bundled_policy_path("v2-multidomain-risk-policy.json"),
) -> tuple[Path, Path]:
    if visibility not in {"owner_only", "public_evidence"}:
        raise ValueError("unsupported report visibility")
    resolved_device = device_ref or _only_device_ref(elder_ref, store_root)
    policy, _ = load_policy(policy_path)
    now_utc = datetime.now(timezone.utc)
    with LongitudinalStore(elder_ref, root=store_root) as store:
        snapshot = build_snapshot(
            store,
            device_ref=resolved_device,
            policy_path=policy_path,
            now=now_utc,
        )
        trends = [dict(row) for row in store.fetch_assessment_history(days=28)]
        reviews = [dict(row) for row in store.fetch_candidate_reviews()]
        candidate_payloads = {
            str(row["candidate_id"]): json.loads(row["payload_json"])
            for row in store.fetch_domain_candidates()
        }
        profile = ProductRuntime._personal_profile_from_store(
            store, snapshot, policy
        )
        wellbeing_checkin = ProductRuntime._wellbeing_checkin_from_store(
            store, policy, now_utc.astimezone()
        )
    synthetic_demo = elder_ref.startswith("demo-") and resolved_device.startswith(
        "demo-"
    )
    if visibility == "owner_only":
        owner_snapshot = snapshot.model_dump(mode="json")
        for item in owner_snapshot["timeline"]:
            excerpt = candidate_payloads.get(item["candidate_id"], {}).get(
                "transcript_excerpt"
            )
            if isinstance(excerpt, str) and excerpt.strip():
                item["transcript_excerpt"] = excerpt.strip()[:120]
        payload: dict[str, object] = {
            "visibility": visibility,
            "elder_ref": elder_ref,
            "device_ref": resolved_device,
            "snapshot": owner_snapshot,
            "synthetic_demo": synthetic_demo,
            "profile": profile,
            "wellbeing_checkin": wellbeing_checkin,
            "trends": [
                {
                    "assessed_at": row["assessed_at"],
                    "domain": row["domain"],
                    "score": row["score"],
                    "status": row["status"],
                }
                for row in trends
            ],
            "reviews": reviews,
        }
    else:
        payload = _public_payload(snapshot, trends)
        payload["synthetic_demo"] = synthetic_demo
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    json_path = output / "report.json"
    html_path = output / "report.html"
    _atomic_write(
        json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    _atomic_write(html_path, _offline_report_html(payload))
    json_path.chmod(0o600)
    html_path.chmod(0o600)
    return html_path, json_path


def _only_device_ref(elder_ref: str, store_root: Path) -> str:
    with LongitudinalStore(elder_ref, root=store_root) as store:
        refs = store.counts().get("device_refs", [])
        ledger_refs = [
            str(row[0])
            for row in store._connection.execute(
                "SELECT DISTINCT device_ref FROM analysis_ledger WHERE device_ref IS NOT NULL"
            )
        ]
    choices = sorted(set(refs) | set(ledger_refs))
    if len(choices) != 1:
        raise ValueError("public export requires a uniquely discoverable target device")
    return choices[0]


def _public_payload(snapshot, trends: list[dict[str, object]]) -> dict[str, object]:
    assessments = [
        {
            "domain": item.domain.value,
            "score": item.score,
            "status": item.status.value,
            "policy_revision": item.policy_revision,
            "policy_digest": item.policy_digest,
            "policy_summary": item.policy_summary,
            "pilot_unvalidated": True,
            "limitations": item.limitations,
        }
        for item in snapshot.assessments
    ]
    public_trends = [
        {
            "date": str(row["assessed_at"])[:10],
            "domain": row["domain"],
            "score": row["score"],
            "status": row["status"],
        }
        for row in trends
    ]
    return {
        "schema_version": "2.0",
        "visibility": "public_evidence",
        "report_version": snapshot.report_version,
        "assessments": assessments,
        "trends": public_trends,
        "data_freshness": {"stale": bool(snapshot.data_freshness.get("stale"))},
        "global_score": None,
        "limitations": snapshot.limitations,
    }


def _offline_report_html(payload: dict[str, object]) -> str:
    return offline_report_html(payload)


def _dashboard_html(csrf_token: str) -> str:
    return dashboard_html(csrf_token)


def _documentation_html() -> str:
    return documentation_html(PRODUCT_VERSION)
