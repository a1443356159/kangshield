"""Public-data engineering checks for fraud rules and personal baselines.

The source datasets stay in the external cache. Reports contain only aggregate
metrics and content-derived digests; raw messages and sensor timestamps are
never copied into the repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import tarfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, BinaryIO, Iterable, Literal
from urllib.request import Request, urlopen

from kangshield.information.multidomain import (
    classify_fraud_text,
    load_policy,
    score_mental_wellbeing,
)
from kangshield.information.privacy import sha256_file
from kangshield.validation.caucafall import default_cache_root


CASAS_RECORD_ID = 15708568
CASAS_DOI = "10.5281/zenodo.15708568"
CASAS_LICENSE = "CC-BY-4.0"
CASAS_ARCHIVE_SIZE = 236_037_656
CASAS_ARCHIVE_MD5 = "ec37d679e85a6ae39e84994888afd514"
CASAS_ARCHIVE_URL = (
    "https://zenodo.org/api/records/15708568/files/labeled_data.zip/content"
)
CASAS_DEV_HOMES = ("hh101", "hh102", "hh103")
CASAS_HOLDOUT_HOMES = ("hh104", "hh105", "hh106")

FBS_COMMIT = "49173b12ab0a42eb9f6ce42e401e6acaef1fbdfd"
FBS_ARCHIVE_URL = (
    "https://github.com/Cypher-Z/FBS_SMS_Dataset/archive/"
    f"{FBS_COMMIT}.tar.gz"
)
FBS_TERMS_TOKEN = "citation-required-ccs2020"
FBS_CATEGORIES = (
    "AD:Loan",
    "AD:Network_service",
    "AD:Other",
    "AD:Real_estate",
    "AD:Retail",
    "FR:Financial",
    "FR:Other",
    "FR:Phishing(Bank)",
    "FR:Phishing(Other)",
    "IL:Escort_service",
    "IL:Fake_ID_and_invoice",
    "IL:Gambling",
    "IL:Political_propaganda",
    "Other",
)
FBS_FRAUD_CATEGORIES = frozenset(
    category for category in FBS_CATEGORIES if category.startswith("FR:")
)

FRAUD_GATE_REVISION = "fbs-fraud-context-engineering-gate-v1"
FRAUD_GATE_THRESHOLDS = {
    "minimum_source_fraud_category_recall": 0.50,
    "maximum_source_non_fraud_category_flag_rate": 0.15,
    "minimum_evaluated_message_count": 1_000,
}
MENTAL_GATE_REVISION = "casas-personal-baseline-engineering-gate-v1"
MENTAL_GATE_THRESHOLDS = {
    "minimum_eligible_days_per_home": 28,
    "minimum_post_baseline_assessment_rate": 0.90,
    "maximum_invalid_line_rate": 0.001,
}

_CASAS_LINE = re.compile(
    r"^(?P<day>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<clock>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
    r"(?P<sensor>\S+)\s+(?P<message>\S+)(?:\s+(?P<tail>.*))?$"
)
_CASAS_ACTIVITY = re.compile(
    r'^(?P<activity>.+?)=(?:")?(?P<boundary>begin|end)(?:")?$',
    re.IGNORECASE,
)


class PublicDomainValidationError(RuntimeError):
    """A deterministic source, parsing, or report-integrity failure."""


@dataclass(frozen=True)
class FraudTextCase:
    case_ref: str
    category: str
    text: str

    @property
    def source_label(self) -> Literal["fraud", "non_fraud"]:
        return "fraud" if self.category in FBS_FRAUD_CATEGORIES else "non_fraud"


@dataclass(frozen=True)
class CasasEvent:
    occurred_at: datetime
    sensor: str
    message: str
    activity: str | None = None
    activity_boundary: Literal["begin", "end"] | None = None


def _hash_file(path: Path, algorithm: str = "sha256") -> str:
    if algorithm == "md5":
        digest = hashlib.md5(usedforsecurity=False)
    else:
        digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download_atomic(url: str, path: Path, *, timeout_seconds: float = 180.0) -> None:
    allowed = (
        "https://zenodo.org/",
        "https://github.com/",
        "https://codeload.github.com/",
    )
    if not url.startswith(allowed):
        raise PublicDomainValidationError("public source URL is outside the allowlist")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".part-{os.getpid()}")
    request = Request(url, headers={"User-Agent": "kangshield-validation/1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response, temporary.open(
            "xb"
        ) as stream:
            os.chmod(temporary, 0o600)
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare_casas_archive(cache_root: Path, *, download: bool = True) -> Path:
    path = cache_root / "casas-longitudinal" / "labeled_data.zip"
    if not path.is_file():
        if not download:
            raise PublicDomainValidationError("CASAS labeled archive is unavailable")
        _download_atomic(CASAS_ARCHIVE_URL, path)
    if path.stat().st_size != CASAS_ARCHIVE_SIZE:
        raise PublicDomainValidationError("CASAS archive size differs from Zenodo")
    if _hash_file(path, "md5") != CASAS_ARCHIVE_MD5:
        raise PublicDomainValidationError("CASAS archive MD5 differs from Zenodo")
    if not zipfile.is_zipfile(path):
        raise PublicDomainValidationError("CASAS labeled archive is not a ZIP file")
    return path


def _fbs_member_map(archive: tarfile.TarFile) -> dict[str, tarfile.TarInfo]:
    by_name: dict[str, tarfile.TarInfo] = {}
    for member in archive.getmembers():
        if not member.isfile():
            continue
        basename = Path(member.name).name
        if basename in FBS_CATEGORIES:
            if basename in by_name:
                raise PublicDomainValidationError(
                    f"FBS archive repeats category {basename}"
                )
            by_name[basename] = member
    missing = sorted(set(FBS_CATEGORIES) - set(by_name))
    if missing:
        raise PublicDomainValidationError(
            f"FBS archive is missing {len(missing)} category files"
        )
    return by_name


def prepare_fbs_archive(cache_root: Path, *, download: bool = True) -> Path:
    path = cache_root / "fbs-sms" / "source.tar.gz"
    if not path.is_file():
        if not download:
            raise PublicDomainValidationError("FBS SMS archive is unavailable")
        _download_atomic(FBS_ARCHIVE_URL, path)
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            _fbs_member_map(archive)
    except (tarfile.TarError, OSError) as error:
        raise PublicDomainValidationError("FBS source archive is invalid") from error
    return path


def _fraud_case_ref(category: str, text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).strip()
    digest = hashlib.sha256(f"{category}\0{normalized}".encode("utf-8")).hexdigest()
    return f"fbs-{digest[:24]}"


def read_fbs_cases(path: Path) -> list[FraudTextCase]:
    cases: dict[str, FraudTextCase] = {}
    with tarfile.open(path, mode="r:gz") as archive:
        members = _fbs_member_map(archive)
        for category in FBS_CATEGORIES:
            extracted = archive.extractfile(members[category])
            if extracted is None:
                raise PublicDomainValidationError(
                    f"FBS category {category} cannot be read"
                )
            try:
                content = extracted.read().decode("utf-8")
            except UnicodeDecodeError as error:
                raise PublicDomainValidationError(
                    f"FBS category {category} is not UTF-8"
                ) from error
            for raw in content.splitlines():
                text = raw.strip()
                if not text:
                    continue
                case_ref = _fraud_case_ref(category, text)
                cases.setdefault(case_ref, FraudTextCase(case_ref, category, text))
    if not cases:
        raise PublicDomainValidationError("FBS source contains no messages")
    return sorted(cases.values(), key=lambda item: item.case_ref)


def fraud_cases_for_split(
    cases: Iterable[FraudTextCase], split: Literal["dev", "holdout", "all"]
) -> list[FraudTextCase]:
    if split not in {"dev", "holdout", "all"}:
        raise ValueError("split must be dev, holdout, or all")
    selected = []
    for item in cases:
        bucket = int(item.case_ref.rsplit("-", 1)[-1][:8], 16) % 5
        if split == "dev" and bucket == 0:
            continue
        if split == "holdout" and bucket != 0:
            continue
        selected.append(item)
    if not selected:
        raise PublicDomainValidationError(f"FBS {split} split is empty")
    return selected


def _fraud_level(categories: Iterable[str]) -> int:
    values = set(categories)
    if not values:
        return 0
    high = bool(
        values & {"transfer_investment", "credential_request", "remote_control"}
    ) and bool(values & {"impersonation", "urgency_secrecy"})
    if high:
        return 3
    return 2 if len(values) >= 2 else 1


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def evaluate_fraud_cases(
    cases: Iterable[FraudTextCase], policy: dict[str, Any]
) -> dict[str, Any]:
    rows = list(cases)
    fraud_rows = [item for item in rows if item.source_label == "fraud"]
    non_fraud_rows = [item for item in rows if item.source_label == "non_fraud"]
    category_counts: Counter[str] = Counter()
    category_flags: Counter[str] = Counter()
    context_counts: Counter[str] = Counter()
    score_counts: Counter[int] = Counter()
    suppressed = 0
    flagged_fraud = 0
    flagged_non_fraud = 0
    for item in rows:
        contexts, hard_negative = classify_fraud_text(item.text, policy)
        flagged = bool(contexts) and not hard_negative
        category_counts[item.category] += 1
        category_flags[item.category] += int(flagged)
        context_counts.update(contexts)
        score_counts[_fraud_level(contexts) if flagged else 0] += 1
        suppressed += int(hard_negative)
        if item.source_label == "fraud":
            flagged_fraud += int(flagged)
        else:
            flagged_non_fraud += int(flagged)
    case_digest = hashlib.sha256(
        "\n".join(item.case_ref for item in sorted(rows, key=lambda row: row.case_ref)).encode(
            "ascii"
        )
    ).hexdigest()
    return {
        "message_count": len(rows),
        "source_fraud_category_count": len(fraud_rows),
        "source_non_fraud_category_count": len(non_fraud_rows),
        "source_fraud_category_recall": _ratio(flagged_fraud, len(fraud_rows)),
        "source_non_fraud_category_flag_rate": _ratio(
            flagged_non_fraud, len(non_fraud_rows)
        ),
        "hard_negative_suppressed_count": suppressed,
        "score_distribution": {
            str(level): score_counts[level] for level in range(4)
        },
        "matched_context_distribution": dict(sorted(context_counts.items())),
        "source_category_metrics": {
            category: {
                "message_count": category_counts[category],
                "flagged_count": category_flags[category],
                "flag_rate": _ratio(
                    category_flags[category], category_counts[category]
                ),
            }
            for category in FBS_CATEGORIES
        },
        "case_set_digest": case_digest,
    }


def development_fraud_ngrams(
    cases: Iterable[FraudTextCase], policy: dict[str, Any], *, limit: int = 40
) -> list[dict[str, Any]]:
    """Return aggregate dev-only phrase candidates without exposing messages."""

    if limit <= 0:
        raise ValueError("limit must be positive")
    missed_fraud: Counter[str] = Counter()
    source_non_fraud: Counter[str] = Counter()
    for item in cases:
        normalized = "".join(
            character
            for character in unicodedata.normalize("NFKC", item.text)
            if "\u4e00" <= character <= "\u9fff"
        )
        document_ngrams = {
            normalized[index : index + width]
            for width in range(2, 7)
            for index in range(max(0, len(normalized) - width + 1))
        }
        if item.source_label == "fraud":
            contexts, suppressed = classify_fraud_text(item.text, policy)
            if contexts or suppressed:
                continue
            missed_fraud.update(document_ngrams)
        else:
            source_non_fraud.update(document_ngrams)
    candidates = []
    for phrase, fraud_count in missed_fraud.items():
        if fraud_count < 5:
            continue
        non_fraud_count = source_non_fraud[phrase]
        precision_proxy = fraud_count / (fraud_count + non_fraud_count)
        candidates.append(
            {
                "phrase": phrase,
                "missed_fraud_document_count": fraud_count,
                "source_non_fraud_document_count": non_fraud_count,
                "precision_proxy": round(precision_proxy, 6),
            }
        )
    candidates.sort(
        key=lambda item: (
            item["precision_proxy"],
            item["missed_fraud_document_count"],
            len(item["phrase"]),
            item["phrase"],
        ),
        reverse=True,
    )
    return candidates[:limit]


def evaluate_fraud_gate(metrics: dict[str, Any]) -> dict[str, Any]:
    recall = metrics.get("source_fraud_category_recall")
    flag_rate = metrics.get("source_non_fraud_category_flag_rate")
    count = metrics.get("message_count")
    thresholds = FRAUD_GATE_THRESHOLDS
    checks = {
        "source_fraud_category_recall": isinstance(recall, (int, float))
        and recall >= thresholds["minimum_source_fraud_category_recall"],
        "source_non_fraud_category_flag_rate": isinstance(flag_rate, (int, float))
        and flag_rate
        <= thresholds["maximum_source_non_fraud_category_flag_rate"],
        "evaluated_message_count": isinstance(count, int)
        and count >= thresholds["minimum_evaluated_message_count"],
    }
    return {
        "revision": FRAUD_GATE_REVISION,
        "scope": "public_chinese_sms_lexical_context_engineering_only",
        "thresholds": thresholds,
        "observed": {
            "source_fraud_category_recall": recall,
            "source_non_fraud_category_flag_rate": flag_rate,
            "evaluated_message_count": count,
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def parse_casas_line(line: str) -> CasasEvent | None:
    text = line.strip()
    if not text:
        return None
    if "," in text:
        fields = next(csv.reader([text]))
        if len(fields) not in {4, 5}:
            raise PublicDomainValidationError("CASAS CSV event has an invalid shape")
        day_text, clock_text, sensor, message = fields[:4]
        tail = fields[4].strip() if len(fields) == 5 else ""
    else:
        matched = _CASAS_LINE.fullmatch(text)
        if matched is None:
            raise PublicDomainValidationError("CASAS event line has an invalid shape")
        day_text = matched.group("day")
        clock_text = matched.group("clock")
        sensor = matched.group("sensor")
        message = matched.group("message")
        tail = (matched.group("tail") or "").strip()
    try:
        occurred_at = datetime.fromisoformat(f"{day_text}T{clock_text}")
    except ValueError as error:
        raise PublicDomainValidationError("CASAS event timestamp is invalid") from error
    activity: str | None = None
    boundary: Literal["begin", "end"] | None = None
    if tail:
        assignment = _CASAS_ACTIVITY.fullmatch(tail)
        if assignment:
            boundary = assignment.group("boundary").casefold()  # type: ignore[assignment]
            activity = assignment.group("activity").strip() or None
        else:
            pieces = tail.split()
            if pieces[-1].casefold() in {"begin", "end"}:
                boundary = pieces[-1].casefold()  # type: ignore[assignment]
                activity = " ".join(pieces[:-1]).strip() or None
    return CasasEvent(
        occurred_at=occurred_at,
        sensor=sensor,
        message=message,
        activity=activity,
        activity_boundary=boundary,
    )


def _casas_member_for_home(archive: zipfile.ZipFile, home: str) -> str:
    matches = []
    for name in archive.namelist():
        if name.endswith("/"):
            continue
        basename = Path(name).name.casefold()
        stem = basename.split(".", 1)[0]
        if stem == home.casefold():
            matches.append(name)
    if len(matches) != 1:
        raise PublicDomainValidationError(
            f"CASAS archive has {len(matches)} files for {home}"
        )
    return matches[0]


def casas_homes_for_split(
    split: Literal["dev", "holdout", "all"]
) -> tuple[str, ...]:
    if split == "dev":
        return CASAS_DEV_HOMES
    if split == "holdout":
        return CASAS_HOLDOUT_HOMES
    if split == "all":
        return CASAS_DEV_HOMES + CASAS_HOLDOUT_HOMES
    raise ValueError("split must be dev, holdout, or all")


def read_casas_daily_rows(
    path: Path, home: str
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    motion_by_day: dict[date, list[datetime]] = defaultdict(list)
    sleep_onset_by_day: dict[date, list[float]] = defaultdict(list)
    total_lines = 0
    invalid_lines = 0
    with zipfile.ZipFile(path) as archive:
        member = _casas_member_for_home(archive, home)
        with archive.open(member) as raw, io.TextIOWrapper(
            raw, encoding="utf-8", errors="strict"
        ) as stream:
            for line in stream:
                if not line.strip():
                    continue
                total_lines += 1
                try:
                    event = parse_casas_line(line)
                except PublicDomainValidationError:
                    invalid_lines += 1
                    continue
                if event is None:
                    continue
                if event.message.casefold() == "on":
                    motion_by_day[event.occurred_at.date()].append(event.occurred_at)
                if (
                    event.activity
                    and "sleep" in event.activity.casefold()
                    and event.activity_boundary == "begin"
                ):
                    hour = (
                        event.occurred_at.hour
                        + event.occurred_at.minute / 60
                        + event.occurred_at.second / 3600
                    )
                    target_day = event.occurred_at.date()
                    if hour < 6:
                        target_day -= timedelta(days=1)
                        hour += 24
                    if hour >= 18:
                        sleep_onset_by_day[target_day].append(hour)
    if total_lines == 0:
        raise PublicDomainValidationError(f"CASAS home {home} has no event lines")

    rows = []
    for local_day in sorted(motion_by_day):
        events = motion_by_day[local_day]
        daytime = [item for item in events if 6 <= item.hour < 18]
        bins = {
            (item.hour - 6) * 4 + item.minute // 15
            for item in daytime
        }
        blocks = {
            (item.hour - 6) // 4
            for item in daytime
        }
        onsets = sleep_onset_by_day.get(local_day, [])
        rows.append(
            {
                "local_date": local_day.isoformat(),
                "eligible_segments": len(blocks),
                "daytime_presence": round(len(bins) / 48, 6),
                "activity_level": round(math.log1p(len(daytime)), 6),
                "speech_interaction": None,
                "sleep_regularity": round(median(onsets), 6) if onsets else None,
                "sleep_confirmed": int(bool(onsets)),
            }
        )
    return rows, {"total_lines": total_lines, "invalid_lines": invalid_lines}


def _score_natural_days(
    rows: list[dict[str, Any]], policy: dict[str, Any], policy_digest: str
) -> dict[str, Any]:
    minimum_segments = int(
        policy["mental_wellbeing"]["minimum_segments_per_day"]
    )
    eligible = [
        item for item in rows if int(item["eligible_segments"]) >= minimum_segments
    ]
    score_counts: Counter[str] = Counter()
    first_eligible_results = []
    post_baseline_total = 0
    post_baseline_assessed = 0
    for index, current in enumerate(eligible):
        current_day = date.fromisoformat(str(current["local_date"]))
        now = datetime.combine(current_day, time(12), tzinfo=timezone.utc)
        result = score_mental_wellbeing(
            eligible[: index + 1],
            now=now,
            stale=False,
            policy=policy,
            policy_digest=policy_digest,
        )
        score_counts["null" if result.score is None else str(result.score)] += 1
        if index < int(policy["mental_wellbeing"]["minimum_baseline_days"]):
            first_eligible_results.append(result.score)
        else:
            post_baseline_total += 1
            post_baseline_assessed += int(result.score is not None)
    return {
        "observed_day_count": len(rows),
        "eligible_day_count": len(eligible),
        "score_distribution": {
            key: score_counts[key] for key in ("null", "0", "1", "2", "3")
        },
        "prebaseline_all_fail_closed": bool(first_eligible_results)
        and all(value is None for value in first_eligible_results),
        "post_baseline_assessment_rate": _ratio(
            post_baseline_assessed, post_baseline_total
        ),
    }


def _controlled_mental_response(
    rows: list[dict[str, Any]], policy: dict[str, Any], policy_digest: str
) -> dict[str, Any]:
    spec = policy["mental_wellbeing"]
    eligible = [
        dict(item)
        for item in rows
        if int(item["eligible_segments"]) >= int(spec["minimum_segments_per_day"])
    ]
    if not eligible:
        return {
            "available": False,
            "usable_variable_feature_count": 0,
            "expected_levels_observed": False,
        }
    latest = date.fromisoformat(str(eligible[-1]["local_date"]))
    first_scenario_day = latest + timedelta(days=1)
    window_start = first_scenario_day - timedelta(
        days=int(spec["baseline_window_days"])
    )
    baseline = [
        item
        for item in eligible
        if date.fromisoformat(str(item["local_date"])) >= window_start
    ]
    feature_stats: dict[str, tuple[float, float]] = {}
    for feature in spec["features"]:
        values = [
            float(item[feature])
            for item in baseline
            if item.get(feature) is not None
            and (feature != "sleep_regularity" or bool(item.get("sleep_confirmed")))
        ]
        if len(values) < int(spec["minimum_baseline_days"]):
            continue
        center = median(values)
        mad = median(abs(value - center) for value in values)
        if mad > 0:
            feature_stats[feature] = (center, mad)
    selected = sorted(feature_stats)[:2]
    if len(selected) < 2 or not baseline:
        return {
            "available": False,
            "usable_variable_feature_count": len(feature_stats),
            "expected_levels_observed": False,
        }

    def generated(
        day_offset: int,
        severity: Literal["mild", "severe"],
        count: int,
        *,
        z_value: float | None = None,
    ):
        item = {
            "local_date": (latest + timedelta(days=day_offset)).isoformat(),
            "eligible_segments": int(spec["minimum_segments_per_day"]),
            "daytime_presence": None,
            "activity_level": None,
            "speech_interaction": None,
            "sleep_regularity": None,
            "sleep_confirmed": 0,
        }
        threshold = (
            z_value
            if z_value is not None
            else float(spec[f"{severity}_z"]) + 0.25
        )
        for feature, (center, _) in feature_stats.items():
            item[feature] = center
            if feature == "sleep_regularity":
                item["sleep_confirmed"] = 1
        for feature in selected[:count]:
            center, mad = feature_stats[feature]
            item[feature] = center + threshold * mad
        return item

    scenarios = {
        "one_mild": [generated(1, "mild", 1)],
        "one_severe": [generated(1, "severe", 1)],
        "two_severe": [generated(1, "severe", 2)],
        "three_day_level_two": [
            generated(1, "severe", 1, z_value=float(spec["severe_z"]) * 4),
            generated(2, "severe", 1, z_value=float(spec["severe_z"]) * 4),
            generated(3, "severe", 1, z_value=float(spec["severe_z"]) * 4),
        ],
    }
    observed: dict[str, int | None] = {}
    for name, additions in scenarios.items():
        sequence = [*baseline]
        score = None
        for item in additions:
            sequence.append(item)
            current_day = date.fromisoformat(str(item["local_date"]))
            result = score_mental_wellbeing(
                sequence,
                now=datetime.combine(current_day, time(12), tzinfo=timezone.utc),
                stale=False,
                policy=policy,
                policy_digest=policy_digest,
            )
            score = result.score
        observed[name] = score
    expected = {
        "one_mild": 1,
        "one_severe": 2,
        "two_severe": 3,
        "three_day_level_two": 3,
    }
    return {
        "available": True,
        "usable_variable_feature_count": len(feature_stats),
        "observed_levels": observed,
        "expected_levels": expected,
        "expected_levels_observed": observed == expected,
    }


def evaluate_casas_homes(
    path: Path,
    homes: Iterable[str],
    policy: dict[str, Any],
    policy_digest: str,
) -> dict[str, Any]:
    home_metrics: dict[str, Any] = {}
    total_lines = invalid_lines = 0
    for home in homes:
        rows, parse = read_casas_daily_rows(path, home)
        natural = _score_natural_days(rows, policy, policy_digest)
        controlled = _controlled_mental_response(rows, policy, policy_digest)
        total_lines += parse["total_lines"]
        invalid_lines += parse["invalid_lines"]
        home_metrics[home] = {
            **natural,
            "controlled_response": controlled,
            "input_digest": hashlib.sha256(
                json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }
    rates = [
        item["post_baseline_assessment_rate"]
        for item in home_metrics.values()
        if item["post_baseline_assessment_rate"] is not None
    ]
    return {
        "home_count": len(home_metrics),
        "total_event_line_count": total_lines,
        "invalid_event_line_count": invalid_lines,
        "invalid_event_line_rate": _ratio(invalid_lines, total_lines),
        "minimum_eligible_days": min(
            (item["eligible_day_count"] for item in home_metrics.values()), default=0
        ),
        "mean_post_baseline_assessment_rate": round(mean(rates), 6)
        if rates
        else None,
        "all_prebaseline_days_fail_closed": bool(home_metrics)
        and all(
            item["prebaseline_all_fail_closed"] for item in home_metrics.values()
        ),
        "all_controlled_responses_match": bool(home_metrics)
        and all(
            item["controlled_response"]["expected_levels_observed"]
            for item in home_metrics.values()
        ),
        "homes": home_metrics,
    }


def evaluate_mental_gate(metrics: dict[str, Any]) -> dict[str, Any]:
    minimum_days = metrics.get("minimum_eligible_days")
    assessed_rate = metrics.get("mean_post_baseline_assessment_rate")
    invalid_rate = metrics.get("invalid_event_line_rate")
    thresholds = MENTAL_GATE_THRESHOLDS
    checks = {
        "minimum_eligible_days": isinstance(minimum_days, int)
        and minimum_days >= thresholds["minimum_eligible_days_per_home"],
        "post_baseline_assessment_rate": isinstance(assessed_rate, (int, float))
        and assessed_rate >= thresholds["minimum_post_baseline_assessment_rate"],
        "invalid_event_line_rate": isinstance(invalid_rate, (int, float))
        and invalid_rate <= thresholds["maximum_invalid_line_rate"],
        "prebaseline_fail_closed": metrics.get("all_prebaseline_days_fail_closed")
        is True,
        "controlled_response_levels": metrics.get("all_controlled_responses_match")
        is True,
    }
    return {
        "revision": MENTAL_GATE_REVISION,
        "scope": "public_smart_home_personal_baseline_engineering_only",
        "thresholds": thresholds,
        "observed": {
            "minimum_eligible_days": minimum_days,
            "mean_post_baseline_assessment_rate": assessed_rate,
            "invalid_event_line_rate": invalid_rate,
            "all_prebaseline_days_fail_closed": metrics.get(
                "all_prebaseline_days_fail_closed"
            ),
            "all_controlled_responses_match": metrics.get(
                "all_controlled_responses_match"
            ),
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def _write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)


def build_report(
    *,
    split: str,
    policy_path: Path,
    policy_digest: str,
    fbs_path: Path | None,
    casas_path: Path | None,
    fraud_metrics: dict[str, Any] | None,
    mental_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    gates = {}
    if fraud_metrics is not None:
        gates["fraud"] = evaluate_fraud_gate(fraud_metrics)
    if mental_metrics is not None:
        gates["mental_wellbeing"] = evaluate_mental_gate(mental_metrics)
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "pilot_unvalidated",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_contract": {
            "split": split,
            "labels_visible_to_rule_matching": False,
            "development_homes": list(CASAS_DEV_HOMES),
            "holdout_homes": list(CASAS_HOLDOUT_HOMES),
            "fbs_partition": "sha256_case_ref_mod_5; holdout_bucket_0",
        },
        "bindings": {
            "multidomain_policy": {
                "filename": policy_path.name,
                "sha256": policy_digest,
            }
        },
        "sources": {},
        "metrics": {},
        "engineering_gates": gates,
        "passed": bool(gates) and all(item["passed"] for item in gates.values()),
        "execution": {
            "surface": "slurm_compute_node"
            if os.environ.get("SLURM_JOB_ID")
            else "direct_process",
            "login_node_compute_prohibited": True,
        },
        "limitations": [
            "public_data_engineering_checks_are_not_clinical_validation",
            "fbs_sms_labels_are_not_camera_audio_or_asr_outputs",
            "fbs_non_fraud_categories_are_spam_or_illicit_content_not_benign_dialogue",
            "casas_ambient_sensors_are_proxies_not_camera_derived_features",
            "casas_has_no_mental_health_outcome_ground_truth",
            "controlled_behavior_changes_are_sensitivity_checks_not_diagnoses",
            "results_do_not_establish_target_c6c_performance",
        ],
    }
    if fbs_path is not None and fraud_metrics is not None:
        report["sources"]["fraud"] = {
            "name": "FBS Spam SMS Dataset",
            "source_commit": FBS_COMMIT,
            "source_url": "https://github.com/Cypher-Z/FBS_SMS_Dataset",
            "usage_terms": "public_research_release_requires_source_and_ccs2020_citation",
            "spdx_license": None,
            "archive_sha256": sha256_file(fbs_path),
            "raw_text_in_report": False,
        }
        report["metrics"]["fraud"] = fraud_metrics
    if casas_path is not None and mental_metrics is not None:
        report["sources"]["mental_wellbeing"] = {
            "name": "CASAS Smart Home dataset - free living, motion, door, activity labels",
            "record_id": CASAS_RECORD_ID,
            "doi": CASAS_DOI,
            "source_url": f"https://zenodo.org/records/{CASAS_RECORD_ID}",
            "license": CASAS_LICENSE,
            "archive_size_bytes": CASAS_ARCHIVE_SIZE,
            "archive_md5": CASAS_ARCHIVE_MD5,
            "archive_sha256": sha256_file(casas_path),
            "raw_timestamps_in_report": False,
        }
        report["metrics"]["mental_wellbeing"] = mental_metrics
    return report


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate fraud rules and personal baselines on public data."
    )
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
    parser.add_argument(
        "--domain", choices=("fraud", "mental_wellbeing", "both"), default="both"
    )
    parser.add_argument("--cache-root", type=Path, default=default_cache_root())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--policy", type=Path, default=Path("configs/v2-multidomain-risk-policy.json"))
    parser.add_argument("--accept-casas-license")
    parser.add_argument("--accept-fbs-terms")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument(
        "--development-diagnostics",
        action="store_true",
        help="print aggregate phrase diagnostics; allowed only for the dev split",
    )
    args = parser.parse_args(argv)
    include_fraud = args.domain in {"fraud", "both"}
    include_mental = args.domain in {"mental_wellbeing", "both"}
    if include_fraud and args.accept_fbs_terms != FBS_TERMS_TOKEN:
        parser.error(f"--accept-fbs-terms must be exactly {FBS_TERMS_TOKEN}")
    if include_mental and args.accept_casas_license != CASAS_LICENSE:
        parser.error(f"--accept-casas-license must be exactly {CASAS_LICENSE}")
    if not args.prepare_only and args.output is None:
        parser.error("--output is required unless --prepare-only is used")
    if args.development_diagnostics and args.split != "dev":
        parser.error("--development-diagnostics is allowed only with --split dev")

    args.cache_root.mkdir(parents=True, exist_ok=True)
    fbs_path = None
    casas_path = None
    if include_fraud:
        _progress("source: verifying FBS SMS archive")
        fbs_path = prepare_fbs_archive(args.cache_root, download=not args.no_download)
    if include_mental:
        _progress("source: verifying CASAS labeled archive")
        casas_path = prepare_casas_archive(
            args.cache_root, download=not args.no_download
        )
    if args.prepare_only:
        print(
            json.dumps(
                {
                    "split": args.split,
                    "domain": args.domain,
                    "fbs_archive_verified": fbs_path is not None,
                    "casas_archive_verified": casas_path is not None,
                    "policy_loaded": False,
                    "raw_data_committed": False,
                },
                sort_keys=True,
            )
        )
        return 0

    policy, policy_digest = load_policy(args.policy)
    fraud_metrics = None
    mental_metrics = None
    if fbs_path is not None:
        _progress(f"fraud: evaluating {args.split} partition")
        cases = fraud_cases_for_split(read_fbs_cases(fbs_path), args.split)
        fraud_metrics = evaluate_fraud_cases(cases, policy)
        if args.development_diagnostics:
            print(
                json.dumps(
                    {"development_fraud_ngrams": development_fraud_ngrams(cases, policy)},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
    if casas_path is not None:
        homes = casas_homes_for_split(args.split)
        _progress(f"mental: evaluating {len(homes)} personal home histories")
        mental_metrics = evaluate_casas_homes(
            casas_path, homes, policy, policy_digest
        )
    report = build_report(
        split=args.split,
        policy_path=args.policy,
        policy_digest=policy_digest,
        fbs_path=fbs_path,
        casas_path=casas_path,
        fraud_metrics=fraud_metrics,
        mental_metrics=mental_metrics,
    )
    assert args.output is not None
    _write_report(report, args.output)
    _progress(f"report: wrote {args.output}")
    print(
        json.dumps(
            {
                "split": args.split,
                "passed": report["passed"],
                "engineering_gates": report["engineering_gates"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
