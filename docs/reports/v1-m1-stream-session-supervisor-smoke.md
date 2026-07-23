# V1-M1 流会话 Supervisor 与恢复账本 E1 报告

状态：Session Gate 与 Controlled Supervisor Recovery Gate 均按各自口径通过；不构成 C6c、同连接重连、非自愿断流恢复或长稳验收

测试日期：2026-07-23（运行 ID 使用 UTC 时间）

实现提交：`6a68371`

## 1. 目的与输入

验证两个彼此独立的工程结论：

1. 通用 supervisor 能把三个成功 capture 保存成三个独立 artifact，并生成可重算的 segment/gap/轨道签名账本；
2. 同一个 loopback HTTP endpoint 在 `ready → HTTP 503 → ready` 时，supervisor 会保留失败、等待 backoff、新开第三段，并生成恢复事件，而不是修改或拼接第一段 raw。

两次运行复用 qualification 第 3 个 +250 ms 音频起点 A/V artifact：

- 输入 SHA-256：`f999ee41bd360b35b227cfe2408e466de5e5ab0818a7887f66fc8ede2d1872f1`；
- 输入大小：11,504,831 bytes；
- 轨道：810×1080、10 fps、FFV1、time base 1/1000；16 kHz mono PCM S16LE、time base 1/1000；
- 两个正式 run 均为 clean `6a68371`、本地 CPU/network/PyAV。该层不执行姿态、ASR 或 GPU 推理，因此没有提交无关的 Slurm 作业。

## 2. 固定配置

| 项目 | 值 |
|---|---:|
| segment count | 3 |
| requested / minimum per segment | 2000 / 1500 ms |
| open / read timeout | 1000 / 1000 ms |
| failure backoff | 100 ms |
| declared minimum session wall | 0 ms |
| long-run hard threshold | 1,800,000 ms |
| audio required | true |

声明 wall 为 0 只用于短时工具验证。因此无论短测是否成功，`segmented_session_long_running_stability_proven` 都必须为 false。

## 3. 全健康 Session

Run：`runs/v1-stream-session-e1/20260723T011139Z-558b1b7b`

输入通过环境变量注入，source/evidence 为 fixture/E1，endpoint scheme 为 local。该 run 验证通用 CLI、独立 artifact、父子 ledger 和全段 gate；网络式 reopen 由第 4 节的 HTTP run 验证。

| Segment | 状态 | start→finish | elapsed | gap | media span |
|---:|---|---:|---:|---:|---:|
| 1 | ready | 0→868 ms | 868 ms | 0 ms | 2050 ms |
| 2 | ready | 868→1482 ms | 614 ms | 0 ms | 2050 ms |
| 3 | ready | 1483→2118 ms | 635 ms | 1 ms | 2050 ms |

父结果：

- ready / not-ready / failed：3 / 0 / 0；session elapsed 2118 ms；
- 唯一轨道签名 1，`track_signatures_consistent=true`；
- 三个 raw 和三个 child report 使用精确、互异的 segment 路径，`independent_segment_artifacts_proven=true`；
- interruption streak 0、recovery event 0，未伪造“发生过恢复”；
- `all_segment_capture_gate_ready=true`；
- `session_duration_gate_ready=true`；
- `session_gate_ready=true`；
- `segmented_session_long_running_stability_proven=false`。

## 4. 受控 HTTP 恢复

Run：`runs/v1-stream-recovery-e1/20260723T011205Z-46d42c9b`

source/evidence 为 fixture/E1，endpoint scheme 为 HTTP。三个 segment 始终使用同一个 loopback endpoint；仅在前一 capture 完成后切换服务端行为。

### 4.1 实际注入遥测

| Segment | 行为 | request | body | chunks | rejection | exercised |
|---:|---|---:|---:|---:|---:|---|
| 1 | full | 1 | 11,504,831 B | 44 | 0 | true |
| 2 | reject / HTTP 503 | 1 | 0 B | 0 | 1 | true |
| 3 | full | 1 | 11,504,831 B | 44 | 0 | true |

三段均有与行为一致的实际服务端遥测，`all_injections_exercised=true`。

### 4.2 Session 与恢复事件

| Segment | 状态 / code | start→finish | elapsed | gap | media span |
|---:|---|---:|---:|---:|---:|
| 1 | ready | 0→829 ms | 829 ms | 0 ms | 2050 ms |
| 2 | failed / `open_failed` | 830→831 ms | 1 ms | 1 ms | — |
| 3 | ready | 931→1521 ms | 590 ms | 100 ms | 2050 ms |

恢复事件严格绑定 segment 2→3：

- interruption start/end：2 / 2；count 1；
- `reopen_delay_ms=100`；
- `interruption_to_ready_artifact_ms=690`；
- segment 2 无 raw、无 child report、无 partial；segment 1/3 是两个独立 artifact；
- 两个 ready artifact 的唯一轨道签名为 1，格式一致。

因此：

- `supervisor_reopen_attempted=true`；
- `supervisor_reopen_recovery_observed=true`；
- `controlled_supervisor_recovery_gate_ready=true`；
- 通用 `all_segment_capture_gate_ready=false`、`session_gate_ready=false`，因为中间失败不能被恢复成功抵消。

## 5. 关键摘要

| 产物 | SHA-256 |
|---|---|
| healthy manifest | `4896a09a02f097dc4050546eca8781ef844ecd7cd85a95a1131243c6f61dc87c` |
| healthy source assets | `5a6f25a0ef1cf336dfd10d31a1a41035e3c9c12e58cba134d339eb2941e94d63` |
| healthy observations | `a91bb7cb1203586a34f7e55430f927a4ee96af5a1d4fc15239aa1431ddb4f2ad` |
| healthy session report | `a67f6819235b200ae75ff8af2c1f2d1c31e0b5213af842f7a3e0900ad59c1368` |
| recovery manifest | `4a165eb43a106d4f7cd4e2d2e21a6ee5ee0010a0165465a3fc91d2797acc3b00` |
| recovery source assets | `1c6820cf24bea246706c412221c79b792d71fe821998028e261e2b7a835765c7` |
| recovery observations | `efb3e18fdaaced806b48c810afd8586b700a1d082a37f3f80f6273a984230372` |
| recovery parent report | `986bb71ffa928f8f646c270c6aba6b5981f9905f94a6b1a987246ed2d701e59b` |

## 6. 自动化、安全与防篡改验证

- clean `6a68371` 全量：170 passed；新增 6 项覆盖 config 上限、健康 session、实际 HTTP 503 恢复、通用/专用 CLI、owner-only ledger、duration/long-run gate、时间/gap、计数、路径、注入和父 gate 防篡改。
- `compileall`、全部 shell/sbatch `bash -n`、`pip check`、Markdown 相对链接和 `git diff --check` 通过。
- 两个 manifest 均为 completed、clean `6a68371`、0 issue。healthy 为 3 assets / 3 observations / 7 artifacts；recovery 为 2 / 2 / 5，与父子 ledger 一致。
- run/子目录和文件全部为 `0700/0600`；失败 segment 2 没有 raw/report/partial。
- endpoint/loopback 地址/端口、fixture 路径/文件名、本地 home/用户名、环境变量、password/token/secret 和 Risk/Alert true 扫描均 0 命中。

## 7. 固定边界与结论

两份报告中的以下结论保持 false：

- 同一 raw 内 reconnect 和跨 segment 媒体拼接；
- same-connection reconnect、非自愿断流恢复；
- single-connection / segmented-session 长稳；
- packet loss、RTSP transport 和网络损伤容忍；
- C6c/萤石平台接入、M2c capture bundle、RiskAssessment 和 Alert。

E1 关闭了 supervisor 工程接缝：系统现在能用独立 artifact 表达多段 session、失败 gap、外部重开和恢复用时；受控 503 不会被静默吞掉，全健康 gate 与恢复 gate 的语义不会互相污染。

下一步必须使用真实 C6c E2 endpoint：先短时 session，再由外部代理/网络仿真注入可审计的 RTSP/鉴权/断流/packet loss/jitter，最后运行声明与实际均至少 30～60 分钟的长稳。当前结果不能替代这些实验。
