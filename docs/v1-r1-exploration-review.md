# V1-R1 探索收敛与 V2 输入清单

状态：In progress；E1 决策基线已冻结，E2/E3 真机门仍 Open

基准日期：2026-07-22

证据快照：截至 `f5bb761` 的 V1-M1～V1-M3 报告，以及许可证 fail-closed 修正 `f4aa1c5`

## 1. Review 目标与状态语义

V1-R1 不再继续无边界地增加模型。它把现有探索结果收敛为可执行决定，并回答三件事：

1. 哪些工程能力直接进入 V2-D1 架构基线。
2. 哪些模型/字段只作为有条件候选，必须先通过什么门。
3. 哪些路线淘汰、延期或明确不属于比赛主线。

本文件使用以下状态：

| 状态 | 含义 |
|---|---|
| Adopt | 进入 V2-D1 设计基线；不等于真机或准确率已验收 |
| Conditional | 允许进入下一轮冻结比较，但不能写成 V2 最终能力 |
| Blocked | 路线必要，但缺少外部权限、设备或真实证据 |
| Reject-primary | 不进入当前主链路；实现可保留作可复现实验 |
| Defer | 当前比赛主线不做，只有新增明确需求和证据才重开 |
| Exclude | 当前设备和证据不支持，禁止出现在“已实现”清单 |

## 2. 当前证据总览

| 切片 | 最高证据 | Review 结果 | 仍未证明 |
|---|---|---|---|
| V1-M1 采集骨架 | E1 fixture | 契约、运行目录、媒体/睡眠/萤石快照探针可用 | 两台目标设备任何真实开发能力 |
| V1-M2a 多模态链路 | E1 public/synthetic | 视频、音频、姿态、VAD/ASR、窗口和报告链路可重复 | 自然音视频同步、C6c 取流和端到端直播延迟 |
| V1-M2b 固定集 | E1 public | 6 case、170 视频帧、137 参考字符的批量评测可重复 | 目标机位精度、人物负样本误报和自然跨模态对齐 |
| V1-M3 姿态 | E1 public | HumanArt + RTMPose 为准确率有条件候选 | C6c 场景、困难横卧关键点、许可证/分发终审 |
| V1-M3 语音 | E1 public | FunASR 保留普通话候选；Whisper small 不晋级主链路 | C6c 远场、方言、电视/噪声和人工 VAD 指标 |
| V1-M3 睡眠 | E1 fixture | 不选模型；采用无值 profiler + fail-closed route gate | SDNL1 真实字段、单位、时间、缺失与准确率 |

## 3. 工程与数据路线决策账本

| ID | 对象 | 决定 | 依据 | V2 约束 |
|---|---|---|---|---|
| R1-D01 | SourceAsset / Observation / FeatureEvent / RunManifest | Adopt | 40 项自动化测试和四个 V1 阶段均复用 | V2 可扩展但不能绕过 evidence、quality、limitations |
| R1-D02 | 一次运行一个目录、原子 JSON/JSONL、摘要绑定 | Adopt | 本地与 Slurm 运行均可反查代码、输入和步骤 | V2 数据库化后仍保留同等 manifest/provenance |
| R1-D03 | 文件回放 + 固定公开集 | Adopt as regression only | 可重复、可离线演示和定位回归 | 不能作为目标设备或自然同步证据 |
| R1-D04 | 独立视频/WAV 共享零时刻 | Reject as real synchronization | M2a/M2b 是构造公共零点 | 只保留测试 harness；真机必须使用容器 PTS 或显式 offset/drift |
| R1-D05 | C6c 视频/音频采集适配器 | Blocked but required | 当前设备最高只有 E0 | 取得 E2 媒体和 E3 能力调用前不声明实时接入 |
| R1-D06 | CS-EP-SDNL1 adapter | Blocked / interface only | 商品与通用服务没有证明目标 schema | 仅通过 SleepRouteAssessment 的字段可进入 adapter |
| R1-D07 | 睡眠无值 profiler + fail-closed gate | Adopt | E1 伪 confirmed 也无法解锁；报告不落数值 | V2 字段 adapter 的强制前置门 |
| R1-D08 | E0～E4 证据、脱敏和受控媒体引用 | Adopt | 多轮隐私扫描未发现报告级密钥、身份、全文或健康值泄漏 | 真机数据仍须独立完成同意、留存和访问审计 |

## 4. 模型与提取器决策账本

| ID | 模型/路线 | 决定 | 当前证据 | 解锁或重开条件 |
|---|---|---|---|---|
| R1-M01 | YOLO26n-pose + ByteTrack | Reject-primary；保留 V1 对照 | lying 9/21 = 42.86%；Ultralytics 为 AGPL-3.0/Enterprise 路线 | 只有项目选择完整 AGPL 开源或取得 Enterprise，且 C6c held-out 反超候选才重开 |
| R1-M02 | YOLOX-m HumanArt + RTMPose-m HumanArt | Conditional accuracy candidate | overall 163/170 = 95.88%；lying 20/21 = 95.24%；RTF 0.123668 | C6c 场景门、fall-01 质量门、负样本门和 Human-Art 权重/训练数据分发门全部通过 |
| R1-M03 | box-only 横卧/下降/静止 + keypoint quality gate | Conditional design input | fall-01 有框但 `>=0.5` 关键点可见率为 0 | 先在 E1 固定集实现离线特征实验，再在 C6c 弯腰/躺床/跌倒负正样本冻结阈值 |
| R1-M04 | FunASR FSMN-VAD + SeACo Paraformer + CT-Punc | Conditional default Mandarin candidate | 9/137，CER 6.57%，静音通过，推理 RTF 0.037648 | C6c 远场/噪声/老人或年龄相近说话人、人工 VAD 和许可证打包门 |
| R1-M05 | OpenAI Whisper small | Reject-primary；保留实验 adapter | 32/137，CER 23.36%，6/6 case 编辑数更差 | 仅在新的方言、多语种或噪声 held-out 集上重开 |
| R1-M06 | 睡眠分期/生命体征模型 | Reject | 当前问题是设备字段是否开放，不是缺少推理模型 | 先取得 E2/E3 schema；不得从雷达参数猜字段或训练目标 |
| R1-M07 | MediaPipe、openSMILE、Face/OpenFace、YAMNet | Defer | 尚无固定任务、标签和 V2 P0 价值证据 | 只有跌倒主线闭合后仍有明确演示需求、数据和验收指标才立项 |

`Conditional` 表示候选进入 V2-D1 的比较接口，不表示模型名称可以直接写进最终比赛能力说明。

## 5. 《监测方案》特征范围收敛

| 监测能力 | V1-R1 状态 | V2 处理 |
|---|---|---|
| 人体框、COCO-17 姿态、短时轨迹 | Conditional | 服务跌倒 P0；必须携带关键点质量和 fallback 原因 |
| 跌倒事件 | Conditional design only | V1 尚未实现 RiskAssessment；V2 先做可解释时序特征和人工确认闭环 |
| 普通话 VAD/ASR | Conditional | 作为交互/证据增强，不从转写直接诊断或自动判诈骗 |
| 睡眠/心率/呼吸/在离床等 direct fields | Blocked per field | 仅接入 route gate 达到 `ready_for_adapter` 的字段 |
| 睡眠趋势、早醒、WASO、IV/IS、RA/M10/L5 | Defer until coverage | 至少多夜/连续 24h 覆盖、时区、缺失和个人基线通过后再设计 |
| RR interval、HRV、SpO2、AHI、体温、血压、原始雷达 | Exclude | 当前设备无证据，禁止在 V2 已实现清单中出现 |
| 诈骗、认知、抑郁风险 | Defer / non-diagnostic | 比赛主线不做自动评分；最多保留人工查看的原始特征证据 |
| 面部表情、社交时序、COP/真实肌力 | Defer / proxy only | 当前单摄像头只能做弱代理，不写成临床或物理测量 |

## 6. 许可证与分发 Review

### 6.1 当前结论

1. 仓库目前没有顶层项目 LICENSE，也没有最终第三方 NOTICE/模型清单。V2-RC 前必须由项目方决定比赛仓库的公开与分发方式；本 Review 不替项目方选择许可证。
2. [Ultralytics 官方说明](https://docs.ultralytics.com/help/contributing)将其代码和模型置于 AGPL-3.0 或 Enterprise 路线。当前项目没有完成对应选择，所以 YOLO 不能作为默认提交模型。
3. [MMPose 实现](https://github.com/open-mmlab/mmpose)为 Apache-2.0，但这只覆盖实现。[Human-Art 官方仓库](https://github.com/IDEA-Research/HumanArt)要求先获授权并用于非商业目的，其 annotations license 为 CC-BY-NC-SA-4.0；因此历史 ModelBinding 直接写 `Apache-2.0` 过宽。提交 `f4aa1c5` 已改为 `model-artifact-license-review-required`，最终比赛权重分发继续阻断。
4. 当前三个 FunASR 冻结 snapshot 的精确模型卡均写明 Apache License 2.0；权重仍以 SHA-256 固定，因为 `master` 不是版本。V2 打包必须保存模型卡/许可证副本与 attribution，不只记录框架许可证。
5. [OpenAI Whisper 官方仓库](https://github.com/openai/whisper)明确代码和模型权重均为 MIT；它的淘汰原因是当前普通话准确率，不是许可证。
6. URFD/FLEURS 只作为 E1 回归输入；默认不进入比赛提交包、演示媒体或训练资产。任何再分发必须另做署名、非商业/相同方式共享和比赛规则审查。

### 6.2 冻结的 FunASR 模型卡证据

| 模型 | Model card SHA-256 | 卡片声明 |
|---|---|---|
| SeACo Paraformer | `c92fa06ad63cc9962b9515eb23872f8ed8052fecb4f2df90ec7d0cdbaf916b9f` | Apache License 2.0 |
| FSMN-VAD | `42377011603a186fc2bae41a5cc5e548ebf98d8ec307bbae9dd405f82567f543` | Apache License 2.0 |
| CT-Punc | `d1f2f3c30db716fb995208608d4305b045f6ef7b7b46a84e7e2d200160df50e0` | Apache License 2.0 |

这些是 2026-07-22 下载的冻结卡片摘要；模型权重摘要见 `configs/v1-m3-speech-models.json`。后续上游卡片变化必须触发 Review，不能静默覆盖。

## 7. V2-D1 可直接采用的输入

| 输入 | 冻结内容 | 来源 |
|---|---|---|
| 证据与运行契约 | E0～E4、SourceAsset、Observation、FeatureEvent、RunManifest | V1-M1/M2a |
| 离线回放与评测边界 | PoseBackend、SpeechBackend、固定 case、隐私安全汇总 | V1-M2b/M3 |
| 姿态候选配置 | 5 fps、RTMPose detector conf 0.05、COCO-17、质量阈值报告 | REV-006 |
| 语言候选配置 | 16 kHz、FunASR 三模型摘要、CER/静音/RTF 口径 | REV-007 |
| 睡眠字段边界 | 19 direct、5 derived、11 not-assumed、fail-closed mapping | REV-008 |
| 真机场景矩阵 | 白天/夜视、距离、遮挡、空场、弯腰、躺床和安全模拟跌倒 | V1-M2c 规程 |
| 隐私边界 | 原始媒体/健康值不入 Git，汇总不含全文、密钥、序列号和姓名 | development workflow |

## 8. V2 冻结前的硬门

| Gate | 必须取得的证据 | 失败时的降级 |
|---|---|---|
| G1 C6c 能力 | 脱敏能力集、直播/回放/抓图调用和一段原始媒体 | 演示只允许受控文件回放，不声称实时萤石接入 |
| G2 音视频时间基 | 容器 track、time_base、首尾 PTS、offset/drift | 视频与语言分开演示，不做自然融合结论 |
| G3 C6c 模型复测 | 至少 8 个必做场景，两个姿态 variant、空场误报和远场 ASR | 保留 E1 离线 demo，模型仍为 conditional |
| G4 跌倒特征 | box-only fallback、关键点质量门、横卧持续与 ADL 负样本 | 不生成自动风险，只展示姿态/轨迹原始特征 |
| G5 模型/项目许可证 | 项目 LICENSE、第三方 NOTICE、最终权重使用与分发决定 | 排除未清门模型和数据；不得临近提交时口头豁免 |
| G6 SDNL1 字段 | 至少一晚 E2 schema，或可复核的权限/不开放证据 | 保留接口和 blocked 状态，不展示合成健康值 |
| G7 数据治理 | 同意、受控存储、留存期、访问人和删除流程 | 不使用真实人物/健康数据 |

## 9. 不等待真机的下一开发顺序

1. 实现 ffprobe/PyAV 容器与逐轨时间基探针，补上当前 OpenCV 无法确认音轨和 PTS 的缺口。
2. 定义并实现仅离线输出的跌倒特征层：box 横卧、中心下降、持续/静止、关键点质量门与 fallback reason；暂不输出 RiskAssessment。
3. 在现有 URFD 固定集加入上述特征，并补人物不存在/ADL 负样本数据来源后冻结误触发口径。
4. 评测一个许可证更清晰、非 Human-Art 训练的姿态候选，避免 V2 只剩两个都带分发硬门的选择。
5. 形成项目 LICENSE/THIRD_PARTY_NOTICES 决策草案；最终许可证由项目方确认。

## 10. V1-R1 完成门

本文件完成 E1 预 Review，但 V1-R1 里程碑保持 In progress。满足以下条件后才能标记 Done：

1. C6c 与 SDNL1 分别被真实证据归类为 available、limited 或 blocked，而不是 Unknown。
2. V2 姿态默认候选同时通过目标设备、负样本和分发 Review。
3. FunASR 在 C6c 远场/噪声集完成 CER 与人工 VAD 评测，或降级为离线可选能力。
4. 每个硬门有负责人和截止日期；无法完成的能力已从 V2 已实现清单删除。
5. V2-D1 明确主路径、离线 fallback 和比赛演示声明三者的边界。
