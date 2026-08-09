# V1-M1 有界音视频流采集 E1 初测报告

状态：Passed for E1 adapter seam；不构成 C6c / RTSP / 萤石平台验收

测试日期：2026-07-23（运行 ID 使用 UTC 时间）

实现提交：`8cbd91f`

## 1. 目的

验证一个不依赖萤石 SDK 的最小链路：HTTP 音视频输入经有界 codec-copy 采集为 owner-only Matroska，重新通过容器时间基门，并在 Slurm L40 上被真实 YOLO/FunASR 同容器 Pipeline 消费。

本测试刻意使用 loopback HTTP 和冻结 A/V fixture，因此证据等级为 E1。

## 2. 输入与环境

- 输入：被 Git 忽略的确定性同容器 A/V fixture，音频相对视频起点为 `+250 ms`。
- 传输：仅运行期间存在的 `127.0.0.1` HTTP server；端点通过进程环境传入。
- capture runtime：已安装 `.venv/bin/kangshield-info`，clean commit `8cbd91f`。
- downstream runtime：Slurm job `1782`，节点 `hepnode1`，1 张 L40，clean commit `8cbd91f`。
- 隐私：报告、manifest 与 stdout 扫描 endpoint、源文件名、本地 home、用户名和测试 secret，均为 0 命中。

## 3. 有界采集结果

Run：`runs/v1-stream-capture-e1/20260722T225832Z-cfed1858`

| 项目 | 结果 |
|---|---:|
| Run 状态 / issue | completed / 0 |
| evidence / source | E1 / fixture |
| endpoint scheme / transport | http / auto |
| termination | duration_limit |
| 请求 / 最短 / 实际媒体跨度 | 4000 / 3000 / 4050 ms |
| inspected / copied packet | 79 / 78 |
| video / audio packet | 40 / 38 |
| 首个视频 packet 为关键帧 | true |
| `capture_artifact_ready` | true |
| `same_container_multimodal_ready` | true |
| `device_platform_integration_proven` | false |
| RiskAssessment / Alert | false / false |

输出只有一条视频轨和一条音轨；audio-minus-video start 为 `+250.0 ms`，end 为 `+50.0 ms`，duration delta 为 `-200.0 ms`。这些值只描述被复制 packet 的容器时间范围；`drift_estimate_available=false`，不得解释成真实声画 drift。

Raw artifact：

- 路径：`artifacts/stream-capture.mkv`
- 大小：22,972,696 bytes
- SHA-256：`53ae54598f6ded0bfba5a59b3c14d0a9d2ca5bf77a2a3eda3b781bb7082bb0ed`
- mode：`0600`；run 与子目录为 `0700`

关键摘要：

| 产物 | SHA-256 |
|---|---|
| manifest | `8d687be53d06877cbaef5b3c04afc30cf0e48ced942b317bbdb269e6f0bbb2bd` |
| source assets | `e617ea41ef1cc24f999ca451aab1a925fb3d8e579135f6dc549f1d9546b78ae7` |
| observations | `eeaf07293282b208ff7c54e10ae63226dfbdb768922c2014d6db752c11939253` |
| stream capture report | `dd958f4352706bcc9fb78dad6ef0507d9df124ac8d6c8dd4ceaa1f5b2779848e` |

## 4. L40 下游 Pipeline 结果

Slurm job：`1782`，状态 `COMPLETED`，退出码 `0:0`，耗时 46 秒。

Run：`runs/v1-stream-capture-pipeline-e1/20260722T225924Z-c98c3772`

| 项目 | 结果 |
|---|---:|
| Run 状态 / issue | completed / 0 |
| input layout | same_container_pts |
| 输入 asset SHA-256 | 与 capture raw artifact 完全一致 |
| audio start offset | +250 ms |
| 处理时长 | 4000 ms |
| sampled / people pose frame | 20 / 20 |
| pose detection | 80 |
| speech segment | 1 |
| multimodal window | 4 |
| warm processing | 2295.910 ms |
| warm realtime factor | 0.573977 |
| video pose | 970.446 ms / RTF 0.242612 |
| speech | 510.962 ms / RTF 0.136257 |
| model load | 37251.170 ms |
| cold total | 39547.080 ms / RTF 9.886770 |

关键摘要：

| 产物 | SHA-256 |
|---|---|
| manifest | `88ac0f2c9295525e0f79cb6244abdd269ac65463e564ea5b2596fa647d4ed99d` |
| source assets | `c3e0e36d8f391d9069d6f40830fa4c2c91e3f314e2ccd8355025bc9a4663b895` |
| observations | `ebaecf5e8b16cdeb6b93124cbef232052a515460919aa757d1eb885576e55c8e` |
| features | `a3f9439775d95546b9d9bb2bdf7ae3b9f28673e62c8a78a2cf5295774dd10861` |
| windows | `c0e1d1bf28e652950f09121be96bb3e45cc58ab7ffc4ea6100dfc9eab7e9ccf5` |
| container probe | `61d320916a62fb53b3b990bfeebc2e1c56c73b4ad200f7e33950c09c3dd7754f` |
| pipeline report | `e68d1ab2ada07f01e51fba7bed3e63bb7454bb6890f2d24c6aa83b8b05418484` |
| Slurm stdout | `5a018166ebfe4a7eae9e46f0d8dda99c92339fe3329d10c33db2d03458b4e394` |

Pipeline run 的目录/文件与 stdout 分别保持 `0700` / `0600` / `0600`。warm RTF 只衡量模型加载后的 4 秒片段处理；cold RTF 包含约 37.25 秒模型加载，二者不可混用。

## 5. 自动化与故障注入

- 全量：154 passed。
- 新增回归覆盖：真实 loopback HTTP + PyAV remux、CLI owner-only 产物、短流 `--require-ready` 返回 2、缺音轨、伪造 E2、E2 缺 device ref、凭据不落盘、post-probe 失败清理和 parser 默认值。
- 静态检查：`compileall`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。
- 测试期间发现输入 container 关闭后访问 PyAV `Stream.codec_context` 可触发 native segfault；实现已改为在容器存活期复制轨道类型/codec 纯值，回归通过。

## 6. 结论与未关闭项

E1 adapter seam 通过：网络式输入可以在有界、owner-only、凭据不落盘的条件下生成同容器 artifact，并被现有真实多模态后端消费。

仍未证明：

- C6c 或萤石平台的 RTSP/HTTP URL、账号鉴权、麦克风音轨和接口权限；
- RTSP TCP/UDP、断线重连、长时稳定性、丢包、抖动和端到端延迟；
- 真实设备时钟、开始/结束同步事件、offset 与 drift；
- C01～C12 目标场景、远场 ASR、三姿态 held-out、RiskAssessment 或 Alert。

因此 V1-M1 增加“有界流采集工具 E1 已完成”，但目标设备能力与 V1-M2c 仍保持 Open。
