"""Owner/public longitudinal assessment report assembly."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..contracts import (
    BaselineDeviationCandidate,
    LongitudinalAssessmentReport,
    LongitudinalBaselinePolicy,
    PersonalBaseline,
)
from .store import LongitudinalStore

REPORT_VERSION = "longitudinal-assessment-v0.1.0"


def _baseline_from_row(row: Any, elder_ref: str) -> PersonalBaseline:
    return PersonalBaseline(
        elder_ref=elder_ref,
        indicator_id=str(row["indicator_id"]),
        bucket=str(row["bucket"]),
        computed_at=datetime.fromisoformat(str(row["computed_at"])),
        window_days=int(row["window_days"]),
        sample_count=int(row["sample_count"]),
        status=str(row["status"]),
        median=row["median"],
        mad=row["mad"],
        ewma=row["ewma"],
        policy_revision=str(row["policy_revision"]),
    )


def _candidate_from_row(row: Any, elder_ref: str) -> BaselineDeviationCandidate:
    return BaselineDeviationCandidate(
        candidate_id=str(row["candidate_id"]),
        elder_ref=elder_ref,
        indicator_id=str(row["indicator_id"]),
        bucket=str(row["bucket"]),
        detected_at=datetime.fromisoformat(str(row["detected_at"])),
        direction=str(row["direction"]),
        z_value=float(row["z_value"]),
        ewma_shift=row["ewma_shift"],
        score=int(row["score"]),
        policy_revision=str(row["policy_revision"]),
        policy_digest=str(row["policy_digest"]),
        baseline_sample_count=int(row["baseline_sample_count"]),
        limitations=json.loads(str(row["limitations_json"])),
    )


def build_assessment_reports(
    store: LongitudinalStore,
    policy: LongitudinalBaselinePolicy,
    *,
    policy_digest: str,
    status_counts: dict[str, int],
) -> tuple[LongitudinalAssessmentReport, LongitudinalAssessmentReport]:
    """Build the owner-only and public-evidence report pair from store state."""
    counts = store.counts()
    observation_counts = {
        "total": counts["observations"],
        "baseline_eligible": counts["baseline_eligible_observations"],
        "episodes": counts["episodes"],
    }
    baselines = [
        _baseline_from_row(row, store.elder_ref) for row in store.fetch_baselines()
    ]
    candidates = [
        _candidate_from_row(row, store.elder_ref)
        for row in store.fetch_deviation_candidates()
    ]
    limitations = [
        "longitudinal_candidates_are_owner_only_and_never_confirm_fall",
        *policy.limitations,
    ]
    owner = LongitudinalAssessmentReport(
        report_version=REPORT_VERSION,
        visibility="owner_only",
        elder_ref=store.elder_ref,
        policy_revision=policy.revision,
        policy_digest=policy_digest,
        baselines=baselines,
        deviation_candidates=candidates,
        observation_counts=observation_counts,
        status_counts=status_counts,
        limitations=limitations,
    )
    public = LongitudinalAssessmentReport(
        report_version=REPORT_VERSION,
        visibility="public_evidence",
        elder_ref=store.elder_ref,
        policy_revision=policy.revision,
        policy_digest=policy_digest,
        observation_counts=observation_counts,
        status_counts=status_counts,
        limitations=limitations,
    )
    return owner, public


def render_longitudinal_markdown(report: LongitudinalAssessmentReport) -> str:
    lines = [
        f"# 长程基线评估（{report.visibility}）",
        "",
        f"- elder_ref: `{report.elder_ref}`",
        f"- policy: `{report.policy_revision}` (`{report.policy_digest[:12]}…`)",
        f"- global_score: `null`（v1 不提供全局分）",
        f"- 观测总数: {report.observation_counts.get('total', 0)}"
        f"（可入基线 {report.observation_counts.get('baseline_eligible', 0)}），"
        f"L0 episodes: {report.observation_counts.get('episodes', 0)}",
        "",
    ]
    if report.visibility == "owner_only":
        lines.append("## 个人基线")
        lines.append("")
        lines.append("| 指标 | 分桶 | 状态 | 样本数 | 中位数 | MAD | EWMA |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for baseline in report.baselines:
            median_text = (
                f"{baseline.median:.4g}" if baseline.median is not None else "—"
            )
            mad_text = f"{baseline.mad:.4g}" if baseline.mad is not None else "—"
            ewma_text = f"{baseline.ewma:.4g}" if baseline.ewma is not None else "—"
            lines.append(
                f"| {baseline.indicator_id} | {baseline.bucket} | {baseline.status}"
                f" | {baseline.sample_count} | {median_text} | {mad_text} | {ewma_text} |"
            )
        lines.append("")
        lines.append("## 偏离 candidate（owner-only，非风险分、非告警）")
        lines.append("")
        if report.deviation_candidates:
            lines.append("| 时间 | 指标 | 分桶 | 方向 | z | 分数 |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            for candidate in report.deviation_candidates:
                lines.append(
                    f"| {candidate.detected_at.isoformat()} | {candidate.indicator_id}"
                    f" | {candidate.bucket} | {candidate.direction}"
                    f" | {candidate.z_value:.2f} | {candidate.score} |"
                )
        else:
            lines.append("无偏离 candidate。")
        lines.append("")
    if report.limitations:
        lines.append("## 限制")
        lines.append("")
        lines.extend(f"- `{item}`" for item in report.limitations)
        lines.append("")
    return "\n".join(lines)
