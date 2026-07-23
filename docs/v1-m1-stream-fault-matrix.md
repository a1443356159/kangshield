# V1-M1 受控流故障矩阵

状态：Implemented E1 v0.1.0；RTSP、packet loss、恢复与长稳仍 Open

基准日期：2026-07-23

## 1. 目的与边界

单次采集和计划性重复开流通过后，还要确认 adapter 在输入被拒绝、停滞、截断或重置时不会发布可用媒体，也不会遗留未登记 partial。`exercise-stream-faults` 用本地 A/V fixture 启动七个互相独立的 loopback HTTP 行为，逐例调用真实 `capture_stream`，再生成 `StreamFaultMatrixReport`。

本工具回答的是“受控故障能否被有界、安全地识别”，不是“真实 C6c 能否自动恢复或容忍网络损伤”。以下声明固定为 false：

- `packet_loss_injected`、`rtsp_transport_tested`；
- `reconnect_attempted`、`involuntary_disconnect_recovery_proven`；
- `network_impairment_tolerance_proven`、`long_running_stability_proven`；
- `device_platform_integration_proven`、M2c bundle、RiskAssessment 和 Alert。

## 2. 固定场景

| 序号 | 场景 | 注入行为 | 预期状态 |
|---:|---|---|---|
| 1 | `healthy_control` | 完整 HTTP body | `captured_ready` |
| 2 | `chunk_delay_jitter` | 完整 body 分块发送，块间交替延迟 | `captured_ready` |
| 3 | `http_rejection` | HTTP 503 | `failed` |
| 4 | `initial_response_stall` | 发送 200/header 后不发送 body，超过 timeout | `failed` |
| 5 | `midstream_stall` | 发送媒体前缀后停止，超过 read timeout | `not_ready_or_failed` |
| 6 | `truncated_transfer` | 声明完整长度，只发送媒体前缀后正常关闭 | `not_ready_or_failed` |
| 7 | `connection_reset` | 发送媒体前缀后以 `SO_LINGER` 触发 TCP reset | `not_ready_or_failed` |

`chunk_delay_jitter` 只是应用层分块延迟，不能写成 packet-level jitter。TCP 本身会重传，本命令没有注入或测量 packet loss。

## 3. 命令

```bash
kangshield-info exercise-stream-faults <local-av-fixture.mkv> \
  --duration-s 2 \
  --minimum-duration-s 1.5 \
  --open-timeout-s 1 \
  --read-timeout-s 1 \
  --stall-duration-s 1.5 \
  --require-ready
```

命令只接受本地 fixture，证据固定为 E1。fixture 路径不进入 manifest/report；只保存 SHA-256、大小和安全的输出 asset URI。正式真机 endpoint 不得作为该命令的位置参数。

默认行为参数：

- 媒体前缀上限 2 MiB，实际前缀还受 fixture 四分之一大小约束；
- jitter chunk 256 KiB，块间交替 5/20 ms；
- 单 case elapsed limit 为 open timeout + 请求时长 + read timeout + 3 s；
- 默认要求一条视频轨和一条音轨，不提供 video-only 放宽。

stall 必须严格长于 open/read timeout；jitter 最大延迟必须大于零。fixture 在矩阵前后重新检查大小和 SHA-256，执行中变化会删除本轮已生成 raw 并使 run failed。

## 4. 实际注入遥测

父报告不只保存配置，还记录 loopback server 实际观察到的：

- HTTP request、body bytes 和 body chunk 数；
- 实际 delay、stall、503 rejection、TCP reset 和提前关闭事件数；
- capture elapsed、固定 failure code、termination、媒体跨度与 readiness。

每个场景的参数和实际事件必须匹配。例如 `midstream_stall` 必须同时看到正数 body bytes 和 stall event；`connection_reset` 必须看到正数 body bytes 和成功设置 reset 的事件。缺少实际事件时 `scenario_exercised=false`，即使 capture 状态碰巧符合预期，父 gate 仍保持 false。

## 5. Gate 语义

`fault_detection_gate_ready=true` 必须同时满足：

1. 七个场景按固定顺序完整存在，索引连续；
2. 每个场景都在 elapsed limit 内返回；
3. 每个场景的实际注入遥测与配置匹配；
4. 两个正向场景 ready，503/stall/截断/reset 场景符合各自预期；
5. 任何预期非 ready 的场景都没有 `captured_ready`；
6. 父报告的状态、计数、路径、固定失败码和 gate 可由内容重新计算。

失败 case 不能引用 raw 或 child report，采集器会删除 partial。若某个负向 case 以完整但过短容器结束，则允许保存 owner-only raw/child report 并标记 `captured_not_ready`，以保留可审计事实；它仍不能通过 gate。

## 6. 产物与隐私

```text
runs/<fault-run>/
├── manifest.json
├── source_assets.jsonl          # 仅成功形成完整 artifact 的 case
├── observations.jsonl
├── artifacts/
│   └── stream-fault-NNN.mkv
└── reports/
    ├── stream-fault-NNN.json
    └── stream-fault-matrix.json
```

run/子目录固定 `0700`，文件固定 `0600`。endpoint、loopback 端口、fixture 路径/文件名、HTTP 日志和底层异常 message 不进入产物。失败只发布 allowlisted code，其他 code 降级为 `stream_capture_failed`。

## 7. E1 结论与 E2 升级

clean `4e637a1` 的正式七场景 E1 全部在界内执行且符合预期，完整证据见[正式报告](reports/v1-m1-stream-fault-matrix-smoke.md)。它关闭的是 adapter 的安全故障识别工具门。

真实 C6c 升级不能直接复用 loopback fixture 结论，后续顺序为：

1. 取得同意和脱敏 endpoint 后完成单次短 E2 与三次 qualification；
2. 在外部受控代理或 OS 网络仿真层执行同一场景 taxonomy，另加 RTSP TCP/UDP、鉴权过期和真实 packet loss；
3. 明确 supervisor 是新建 run 还是协议化 session，不在同一 raw 中静默拼接；
4. 单独执行 30～60 分钟长稳和恢复时间测量；
5. 通过后才进入 C01～C12、双同步事件和 M2c 包。
