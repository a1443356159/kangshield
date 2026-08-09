# V1-M1 Stream Session 媒体时长门加固 E1 报告

状态：Accepted for E1 contract/tooling；实际 30～60 分钟长稳与 C6c E2 仍 Open

测试日期：2026-07-30（运行 ID 使用 UTC 时间）

实现提交：`ab1f366`

## 1. 问题与修正

`stream-session-v0.1.0` 的 segmented-session 长稳只要求：

- 全部 segment ready、artifact 独立且轨道签名一致；
- 操作者声明的最短 session wall time 至少 1,800,000 ms；
- 实际 `session_elapsed_ms` 至少 1,800,000 ms。

该口径没有独立核验有效媒体覆盖。长时间 open、stall、gap 或 backoff 理论上可以撑大 wall time，即使累计可用媒体不足 30 分钟，也可能产生长稳假阳性。

`stream-session-v0.2.0` 新增：

- `minimum_ready_media_ms`：操作者独立声明的累计 ready 媒体下限；
- `ready_media_span_ms`：父契约从所有 `captured_ready` segment 的 `captured_media_span_ms` 重算；
- `session_media_duration_gate_ready`：实际 ready media 达到声明下限；
- 组合 `session_gate_ready` 同时要求 all-segment、wall duration 与 media duration 三门；
- long-run 只有在 wall / ready media 的声明值和实际值分别达到 1,800,000 ms 时才为 true。

`stream-recovery-exercise` 因嵌套新 session 契约同步升级到 v0.2.0。设备平台、RTSP、网络损伤、单连接连续性、RiskAssessment 和 Alert 语义没有变化。

## 2. Clean 实现验证

- clean commit：`ab1f3668b056ce32b0cbd71171cef7360da2ff61`；
- 全量自动化：170 passed；
- 定向测试同时覆盖：
  - ready media 父级汇总防篡改；
  - wall gate 与 media gate 独立 fail closed；
  - wall 达到 1,800,000 ms、ready media 不足时 long-run 必须为 false；
  - wall / media 的声明值和实际值均达到 1,800,000 ms 时 long-run 才可为 true；
  - v0.2 CLI、健康 session 与受控恢复的 owner-only ledger；
- `py_compile`、全部 Python 脚本、shell/sbatch `bash -n`、`pip check` 和 `git diff --check` 通过。

上述 30 分钟正反例是契约构造测试，只证明判定公式，不是实际运行 30 分钟的稳定性证据。

## 3. 健康 Session

Run：`runs/v1-stream-session-media-gate-e1/20260730T072716Z-fb419398`

固定配置：

| 项目 | 值 |
|---|---:|
| session / evidence | v0.2.0 / E1 |
| segment count | 3 |
| requested / minimum per segment | 800 / 500 ms |
| declared minimum wall | 0 ms |
| declared minimum ready media | 1,500 ms |
| long-run threshold | 1,800,000 ms |

三个 segment 均为 `captured_ready`，每段 `captured_media_span_ms=850`。父报告重算：

- `ready_media_span_ms=2550`；
- `session_elapsed_ms=1595`；
- ready / not-ready / failed = 3 / 0 / 0；
- `all_segment_capture_gate_ready=true`；
- `session_duration_gate_ready=true`；
- `session_media_duration_gate_ready=true`；
- `session_gate_ready=true`；
- `segmented_session_long_running_stability_proven=false`。

本 run 显式关闭了新增媒体下限，不是依赖默认值通过；wall 下限为 0，因此不声称短 fixture 形成任何长稳证据。

## 4. 受控恢复兼容性

Run：`runs/v1-stream-recovery-media-gate-e1/20260730T072946Z-5d163ce2`

同一 loopback HTTP endpoint 固定执行 full → 503 → full：

- 3/3 request/injection 有实际服务端遥测，`all_injections_exercised=true`；
- segment 状态为 ready / `open_failed` / ready；
- 两个 ready segment 各贡献 850 ms，父报告重算 `ready_media_span_ms=1700`；
- segment 2→3 的 `reopen_delay_ms=10`，`interruption_to_ready_artifact_ms=479`；
- `supervisor_reopen_recovery_observed=true`；
- `controlled_supervisor_recovery_gate_ready=true`；
- 中间失败没有被恢复抵消，`session_gate_ready=false`；
- `segmented_session_long_running_stability_proven=false`。

该 run 验证 v0.2 媒体字段没有破坏原有恢复账本和通用/专用 gate 隔离；HTTP 503 仍不是非自愿断流或 same-connection reconnect。

## 5. 摘要、权限与脱敏

| 产物 | SHA-256 |
|---|---|
| healthy manifest | `145aa6a2e28db0b288b23daf8c3bd73bf61cfbedccc073252680e8183b3c0b23` |
| healthy source assets | `3a3d2647df0a3d0d97601e8099f1c251daf6c7828852d762a18f89720d63ec7c` |
| healthy observations | `7de910a64abae75c53b6693b59ff93c0aca3a0c1c38792df161fa77cd19dfac5` |
| healthy session report | `4e68af59cac4a7011cb25b3d2a9ef46158495e8d63c359a7c484cc005c58f952` |
| recovery manifest | `9f9eaf61d08ff5ae7652bf71c005854a8685a79d37afdaa2186f35c34bd77cf8` |
| recovery source assets | `bba2fbdfd08eadc039c4d1e517f7a3c3c386e26da129ead2d36c9900158318e8` |
| recovery observations | `0215de6722001e923f9d1bfb82c4f2432c2620c648f75601c5eaffca43fefa81` |
| recovery parent report | `ce32af1f480cbbec16c5dab46d17e4909572451af55368b72d7bd5a21075f8c1` |

两个正式 manifest 均为 completed、clean `ab1f366`、0 issue。run/子目录为 `0700`，文件为 `0600`。环境变量名和值、fixture 路径/文件名、本地 home/用户名、loopback host/port、password/token/secret 和 Risk/Alert true 扫描 0 命中。

环境内第一次 loopback recovery 预检因沙箱不允许绑定 socket 而形成 failed run `20260730T072718Z-82ef3f62`；它是 clean failure ledger、无任何 artifact，不纳入本报告正式证据。解除该环境限制后的 completed run 才是上文引用对象。

## 6. 结论与剩余边界

本切片关闭的是长稳判定的工程假阳性：空闲 wall time 不能替代累计 ready media，父级媒体汇总也不能脱离 segment ledger 手工填写。

本报告没有执行 30～60 分钟真实运行，也没有使用 C6c、RTSP、萤石账号或真实人物媒体。因此以下结论仍未成立：

- C6c/萤石平台接入与音轨能力；
- RTSP TCP/UDP、鉴权过期、packet loss/delay/jitter；
- 非自愿断流恢复或 same-connection reconnect；
- 实际 segmented-session 或 single-connection 长稳；
- M2c 真实采集包、RiskAssessment 或 Alert。

下一次 E2 长稳必须显式设置 `--minimum-session-wall-s` 和 `--minimum-ready-media-s`，并同时保留真实 endpoint、外部故障注入 receipt、session report 和 raw 留存/删除审计。
