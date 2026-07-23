# V1-R1 探索收敛与 V2 输入清单

状态：In progress；E1 决策基线已冻结，E2/E3 真机门仍 Open

基准日期：2026-07-23

证据快照：截至 `f5bb761` 的 V1-M1～V1-M3 报告、许可证 fail-closed 修正 `f4aa1c5`、G4 离线特征实现 `782026b`、CAUCAFall ADL 压力实现 `336bbe9`、Keypoint R-CNN 候选实现 `eae5f56` / G4 派生接入 `d956203`、Open Images 静态人物检测实现 `40359c1` / 标注审计修正 `fad9491`、双标注/裁决/事件评估工具 `b0b2e97`、首版 candidate episode 生成器 `dc6cace`、capture producer `7a8dc23` / tracker 修复与加固 `b233abe` / `b4b72f7`、event bundle assembler `7b64719`，同容器音轨 adapter `8c6df2d` / bitexact smoke `eca6231` / 路径脱敏 `195c966`、owner-only artifact 修复 `d1d4b5a` / `8b4b52d`，正式 Slurm runtime/submit 契约 `673560d` / `667ad8d` / `b54d8b8`、比赛提交分发就绪门 `6c32364`、候选 runtime closure `876ce07`、有界流采集 adapter `8cbd91f`、重复开流资格门 `fea40f7` / 轨道签名加固 `c8bda16`，以及受控流故障矩阵 `4e637a1`

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
| V1-M1 采集骨架 | E1 fixture/HTTP | 契约、运行目录、媒体/睡眠/萤石快照探针、有界采集与三次独立开流格式 gate 可用；raw 均 owner-only | 两台目标设备任何真实开发能力、C6c RTSP/鉴权/非自愿重连/长稳 |
| V1-M2a 多模态链路 | E1 public/synthetic | 独立 WAV harness 与同容器 PTS/16 kHz/VAD-ASR/窗口链路均可重复；owner-only L40 jobs `1777` / `1782` 已通过 | 自然 capture clock、C6c 取流和端到端直播延迟 |
| V1-M2b 固定集 | E1 public | 6 case、170 视频帧、137 参考字符的批量评测可重复 | 目标机位精度、人物负样本误报和自然跨模态对齐 |
| V1-M3 姿态 | E1 public | HumanArt + RTMPose 为准确率条件参考；Keypoint R-CNN 仅保留 fallback | C6c 场景、困难横卧关键点、两条权重路线的许可证/分发终审 |
| V1-M3 语音 | E1 public | FunASR 保留普通话候选；Whisper small 不晋级主链路 | C6c 远场、方言、电视/噪声和人工 VAD 指标 |
| V1-M3 睡眠 | E1 fixture | 不选模型；采用无值 profiler + fail-closed route gate | SDNL1 真实字段、单位、时间、缺失与准确率 |
| V1-R1 G4 跌倒运动/候选/事件评估 | E1 public/fixture | box/keypoint 时序特征、label-blind candidate episode、公开压力与双标注/裁决/event scorer 均可重复；job `1776` 三姿态 producer 到 clean owner-only scorer 全链已通过；不生成风险/告警 | C6c 正负视频、空场持续、床上躺卧、宠物移动、多人 tracking、冻结策略的目标域候选与真实事件指标 |
| V1-R1 G5 发布工程 | E1 repository/runtime | 分发门 0/5 正确阻断；runtime closure 工具完成且共享环境 3/8 ready | 最终模型/打包/项目许可证、隔离运行环境、competition lock、NOTICE 与 owner 签字 |

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
| R1-D09 | 双人标注、裁决与外部 candidate event evaluator | Adopt as tooling contract | REV-016 已验证 interval/onset agreement、held-out provenance、TP/FP/FN、误触发/小时与 delay，fixture 永远不能开真实门 | 真实 C6c 必须先冻结裁决与 candidate policy；`event_metrics_ready_for_review` 不授权 Risk/Alert |
| R1-D10 | Label-blind fall candidate episode 状态机 | Conditional implementation baseline | REV-017 在查看 C6c held-out 输出前冻结 transition/settled、回溯、release、refractory 与 track/gap reset；54 项公开开发压力可重复 | C6c 首轮必须原样使用 policy；公开数据上的 0/3、1/3、3/3 不用于最终选型或准确率宣传 |
| R1-D11 | 同容器音轨 PTS → 16 kHz SpeechBackend adapter | Adopt as offline adapter seam | +250 ms bitexact E1 A/V 上完成真实 YOLO/FunASR、事件平移、单来源 ledger 与 fail-closed timing gate | 真实录制必须保留容器 PTS；单一 start offset 不表达 drift，也不证明平台开放音轨 |
| R1-D12 | V1 run artifact owner-only 权限 | Adopt | `d1d4b5a` 将 run/子目录固定为 `0700`、JSON/JSONL 与两条正式 Slurm stdout 固定为 `0600`；`8b4b52d` 继续将 `--runs-dir` 根固定为 `0700`；权限漂移的早期 run 被拒绝并用新路径重跑 | V2 对象存储/数据库必须提供同等或更强的访问控制、审计与留存，不得依赖宿主默认 umask |
| R1-D13 | 正式 Slurm 提交与运行时契约 | Adopt | 全部正式入口复用 `slurm-runtime-v0.2.0`；统一提交器要求 clean checkout、冻结完整 submit commit，计算节点复核 execution commit、实际 import、owner-only stdout/runs 与所需 CUDA 动态库 | V2 批处理或部署系统必须保留不可变版本绑定和 fail-closed runtime preflight；裸 `sbatch` 不构成正式证据 |
| R1-D14 | 比赛提交分发就绪门 | Adopt as release-gate tooling | `6c32364` 将 7 个事实来源、13 项资产、5 项 owner decision、3 个发布文件和 5 个 gate 冻结为 `distribution-readiness-v0.1.0`；正向/故障测试均通过，当前报告正确保持 0/5 ready | V2-RC 必须在最终 profile 上以 `--require-ready` 通过；工程工具不选择许可证、不提供法律意见，也不允许 excluded 资产静默进入提交包 |
| R1-D15 | 候选 Python runtime closure 门 | Adopt as pre-lock tooling | `876ce07` 冻结候选 RTMPose + FunASR profile，并从脱敏 `pip inspect` 传播 extras/marker、检查八门；共享环境仅 3/8 ready | 只有独立、非 editable、无 `PYTHONPATH` 的最终候选环境八门通过后，才能生成 lock/NOTICE 草案；更换模型/平台必须新 profile |
| R1-D16 | 有界网络音视频流采集接缝 | Adopt as E1 adapter seam | `8cbd91f` 以环境端点、首视频关键帧、timeout/时长/packet 上限和 owner-only 原子 Matroska 完成 loopback HTTP E1；job `1782` 用同一 artifact SHA-256 完成真实姿态/语言 Pipeline | C6c 必须另做 RTSP/鉴权/音轨、长稳/重连、丢包抖动与双同步事件 E2/E3；单次 clip 不代表平台接入 |
| R1-D17 | 重复开流资格门 | Adopt as E1 pre-capture gate | `fea40f7` / `c8bda16` 将多次独立 open、固定失败码、父/子 ledger 和 codec/time-base/视频尺寸帧率/音频采样率声道签名冻结；3/3 HTTP E1 ready | C6c 短 E2 可复用，但 scheduled reopen 不代表非自愿断线恢复、长稳或网络损伤容忍；每个 raw 仍受同意/留存约束 |
| R1-D18 | 受控流故障识别矩阵 | Adopt as E1 adapter safety gate | `4e637a1` 固定完整/分块延迟/503/双 stall/截断/reset 七场景、实际 server 遥测、有界状态和严格父 gate；7/7 E1 执行且 0 unexpected ready | 只证明 loopback HTTP 安全识别；RTSP、packet loss、packet-level jitter、恢复、容忍、长稳和 C6c 都须另做 E2/E3 |

## 4. 模型与提取器决策账本

| ID | 模型/路线 | 决定 | 当前证据 | 解锁或重开条件 |
|---|---|---|---|---|
| R1-M01 | YOLO26n-pose + ByteTrack | Reject-primary；保留 V1 对照 | lying 9/21 = 42.86%；Open Images static 为 3/8 无人激活、9/11 多人 matched；Ultralytics 为 AGPL-3.0/Enterprise 路线 | 只有项目选择完整 AGPL 开源或取得 Enterprise，且 C6c held-out 反超候选才重开 |
| R1-M02 | YOLOX-m HumanArt + RTMPose-m HumanArt | Conditional accuracy candidate | URFD overall 163/170 = 95.88%、lying 20/21；CAUCAFall person-box 602/661 = 91.07%；Open Images static 为 2/8 无人激活、11/11 多人 matched，但低阈值仍产生 5 个 overall FP | C6c 场景/视频负样本门、fall-01 质量门和 Human-Art 权重/训练数据分发门全部通过 |
| R1-M03 | box-only 横卧/下降/静止 + keypoint quality gate + candidate episode | Conditional implementation input | REV-017 冻结首版组合状态机；公开开发压力中 YOLO/RTMPose/Keypoint R-CNN fall 激活分别为 0/3、1/3、3/3，RTMPose 另有 1 个行走负候选，证明结果强依赖上游 variant | 在 C6c 跌倒正负、空场持续、躺床、宠物移动和多人 held-out 集上原样评测已冻结 policy，再生成裁决后的真实事件指标 |
| R1-M04 | FunASR FSMN-VAD + SeACo Paraformer + CT-Punc | Conditional default Mandarin candidate | 9/137，CER 6.57%，静音通过，推理 RTF 0.037648 | C6c 远场/噪声/老人或年龄相近说话人、人工 VAD 和许可证打包门 |
| R1-M05 | OpenAI Whisper small | Reject-primary；保留实验 adapter | 32/137，CER 23.36%，6/6 case 编辑数更差 | 仅在新的方言、多语种或噪声 held-out 集上重开 |
| R1-M06 | 睡眠分期/生命体征模型 | Reject | 当前问题是设备字段是否开放，不是缺少推理模型 | 先取得 E2/E3 schema；不得从雷达参数猜字段或训练目标 |
| R1-M07 | MediaPipe、openSMILE、Face/OpenFace、YAMNet | Defer | 尚无固定任务、标签和 V2 P0 价值证据 | 只有跌倒主线闭合后仍有明确演示需求、数据和验收指标才立项 |
| R1-M08 | TorchVision Keypoint R-CNN COCO_V1 | Conditional fallback；not selected | M2b 163/170、lying 21/21、RTF 0.100451；但 lying gate 仅 4/21；CAUCAFall 有 46 torso-horizontal no-fall 帧；Open Images static 为 3/8 无人激活、11/11 matched、6 overall FP | C6c held-out 反超、横卧关键点门改善，并关闭 COCO/ImageNet/weight 分发 Review 后才可重开主候选决定 |

`Conditional` 表示候选进入 V2-D1 的比较接口，不表示模型名称可以直接写进最终比赛能力说明。

## 5. 《监测方案》特征范围收敛

| 监测能力 | V1-R1 状态 | V2 处理 |
|---|---|---|
| 人体框、COCO-17 姿态、短时轨迹 | Conditional | 服务跌倒 P0；必须携带关键点质量和 fallback 原因 |
| 跌倒事件 | Conditional features/candidates/evaluator only | V1 已实现 E1 可解释时序特征、首版非 fixture candidate policy 与事件 scorer，但没有 C6c 事件指标、RiskAssessment 或 Alert；V2 须先关闭真实 G3/G4/G5，再设计人工确认闭环 |
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
4. [TorchVision LICENSE](https://github.com/pytorch/vision/blob/main/LICENSE)只关闭实现 BSD-3-Clause；其[预训练模型说明](https://docs.pytorch.org/vision/master/models.html)要求使用者审查关联数据集。Keypoint R-CNN 移除了 HumanArt，但 COCO 逐图许可、ImageNet access/use 和权重再分发均仍为 review-required。
5. 当前三个 FunASR 冻结 snapshot 的精确模型卡均写明 Apache License 2.0；权重仍以 SHA-256 固定，因为 `master` 不是版本。V2 打包必须保存模型卡/许可证副本与 attribution，不只记录框架许可证。
6. [OpenAI Whisper 官方仓库](https://github.com/openai/whisper)明确代码和模型权重均为 MIT；它的淘汰原因是当前普通话准确率，不是许可证。
7. URFD/FLEURS 只作为 E1 回归输入；默认不进入比赛提交包、演示媒体或训练资产。任何再分发必须另做署名、非商业/相同方式共享和比赛规则审查。
8. Open Images 静态 suite 的 annotations 记录 Google LLC / CC BY 4.0，12 张图片逐图记录 CC BY 2.0 作者、标题和 landing page；官方不保证逐图许可证状态，因此当前检查只支持 E1 回归，比赛展示或再分发前必须重新审计并生成最终 attribution / NOTICE。
9. `distribution-readiness-v0.1.0` 已将上述边界变成机器可执行的 G5 门。当前 13 项资产为 include 2、exclude 7、undecided 4；5 项 owner decision 与 3 个 release file 均未关闭，因此提交包保持 blocked。该结果是工程证据状态，不是法律结论。
10. `runtime-closure-v0.1.0` 把候选依赖资产细化为八个前置门。当前共享环境缺 headless OpenCV 和四项 ONNX Runtime CUDA extras，存在 editable/direct-URL 来源、76 个闭包外包和 3 项许可证 metadata 缺口，只能作为候选缺口清单；不得据此生成 final lock/NOTICE。

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
| 本地运行权限 | `--runs-dir` 根、run/子目录 `0700`，JSON/JSONL `0600`，Slurm stdout `0600`；同容器 run 的模型本地目录不入 manifest | R1-D12 |
| 正式批处理 provenance | clean submit checkout、完整 submit/execution commit 一致、checkout-bound import、owner-only stdout/runs、按 backend 验证 CUDA runtime | R1-D13 / REV-022 |
| 比赛分发门禁 | 来源配置摘要、资产 include/exclude/undecided、owner decision、LICENSE/NOTICE/competition lock 与五级 fail-closed gate | R1-D14 / REV-023 |
| 候选 runtime 闭包 | 固定直接版本、根 extras/目标 marker 传播、安装 provenance、环境纯净度、许可证 metadata 与八级 fail-closed gate | R1-D15 / REV-024 |
| 离线回放与评测边界 | PoseBackend、SpeechBackend、固定 case、隐私安全汇总 | V1-M2b/M3 |
| 同容器音轨 adapter | 单 A/V asset、严格 track/PTS gate、16 kHz PCM、signed start offset 与 Pipeline 统一时间平移 | REV-010 / REV-021 |
| 有界流采集 adapter | 环境端点、首视频关键帧、open/read timeout、时长/packet 上限、owner-only 原子 Matroska、输出 timing probe 与失败清理 | R1-D16 / REV-025 |
| 重复开流资格 gate | 多次独立 raw/child report、固定失败码、完整音视频轨道签名、严格计数/路径/readiness 父 gate；断线/长稳/损伤声明分离 | R1-D17 / REV-026 |
| 受控流故障识别 gate | 七个固定 loopback HTTP 行为、实际 request/body/delay/stall/reject/reset/early-close 遥测、有界状态、0 unexpected ready 与失败 partial 清理 | R1-D18 / REV-027 |
| 姿态候选配置 | 5 fps、RTMPose detector conf 0.05；Keypoint R-CNN conf 0.5 / resize 800～1333；COCO-17 与分数语义分开记录 | REV-006 / REV-013 |
| 跌倒运动特征契约 | box-only、关键点质量门、同 track 历史、fallback reason、无风险/告警硬约束；单一横卧框或 gate-passed torso-horizontal 均不得直接告警；静态 person detection 结果不得冒充事件指标 | REV-011 / REV-012 / REV-013 / REV-015 |
| 跌倒候选生成契约 | transition 600 ms + 近期下降、settled 1200 ms + low-motion、gap/track reset、release 600 ms、refractory 3000 ms；label-blind，精确窗口只进 derived-sensitive FeatureEvent | REV-017 |
| 跌倒事件评估契约 | 两份以上 independent annotation、pairwise interval/onset agreement、adjudication、统一 candidate-policy 摘要、one-to-one TP/FP/FN、总暴露 FP/hour、negative-clip activation 与 delay；不复制原始窗口或授权告警 | REV-016 |
| 语言候选配置 | 16 kHz、FunASR 三模型摘要、CER/静音/RTF 口径 | REV-007 |
| 睡眠字段边界 | 19 direct、5 derived、11 not-assumed、fail-closed mapping | REV-008 |
| 真机场景与 held-out 契约 | C01～C12 场景/动作标签；8 clip 核心复测门；C01～C10 完整 Review 门；三姿态策略摘要 | V1-M2c 规程 / REV-014 |
| 隐私边界 | 原始媒体/健康值不入 Git，汇总不含全文、密钥、序列号和姓名 | development workflow |

## 8. V2 冻结前的硬门

| Gate | 必须取得的证据 | 失败时的降级 |
|---|---|---|
| G1 C6c 能力 | 脱敏能力集、直播/回放/抓图调用和一段原始媒体；E1 HTTP 采集/重复开流/故障识别 gate 只作为接收工具证据 | 演示只允许受控流/文件回放，不声称实时萤石接入 |
| G2 音视频时间基 | C6c 容器 track、time_base、首尾 PTS 与两次同步事件的 offset/drift；E1 packet span 不计入 | 视频与语言分开演示，不做自然融合结论 |
| G3 C6c 模型复测 | `camera_ready_for_model_retest=true`；至少 8 个 E2 核心 clip，三姿态 variant、空场误触发和远场 ASR；C01～C10 完成后才申请 M2c Review | 保留 E1 离线 demo，模型仍为 conditional |
| G4 跌倒特征/候选/事件 | E1 feature/fallback、首版 candidate policy、公开压力与双标注/裁决/event scorer 已通过；仍需 C6c 正负视频、空场持续、躺床、宠物移动、多人 tracking 和冻结策略的真实事件指标 | 不生成自动风险，只展示姿态/轨迹派生特征、candidate 与 tooling-only scorer |
| G5 模型/项目许可证 | 先以 `runtime-closure-v0.1.0` 关闭候选环境八门，再以 `distribution-readiness-v0.1.0` 核对项目 LICENSE、第三方 NOTICE、competition lock、最终权重/打包决定和来源摘要；当前分别为 3/8 与 0/5 ready | 任一 `--require-ready` 不通过即重建环境、排除未清门模型/数据或停止 RC；不得临近提交时口头豁免 |
| G6 SDNL1 字段 | 至少一晚 E2 schema，或可复核的权限/不开放证据 | 保留接口和 blocked 状态，不展示合成健康值 |
| G7 数据治理 | 同意、受控存储、留存期、访问人和删除流程 | 不使用真实人物/健康数据 |

## 9. 不等待真机的下一开发顺序

1. `[E1 tools done，REV-010/014/021/025/026]` 使用 PyAV 实现有界 HTTP/RTSP 接收、重复独立开流/格式 gate、容器时间基和同容器音轨到 VAD/ASR 的 PTS adapter，并把采集包、双事件与 held-out 冻结成可执行门；下一步按“单次 C6c 短 E2 → 三次 qualification → 故障/长稳 → C01～C12”执行，不把 E1 HTTP 或 scheduled reopen 当平台/重连结论。
2. `[E1 tools done，REV-011/012/015/016/017]` 已实现仅离线输出的跌倒特征层、首版 label-blind candidate episode、CAUCAFall/Open Images 压力支路，以及双标注/裁决/事件 scorer；保持不输出 RiskAssessment 或 Alert。
3. 当前下一步是按 REV-014 采集 C01～C12；空场、家具遮挡、床上躺卧和安全模拟跌倒已进入标签契约，宠物移动和真实多人 tracking 作为扩展视频负样本继续 Open。C6c 首轮必须原样使用 REV-017 policy，再复用 REV-016 口径生成事件指标。
4. `[E1 comparison done，REV-013]` 已评测非 Human-Art 的 Keypoint R-CNN；因 lying gate 4/21 和权重分发仍 Open，只保留 fallback。下一步不再横向增加 checkpoint，而是进入 C6c held-out 与自有训练路线判断。
5. `[E1 gate tooling done，REV-023/024]` 分发与 runtime closure 门禁均已实现并正确阻断当前 draft profile/共享环境；下一步先由项目方和模型负责人确认许可证、打包方式与最终姿态 variant，再按该选择建立独立候选环境并关闭八个 closure gate。只有此后才生成 competition lock/NOTICE、绑定摘要并通过两道 `--require-ready`。

## 10. V1-R1 完成门

本文件完成 E1 预 Review，但 V1-R1 里程碑保持 In progress。满足以下条件后才能标记 Done：

1. C6c 与 SDNL1 分别被真实证据归类为 available、limited 或 blocked，而不是 Unknown。
2. V2 姿态默认候选同时通过目标设备、负样本和分发 Review。
3. FunASR 在 C6c 远场/噪声集完成 CER 与人工 VAD 评测，或降级为离线可选能力。
4. C6c 三路候选按冻结 policy 生成，并通过双标注/裁决后的事件指标 Review，或明确降级为人工查看工具。
5. 每个硬门有负责人和截止日期；无法完成的能力已从 V2 已实现清单删除。
6. V2-D1 明确主路径、离线 fallback 和比赛演示声明三者的边界。
