"""Small command surface for the final KangShield local product."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from kangshield import __version__

from .contracts import EvidenceLevel, SourceType


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
        raise argparse.ArgumentTypeError(
            f"source type must be one of: {choices}"
        ) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kangshield-info",
        description="康盾连续三域风险本地产品",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"kangshield-info {__version__}",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    monitor = commands.add_parser(
        "run-edge-monitor",
        help="连续筛选内存分段并分析关键窗口，不在本机保存原始媒体",
    )
    monitor.add_argument("--elder-ref", required=True)
    monitor.add_argument("--device-ref", required=True)
    monitor.add_argument(
        "--provider", choices=("endpoint_env", "ezviz"), default="endpoint_env"
    )
    monitor.add_argument("--endpoint-env", default="KANG_STREAM_ENDPOINT")
    monitor.add_argument("--device-serial-env", default="KANG_DEVICE_SERIAL")
    monitor.add_argument("--endpoint-refresh-seconds", type=float, default=1800.0)
    monitor.add_argument(
        "--store-root",
        type=Path,
        default=Path("data/processed/longitudinal"),
    )
    monitor.add_argument(
        "--risk-policy",
        type=Path,
        default=Path("configs/v2-multidomain-risk-policy.json"),
    )
    monitor.add_argument(
        "--edge-policy",
        type=Path,
        default=Path("configs/v2-edge-segment-policy.json"),
    )
    monitor.add_argument("--evidence-level", type=_evidence, default=EvidenceLevel.E2)
    monitor.add_argument(
        "--source-type", type=_source_type, default=SourceType.NETWORK_STREAM
    )
    monitor.add_argument("--open-timeout-s", type=float, default=10.0)
    monitor.add_argument("--read-timeout-s", type=float, default=5.0)
    monitor.add_argument("--transport", choices=("auto", "tcp", "udp"), default="auto")
    monitor.add_argument("--failure-backoff-s", type=float, default=2.0)
    monitor.add_argument(
        "--local-anomaly-archive",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="按边缘策略归档异常事件 MP4；可用 --no-local-anomaly-archive 关闭",
    )
    monitor.add_argument(
        "--max-segments",
        type=int,
        default=0,
        help="0 表示持续运行；正整数用于受控验收",
    )

    product = commands.add_parser(
        "serve-product",
        help="启动 localhost 三域看板、复核、问卷和可选连续分析",
    )
    product.add_argument("--elder-ref", required=True)
    product.add_argument("--device-ref", required=True)
    product.add_argument("--host", default="127.0.0.1")
    product.add_argument("--port", type=int, default=8765)
    product.add_argument(
        "--store-root",
        type=Path,
        default=Path("data/processed/longitudinal"),
    )
    product.add_argument(
        "--policy",
        type=Path,
        default=Path("configs/v2-multidomain-risk-policy.json"),
    )
    product.add_argument("--continuous", action="store_true")
    product.add_argument("--edge-endpoint-env", default="KANG_STREAM_ENDPOINT")
    product.add_argument(
        "--edge-provider", choices=("endpoint_env", "ezviz"), default="endpoint_env"
    )
    product.add_argument("--edge-device-serial-env", default="KANG_DEVICE_SERIAL")
    product.add_argument("--edge-endpoint-refresh-seconds", type=float, default=1800.0)
    product.add_argument(
        "--edge-policy",
        type=Path,
        default=Path("configs/v2-edge-segment-policy.json"),
    )
    product.add_argument("--edge-failure-backoff-s", type=float, default=2.0)
    product.add_argument(
        "--local-anomaly-archive",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="连续模式下归档异常事件 MP4；默认读取边缘策略",
    )
    product.add_argument(
        "--cloud-playback-provider",
        choices=("auto", "none", "ezviz"),
        default="auto",
        help="异常事件点击回看时临时解析云端地址",
    )
    product.add_argument(
        "--demo",
        action="store_true",
        help="生成相对当前时间的合成记录；老人和设备引用必须以 demo- 开头",
    )

    export = commands.add_parser(
        "export-product-report", help="生成 owner 或完全脱敏的 public 离线报告"
    )
    export.add_argument("--elder-ref", required=True)
    export.add_argument("--device-ref")
    export.add_argument(
        "--visibility", required=True, choices=("owner_only", "public_evidence")
    )
    export.add_argument("--output", type=Path, required=True)
    export.add_argument(
        "--store-root",
        type=Path,
        default=Path("data/processed/longitudinal"),
    )
    export.add_argument(
        "--policy",
        type=Path,
        default=Path("configs/v2-multidomain-risk-policy.json"),
    )

    delete = commands.add_parser(
        "delete-product-data", help="完整删除一个老人的本机派生数据库"
    )
    delete.add_argument("--elder-ref", required=True)
    delete.add_argument("--confirm-ref", required=True)
    delete.add_argument(
        "--store-root",
        type=Path,
        default=Path("data/processed/longitudinal"),
    )
    return parser


def _run_edge_monitor(args: argparse.Namespace) -> int:
    from .edge_monitor import (
        EdgeMonitor,
        endpoint_provider_from_environment,
        ezviz_provider_from_environment,
    )

    provider = (
        ezviz_provider_from_environment(
            args.device_serial_env,
            refresh_seconds=args.endpoint_refresh_seconds,
        )
        if args.provider == "ezviz"
        else endpoint_provider_from_environment(args.endpoint_env)
    )
    monitor = EdgeMonitor(
        elder_ref=args.elder_ref,
        device_ref=args.device_ref,
        endpoint_provider=provider,
        store_root=args.store_root,
        risk_policy_path=args.risk_policy,
        selection_policy_path=args.edge_policy,
        evidence_level=args.evidence_level,
        source_type=args.source_type,
        open_timeout_s=args.open_timeout_s,
        read_timeout_s=args.read_timeout_s,
        transport=args.transport,
        failure_backoff_s=args.failure_backoff_s,
        archive_anomaly_clips=args.local_anomaly_archive,
    )
    try:
        counts = monitor.run(max_segments=args.max_segments)
    except KeyboardInterrupt:
        monitor.stop_event.set()
        counts = {"interrupted": 1}
    print(
        json.dumps(
            {
                "monitor_version": "edge-monitor-v0.2.0",
                "counts": counts,
                "raw_video_persisted": False,
                "raw_audio_persisted": False,
                "derived_anomaly_archive_enabled": monitor.archive_anomaly_clips,
                "cloud_recording_is_source_of_truth": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _serve_product(args: argparse.Namespace) -> int:
    from .product import serve_product

    serve_product(
        elder_ref=args.elder_ref,
        device_ref=args.device_ref,
        host=args.host,
        port=args.port,
        store_root=args.store_root,
        policy_path=args.policy,
        demo=args.demo,
        continuous=args.continuous,
        edge_endpoint_env=args.edge_endpoint_env,
        edge_provider=args.edge_provider,
        edge_device_serial_env=args.edge_device_serial_env,
        edge_endpoint_refresh_seconds=args.edge_endpoint_refresh_seconds,
        edge_policy_path=args.edge_policy,
        edge_failure_backoff_s=args.edge_failure_backoff_s,
        archive_anomaly_clips=args.local_anomaly_archive,
        cloud_playback_provider=args.cloud_playback_provider,
    )
    return 0


def _export_product(args: argparse.Namespace) -> int:
    from .product import export_product_report

    html_path, json_path = export_product_report(
        elder_ref=args.elder_ref,
        device_ref=args.device_ref,
        visibility=args.visibility,
        output=args.output,
        store_root=args.store_root,
        policy_path=args.policy,
    )
    print(
        json.dumps(
            {"html": str(html_path), "json": str(json_path)}, ensure_ascii=False
        )
    )
    return 0


def _delete_product_data(args: argparse.Namespace) -> int:
    from .longitudinal.store import LongitudinalStore

    if args.confirm_ref != args.elder_ref:
        raise ValueError("--confirm-ref must exactly match --elder-ref")
    removed = LongitudinalStore.delete_elder(args.elder_ref, root=args.store_root)
    print(json.dumps({"elder_ref": args.elder_ref, "removed": removed}))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run-edge-monitor":
        return _run_edge_monitor(args)
    if args.command == "serve-product":
        return _serve_product(args)
    if args.command == "export-product-report":
        return _export_product(args)
    if args.command == "delete-product-data":
        return _delete_product_data(args)
    raise AssertionError(f"unhandled command: {args.command}")
