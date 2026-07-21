from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .artifacts import RunArtifacts
from .contracts import EvidenceLevel, SourceType
from .ezviz_snapshot import inspect_ezviz_snapshot
from .media_probe import probe_media
from .sleep_profile import profile_sleep_export


def _evidence(value: str) -> EvidenceLevel:
    try:
        return EvidenceLevel(value.upper())
    except ValueError as error:
        raise argparse.ArgumentTypeError("evidence level must be E0..E4") from error


def _source_type(value: str) -> SourceType:
    try:
        return SourceType(value)
    except ValueError as error:
        choices = ", ".join(item.value for item in SourceType)
        raise argparse.ArgumentTypeError(f"source type must be one of: {choices}") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kangshield-info",
        description="KangShield V1 information-side probes",
    )
    parser.add_argument("--version", action="version", version="kangshield-info 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    media = subparsers.add_parser(
        "probe-media",
        help="Inspect file facts and WAV/video metadata",
    )
    media.add_argument("paths", nargs="+", type=Path)
    media.add_argument("--runs-dir", type=Path, default=Path("runs"))
    media.add_argument("--evidence-level", type=_evidence, default=EvidenceLevel.E1)
    media.add_argument("--source-type", type=_source_type, default=SourceType.LOCAL_FILE)
    media.add_argument("--device-ref")
    media.add_argument("--elder-ref")

    sleep = subparsers.add_parser(
        "profile-sleep",
        help="Discover JSON/CSV sleep-export fields without persisting values",
    )
    sleep.add_argument("path", type=Path)
    sleep.add_argument("--runs-dir", type=Path, default=Path("runs"))
    sleep.add_argument("--evidence-level", type=_evidence, default=EvidenceLevel.E1)
    sleep.add_argument("--source-type", type=_source_type, default=SourceType.FIXTURE)
    sleep.add_argument("--device-ref")
    sleep.add_argument("--elder-ref")

    ezviz = subparsers.add_parser(
        "inspect-ezviz",
        help="Inspect and redact an EZVIZ SDK/API JSON snapshot",
    )
    ezviz.add_argument("path", type=Path)
    ezviz.add_argument("--runs-dir", type=Path, default=Path("runs"))
    ezviz.add_argument("--evidence-level", type=_evidence, default=EvidenceLevel.E1)
    ezviz.add_argument("--source-type", type=_source_type, default=SourceType.FIXTURE)

    return parser


def _print_result(run: RunArtifacts, details: dict) -> None:
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "run_dir": str(run.run_dir),
                "manifest": str(run.manifest_path),
                **details,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _probe_media_command(args: argparse.Namespace) -> int:
    configuration = {
        "command": "probe-media",
        "path_count": len(args.paths),
        "source_type": args.source_type.value,
    }
    with RunArtifacts(
        args.runs_dir,
        stage="v1-media-probe",
        evidence_level=args.evidence_level,
        configuration=configuration,
    ) as run:
        reports = []
        for index, path in enumerate(args.paths):
            with run.step(f"probe-media:{index}") as step:
                report = probe_media(
                    path,
                    evidence_level=args.evidence_level,
                    device_ref=args.device_ref,
                    elder_ref=args.elder_ref,
                    source_type=args.source_type,
                )
                run.record_asset(report.asset)
                run.record_observation(report.observation)
                output = run.write_report(f"media-probe-{index:03d}.json", report)
                step.outputs.append(run.relative(output))
                reports.append(
                    {
                        "asset_id": report.asset.asset_id,
                        "modality": report.asset.modality.value,
                        "quality_status": report.observation.quality_status.value,
                    }
                )
    _print_result(run, {"reports": reports})
    return 0


def _profile_sleep_command(args: argparse.Namespace) -> int:
    with RunArtifacts(
        args.runs_dir,
        stage="v1-sleep-profile",
        evidence_level=args.evidence_level,
        configuration={
            "command": "profile-sleep",
            "source_type": args.source_type.value,
        },
    ) as run:
        with run.step("profile-sleep") as step:
            report = profile_sleep_export(
                args.path,
                evidence_level=args.evidence_level,
                source_type=args.source_type,
                device_ref=args.device_ref,
                elder_ref=args.elder_ref,
            )
            run.record_asset(report.asset)
            run.record_observation(report.observation)
            output = run.write_report("sleep-field-profile.json", report)
            step.outputs.append(run.relative(output))
    _print_result(
        run,
        {
            "record_count": report.record_count,
            "field_count": len(report.fields),
            "mapping_candidate_count": len(report.mapping_candidates),
        },
    )
    return 0


def _inspect_ezviz_command(args: argparse.Namespace) -> int:
    with RunArtifacts(
        args.runs_dir,
        stage="v1-ezviz-snapshot",
        evidence_level=args.evidence_level,
        configuration={
            "command": "inspect-ezviz",
            "source_type": args.source_type.value,
        },
    ) as run:
        with run.step("inspect-ezviz") as step:
            report = inspect_ezviz_snapshot(
                args.path,
                evidence_level=args.evidence_level,
                source_type=args.source_type,
            )
            run.record_asset(report.asset)
            output = run.write_report("ezviz-capability-snapshot.json", report)
            step.outputs.append(run.relative(output))
    _print_result(
        run,
        {
            "device_count": len(report.devices),
            "models_found": report.models_found,
            "target_models_found": report.target_models_found,
        },
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "probe-media":
        return _probe_media_command(args)
    if args.command == "profile-sleep":
        return _profile_sleep_command(args)
    if args.command == "inspect-ezviz":
        return _inspect_ezviz_command(args)
    raise RuntimeError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
