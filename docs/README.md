# KangShield 文档导航

状态：Active v1.0

更新时间：2026-07-30

本目录按功能域组织导航，文件路径暂保持稳定。每个功能域优先阅读“设计/规程”，再阅读对应“报告/证据”；跨域结论最终回到[里程碑](milestones.md)和[Review 记录](review-log.md)。

## 1. 推荐阅读路径

| 目标 | 阅读顺序 |
|---|---|
| 快速理解项目 | [原始指标](../监测方案.docx) → [工程架构](architecture.md) → [信息侧技术路线](information-side-technical-route.md) → [里程碑](milestones.md) |
| 理解 V1 信息采集 | [信息采集与模型探索](v1-information-acquisition.md) → [设备能力矩阵](device-capability-matrix.md) → 第 3、4 节设计和报告 |
| 理解模型选型 | [公开固定集](v1-m2b-public-dataset-benchmark.md) → 第 5 节姿态/语音/睡眠文档 → [V1-R1 收敛清单](v1-r1-exploration-review.md) |
| 理解跌倒工程链 | [跌倒运动特征](v1-g4-fall-motion-features.md) → [候选事件](v1-g4-fall-event-candidates.md) → [事件评估](v1-g4-event-evaluation-readiness.md) |
| 准备 V2/比赛包 | [V1-R1 收敛清单](v1-r1-exploration-review.md) → [分发就绪门](v1-r1-distribution-readiness.md) → [Runtime Closure](v1-r1-runtime-closure.md) |

## 2. 总览、治理与计划

| 文档 | 功能 |
|---|---|
| [工程架构与模块设计](architecture.md) | V1/V2 边界、M0～M7 模块和公共架构原则 |
| [信息侧详细技术路线](information-side-technical-route.md) | 数据流、契约、命令、证据等级和实现细节 |
| [开发与证据晋级流程](development-workflow.md) | 开发、测试、Review、证据晋级和提交规则 |
| [里程碑与验收门](milestones.md) | 排期、完成状态、验收门和远端发布证据 |
| [Review 记录](review-log.md) | 逐切片发现、决定、验证、行动项和未决问题 |
| [V1-R1 探索收敛与 V2 输入清单](v1-r1-exploration-review.md) | V1 采用/候选/淘汰决定和 V2 硬门 |

项目源材料：

- [监测方案](../监测方案.docx)：七维指标和四类风险的需求锚点。
- [MVP 工程实现与模块 Pipeline 规划](../康盾-MVP工程实现与模块Pipeline规划.md)：早期工程包与批次规划。
- [施工计划草案](../plan.md)：早期模块施工视图；当前状态以本目录里程碑和 Review 为准。

## 3. 设备能力与流采集

| 设计/台账 | 对应报告/证据 | 功能 |
|---|---|---|
| [V1 信息采集与模型探索](v1-information-acquisition.md) | [V1-M1 初步开发报告](reports/v1-m1-initial-development.md) | 指标到采集 Backlog、设备边界和候选模型总览 |
| [设备能力矩阵](device-capability-matrix.md) | [Review 记录](review-log.md) | C6c/SDNL1 每项能力的 E0～E4 状态 |
| [萤石赛事平台使用与资源边界](v1-m1-ezviz-platform-competition-notes.md) | — | 赛事 FAQ/资源说明归档、套餐激活、录像下载与雷达开放边界 |
| [有界音视频流采集适配器](v1-m1-bounded-stream-capture.md) | [有界流采集 E1 报告](reports/v1-m1-bounded-stream-capture-smoke.md) | RTSP/HTTP 有界接收、关键帧、原子 Matroska 和 timing gate |
| [重复开流资格门](v1-m1-stream-qualification.md) | [重复开流 E1 报告](reports/v1-m1-stream-qualification-smoke.md) | 多次独立 open、完整轨道签名和格式稳定性 |
| [受控流故障矩阵](v1-m1-stream-fault-matrix.md) | [故障矩阵 E1 报告](reports/v1-m1-stream-fault-matrix-smoke.md) | delay/503/stall/truncate/reset 的安全识别 |
| [流会话 Supervisor](v1-m1-stream-session-supervisor.md) | [Supervisor E1 报告](reports/v1-m1-stream-session-supervisor-smoke.md) / [媒体时长门加固报告](reports/v1-m1-stream-session-media-duration-gate-smoke.md) | segment/gap/recovery ledger 和 wall/ready-media 双时长门 |

## 4. 多模态回放、时间基与目标样本

| 设计/规程 | 对应报告/证据 | 功能 |
|---|---|---|
| [视频与语言多模态 Pipeline](v1-multimodal-pipeline.md) | [多模态初测报告](reports/v1-m2a-multimodal-smoke.md) / [同容器 PTS 报告](reports/v1-m2a-same-container-audio-smoke.md) | 视频姿态、VAD/ASR、FeatureEvent 和窗口对齐 |
| [容器音视频时间戳探针](v1-m2c-media-timing-probe.md) | [时间戳探针报告](reports/v1-m2c-media-timing-smoke.md) | 轨道、time base、PTS/DTS、offset 和截断检查 |
| [目标设备样本采集规程](v1-m2c-device-sample-protocol.md) | [采集包就绪门报告](reports/v1-m2c-capture-readiness-smoke.md) | C01～C12、同意、双同步事件和 held-out 采集要求 |
| [采集包与 Held-out 就绪门](v1-m2c-capture-readiness-gate.md) | [采集包就绪门报告](reports/v1-m2c-capture-readiness-smoke.md) | manifest、摘要、媒体、场景、标注和真机 readiness |

## 5. 公开数据、模型对比与睡眠字段

| 设计 | 对应报告/证据 | 功能 |
|---|---|---|
| [公开真实场景固定集](v1-m2b-public-dataset-benchmark.md) | [M2b 固定集报告](reports/v1-m2b-public-dataset-benchmark.md) | URFD/FLEURS 固定输入、覆盖率、CER 和可重复评测 |
| [姿态模型对比](v1-m3-pose-model-comparison.md) | [姿态对比报告](reports/v1-m3-pose-model-comparison.md) | YOLO 与 RTMPose 的同集质量/性能对比 |
| [Keypoint R-CNN 独立候选](v1-m3-torchvision-keypointrcnn-candidate.md) | [Keypoint R-CNN 报告](reports/v1-m3-torchvision-keypointrcnn-candidate.md) | 第三姿态 variant、权重血缘和 fallback 结论 |
| [语音模型对比](v1-m3-speech-model-comparison.md) | [语音对比报告](reports/v1-m3-speech-model-comparison.md) | FunASR 与 Whisper 的 CER、静音和性能对比 |
| [睡眠字段路线](v1-m3-sleep-field-route.md) | [睡眠字段报告](reports/v1-m3-sleep-field-route.md) | 无值 profiler、字段映射和 fail-closed route gate |

## 6. 跌倒特征、候选与事件评估

| 设计 | 对应报告/证据 | 功能 |
|---|---|---|
| [跌倒运动特征](v1-g4-fall-motion-features.md) | [运动特征报告](reports/v1-g4-fall-motion-features.md) | 横卧、下降、低运动、关键点质量和 fallback |
| [CAUCAFall ADL 压力集](v1-g4-caucafall-adl-stress.md) | [ADL 压力报告](reports/v1-g4-caucafall-adl-stress.md) | 拾物、坐下、跪地、行走等负样本压力 |
| [Open Images 静态居家压力集](v1-g4-openimages-static-home-stress.md) | [静态压力报告](reports/v1-g4-openimages-static-home-stress.md) | 家具、宠物、多人画面的人物检测压力 |
| [跌倒候选 Episode](v1-g4-fall-event-candidates.md) | [候选公开压力报告](reports/v1-g4-fall-candidate-public-stress.md) | label-blind 状态机、release/refractory 和候选去重 |
| [Capture Fall Feature Producer](v1-g4-fall-feature-capture.md) | [Feature Producer 报告](reports/v1-g4-fall-feature-capture.md) | 真实采集包到姿态/G4 frame feature 的生产接口 |
| [Candidate Export Bridge](v1-g4-candidate-export-bridge.md) | [Export Bridge 报告](reports/v1-g4-candidate-export-bridge.md) | capture-bound feature 到 evaluator prediction |
| [事件标注与评估就绪门](v1-g4-event-evaluation-readiness.md) | [事件评估报告](reports/v1-g4-event-evaluation-smoke.md) | 双标注、裁决、TP/FP/FN、误触发和延迟 |
| [Event Bundle Assembler](v1-g4-event-bundle-assembly.md) | [Bundle Assembly 报告](reports/v1-g4-event-bundle-assembly.md) | 多来源 prediction/标注的 owner-only 原子组装 |

## 7. 运行环境、分发与比赛提交

| 设计/门禁 | 对应报告/证据 | 功能 |
|---|---|---|
| [比赛提交分发就绪门](v1-r1-distribution-readiness.md) | [分发就绪报告](reports/v1-r1-distribution-readiness.md) | 资产 disposition、人工决定、LICENSE/NOTICE/lock |
| [候选 Runtime Closure](v1-r1-runtime-closure.md) | [Runtime Closure 报告](reports/v1-r1-runtime-closure.md) | 直接/传递依赖、extras、来源、隔离和许可证 metadata |
| [开发与证据晋级流程](development-workflow.md) | [Slurm Runtime Preflight 报告](reports/v1-slurm-runtime-preflight.md) | clean commit、提交/执行 SHA、GPU runtime 和 owner-only stdout |

## 8. 文档维护规则

1. 功能设计、契约和规程放在 `docs/`；一次正式运行或评测的证据放在 `docs/reports/`。
2. 新功能至少同步设计文档、正式报告、[Review 记录](review-log.md)和[里程碑](milestones.md)；根 README 只保留高层入口。
3. 每份文档必须在开头声明状态和日期；“Implemented”“Accepted”“Done”必须有对应证据。
4. E1 fixture、E2 导出、E3 live 和 E4 repeatable 的能力结论不得混写。
5. 本索引按功能分类，不改变稳定文件路径；确需移动文件时，应在同一提交中修复全部相对链接并运行链接检查。
