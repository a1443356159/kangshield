"""Local-only multidomain dashboard, review API, and offline reports."""

from __future__ import annotations

import html
import json
import secrets
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .artifacts import atomic_write_json, atomic_write_text
from .contracts import CandidateReviewDecision
from .incremental_analysis import IncrementalAnalyzer
from .longitudinal.store import DEFAULT_STORE_ROOT, LongitudinalStore
from .multidomain import DEFAULT_POLICY_PATH, build_snapshot, candidate_from_row

PRODUCT_VERSION = "multidomain-product-v0.1.0"


class ProductRuntime:
    def __init__(
        self,
        *,
        elder_ref: str,
        device_ref: str,
        store_root: Path = DEFAULT_STORE_ROOT,
        runs_dir: Path = Path("runs"),
        policy_path: Path = DEFAULT_POLICY_PATH,
        scan_interval_seconds: int = 300,
    ) -> None:
        self.elder_ref = elder_ref
        self.device_ref = device_ref
        self.store_root = Path(store_root)
        self.runs_dir = Path(runs_dir)
        self.policy_path = Path(policy_path)
        self.scan_interval_seconds = max(1, int(scan_interval_seconds))
        self.csrf_token = secrets.token_urlsafe(32)
        self.analyzer = IncrementalAnalyzer(
            elder_ref=elder_ref,
            device_ref=device_ref,
            store_root=self.store_root,
            runs_dir=self.runs_dir,
            policy_path=self.policy_path,
        )
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.last_scan: dict[str, object] = {"status": "not_started"}

    def start(self) -> None:
        if self.worker is not None:
            return
        self.worker = threading.Thread(
            target=self._scan_loop, name="kangshield-product-analysis", daemon=True
        )
        self.worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.worker is not None:
            self.worker.join(timeout=5)

    def _scan_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                counts = self.analyzer.scan_once()
                if counts.get("completed"):
                    with LongitudinalStore(
                        self.elder_ref, root=self.store_root
                    ) as store:
                        build_snapshot(
                            store,
                            device_ref=self.device_ref,
                            policy_path=self.policy_path,
                            persist=True,
                        )
            except Exception as error:
                self.last_scan = {
                    "status": "failed",
                    "error": type(error).__name__,
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                self.last_scan = {
                    "status": "completed",
                    "counts": counts,
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            self.stop_event.wait(self.scan_interval_seconds)

    def snapshot(self):
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            return build_snapshot(
                store,
                device_ref=self.device_ref,
                policy_path=self.policy_path,
            )

    def candidates(self) -> list[dict[str, object]]:
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            rows = store.fetch_domain_candidates()
            result: list[dict[str, object]] = []
            for row in rows:
                item = candidate_from_row(row).model_dump(mode="json")
                item["reviews"] = [dict(review) for review in store.fetch_candidate_reviews(str(row["candidate_id"]))]
                result.append(item)
            return result

    def trends(self) -> list[dict[str, object]]:
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            return [
                {
                    "assessed_at": row["assessed_at"],
                    "domain": row["domain"],
                    "score": row["score"],
                    "status": row["status"],
                }
                for row in store.fetch_assessment_history(days=28)
            ]

    def review(self, decision: CandidateReviewDecision) -> dict[str, object]:
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
        server_version = "KangShieldLocal/0.1"

        def log_message(self, format: str, *args: object) -> None:
            return None

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/":
                self._send_html(_dashboard_html(runtime.csrf_token))
            elif path == "/api/health":
                self._send_json(
                    {
                        "status": "ok",
                        "product_version": PRODUCT_VERSION,
                        "local_only": True,
                        "global_score": None,
                        "last_scan": runtime.last_scan,
                    }
                )
            elif path == "/api/snapshot":
                self._send_json(runtime.snapshot().model_dump(mode="json"))
            elif path == "/api/candidates":
                self._send_json({"candidates": runtime.candidates()})
            elif path == "/api/trends":
                self._send_json({"trends": runtime.trends()})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            parts = path.strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "candidates"] or parts[3] != "review":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not self._valid_same_origin(expected_origin):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if not self.headers.get("Content-Type", "").lower().startswith(
                "application/json"
            ):
                self.send_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            if not secrets.compare_digest(
                self.headers.get("X-CSRF-Token", ""), runtime.csrf_token
            ):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 16_384:
                    raise ValueError("invalid request length")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                payload["candidate_id"] = parts[2]
                decision = CandidateReviewDecision.model_validate(payload)
                snapshot = runtime.review(decision)
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            except Exception:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"snapshot": snapshot})

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
            self.send_header("Content-Security-Policy", "default-src 'none'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, body_text: str) -> None:
            body = body_text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'",
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
    runs_dir: Path = Path("runs"),
    policy_path: Path = DEFAULT_POLICY_PATH,
    scan_interval_seconds: int = 300,
) -> None:
    if host != "127.0.0.1":
        raise ValueError("serve-product only permits host 127.0.0.1")
    if not 1 <= port <= 65535:
        raise ValueError("port must be 1..65535")
    runtime = ProductRuntime(
        elder_ref=elder_ref,
        device_ref=device_ref,
        store_root=store_root,
        runs_dir=runs_dir,
        policy_path=policy_path,
        scan_interval_seconds=scan_interval_seconds,
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
    policy_path: Path = DEFAULT_POLICY_PATH,
) -> tuple[Path, Path]:
    if visibility not in {"owner_only", "public_evidence"}:
        raise ValueError("unsupported report visibility")
    resolved_device = device_ref or _only_device_ref(elder_ref, store_root)
    with LongitudinalStore(elder_ref, root=store_root) as store:
        snapshot = build_snapshot(
            store, device_ref=resolved_device, policy_path=policy_path
        )
        trends = [dict(row) for row in store.fetch_assessment_history(days=28)]
        reviews = [dict(row) for row in store.fetch_candidate_reviews()]
    if visibility == "owner_only":
        payload: dict[str, object] = {
            "visibility": visibility,
            "elder_ref": elder_ref,
            "device_ref": resolved_device,
            "snapshot": snapshot.model_dump(mode="json"),
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
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    json_path = output / "report.json"
    html_path = output / "report.html"
    atomic_write_json(json_path, payload)
    atomic_write_text(html_path, _offline_report_html(payload))
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
    serialized = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    title = "KangShield 三域风险离线报告"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{_STYLE}</style></head>
<body><main><h1>{html.escape(title)}</h1><p class="pilot">本地试点，pilot_unvalidated；不是概率、临床诊断或诈骗确认结论。</p><div id="cards"></div><h2>28 天趋势</h2><div id="trends"></div><h2>候选事件</h2><div id="timeline"></div><h2>复核审计</h2><div id="reviews"></div></main>
<script type="application/json" id="payload">{serialized}</script><script>{_OFFLINE_SCRIPT}</script></body></html>"""


def _dashboard_html(csrf_token: str) -> str:
    token = html.escape(csrf_token, quote=True)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>KangShield 三域风险</title><style>{_STYLE}</style></head>
<body><main><h1>KangShield 三域风险</h1><p class="pilot">本地试点，未达发布门。分数为 pilot_unvalidated 规则等级，不是概率、临床诊断或诈骗确认。</p><div id="cards"></div><h2>28 天趋势</h2><div id="trends"></div><h2>候选事件与人工复核</h2><div id="timeline"></div><h2>设备 / 模型 / 数据质量</h2><pre id="quality"></pre></main>
<script>const CSRF="{token}";{_DASHBOARD_SCRIPT}</script></body></html>"""


_STYLE = """
:root{font-family:system-ui,sans-serif;color:#16202a;background:#f4f6f8}body{margin:0}main{max-width:1080px;margin:auto;padding:24px}.pilot{padding:12px;background:#fff3cd;border-left:4px solid #d99b00}.grid,#cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}.card{background:white;border-radius:10px;padding:16px;box-shadow:0 1px 4px #0002}.score{font-size:2.4rem;font-weight:700}.muted{color:#5f6b76;font-size:.9rem}.event{background:white;margin:8px 0;padding:12px;border-radius:8px}button{margin-right:8px;padding:6px 10px}pre{white-space:pre-wrap;background:white;padding:14px;border-radius:8px}table{border-collapse:collapse;width:100%;background:white}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:left}
"""

_OFFLINE_SCRIPT = r"""
const p=JSON.parse(document.getElementById('payload').textContent);const snap=p.snapshot||p;const a=snap.assessments||[];const cards=document.getElementById('cards');cards.className='grid';for(const x of a){const d=document.createElement('section');d.className='card';const h=document.createElement('h2');h.textContent=x.domain;const s=document.createElement('div');s.className='score';s.textContent=x.score===null?'暂无评分':String(x.score);const q=document.createElement('p');q.textContent=(x.evidence_summary||[]).join('；')||x.policy_summary||x.status;const c=document.createElement('p');c.className='muted';c.textContent=x.data_coverage?'数据覆盖：'+JSON.stringify(x.data_coverage):x.status;d.append(h,s,q,c);cards.append(d)}for(const [id,value] of [['trends',p.trends||[]],['timeline',snap.timeline||[]],['reviews',p.reviews||[]]]){const node=document.getElementById(id),pre=document.createElement('pre');pre.textContent=JSON.stringify(value,null,2);node.append(pre)}
"""

_DASHBOARD_SCRIPT = r"""
const names={fall:'跌倒风险',mental_wellbeing:'心理健康风险',fraud:'诈骗风险'};function el(t,c){const x=document.createElement(t);if(c)x.className=c;return x}async function load(){const [s,c,t]=await Promise.all([fetch('/api/snapshot').then(r=>r.json()),fetch('/api/candidates').then(r=>r.json()),fetch('/api/trends').then(r=>r.json())]);const cards=document.getElementById('cards');cards.textContent='';for(const a of s.assessments){const d=el('section','card'),h=el('h2'),sc=el('div','score'),st=el('p','muted'),cov=el('p','muted'),ev=el('p');h.textContent=names[a.domain]||a.domain;sc.textContent=a.score===null?'暂无评分':String(a.score);st.textContent=a.status+' · pilot_unvalidated · 更新 '+s.generated_at;cov.textContent='数据覆盖：'+JSON.stringify(a.data_coverage);ev.textContent=(a.evidence_summary||[]).join('；')||a.limitations.join('；');d.append(h,sc,st,cov,ev);cards.append(d)}document.getElementById('quality').textContent=JSON.stringify({freshness:s.data_freshness,quality:s.quality_status},null,2);const timeline=document.getElementById('timeline');timeline.textContent='';for(const x of c.candidates){const d=el('div','event'),h=el('strong'),p=el('p','muted'),audit=el('p','muted');h.textContent=(names[x.domain]||x.domain)+' · '+x.category;p.textContent=x.occurred_at+' · '+x.review_status+' · '+x.evidence_summary.join('；');audit.textContent=(x.reviews||[]).map(r=>r.decided_at+' '+r.decision+' '+(r.owner_note||'')).join('；');d.append(h,p,audit);if(x.review_status==='pending'){for(const decision of ['confirmed','rejected']){const b=el('button');b.textContent=decision==='confirmed'?'确认':'驳回';b.onclick=()=>review(x.candidate_id,decision);d.append(b)}}timeline.append(d)}document.getElementById('trends').textContent=JSON.stringify(t.trends,null,2)}async function review(id,decision){const note=prompt('Owner-only 备注（可留空）')||null;const r=await fetch('/api/candidates/'+encodeURIComponent(id)+'/review',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':CSRF},body:JSON.stringify({decision,operator:'local_owner',owner_note:note})});if(!r.ok)alert('复核失败: '+r.status);await load()}load();setInterval(load,30000);
"""
