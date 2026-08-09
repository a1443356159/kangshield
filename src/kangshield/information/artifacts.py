from __future__ import annotations

import json
import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import Any, Iterator
from uuid import uuid4

from pydantic import BaseModel

from .contracts import (
    EvidenceLevel,
    FeatureEvent,
    MultimodalWindow,
    Observation,
    QualityIssue,
    RunManifest,
    RunStatus,
    RunStep,
    Severity,
    SourceAsset,
    StepStatus,
    utc_now,
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def atomic_write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_jsonable(value), ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        stream.write(payload)
        temporary = Path(stream.name)
    temporary.replace(path)


def atomic_write_text(path: Path, value: str) -> None:
    path = Path(path)
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


def append_jsonl(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(
        path,
        os.O_APPEND | os.O_CREAT | os.O_WRONLY,
        0o600,
    )
    with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(_jsonable(value), ensure_ascii=False) + "\n")
    path.chmod(0o600)


def _git_state(workdir: Path) -> tuple[str, bool]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=workdir,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=workdir,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
        )
        return revision or "unknown", dirty
    except (OSError, subprocess.SubprocessError):
        return "unknown", False


class RunArtifacts:
    def __init__(
        self,
        runs_dir: Path,
        stage: str,
        evidence_level: EvidenceLevel,
        configuration: dict[str, Any] | None = None,
        project_dir: Path | None = None,
    ):
        timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        self.run_id = f"{timestamp}-{uuid4().hex[:8]}"
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.runs_dir.chmod(0o700)
        self.run_dir = self.runs_dir / self.run_id
        self.reports_dir = self.run_dir / "reports"
        self.logs_dir = self.run_dir / "logs"
        self.artifacts_dir = self.run_dir / "artifacts"
        for directory in (
            self.run_dir,
            self.reports_dir,
            self.logs_dir,
            self.artifacts_dir,
        ):
            directory.mkdir(parents=True, exist_ok=False, mode=0o700)
            directory.chmod(0o700)

        revision, dirty = _git_state(project_dir or Path.cwd())
        self.manifest = RunManifest(
            run_id=self.run_id,
            stage=stage,
            evidence_level=evidence_level,
            code_version=revision,
            code_dirty=dirty,
            configuration=configuration or {},
        )
        self._finished = False
        self.save_manifest()

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.json"

    def relative(self, path: Path) -> str:
        return Path(path).relative_to(self.run_dir).as_posix()

    def save_manifest(self) -> None:
        atomic_write_json(self.manifest_path, self.manifest)

    def record_asset(self, asset: SourceAsset) -> None:
        append_jsonl(self.run_dir / "source_assets.jsonl", asset)
        if asset.asset_id not in self.manifest.inputs:
            self.manifest.inputs.append(asset.asset_id)
        self.save_manifest()

    def record_observation(self, observation: Observation) -> None:
        append_jsonl(self.run_dir / "observations.jsonl", observation)

    def record_feature(self, feature: FeatureEvent) -> None:
        append_jsonl(self.run_dir / "features.jsonl", feature)

    def record_feature_artifact(
        self,
        relative_path: str,
        feature: FeatureEvent,
    ) -> Path:
        """Append a feature to a manifest-bound JSONL inside artifacts/."""

        pure = PurePosixPath(relative_path)
        if (
            pure.is_absolute()
            or len(pure.parts) < 2
            or pure.parts[0] != "artifacts"
            or any(part in {"", ".", ".."} for part in pure.parts)
            or "\\" in relative_path
            or pure.suffix != ".jsonl"
        ):
            raise ValueError(
                "feature artifact must be a normalized artifacts/*.jsonl path"
            )
        path = self.run_dir.joinpath(*pure.parts)
        append_jsonl(path, feature)
        if relative_path not in self.manifest.artifacts:
            self.manifest.artifacts.append(relative_path)
            self.save_manifest()
        return path

    def record_multimodal_window(self, window: MultimodalWindow) -> None:
        append_jsonl(self.run_dir / "multimodal_windows.jsonl", window)

    def log_event(self, event: dict[str, Any]) -> None:
        append_jsonl(
            self.logs_dir / "events.jsonl",
            {"at": utc_now().isoformat(), **event},
        )

    def write_report(self, filename: str, report: Any) -> Path:
        if Path(filename).name != filename or not filename.endswith(".json"):
            raise ValueError("report filename must be a simple .json filename")
        path = self.reports_dir / filename
        atomic_write_json(path, report)
        relative = self.relative(path)
        if relative not in self.manifest.artifacts:
            self.manifest.artifacts.append(relative)
        self.save_manifest()
        return path

    def write_markdown(self, filename: str, content: str) -> Path:
        if Path(filename).name != filename or not filename.endswith(".md"):
            raise ValueError("markdown filename must be a simple .md filename")
        path = self.reports_dir / filename
        atomic_write_text(path, content)
        relative = self.relative(path)
        if relative not in self.manifest.artifacts:
            self.manifest.artifacts.append(relative)
        self.save_manifest()
        return path

    @contextmanager
    def step(self, name: str) -> Iterator[RunStep]:
        step = RunStep(name=name)
        self.manifest.steps.append(step)
        self.save_manifest()
        started = perf_counter()
        try:
            yield step
        except Exception as error:
            step.status = StepStatus.FAILED
            step.error = f"{type(error).__name__}: {error}"
            step.finished_at = utc_now()
            step.duration_ms = max(0, round((perf_counter() - started) * 1000))
            self.manifest.issues.append(
                QualityIssue(
                    code="step_failed",
                    severity=Severity.ERROR,
                    message=f"Step {name} failed",
                    details={"error_type": type(error).__name__},
                )
            )
            self.save_manifest()
            raise
        else:
            step.status = StepStatus.COMPLETED
            step.finished_at = utc_now()
            step.duration_ms = max(0, round((perf_counter() - started) * 1000))
            self.save_manifest()

    def finish(self, status: RunStatus = RunStatus.COMPLETED) -> None:
        if self._finished:
            return
        self.manifest.status = status
        self.manifest.finished_at = utc_now()
        self.save_manifest()
        self._finished = True

    def __enter__(self) -> "RunArtifacts":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.finish(RunStatus.FAILED if exc_type else RunStatus.COMPLETED)
