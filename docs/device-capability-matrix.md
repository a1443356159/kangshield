# 设备能力矩阵

状态：Live Ledger v0.4

更新时间：2026-07-23

本文件只记录设备能力证据。E0/E1 不得写成已接通。

## 1. 目标设备

| 设备 | 型号 | 来源 | 当前最高证据 |
|---|---|---|---|
| 摄像头 | CS-C6c-V101-1J4WF | 用户确认，带麦克风 | E0 |
| 睡眠仪 | CS-EP-SDNL1 | 用户确认；官方产品页存在该型号 | E0 |

证据等级定义见[信息侧详细技术路线](information-side-technical-route.md#2-证据等级)。

## 2. 摄像头能力

| 能力 | 文档/产品支持 | 真实账号验证 | 输出证据 | 状态 |
|---|---|---|---|---|
| 设备授权与列表 | 萤石 SDK 通用能力 | 未验证 | — | Unknown |
| 设备在线状态 | SDK 设备信息可提供基础数据 | 未验证 | — | Unknown |
| 设备能力集 | SDK 要求按能力集判断 | 未验证 | — | P0 |
| 实时预览 | 萤石 SDK 通用能力 | 未验证 | — | P0 |
| 回放/录像列表 | 萤石 SDK 通用能力 | 未验证 | — | P0 |
| 抓图 | captureCamera，需设备支持 | 未验证 | — | P0 |
| 告警列表/消息 | getAlarmList 等通用能力 | 未验证 | — | P0 |
| 服务端有界 RTSP/HTTP 接收与落盘 | 项目 adapter 已实现 | 仅 loopback HTTP fixture | REV-025 / E1 | Tooling ready；Device Unknown |
| 服务端可解码视频 | 不由通用功能列表保证 | 未验证 | — | P0 |
| 音频轨 | 用户确认设备有麦克风；开放取流未知 | 未验证 | — | P0 |
| 音频编码/采样率 | 无目标 SKU 证据 | 未验证 | — | Unknown |
| 夜视模式 | 同系列资料不能替代目标 SKU 验证 | 未验证 | — | P1 |
| 云台/对讲 | 必须查询能力集 | 未验证 | — | P2 |
| 设备侧人形/声音 AI | 必须查询能力集和消息类型 | 未验证 | — | P2 |

### 摄像头首个证据包

应包含：

- 脱敏设备信息/能力集响应。
- 调用时间和 SDK/API 版本。
- 直播或回放取得的一段 30～60 秒媒体。
- 容器、视频编码、分辨率、FPS、音轨、音频编码。
- 抓图与告警调用结果。
- 失败接口的错误码和权限说明。

V1-M2c 已完成 E1 容器轨道/PTS 探针及确定性回归夹具，见[设计](v1-m2c-media-timing-probe.md)与[报告](reports/v1-m2c-media-timing-smoke.md)。该工具没有使用 C6c 媒体，因此本矩阵的音频轨、编码和时间基状态仍为未验证，最高证据仍为 E0。

V1-M2a 随后把该 timing gate 接入同容器音轨解码、16 kHz VAD/ASR 和 FeatureEvent 时间平移，并在工程构造的 +250 ms 公开 A/V 上完成 clean CPU 真实后端运行，见[同容器初测报告](reports/v1-m2a-same-container-audio-smoke.md)。这只证明 adapter seam 可运行；输入仍是 E1 fixture，不能证明 C6c 开放平台能取得音轨，因此上表状态和 E0 上限不变。

REV-025 又把 RTSP/HTTP(S) endpoint 接到有界 codec-copy、首视频关键帧、owner-only Matroska 与输出 timing probe，并由 L40 job `1782` 消费该 artifact，见[设计](v1-m1-bounded-stream-capture.md)与[报告](reports/v1-m1-bounded-stream-capture-smoke.md)。正式输入仍是 loopback HTTP fixture，未使用 C6c、RTSP 或萤石账号；因此只将“项目接收工具”标为 E1 ready，设备的实时预览、视频/音轨与平台能力仍为 Unknown/E0。

REV-014 又完成了 E1 采集包/场景标注/held-out readiness gate，见[设计](v1-m2c-capture-readiness-gate.md)与[报告](reports/v1-m2c-capture-readiness-smoke.md)。正式 fixture 虽有 10/10 结构可用 clip，`camera_ready_for_model_retest`、`sleep_sample_ready_for_profiling` 和 `capture_bundle_ready_for_review` 均为 false；因此本能力矩阵仍不提升目标设备证据等级。

REV-016 进一步完成双人标注一致性、裁决和事件误触发/检出延迟的 E1 scorer，见[设计](v1-g4-event-evaluation-readiness.md)与[报告](reports/v1-g4-event-evaluation-smoke.md)。其 12 clip/三 candidate stream 均为确定性 synthetic 输入，`capture_camera_gate_passed=false`、`event_metrics_ready_for_review=false`；同样不能证明 C6c 画面、模型或事件性能。

## 3. 睡眠仪能力

官方商品页可确认的硬件事实：

- 59～64 GHz FMCW。
- 50 ms 数据周期。
- 0.5～1.5 m 测距范围。
- 两组测量范围为 40～120 bpm 和 6～40 bpm。
- 通过萤石云视频 APP 联网。

2026-07-22 复核发现萤石开放平台另有通用“居家养老雷达开发套件”和“睡觉检测”服务，公开宣传睡眠时长、心率、呼吸、睡眠深度、体动和翻身等维度；但推荐设备型号不是 CS-EP-SDNL1，具体产品文档也未公开可抓取的请求/响应字段。因此这些只列为账号/商务确认候选，不改变下表“未验证”。

这些事实均为 E0，不能推导开放接口。

| 能力/字段 | 产品或方案声明 | 真实接口验证 | 输出证据 | 状态 |
|---|---|---|---|---|
| 开放平台设备枚举 | 未确认 | 未验证 | — | P0 |
| 数据获取方式 | APP 联网；开发方式未知 | 未验证 | — | P0 |
| 心率 | 产品参数存在一组 bpm 范围，字段语义待确认 | 未验证 | — | P0 |
| 呼吸率 | 产品参数存在另一组 bpm 范围，字段语义待确认 | 未验证 | — | P0 |
| 在床/离床 | 《监测方案》需要 | 未验证 | — | P0 |
| 总睡眠时长 | 《监测方案》需要 | 未验证 | — | P0 |
| 入睡/起床 | 《监测方案》需要 | 未验证 | — | P0 |
| 夜间觉醒/WASO | 《监测方案》需要 | 未验证 | — | P1 |
| 睡眠效率/阶段 | 《监测方案》需要 | 未验证 | — | P1 |
| 体动/翻身 | 萤石通用睡觉检测服务宣传；目标型号兼容性未知 | 未验证 | — | P1 |
| 原始雷达数据 | 无开放证据 | 未验证 | — | Unknown |
| HRV 原始间期 | 无开放证据 | 未验证 | — | Not assumed |
| 血氧 | 无当前设备证据 | 未验证 | — | Not assumed |
| AHI | 无开放证据 | 未验证 | — | Not assumed |
| 历史查询粒度 | 未确认 | 未验证 | — | P0 |
| 更新延迟/调用频率 | 未确认 | 未验证 | — | P0 |

### 睡眠仪首个证据包

应包含：

- 脱敏 API 响应或官方导出原文件副本的摘要。
- 接口/导出方式、调用时间、时间范围。
- 字段名、类型、单位、时间粒度、缺失值。
- 设备离线、无人/离床和正常睡眠三种状态如何表达。
- 至少连续三晚的字段完整率；V1-M1 可先提供一晚样例。

## 4. 监测指标覆盖结论

| 监测维度 | 当前设备理论来源 | 当前结论 |
|---|---|---|
| 步态时空参数 | C6c 视频模型 | 可探索代理量；真实尺度需标定 |
| 昼夜节律 | 睡眠仪 + 摄像头活动 | 依赖睡眠接口和多日数据 |
| 语音声学/语义 | C6c 麦克风 | 依赖音轨权限与远场质量 |
| 面部表情动态 | C6c 视频模型 | 依赖脸部像素；低优先级 |
| 社交交互时序 | C6c 视野内活动 | 只能做弱代理；无门锁/电话数据 |
| 生理指标 | 睡眠仪 | 仅接受接口实际返回字段 |
| 肌力与姿势稳定 | C6c 姿态模型 | 可做图像代理；不能声称 COP |

## 5. 更新规则

每次能力变化追加以下信息：

- 日期和操作者。
- 设备固件、SDK/API 版本。
- 证据等级变化。
- 证据运行目录或脱敏附件。
- 成功率、失败码和限制。
- Review 编号。

不得删除失败记录；能力降级也必须记录。

字段需求与 fail-closed 解锁规则见 [V1-M3 睡眠字段路线](v1-m3-sleep-field-route.md)。官方公开来源：[CS-EP-SDNL1 商品页](https://www.ys7.com/item/994492.html?position=search_pc)、[居家养老雷达开发套件](https://open.ys7.com/cn/s/157)、[睡觉检测服务](https://open.ys7.com/cn/s/623)。
