# 康盾里程碑与验收门

状态：Active v0.9

基准日期：2026-07-22

比赛提交目标：2026-09-05

## 1. 状态定义

- Planned：已排期，尚未开始。
- In progress：正在执行。
- Review：产物已完成，等待评审。
- Done：验收门通过。
- Blocked：外部条件阻塞，必须记录责任人与下一次检查时间。

## 2. 总体排期

| 里程碑 | 日期 | 状态 | 主要产物 | 验收门 |
|---|---|---|---|---|
| D0 文档基线 | 07-22～07-24 | Done | 架构、模块、里程碑、Review、采集探索文档 | 三份原始资料与硬件边界没有冲突口径 |
| V1-M1 设备能力探测 | 07-25～07-28 | In progress | 摄像头/睡眠仪能力矩阵、API 样例、原始样本 | 每项能力有真实调用或明确“不开放/待确认”证据 |
| V1-M2a 设备无关多模态链路 | 07-22～07-23 | Done | 视频/语言回放、姿态、VAD/ASR、窗口、Slurm 报告 | 干净提交在 L40 上完成 E1 smoke，warm/cold 口径分离 |
| V1-M2b 公开真实场景固定集与对齐评测 | 07-22～07-23 | Done | URFD/FLEURS 固定集、批量 Pipeline、标签/CER/覆盖率与 Slurm 报告 | 六 case 在干净提交和 L40 上可重复完成，公开数据边界固定为 E1 |
| V1-M2c 目标设备样本与时间基 | 07-22～08-01 | In progress | 容器时间戳探针、采集包/标注/held-out gate、C6c 音视频样本、睡眠样例 | 两个 E1 工具切片已验收；目标设备视频、音频、睡眠样例仍须形成 E2/E3 证据 |
| V1-M3 模型快速对比 | 08-02～08-07 | Done | 姿态、VAD/ASR、睡眠字段的对比报告 | E1 姿态、语音与睡眠路线均可重复并完成采用/候选/放弃决定；真机门仍属 M2c |
| V1-R1 探索 Review | 08-08～08-09 | In progress | V1 结论、淘汰项、G4 离线特征/ADL/静态人物检测压力/事件评估、V2 输入清单 | E1 决策账本、G4 feature/fallback、公开压力与事件 scorer 子门已冻结；真机视频、真实候选/事件指标、许可证和负责人硬门关闭后验收 |
| V2-D1 设计冻结 | 08-10～08-12 | Planned | V2 架构、Schema、测试矩阵、任务分工 | 跌倒主线、平台接入和演示脚本闭合 |
| V2-M1 主链路实现 | 08-13～08-20 | Planned | 真实设备/回放、识别、风险、告警基础链路 | 一次跌倒场景可完整追踪 |
| V2-M2 联合验收 | 08-21～08-28 | Planned | 前端处置、失败降级、指标报告 | 场景矩阵、误报、延迟和处置均有结果 |
| V2-RC 发布候选 | 08-29～09-01 | Planned | 可部署 RC、演示和离线备用方案 | 新环境可复现；阻断问题清零 |
| Final Freeze | 09-02～09-04 | Planned | 最终代码、材料、录屏、交付清单 | 只允许修复阻断问题 |
| 比赛提交 | 09-05 | Planned | V2 最终版 | 完成提交 |

V1 必须在 8 月 9 日结束探索。未完成的候选项默认不进入 V2，不允许无限延长调研。

## 3. 提交与推送证据

| 交付切片 | Commit | 远端分支 | 推送验证 | 范围说明 |
|---|---|---|---|---|
| D0 文档基线 | `214c2f6` | `origin/main` | 2026-07-22 已验证 | 原始资料、架构、技术路线、能力矩阵、里程碑与 Review 基线 |
| V1-M1 初步开发 | `98233f1` | `origin/main` | 2026-07-22 已验证 | 公共契约、运行产物、三类探针、Fixture、测试与初步开发报告；不代表真实设备验收完成 |
| V1-M2a 多模态链路 | `fb39903` / `6f1287f` | `origin/main` | 2026-07-22 已验证 | 视频/语言回放、模型绑定、融合窗口、Slurm 脚本、测试与脱敏报告；不代表真实设备或 V2 模型验收 |
| V1-M2b 公开固定集评测 | `93f7d09` / `e9355e3` | `origin/main` | 2026-07-22 已验证 | 固定 URFD/FLEURS 子集、可重复准备、六 case 标签/CER/覆盖率和 L40 证据；明确只属于 E1 |
| V1-M3 姿态同集对比 / M2c 采集准备 | `0674be9` / `3c1dc32` | `origin/main` | 2026-07-22 已验证 | HumanArt + RTMPose ONNX 链路、L40 同集报告、条件候选决定，以及 C6c/睡眠仪采集规程；不代表 M2c 已取得实机证据 |
| V1-M3 语音同集对比 | `270fdc1` / `271bf94` | `origin/main` | 2026-07-22 已验证 | FunASR 与 Whisper small 的固定六 case、静音、性能和隐私对比；FunASR 保留默认候选，结论只属于 E1 |
| V1-M3 睡眠字段路线 / E1 总 Review | `5635e95` / `ccb8e47` | `origin/main` | 2026-07-22 已验证 | 无值 profiler、fail-closed route gate、正式 E1 报告和 REV-008；V1-M3 仅在 E1 探索范围 Done，不代表 SDNL1 真机字段已取得 |
| V1-R1 E1 决策基线 | `f4aa1c5` / `ea9b837` | `origin/main` | 2026-07-22 已验证 | HumanArt 许可证 fail-closed 修正、采用/候选/放弃账本、V2 七个硬门和 REV-009；V1-R1 仍等待真机与最终分发决定 |
| V1-M2c 容器时间戳 E1 工具 | `4b17b21` / `4a65630` / `c5f2715` | `origin/main` | 2026-07-22 已验证 | PyAV 轨道与逐包 PTS/DTS、required-audio gate、确定性 AVI、正式 E1 报告和 REV-010；不代表 C6c 音频或 G2 已验收 |
| V1-R1 G4 跌倒运动特征 E1 工具 | `782026b` / `3defab6` | `origin/main` | 2026-07-22 已验证 | box-only 时序代理、COCO-17 质量门、fail-closed fallback、双变体正式报告和 REV-011；不代表真实 G4、跌倒判断或告警已验收 |
| V1-R1 G4 CAUCAFall ADL 压力 | `336bbe9` / `97062d5` | `origin/main` | 2026-07-22 已验证 | CC-BY-4.0 固定 12-case、确定性准备/lock、双变体 L40 压力报告和 REV-012；只关闭公开拾物/坐下/跪地/行走子门 |
| V1-M3/G4 Keypoint R-CNN 独立候选 | `eae5f56` / `d956203` / `5ad8053` | `origin/main` | 2026-07-22 已验证 | 三模型 M2b 与 CAUCAFall L40 对比、候选 G4 派生、权重血缘 fail-closed 和 REV-013；保留 fallback，不是最终选型 |
| V1-M2c 采集包就绪门 E1 工具 | `8838168` / `6928ac8` / `542bddf` / `6f1c02a` / `967e585` | `origin/main` | 2026-07-22 已验证 | manifest 1.1、场景/标注、文件/媒体、双同步事件、三模型 held-out 摘要、两级 readiness 与 REV-014；不代表取得真机样本 |
| V1-R1 G4 Open Images 静态人物检测压力 | `40359c1` / `fad9491` / `c77525e` | `origin/main` | 2026-07-22 已验证 | 逐图 CC BY 2.0 / 标注 CC BY 4.0 归因、12-case r2、确定性准备/lock、三模型 L40 与 REV-015；只关闭静态 furniture/pet/multi-person 人物检测子门 |
| V1-R1 G4 双标注/裁决/事件评估 E1 工具 | `b0b2e97` / `5413b46` | `origin/main` | 2026-07-22 已验证 | 12-clip 确定性 bundle、pairwise agreement、adjudication、三 candidate stream TP/FP/FN/误触发/delay、严格 provenance 与 REV-016；不代表真实模型或 C6c 事件性能 |
| V1-R1 G4 Candidate Episode 生成与公开压力 | `dc6cace` / `944e472` | `origin/main` | 2026-07-23 已验证 | held-out 前冻结 label-blind 状态机、54 项三模型公开压力、严格 parent/child provenance、确定性/隐私审计与 REV-017；不代表 C6c 准确率或最终模型选型 |

这里的“推送验证”只证明代码已到达远端。V1-M1 仍为 In progress，必须取得 C6c 与 CS-EP-SDNL1 的 E2/E3 证据后才能进入 Review/Done。V1-M2a 和 V1-M2b 的 Done 只关闭设备无关 E1 链路及公开固定集评测，不会提升真实设备证据等级。V1-M3 的姿态、语言和睡眠字段三个 E1 切片均已验收，因此仅在 E1 探索范围标记 Done；M2c 已有采集规程、容器时间戳工具和采集包 readiness gate，但仍没有真实 C6c 媒体或 SDNL1 字段证据。V1-R1 G4 的离线特征、首版候选状态机、公开压力与双标注/裁决/事件 scorer 也都只属于 E1，不能替代 C6c 正负视频、冻结策略的真实候选/事件指标、床上躺卧、多人 tracking 或跌倒风险/告警验收。

## 4. 当前阶段任务

### D0：文档基线

- [x] 确认采用 V1 探索版、V2 比赛版两阶段。
- [x] 确认当前设备型号。
- [x] 提取《监测方案》七维指标与四风险方向。
- [x] 完成信息侧详细技术路线和设备能力矩阵。
- [ ] 向萤石确认两个设备的开发账号、权限和接口文档。
- [x] 确认 Slurm `hepnodes` 可申请 NVIDIA L40；Python 3.13.13 + Torch 2.13.0+cu130 已完成 smoke。
- [ ] 为模块和里程碑指定负责人。

### V1-M1：设备能力探测

摄像头必须验证：

- 设备授权、在线状态和能力集。
- 直播、回放、抓图、告警消息分别是否可用。
- 服务端能否取得可解码的视频与音频。
- 分辨率、帧率、编码、夜视、时延、断流行为。
- 同一媒体流上的视频与音频时间戳关系。

睡眠仪必须验证：

- 开放平台是否能枚举该设备。
- 可获得的是原始数据、实时事件还是日级报告。
- 每个字段的名称、单位、时间戳、采样周期、缺失值和调用频率。
- 是否实际提供心率、呼吸率、在床/离床、睡眠时长、觉醒、睡眠分期。
- 是否提供 HRV、AHI、血氧；未提供时必须明确标记不可得。

当前开发进度：

- [x] 公共 SourceAsset、Observation、FeatureEvent、RunManifest 契约。
- [x] 运行目录、原子 JSON、JSONL、步骤状态和失败留痕。
- [x] WAV/OpenCV 视频媒体探测。
- [x] 睡眠 JSON/CSV 字段发现与映射候选。
- [x] 萤石 SDK/API 快照脱敏分析。
- [x] E0～E3 证据与输入来源的上限校验。
- [x] Synthetic Fixture 与自动化测试。
- [ ] C6c 真实 E2/E3 证据。
- [ ] CS-EP-SDNL1 真实 E2/E3 证据。

当前实现验证见 [V1-M1 初步开发报告](reports/v1-m1-initial-development.md)。

### V1-M2a：设备无关多模态链路

- [x] OpenCV 时间戳视频回放与 16 kHz PCM WAV 语言回放。
- [x] YOLO26n-pose + ByteTrack 结构化姿态基线。
- [x] FunASR FSMN-VAD + Paraformer + CT-Punc 中文语言基线。
- [x] ModelBinding、敏感 FeatureEvent 与 MultimodalWindow。
- [x] 权重 SHA-256、许可证、环境、峰值显存与性能口径。
- [x] Slurm 离线模型缓存与代理隔离。
- [x] 18 项自动化测试和干净提交 L40 smoke。

证据见 [V1-M2a 多模态 Pipeline 初测报告](reports/v1-m2a-multimodal-smoke.md)。V1-M2b 先把公开真实人物录制扩展成固定评测集；C6c 音视频时间基和受控居家样本仍由 V1-M2c 验收，不允许用公开数据代替。

### V1-M2b：公开真实场景固定集与对齐评测

- [x] 固定 URFD 3 段模拟跌倒、3 段 ADL camera 0 RGB 与帧级标签。
- [x] 固定 FLEURS 普通话 3 女、3 男 dev 语音及参考转写。
- [x] 下载 URL/revision、大小、SHA-256 和许可证清单。
- [x] URFD PNG/CSV 到恒帧率 replay 与逐帧 sidecar。
- [x] FLEURS float WAV 到 16 kHz 单声道 PCM16。
- [x] 六 case 批量调度、独立 child run、CER、阶段与覆盖率汇总。
- [x] 跨数据集 `synthetic_common_zero` 与 E1 证据约束。
- [x] 干净提交的 L40 六 case benchmark 与 Review 报告。

设计和口径见 [V1-M2b 公开真实场景固定集与对齐评测](v1-m2b-public-dataset-benchmark.md)，实测证据见 [初测报告](reports/v1-m2b-public-dataset-benchmark.md)。job `1759` 在 NVIDIA L40 上完成，姿态帧覆盖率 89.41%、跟踪覆盖率 97.37%、corpus CER 6.57%；本门不会把公开数据晋级为 C6c/CS-EP-SDNL1 证据。

### V1-M2c：目标设备样本与时间基

- [x] 冻结 C6c 白天/夜视、距离、遮挡、日常动作、横卧与空场采集规程和 manifest 模板。
- [x] 实现 PyAV 容器轨道、逐包 PTS/DTS、required audio 和扫描截断的 fail-closed 探针。
- [x] 在干净提交 `4a65630` 上完成确定性同容器音视频 E1 正式运行与隐私审计。
- [x] 冻结 manifest 1.1、C01～C12 场景/动作标签、三姿态 held-out 策略和两级 readiness policy。
- [x] 实现包内路径/摘要、媒体探针、双同步事件、fixture marker、重复媒体和隐私安全报告 gate。
- [x] 在干净提交 `6f1c02a` 上完成 10 场景 E1 正式运行：结构 10/10，最终决定 `tooling_only`，四个真机门均为 false。
- [ ] 录制有明确同意的 C6c 正常行走、起坐、模拟跌倒、遮挡/夜视样本。
- [ ] 证明 C6c 视频与音频是否同容器，并保存 PTS/时钟偏差。
- [ ] 获取 CS-EP-SDNL1 真实 API/SDK/导出样例和字段时间语义。
- [ ] 使用 M2b 相同契约形成 E2/E3 运行证据。

采集规程见 [V1-M2c 目标设备样本与时间基](v1-m2c-device-sample-protocol.md)。E1 工具与证据包括[容器时间戳探针](v1-m2c-media-timing-probe.md)、[采集包就绪门](v1-m2c-capture-readiness-gate.md)及各自[时间戳报告](reports/v1-m2c-media-timing-smoke.md)、[readiness 报告](reports/v1-m2c-capture-readiness-smoke.md)。工具完成不提升设备证据等级；真实样本和接口响应仍未到位，因此 M2c 只能处于 In progress。

### V1-M3：模型对比

当前姿态切片：

- [x] 冻结 YOLO26n-pose 与 YOLOX-m HumanArt + RTMPose-m HumanArt 两个 variant。
- [x] 固定模型 URL、ZIP/ONNX SHA-256、输入尺寸与许可证记录。
- [x] 实现不依赖 MMCV 的 ONNXRuntime 后端、短时 IoU ID 和视频-only 对比契约。
- [x] 复用 M2b 六段视频、170 个抽帧和阶段标签，不重复运行 ASR。
- [x] CPU 开发预检验证完整报告；该 dirty run 不作为正式里程碑证据。
- [x] 在干净提交 `0674be9` 上完成 L40 双 variant 对比（job `1760`）。
- [x] Review 横卧覆盖、fall-01 关键点质量和性能；候选有条件进入 V2，许可证门仍 Open。
- [x] 冻结并接入 TorchVision Keypoint R-CNN 独立候选，不针对固定集调参。
- [x] 在 job `1763` / `1764` 完成三模型 M2b 与 CAUCAFall E1 回放，并从干净 child events 派生候选 G4 特征。
- [x] Review 候选 lying gate 4/21、ADL 几何混淆和 COCO/ImageNet 权重血缘；决定仅保留 fallback，不替换 RTMPose 条件参考。

设计见 [V1-M3 姿态模型对比](v1-m3-pose-model-comparison.md)，历史双模型证据见 [同集对比报告](reports/v1-m3-pose-model-comparison.md)。REV-013 的独立候选设计与三模型结果见 [Keypoint R-CNN 设计](v1-m3-torchvision-keypointrcnn-candidate.md)和[正式报告](reports/v1-m3-torchvision-keypointrcnn-candidate.md)。姿态 E1 探索有了 fallback 结论，但最终比赛模型仍等待真机和分发门。

当前语言切片：

- [x] 冻结 FunASR baseline 与 OpenAI Whisper small candidate、权重摘要和许可证。
- [x] 固定 `zh/transcribe`、beam 5、temperature 0 和现有字符归一化/CER 口径。
- [x] 实现 audio-only 双 variant、privacy-safe case/aggregate 契约和 2 秒全零静音探针。
- [x] 完成 35 项自动化测试、全部权重离线校验及两个 variant 各自六 case + 静音 CPU 开发预检；baseline 复现 `9/137`。
- [x] 在干净提交 `270fdc1` 的 L40 上复现 FunASR `9/137` 并完成 Whisper 六 case 正式对比（job `1761`）。
- [x] Review CER、静音、性能和真实设备缺口；FunASR 保留默认候选，Whisper small 不晋级普通话主链路。

语言切片设计见 [V1-M3 语音模型同集对比](v1-m3-speech-model-comparison.md)，正式证据见 [同集对比报告](reports/v1-m3-speech-model-comparison.md)。语言切片已通过 Review；后续 REV-008 已关闭睡眠字段路线。

当前睡眠字段路线：

- [x] 按《监测方案》冻结 19 个 direct-if-exposed、5 组 multi-night derived 和 11 个 not-assumed 字段。
- [x] 实现无值 SleepProfile v0.2、mapping evidence/语义 gate、SleepRouteAssessment 严格契约与 CLI。
- [x] fixture、伪 confirmed E1 拒绝、E2 单字段解锁和监测方案摘要漂移均有自动化测试；全套 40 passed。
- [x] 在干净提交 `5635e95` 上生成 E1 路线报告，审计身份/数值不落报告并完成 Review。

本切片只决定“不训练睡眠模型、保留字段接口和派生前置条件”，不会替代 V1-M2c 的真实 SDNL1 API/SDK/导出证据。设计见 [V1-M3 睡眠字段路线](v1-m3-sleep-field-route.md)，正式证据见[睡眠字段路线评审报告](reports/v1-m3-sleep-field-route.md)。姿态、语言与睡眠三个 E1 切片均已 Review，V1-M3 在 E1 探索范围标记 Done。

每个候选模型必须记录：

- 模型及权重版本、许可证、输入尺寸。
- CPU/GPU、运行环境、FPS 或实时系数、峰值显存。
- 输出字段、质量分数、失败条件。
- 固定样本上的可视化和错误案例。
- 是否晋级 V2，以及晋级理由。

### V1-R1：探索收敛

- [x] 汇总 V1-M1～M3 的证据等级、可复现指标和未证明边界。
- [x] 对工程链路、模型和《监测方案》特征逐项标记 Adopt、Conditional、Blocked、Reject-primary、Defer 或 Exclude。
- [x] 明确 YOLO26n、HumanArt + RTMPose、FunASR、Whisper 和睡眠路线的当前决定。
- [x] 复核框架、模型权重、训练数据与公开评测数据的许可证边界；在 `f4aa1c5` 纠正 HumanArt ModelBinding 的 Apache-only 过宽标记。
- [x] 形成 V2-D1 可直接采用输入、七个硬门和不等待真机的开发顺序。
- [x] 在干净提交 `782026b` 上完成 G4 box-only、COCO-17 关键点质量门、同 track 时间特征和 fallback reason 的双变体 E1 正式运行；硬约束不输出风险或告警。
- [x] 在干净提交 `336bbe9` 上完成 CAUCAFall 12 段 ADL、三档光照、双变体 E1 压力运行；确认 RTMPose 在 no-fall ADL 中有 17 个 horizontal box-only 帧，单一框比例不得触发告警。
- [x] 在干净提交 `eae5f56` 上完成 Keypoint R-CNN 三模型复跑；确认 no-fall ADL 中“关键点门通过 + torso-horizontal”也会激活，不得直接触发告警。
- [x] 完成一个不依赖 HumanArt 的公开权重候选评测；因 lying gate 4/21 和 COCO/ImageNet 分发仍 Open，只保留 fallback。
- [x] 在干净修正提交 `fad9491` / job `1766` 上完成 Open Images r2 静态家具无人、宠物无人和室内多人三模型压力；首轮标注异常 run 被拒绝，正式结果保持无风险/告警。
- [x] 在干净提交 `b0b2e97` 上完成双人 interval/onset agreement、裁决、三 candidate stream TP/FP/FN、误触发/小时与 delay 的 E1 正式工具运行；fixture 指标不用于模型比较。
- [x] 在查看未来 C6c held-out 输出前冻结首版 label-blind candidate episode 状态机；在干净提交 `dc6cace` 上复用 URFD/CAUCAFall 三路 G4 特征完成 54 项 E1 公开压力，结果如实保留 YOLO/RTMPose 漏候选与 RTMPose 行走负候选。
- [x] 将 capture-bound `FallFeatureCaptureSet`、公共 event prediction、strict source provenance 和 `export-fall-candidates` 接到 REV-016 scorer；三路 rule-bearing E1 fixture 已验证真实状态机到 evaluator 的接口，未使用模型推理。
- [ ] 使用 C6c 正负视频继续补空场持续、床上躺卧、宠物移动和真实多人 tracking，按已冻结 policy 生成真实候选并复用事件评估口径。
- [ ] 用 E2/E3 证据把 C6c 与 SDNL1 从 Unknown 归类为 available、limited 或 blocked。
- [ ] 决定 V2 最终姿态权重和项目分发许可证，生成第三方 NOTICE；HumanArt 与 Keypoint R-CNN 均未关闭该门。
- [ ] 为硬门指定负责人和截止日期，并删除无法完成的 V2 能力声明。

预 Review 见 [V1-R1 探索收敛与 V2 输入清单](v1-r1-exploration-review.md)。G4 基础设计与证据见[跌倒运动特征设计](v1-g4-fall-motion-features.md)和[正式报告](reports/v1-g4-fall-motion-features.md)，扩展 ADL 子门见 [CAUCAFall 设计](v1-g4-caucafall-adl-stress.md)和[压力报告](reports/v1-g4-caucafall-adl-stress.md)，静态人物检测子门见 [Open Images 设计](v1-g4-openimages-static-home-stress.md)与[正式报告](reports/v1-g4-openimages-static-home-stress.md)，候选生成子门见[episode 设计](v1-g4-fall-event-candidates.md)与[公开压力报告](reports/v1-g4-fall-candidate-public-stress.md)，生产桥接见 [Capture Feature 到 Candidate 导出](v1-g4-candidate-export-bridge.md)，事件工具子门见[事件评估设计](v1-g4-event-evaluation-readiness.md)与[初测报告](reports/v1-g4-event-evaluation-smoke.md)。E1 工具与公开压力集完成不等于 V1-R1 Done；真机视频、真实候选/事件指标、床上躺卧/时序多人、最终姿态分发路线和责任人仍是验收门。

## 5. 里程碑决策优先级

1. 真实设备能否拿到数据。
2. 数据质量是否足以支持指标。
3. 模型输出是否稳定、可解释、可复现。
4. 是否能支撑跌倒主线。
5. 最后才考虑诈骗、认知和抑郁趋势增强。

任何“看起来有价值但无法在固定样本上复现”的能力，不进入 V2 主路径。
