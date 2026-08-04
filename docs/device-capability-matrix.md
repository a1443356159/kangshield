# 设备能力矩阵

状态：Live Ledger v1.0

更新时间：2026-08-02

本文件只记录设备能力证据。E0/E1 不得写成已接通。

## 1. 目标设备

| 设备 | 型号 | 来源 | 当前最高证据 |
|---|---|---|---|
| 摄像头 | CS-C6c-V101-1J4WF | 用户确认，带麦克风；REV-033 起单机位（双机位保留为扩展） | E0 |
| 睡眠仪 | CS-EP-SDHY1 | 2026-08-04 实际绑定账号；huayi 接口族实测返回真实数据 | E0 |

证据等级定义见[信息侧详细技术路线](information-side-technical-route.md#2-证据等级)。

### 1.1 硬件能力表述边界（REV-031 冻结）

CS-C6c-V101-1J4WF（公开资料，同系列 `1J4WF` 档）：

- 支持：室内云台 RGB；按"400 万/2K+ 档"对待，同系列参数最高 2560×1440、4 mm 镜头、水平视场约 75°、H.265、双码流、红外夜视约 10 米、水平云台约 340°、网传帧率自适应。
- 不能承诺：不按 4K 宣传；不预设恒定 25 fps；不承诺任意方向均可精确测量；不假定 RTSP/ONVIF（同系列接口协议为萤石云私有协议）。精确型号字符串未在官方页面完整列出，分辨率、实际帧率、固件版本和码流接口以实机能力集确认为准。

CS-EP-SDHY1（公开资料 + 2026-08-04 实测）：

- 支持：心率 45～150 bpm、呼吸率 0～36 次/分、分辨率 1 bpm（厂商精度口径 AP8/AP3>90%）；萤石云视频 APP 联网；huayi 族统计与属性接口实测可用（每 10 分钟统计序列、约 1 秒间隔属性历史、state 字符串枚举）。
- 不能承诺：不测血氧、血压、心电；不诊断睡眠呼吸暂停；睡眠报告不等同于 PSG 睡眠分期；不作为步态测距雷达；原始雷达数据官方确认不开放；字段单位/时间/缺失语义以真实响应复核为准。

家庭内只部署上述两台设备，不安排任何主动步行或睡眠测试；相机标定、对时和安装验收由工作人员完成。C6Wi、H3、RGB-D、压力步道等方案均已排除；REV-031 双机位设计保留为后续扩展。

## 2. 摄像头能力

| 能力 | 文档/产品支持 | 真实账号验证 | 输出证据 | 状态 |
|---|---|---|---|---|
| 设备授权与列表 | 萤石 SDK 通用能力 | 未验证 | — | Unknown |
| 设备在线状态 | SDK 设备信息可提供基础数据 | 未验证 | — | Unknown |
| 设备能力集 | SDK 要求按能力集判断 | 未验证 | — | P0 |
| 实时预览 | 萤石 SDK 通用能力 | 2026-08-04 E2 实测：激活码激活后 HLS/FLV 直播地址可用 | runs/20260804T075947Z | E2 |
| 回放/录像列表 | 萤石 SDK 通用能力 | 未验证 | — | P0 |
| 抓图 | captureCamera，需设备支持 | 未验证 | — | P0 |
| 告警列表/消息 | getAlarmList 等通用能力 | 未验证 | — | P0 |
| 服务端有界 RTSP/HTTP 接收与落盘 | 项目 adapter 已实现 | 2026-08-04 E2 实测：FLV 采集 20 s、300 视频包/310 音频包、双 ready | runs/20260804T075947Z | E2 |
| 服务端重复开流与格式稳定 gate | 项目 qualification 已实现 | 2026-08-04 E2 实测：3/3 ready、轨道签名一致（HEVC 2560×1440@15 + AAC 16 kHz mono） | runs/20260804T081325Z | E2 |
| 服务端受控故障识别 gate | 项目七场景 HTTP fault matrix 已实现 | 仅 loopback fixture；无 RTSP/packet loss | REV-027 / E1 | Tooling ready；Device Unknown |
| 服务端分段 session / 外部重开恢复 gate | 项目 supervisor 与 gap/recovery ledger 已实现 | 仅 fixture；受控 HTTP 503，不是非自愿断流 | REV-028 / E1 | Tooling ready；Device Unknown |
| 服务端 long-run wall/media 双时长 gate | 项目 v0.2 契约已实现并防空闲时长假阳性 | 仅短 fixture 与契约测试；未实际运行 30～60 分钟 | REV-029 / E1 | Tooling ready；Device Unknown |
| 服务端可解码视频 | 不由通用功能列表保证 | 2026-08-04 E2 实测：主码流 HEVC 2560×1440@15fps 可解码落盘 | runs/20260804T075947Z | E2 |
| 音频轨 | 用户确认设备有麦克风；开放取流未知 | 2026-08-04 E2 实测：FLV 含 AAC 16 kHz 单声道音轨；HLS 占位段无音轨系 9048 假象 | runs/20260804T075947Z | E2 |
| 音频编码/采样率 | 无目标 SKU 证据 | 2026-08-04 E2 实测：AAC 16 kHz mono | runs/20260804T075947Z | E2 |
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

赛事官方材料确认：C6C 为赛事统一主推设备；视频流本地拉取除直播协议外可用[录像下载](https://open.ys7.com/help/4162)，其开放范围、码流规格和费用需在首个证据包中一并验证（[赛事材料归档](v1-m1-ezviz-platform-competition-notes.md)）。

2026-08-04 交互式实测（非正式 run）：设备列表/信息 API 确认型号 CS-C6c-V101-1J4WF 与固件 V5.3.8，设备在线；`encrypt/off` 远程关加密与麦克风开关 API 均验证可用；直播地址接口（HLS/quality=1）可调用，但因设备套餐未激活仅返回 9048 占位段。实时预览、主码流规格、音轨仍为未验证，待套餐激活后复测。

V1-M2c 已完成 E1 容器轨道/PTS 探针及确定性回归夹具，见[设计](v1-m2c-media-timing-probe.md)与[报告](reports/v1-m2c-media-timing-smoke.md)。该工具没有使用 C6c 媒体，因此本矩阵的音频轨、编码和时间基状态仍为未验证，最高证据仍为 E0。

V1-M2a 随后把该 timing gate 接入同容器音轨解码、16 kHz VAD/ASR 和 FeatureEvent 时间平移，并在工程构造的 +250 ms 公开 A/V 上完成 clean CPU 真实后端运行，见[同容器初测报告](reports/v1-m2a-same-container-audio-smoke.md)。这只证明 adapter seam 可运行；输入仍是 E1 fixture，不能证明 C6c 开放平台能取得音轨，因此上表状态和 E0 上限不变。

REV-025 又把 RTSP/HTTP(S) endpoint 接到有界 codec-copy、首视频关键帧、owner-only Matroska 与输出 timing probe，并由 L40 job `1782` 消费该 artifact，见[设计](v1-m1-bounded-stream-capture.md)与[报告](reports/v1-m1-bounded-stream-capture-smoke.md)。正式输入仍是 loopback HTTP fixture，未使用 C6c、RTSP 或萤石账号；因此只将“项目接收工具”标为 E1 ready，设备的实时预览、视频/音轨与平台能力仍为 Unknown/E0。

REV-026 再以三个独立连接检查 requested readiness 和完整轨道签名，见[资格门](v1-m1-stream-qualification.md)与[报告](reports/v1-m1-stream-qualification-smoke.md)。三次 E1 HTTP 都得到 810×1080/10 fps FFV1 + 16 kHz mono PCM，但这是同一 fixture 的计划性 reopen；C6c 的真实格式、RTSP 鉴权、断线恢复、丢包/抖动和长稳仍未验证，设备最高证据仍为 E0。

REV-027 使用同一 E1 child 实际执行完整响应、分块延迟、503、首包/部分 body stall、截断和 TCP reset，见[故障矩阵](v1-m1-stream-fault-matrix.md)与[报告](reports/v1-m1-stream-fault-matrix-smoke.md)。7/7 场景有界且无意外 ready 只证明项目 adapter 的安全识别；没有使用 C6c、RTSP、鉴权、packet loss 或恢复策略，设备最高证据仍为 E0。

REV-028 将多次有界 capture 组织为独立 segment/raw、start/finish/gap/interruption/recovery ledger，并在同一 loopback HTTP endpoint 完成 ready→503→ready，见[Supervisor 设计](v1-m1-stream-session-supervisor.md)与[报告](reports/v1-m1-stream-session-supervisor-smoke.md)。专用恢复 gate 通过只证明外部 supervisor 会在受控拒绝后新开 artifact；same-connection reconnect、非自愿断流、RTSP/packet loss、30～60 分钟长稳和 C6c 仍未验证，设备最高证据仍为 E0。

REV-029 将长稳 gate 升级为 wall time 与累计 ready media 的双声明、双观测门，父契约从 segment 重算媒体总时长，见[加固报告](reports/v1-m1-stream-session-media-duration-gate-smoke.md)。短 E1 健康/恢复 run 与 30 分钟契约正反例只证明判定不会被空闲时间放大；没有实际运行 30 分钟，更没有使用 C6c，因此设备最高证据仍为 E0。

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

2026-08-02 赛事官方材料进一步确认：毫米波雷达**不开放原始数据**（信号点不可得），跌倒检测雷达仅开放“人员跌倒结果通知”告警；但**睡眠雷达经设备云组件仓提供心率/呼吸率/睡眠统计与属性查询接口**（help/1849、help/1850），功能点文档覆盖每日/周/月/年统计、异常心率统计和分页属性历史记录。CS-EP-SDNL1 与该组件文档的型号兼容性、字段清单与粒度（是否分钟级）须在赛事账号内实测（[赛事材料归档](v1-m1-ezviz-platform-competition-notes.md)）。

2026-08-04 交互式实测（非正式 run）：账号实际绑定睡眠设备为 **CS-EP-SDHY1（小贝壳）**，非本矩阵冻结的 CS-EP-SDNL1，型号边界待 REV 决定。huayi 族接口实测可用：每日心率统计（10 分钟序列）与属性历史（约 1 秒间隔，state 为字符串枚举）均返回真实数据；每日睡眠统计待完整夜间数据。原始雷达数据仍不开放。

这些事实均为 E0，不能推导开放接口。

| 能力/字段 | 产品或方案声明 | 真实接口验证 | 输出证据 | 状态 |
|---|---|---|---|---|
| 开放平台设备枚举 | 未确认 | 未验证 | — | P0 |
| 数据获取方式 | APP 联网；设备云组件仓统计/属性接口有官方文档 | 2026-08-04 E2 实测：huayi 族属性历史/每日心率均 200 | runs/20260804T075034Z | E2 |
| 心率 | 产品参数一组 bpm 范围；组件仓心率统计（日/周/月/年+异常）有文档 | 2026-08-04 E2 实测：10 分钟统计序列与约 1 秒属性历史均返回真实值；route 评估 blocked_semantics 仅缺缺失值语义 | runs/20260804T075035Z | E2 |
| 呼吸率 | 产品参数一组 bpm 范围；组件仓呼吸率统计（日/周/月/年）有文档 | 2026-08-04 E2 实测：属性历史 breathRate 返回真实值；每日呼吸率接口当日 500 待重试 | runs/20260804T075035Z | E2 |
| 在床/离床 | whst bodyDetect 事件流（1=在床 2=离床）+ 属性 state + EP 报告 | 2026-08-04 API 实测 200，暂无事件（白日新装） | 赛事材料归档 §15 | E2 |
| 总睡眠时长 | EP 睡眠报告 timeOutput（9=睡眠总时长）+ 每日睡眠统计 | 2026-08-04 API 实测 200，待首个完整夜 | 赛事材料归档 §15 | E2 |
| 入睡/起床 | EP 睡眠报告 timeOutput（2=入睡/3=醒来/4=起床） | 2026-08-04 API 实测 200，待首个完整夜 | 赛事材料归档 §15 | E2 |
| 夜间觉醒/WASO | 《监测方案》需要 | 未验证 | — | P1 |
| 睡眠效率/阶段 | 《监测方案》需要 | 未验证 | — | P1 |
| 体动/翻身 | 萤石通用睡觉检测服务宣传；目标型号兼容性未知 | 未验证 | — | P1 |
| 原始雷达数据 | 赛事官方明确不开放（2026-08-02 归档） | 不适用 | 赛事材料归档 | Not assumed |
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
| 步态时空参数 | 2× C6c 视频模型 | 双侧独立测量+事件级时间对齐+质量择优融合；真实尺度需锁定云台和地面标定；不做同步双目三维重建；步态疾病类型仅作筛查 |
| 昼夜节律 | 睡眠仪 + 摄像头活动 | 在床时段趋势依赖睡眠接口；IV/IS/RA/M10/L5 需近 24 小时连续活动计数，当前设备组合不可得 |
| 语音声学/语义 | C6c 麦克风 | 依赖音轨权限与远场质量；Jitter/Shimmer/HNR 仅限近讲标准化任务 |
| 面部表情动态 | C6c 视频模型 | 高位远场脸部像素不足，默认不支持 AU；仅保留交互近景采样 |
| 社交交互时序 | C6c 视野内活动 | 只能做弱代理；外出目的地、访客身份、通话对象不可得 |
| 生理指标 | 睡眠仪 | 仅接受接口实际返回字段；HRV 频域、血氧、AHI、体温、血压无证据 |
| 功能活动表现（原"肌力"） | C6c 姿态模型 | 坐站/转身计时与躯干摇摆图像代理；不能声称 COP |

指标可行性、命名规范与三层验证口径的完整修正见[信息采集探索](v1-information-acquisition.md)第 3 节和 REV-030（2026-08-02）。

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
