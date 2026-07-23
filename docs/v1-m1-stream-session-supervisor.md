# V1-M1 流会话 Supervisor 与恢复账本

状态：Implemented E1 v0.1.0；C6c E2、非自愿断流与 30～60 分钟长稳仍 Open

基准日期：2026-07-23

## 1. 目的与边界

单次 `capture-stream`、计划性 `qualify-stream` 和受控故障矩阵分别回答“能否接收一次”“能否重复开流”“故障能否安全识别”，但此前没有把多次有界采集组织为一段可审计运行。V1 选择外部 supervisor：每个 segment 都独立 open、独立生成 raw 和 child report；失败后等待固定 backoff，再由 supervisor 发起下一次 open。

本层明确禁止在同一个 Matroska 中静默重连或拼接断点。它可以记录：

- 每段 start/finish offset、实际 elapsed 和前置 gap；
- captured-ready、captured-not-ready 或 failed，以及固定 failure code；
- 跨 ready artifact 的完整视频/音频轨道签名；
- 连续 interruption streak 和随后 ready artifact 的恢复事件；
- 声明的 session 最短 wall time 是否满足，以及是否达到 30 分钟长稳硬阈值。

`supervisor_reopen_recovery_observed=true` 只表示一个非 ready segment 后，外部 supervisor 又取得了新的独立 ready artifact。它不等于同一连接自动重连，也不能在故障原因未知时写成“非自愿断流恢复”。

## 2. 运行结构

```text
同一受控 endpoint
  ├─ open segment 001 → artifacts/stream-session-001.mkv
  ├─ open segment 002 → failed / no raw
  └─ backoff → open segment 003 → artifacts/stream-session-003.mkv
                                  ↓
                    StreamSessionReport
                    ├─ segment ledger
                    ├─ gap ledger
                    ├─ track signatures
                    └─ recovery event 002 → 003
```

每次成功形成完整容器的 segment 都有一个 `StreamCaptureReport`。failed segment 不得引用 raw/child report，采集器遗留的 partial 会被删除。captured-not-ready 可以保留完整但未通过 requested readiness 的 artifact，父 gate 仍 fail closed。

## 3. 真实 endpoint 命令

endpoint 仍只能经进程环境输入：

```bash
read -rsp 'Stream endpoint: ' KANG_STREAM_ENDPOINT
printf '\n'
export KANG_STREAM_ENDPOINT

kangshield-info run-stream-session \
  --evidence-level E2 \
  --source-type network_stream \
  --device-ref c6c_demo_01 \
  --segment-count 3 \
  --duration-s 10 \
  --minimum-duration-s 8 \
  --failure-backoff-s 1 \
  --transport tcp \
  --require-ready

unset KANG_STREAM_ENDPOINT
```

短时预检通过后，30 分钟 supervisor 长稳候选可使用 30 个 60 秒 segment，并显式声明最短 wall time：

```bash
kangshield-info run-stream-session \
  --evidence-level E2 \
  --source-type network_stream \
  --device-ref c6c_demo_01 \
  --segment-count 30 \
  --duration-s 60 \
  --minimum-duration-s 50 \
  --minimum-session-wall-s 1800 \
  --failure-backoff-s 2 \
  --transport tcp \
  --require-ready
```

`minimum-session-wall-s` 是验收条件，不是自动延长器。若 segment 数量与时长不足，命令会完成既定尝试、写出报告，再因 `--require-ready` 返回 2。长稳声明只有在声明值和实际 `session_elapsed_ms` 都至少为 1,800,000 ms，且全部 segment ready、轨道签名一致时才可能为 true。60 分钟测试应相应提高 segment 数量或时长和最短 wall time。

## 4. 受控恢复命令

真机前先用本地 A/V fixture 验证 supervisor 状态机：

```bash
kangshield-info exercise-stream-recovery <local-av-fixture.mkv> \
  --duration-s 2 \
  --minimum-duration-s 1.5 \
  --open-timeout-s 1 \
  --read-timeout-s 1 \
  --failure-backoff-s 0.1 \
  --require-ready
```

该命令在同一个 loopback HTTP endpoint 上、仅在前一 capture 完成后切换固定行为：

| Segment | 服务端行为 | 预期结果 |
|---:|---|---|
| 1 | 完整媒体 body | `captured_ready` |
| 2 | HTTP 503 | `failed / open_failed` |
| 3 | 完整媒体 body | `captured_ready` |

父 `StreamRecoveryExerciseReport` 同时要求三段服务端 request/body/rejection 遥测确实发生，以及 session ledger 出现 2→3 的 recovery event。中间失败是测试设计的一部分，所以通用 `session_gate_ready=false`；专用 `controlled_supervisor_recovery_gate_ready=true` 才表示状态机通过。这两个 gate 不得互相替代。

## 5. 契约与 Gate

### 5.1 Segment

`StreamSessionSegment` 对每段保存：

- 连续 `segment_index`；
- 相对 session 起点的 `started_offset_ms` / `finished_offset_ms`；
- 可重算的 `elapsed_ms` 和相对上一段 finish 的 `gap_before_ms`；
- 状态、allowlisted failure code 或精确的 `artifacts/` / `reports/` 引用；
- media span、termination、readiness、path-free track signature 和 A/V 起点偏移。

父契约会重算时间、gap、路径、requested readiness 和计数。任何 segment 不能引用另一个索引的 artifact。

### 5.2 Recovery event

连续一个或多个非 ready segment 形成 interruption streak；其后第一次 ready segment 生成一条 `StreamSessionRecoveryEvent`：

- interruption start/end 与 recovered segment index；
- interrupted segment count；
- 最后一个 interruption 完成到下一次 open 的 `reopen_delay_ms`；
- 第一个 interruption 完成到新 ready artifact 完成的 `interruption_to_ready_artifact_ms`。

尾部未恢复的 streak 不产生 recovery event，但仍进入 `longest_interruption_streak`。报告不删除 gap，也不把多段媒体改写成连续时间轴。

### 5.3 Gate

| 字段 | 成立条件 | 不能证明 |
|---|---|---|
| `all_segment_capture_gate_ready` | 全部 segment ready、artifact 独立、完整轨道签名一致 | 最短 wall time、断流恢复 |
| `session_duration_gate_ready` | 实际 session wall time达到操作者声明值 | 媒体全部可用 |
| `session_gate_ready` | 上述两门同时通过 | 同一连接长稳或设备平台 |
| `supervisor_reopen_recovery_observed` | 非 ready streak 后出现新 ready artifact | 故障原因、同连接 reconnect、网络容忍 |
| `segmented_session_long_running_stability_proven` | session gate 通过，且声明值和实际值均至少 30 分钟 | 单连接连续性、60 分钟或更长稳定性 |
| `controlled_supervisor_recovery_gate_ready` | 固定 ready→503→ready 注入与 session 恢复事实同时通过 | RTSP、非自愿断流、packet loss、C6c |

以下边界保持 false：same-raw reconnect、跨段拼接、非自愿断流恢复、单连接长稳、网络损伤容忍、设备平台、M2c bundle、RiskAssessment 和 Alert。

## 6. 产物与隐私

```text
runs/<session-run>/
├── manifest.json
├── source_assets.jsonl
├── observations.jsonl
├── artifacts/
│   └── stream-session-NNN.mkv
└── reports/
    ├── stream-session-NNN.json
    └── stream-session.json
```

受控恢复 run 将父报告命名为 `stream-recovery-exercise.json`，其中嵌入完整 session ledger。run/子目录固定 `0700`，文件固定 `0600`。endpoint 值/摘要/变量名、loopback 端口、fixture 路径/文件名和底层异常 message 不进入产物。每个 ready/not-ready segment 都新增一份 raw，必须按 artifact 数量执行同意、访问、留存和删除流程。

## 7. E2 升级顺序

1. 用 C6c 完成单次短 E2，确认音轨、关键帧、PTS、凭据和删除流程；
2. 执行三次 qualification，冻结预期轨道 profile；
3. 用本命令做三段短 session，确认真实 endpoint 可被 supervisor 重开；
4. 在外部代理或 OS 网络仿真层注入 RTSP TCP/UDP、鉴权过期、packet loss、packet-level jitter 和断流；把注入 receipt 与 session report 一起评审；
5. 执行至少 30～60 分钟 segmented session 长稳，并单独保留单连接连续性结论；
6. 通过后才进入 C01～C12 与双同步事件采集。

## 8. E1 结论

clean `6a68371` 已完成两次正式运行：全健康 fixture session 为 3/3 ready、唯一轨道签名 1、`session_gate_ready=true`；同一 loopback HTTP endpoint 的 ready→503→ready 为 2 ready + 1 `open_failed`、1 条 2→3 recovery event、`controlled_supervisor_recovery_gate_ready=true`。完整时间、注入遥测、摘要与隐私审计见[正式 E1 报告](reports/v1-m1-stream-session-supervisor-smoke.md)。

两次短 run 的 segmented/single-connection 长稳、same-connection reconnect、非自愿断流恢复、RTSP、packet loss、网络容忍和设备平台声明都保持 false。fixture 恢复只关闭工程接缝，不提升 C6c 的设备证据等级。
