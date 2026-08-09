# V1-M1 受控流故障矩阵 E1 报告

状态：Fault Detection Gate Passed for E1；不构成 RTSP、packet loss、恢复或长稳验收

测试日期：2026-07-23（运行 ID 使用 UTC 时间）

实现提交：`4e637a1`

## 1. 目的与输入

验证现有有界采集器在七种真实 loopback socket 行为下能否按预期 ready 或 fail closed，并留下可重算、路径安全、owner-only 的父子证据。

- 输入：qualification 第 3 个 +250 ms 音频起点 A/V artifact；
- 输入 SHA-256：`f999ee41bd360b35b227cfe2408e466de5e5ab0818a7887f66fc8ede2d1872f1`；
- 输入大小：11,504,831 bytes；
- 正式 run：clean `4e637a1`，本地 CPU/network/PyAV；该工具不执行模型或 GPU 推理，因此没有提交无关的 Slurm 作业。

## 2. 配置

| 项目 | 值 |
|---|---:|
| requested / minimum | 2000 / 1500 ms |
| open / read timeout | 1000 / 1000 ms |
| stall | 1500 ms |
| elapsed limit per case | 7000 ms |
| partial body limit | 2,097,152 bytes |
| jitter chunk | 262,144 bytes |
| jitter delay | 5 / 20 ms alternating |

## 3. 场景结果

Run：`runs/v1-stream-fault-matrix-e1/20260723T003417Z-2f683f0f`

| 场景 | 实际遥测 | 状态 / code | elapsed |
|---|---|---|---:|
| healthy control | 11,504,831 B / 44 chunks | ready | 851 ms |
| chunk delay jitter | 11,504,831 B / 44 chunks / 43 delays | ready | 1142 ms |
| HTTP rejection | 1 rejection | failed / `open_failed` | 2 ms |
| initial response stall | 1 stall / 0 body | failed / `open_failed` | 1003 ms |
| midstream stall | 2,097,152 B / 8 chunks / 1 stall | failed / `remux_failed` | 1009 ms |
| truncated transfer | 2,097,152 B / 8 chunks / 1 early close | failed / `remux_failed` | 5 ms |
| connection reset | 2,097,152 B / 8 chunks / 1 reset | failed / `remux_failed` | 6 ms |

父结果：

- scenario / bounded / expectation / exercised：7 / 7 / 7 / 7；
- ready / not-ready / failed：2 / 0 / 5；
- unexpected ready：0；
- `fault_detection_gate_ready=true`。

五个失败场景均没有 raw 或 child report，目录内不存在 partial。两个正向场景分别产生独立同容器 artifact，跨度均为 2050 ms，`capture_artifact_ready` 与 `same_container_multimodal_ready` 均为 true。

## 4. 关键摘要

| 产物 | SHA-256 |
|---|---|
| manifest | `9175c7236ec06f872a2949e9f4344201dcf8832f4a844ec3baf9e89221526116` |
| source assets | `c50a9baa36798c41135538064fcb1e0d914b22b789747e69e76164574bb221d1` |
| observations | `75a639f765d052d8df79f7850f7798c47c5edbbadf56089b35282ac4fc16df98` |
| capture report 001 | `0edf5263a233fa1955c653ea37074b441df377641021300a9508ff4543495411` |
| capture report 002 | `b5cd77bcd1127c9e0c5ff0da7cf4147614408b604b2dc7275805dace06ec644c` |
| fault matrix report | `0ccc2efb336e96e8821d2d6b2e14870f4a4bf2a73bce4de85ae7faa324a528f1` |
| healthy raw | `1e6a9463e1cb992bbfcd930aeac63944c6e23b70d094c96895c02a2b76fe6fe9` |
| delayed raw | `8ef41b034b98ecf6b6a264ec2d93cc1ecdb82d0a0ed039d1ea3af15a4d1a20d4` |

## 5. 自动化与安全验证

- 全量：164 passed；新增覆盖固定七场景真实 socket 行为、实际注入遥测、父子 ledger、owner-only 权限、配置拒绝、计数/gate/遥测/路径/私有失败码防篡改和 parser 默认值。
- `compileall`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。
- manifest：completed、clean `4e637a1`、0 issue；输入 digest 与 qualification child 一致。
- run/子目录和文件为 `0700/0600`；2 个 asset、2 个 observation、2 个 child report 与 1 个父报告一致。
- loopback 地址/端口、fixture 原文件名、本地 home/用户名、环境变量、password/token/secret 和 Risk/Alert true 扫描 0 命中。

## 6. 固定 false 与结论

以下字段仍为 false：packet loss、RTSP、reconnect attempted、非自愿断线恢复、网络损伤容忍、长稳、平台接入、M2c bundle、RiskAssessment 和 Alert。

E1 安全故障识别工具门通过：受控正向输入仍可消费，拒绝/stall/截断/reset 没有被误报为 ready，所有 case 有界结束，父报告能证明实际注入动作发生。

该结果不证明真实 C6c、萤石鉴权、UDP/TCP 差异、packet loss、packet-level jitter、自动恢复、恢复时间或 30～60 分钟稳定性。
