# 康盾 Review 记录

本文件记录范围、架构、模型和里程碑决策。会议讨论只有写入本文件后才视为项目决定。

## Review 模板

### REV-XXX 标题

- 日期：
- 状态：Open / Accepted / Superseded
- 参与人：
- 评审范围：
- 输入材料：

发现：

1. （待填写）

决定：

1. （待填写）

行动项：

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
|  |  |  |  |

未决问题：

1. （待填写）

---

## REV-001 初始工程方案 Review

- 日期：2026-07-22
- 状态：Accepted
- 参与人：项目组、Codex
- 评审范围：MVP 范围、工程架构、推进方式
- 输入材料：plan.md、《康盾-MVP工程实现与模块Pipeline规划》、《监测方案》

### 发现

1. 两份工程规划都主张接口先行和回放测试，但在模块命名、公共对象、进程数量和必做范围上没有统一。
2. 《监测方案》定义七个数据维度和跌倒、认知症、抑郁、诈骗四个风险方向，属于研究型完整目标，不等同于比赛周期内可实现范围。
3. 《监测方案》假设摄像头、睡眠仪、手环、门锁和存在传感器共同提供数据；当前实际只有摄像头和睡眠仪。
4. 多项指标不能由单目摄像头直接可靠测得，例如未标定的真实步速/步长、COP 面积与速度；HRV、血氧、门锁记录也不能在未验证接口前假定存在。
5. 原 8 周计划从当前日期开始将晚于 9 月 5 日，必须设置探索停止时间。

### 决定

1. 采用两阶段交付：V1 探索版，V2 最终比赛版。
2. 当前先写文档，不继续搭建完整 V1 业务代码。
3. V1 首先完成信息采集和模型可行性探索，允许使用本地录制文件、单进程和 JSONL。
4. V1 的目标是确认“能获得什么数据、能稳定提取什么特征”，不输出正式健康诊断或四风险统一评分。
5. V2 只接纳经过 V1 固定样本测试并通过 Review 的能力；跌倒链路保持 P0。
6. 当前硬件冻结为 CS-C6c-V101-1J4WF 摄像头和 CS-EP-SDNL1 睡眠仪。
7. 手环、门锁和红外传感器指标保留在远期指标表，但不写成 V1/V2 已具备数据。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 获取两台设备、开发账号和权限说明 | 待指定 | 2026-07-24 | Open |
| 完成设备 API 能力探测 | 待指定 | 2026-07-28 | Open |
| 准备受控视频/音频与睡眠样例 | 待指定 | 2026-07-29 | Open |
| 完成首轮姿态与语音模型对比 | 待指定 | 2026-08-07 | Open |
| 召开 V1-R1 晋级 Review | 待指定 | 2026-08-09 | Open |

### 未决问题

1. CS-EP-SDNL1 对开发者开放哪些字段和历史粒度？
2. C6c 服务端取流是否包含音频，编码和鉴权方式是什么？
3. 开发机器的 GPU 型号、显存和部署系统是什么？
4. 比赛评分细则对“基于萤石开放平台”的最低真实接入要求是什么？
5. 团队人数和模块负责人如何分配？

---

## REV-002 监测指标与设备边界 Review

- 日期：2026-07-22
- 状态：Accepted
- 参与人：项目组、Codex
- 评审范围：《监测方案》指标如何进入 V1，现有设备覆盖范围
- 输入材料：《监测方案》、设备型号信息、萤石公开资料

### 发现

1. 七维指标中存在设备直接量、模型估计量、长期聚合量和当前不可得量，不能放在同一可信级别。
2. CS-C6c-V101-1J4WF 可作为视频/受控音频入口，但具体码流、音频、回放和告警能力仍取决于真实账号能力集。
3. CS-EP-SDNL1 官方产品资料表明其为毫米波/FMCW 睡眠设备并列出两组频率测量范围，但开发接口字段与粒度没有公开证据。
4. MediaPipe blendshape 不是 FACS AU；视频中的身体摆动代理也不是力平台 COP。
5. 没有手环、门锁和电话元数据时，不能声称已经获得血氧、完整 HRV、真实出门记录或联系人多样性。

### 决定

1. 《监测方案》作为指标 Backlog 主来源，但每个指标必须标记 A/B/C/D 可行性。
2. V1 优先完成设备事实和数据质量，再运行模型；不得用模型演示代替设备 API 验证。
3. 跌倒相关视频特征、VAD/中文 ASR、睡眠字段探测列为 P0。
4. 步态窗口、声学特征、面部可用性和多日节律列为 P1/P2。
5. 认知和抑郁指标仅做采集可行性，不形成诊断；诈骗音频只允许主动开启或脚本化实验。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 获取 C6c 真实能力集与一段含音频媒体 | 待指定 | 2026-07-26 | Open |
| 获取睡眠仪真实接口/导出样例 | 待指定 | 2026-07-26 | Open |
| 按 P0 字段制作首批样本 Manifest | 待指定 | 2026-07-29 | Open |
| 记录不可得指标并从比赛已实现清单移除 | 待指定 | 2026-08-09 | Open |

### 未决问题

1. 睡眠仪是否向开发应用开放实时/分钟级数据？
2. 摄像头音频能否通过服务端或 PC SDK 合规取得？
3. 比赛演示是否要求实时流，还是开放平台授权、设备状态与回放链路即可满足？

---

## REV-003 V1 信息侧初步实现 Review

- 日期：2026-07-22
- 状态：Accepted for V1-M1
- 参与人：项目组、Codex
- 评审范围：公共契约、运行产物、媒体探测、睡眠字段发现、萤石快照分析
- 输入材料：信息侧技术路线、设备能力矩阵、初步实现与测试

### 发现

1. 当前没有确认过的萤石最新 REST 路径和睡眠仪字段，硬编码旧接口会把不确定性扩散到核心模块。
2. 本地系统没有 ffprobe，但已有 OpenCV；OpenCV 能探测视频图像参数，不能证明音轨存在。
3. Fixture 中可能包含看似真实的 token、序列号和设备名，若不脱敏容易进入运行报告。
4. 单个本地文件、SDK 导出或 API 快照能够支持的最高证据等级不同，不能完全依靠操作者自觉填写。

### 决定

1. 首版采用 SDK/API 脱敏快照导入，获得确认接口后再增加 LiveTransport。
2. 核心契约与 artifacts 不依赖 OpenCV、萤石 SDK 或模型框架。
3. 视频探测将音轨状态明确写成 not_inspected_by_opencv。
4. 本地 URI 使用内容摘要，不保留可能含姓名的原始文件名。
5. Fixture 最高 E1，本地文件和 SDK 导出最高 E2，单次 API 响应最高 E3；E4 只能由后续重复性 Review 晋级。
6. 睡眠字段名匹配只生成 candidate，不自动确认单位或医学语义。

### 验证

- 自动化测试：11 passed。
- 手工命令：WAV、合成视频、睡眠 Fixture、萤石 Fixture 均生成 completed manifest。
- 敏感值扫描：Fixture token、序列号、设备名、姓名均未进入运行产物。
- 真实设备：尚未验证，当前能力矩阵仍为 E0。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 获取 C6c 脱敏 SDK/API 快照和媒体 | 待指定 | 2026-07-26 | Open |
| 获取睡眠仪真实导出/API 样例 | 待指定 | 2026-07-26 | Open |
| 基于真实媒体运行无模型质量探测 | 待指定 | 2026-07-28 | Open |
| 决定 LiveTransport 的 SDK/API 路线 | 待指定 | 2026-07-28 | Open |

### 未决问题

1. 萤石是否提供服务端媒体 URL，还是需要 PC/移动 SDK 导出？
2. 睡眠仪是否属于开放平台通用设备模型或专用健康组件？
3. 真实摄像头音轨是否能在服务端环境取得？

---

## REV-004 V1 视频与语言多模态基线 Review

- 日期：2026-07-22
- 状态：Accepted for V1-M2a
- 参与人：项目组、Codex
- 评审范围：设备无关视频/语言链路、模型基线、Slurm 运行和产物边界
- 输入材料：[V1 多模态 Pipeline](v1-multimodal-pipeline.md)、[初测报告](reports/v1-m2a-multimodal-smoke.md)、提交 `fb39903`、Slurm job `1757`

### 发现

1. 不等待萤石取流权限，也可以先用回放适配器冻结姿态、语音、语言和时间窗的数据契约；后续真实流只需替换输入层。
2. 当前 P0 需要逐帧坐标、track_id、VAD 段和中文转写时间，专用结构化模型比直接使用通用音视频大模型更适合作为可审计基线。
3. 模型已加载后的 5 秒处理为 2.172 秒，但冷启动约 39.245 秒；只报告一个“端到端”数值会造成错误容量判断。
4. 公开 bus 图片回放和标准普通话只能验证链路，不能验证跌倒、夜视、跟踪稳定性、老人语音或 ASR 字错率。
5. FunASR 固定权重模型卡记录为 Apache-2.0；Ultralytics YOLO 是 AGPL-3.0/Enterprise 路线，V2 必须有显式许可证决策。

### 决定

1. V1 姿态基线采用 YOLO26n-pose + ByteTrack；V1 语言基线采用 FSMN-VAD + SeACo Paraformer + CT-Punc。
2. 原始转写属于 derived_sensitive，只进入受控 FeatureEvent；汇总报告只记录计数、摘要和引用。
3. 统一生成 ModelBinding 与 MultimodalWindow；关键词只标注词面观察，不输出诈骗、跌倒意图或健康风险结论。
4. Slurm 计算节点只使用预取并校验摘要的离线权重；清除本地代理变量，失败运行保留 failed manifest。
5. V1 demo 使用常驻并预热的模型进程。报告同时保留 processing 与 cold-start 口径。
6. V1-M2a 标记 Done；V1-M1、V1-M2b 和 V1-M3 状态不因本次公开 smoke 自动提升。
7. V2 冻结前在相同真实样本上对比 RTMPose/MMPose，或确认满足 Ultralytics 许可证要求。

### 验证

- 自动化：18 passed。
- Slurm：job `1757`，`COMPLETED`，exit `0:0`，NVIDIA L40。
- 代码：`fb39903`，运行时 `code_dirty=false`。
- 产物：25 个姿态帧、98 个姿态实例、1 个 VAD/转写段、5 个多模态窗口。
- 性能：processing RTF 0.434464；cold-start RTF 7.849024；峰值 CUDA allocated 2,126.966 MiB。
- 隐私：汇总报告未复制完整转写；原始媒体和运行目录未进入 Git。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 录制有明确同意的 C6c 正常行走、起坐、模拟跌倒、遮挡/夜视样本 | 待指定 | 2026-07-29 | Open |
| 验证 C6c 音视频是否同容器及 PTS/时钟偏差 | 待指定 | 2026-07-29 | Open |
| 建立近场、远场、电视背景和目标人群语音参考转写 | 待指定 | 2026-07-31 | Open |
| 在同一固定样本比较 YOLO26n-pose 与 RTMPose | Codex | 2026-07-22 | Done（REV-006） |
| 形成 V2 姿态模型许可证决定 | 待指定 | 2026-08-09 | In progress（REV-009；artifact 分发仍 Open） |

### 未决问题

1. C6c 实际视频分辨率、夜视码率、音频编码和音视频时间基是什么？
2. 目标居家镜头中人体最小像素高度和典型遮挡比例是多少？
3. 方言、电视串音和远场条件下 Paraformer 的 CER 与误触发率是否合格？
4. 最终比赛仓库的开源/分发方式是否满足 Ultralytics AGPL，还是必须切换 RTMPose？

---

## REV-005 V1-M2b 公开固定集与评测 Review

- 日期：2026-07-22
- 状态：Accepted for V1-M2b
- 参与人：项目组、Codex
- 评审范围：公开真实人物录制固定集、标签/转写评测、批量 Pipeline、证据与许可证边界
- 输入材料：[V1-M2b 设计](v1-m2b-public-dataset-benchmark.md)、[初测报告](reports/v1-m2b-public-dataset-benchmark.md)、提交 `93f7d09`、Slurm job `1759`

### 发现

1. URFD 官方数据能以较小固定子集提供模拟跌倒/ADL RGB 序列、同步时间和帧级姿态阶段；FLEURS 普通话 dev 能提供版本固定的 16 kHz 真实语音和参考转写。
2. FLEURS 源 WAV 使用 IEEE float，现有 PCM 回放器不能直接读取；在数据准备层统一转成 PCM16 可以保持在线 Pipeline 的输入契约不变。
3. URFD 视频与 FLEURS 语言并非自然同步录制。把它们配成共同零时刻只能验证窗口与 schema，不能计算跨模态语义准确率。
4. 六 case 姿态帧覆盖率为 89.41%，但 lying 阶段只有 42.86%；YOLO26n-pose 在 fall-01/02 倒地后的横卧人体上明显漏检。
5. corpus CER 为 6.57%，9 次编辑中 7 次来自一条中英混合样本省略 `Moldova`；普通话主体表现较好，但固定集官方口径不能删除该样本。
6. 六 case processing 合计 RTF 为 0.150，整套冷启动 wall/media 为 1.056；FunASR 共享加载 36.228 秒，常驻模型进程仍是 demo 必需条件。
7. URFD 的 CC-BY-NC-SA-4.0、FLEURS 的 CC-BY-4.0 和 Ultralytics 的 AGPL/Enterprise 路线都需要进入比赛材料与 V2 分发审查。

### 决定

1. V1-M2b 定义为“公开真实场景固定集与对齐评测”，验收 E1 工程、标签/CER、性能和可重复性；状态标记 Done。
2. 原计划中的 C6c 音视频时间基、受控居家样本和睡眠仪真实字段改列 V1-M2c，仍要求 E2/E3，公开数据不得替代。
3. 所有跨数据集 case 强制声明 `cross_dataset_synthetic_common_zero`；视频和语言精度分别计算，融合窗口只作工程验证。
4. YOLO26n-pose + ByteTrack 和 FunASR 继续保留为 V1 baseline，不因本次结果自动晋级 V2。
5. M3 姿态比较优先评价 lying 阶段，不能只看整体覆盖率；需评估 RTMPose/MMPose、人体检测 fallback 和短时轨迹容错。
6. 汇总报告不复制完整参考/识别文本；原始数据、派生媒体和 runs 不进入 Git。

### 验证

- 数据准备：16 个固定源文件，995 个 URFD RGB 帧，六段 PCM16，重复生成 lock 摘要一致。
- 自动化：22 passed。
- Slurm：job `1759`，`COMPLETED`，exit `0:0`，NVIDIA L40，elapsed 00:00:51。
- 代码：`93f7d09`，parent/child 全部 `code_dirty=false`。
- 视频：170 个抽样帧，152 个人物阳性帧，148 个含 track_id 的人物阳性帧。
- 语言：137 个参考字符，9 次编辑，3/6 完全匹配。
- 隐私：汇总 JSON 未出现六条完整参考转写。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 获取 C6c 同意录制样本并验证音视频 PTS/时钟偏差 | 待指定 | 2026-07-29 | Open |
| 获取 CS-EP-SDNL1 真实 API/SDK/导出字段样例 | 待指定 | 2026-07-29 | Open |
| 在当前六段视频对比 RTMPose/MMPose 的 lying 阶段覆盖率 | Codex | 2026-07-22 | Done（REV-006） |
| 设计人体检测 fallback 与短时轨迹容错基线 | 待指定 | 2026-08-05 | Open |
| 完成 URFD/FLEURS/Ultralytics 的比赛使用与分发审查 | 待指定 | 2026-08-09 | In progress（REV-009） |

### 未决问题

1. C6c 夜视和目标机位下 lying 阶段的人体像素高度、遮挡和姿态覆盖率是多少？
2. RTMPose/MMPose 能否在相同算力与许可证约束下显著改善横卧检出？
3. 目标老人远场普通话、方言和电视背景下的 CER/VAD 覆盖率是多少？
4. 比赛材料是否会分发 URFD 派生媒体，若会，如何满足 BY-NC-SA 条款？

---

## REV-006 V1-M3 姿态模型同集对比 Review

- 日期：2026-07-22
- 状态：Accepted for V1-M3 pose slice
- 参与人：项目组、Codex
- 评审范围：横卧姿态覆盖、关键点质量、ONNXRuntime 兼容性、性能与 V2 候选状态
- 输入材料：[V1-M3 设计](v1-m3-pose-model-comparison.md)、[同集对比报告](reports/v1-m3-pose-model-comparison.md)、提交 `0674be9`、Slurm job `1760`

### 发现

1. 完整 MMPose + MMCV 在当前 Python 3.13/Torch 2.13/CUDA 13 环境没有直接可用的严格匹配构建；官方 ONNX 导出可以绕开框架运行时依赖，并在 L40 上实际启用 CUDAExecutionProvider。
2. YOLOX-m HumanArt + RTMPose-m HumanArt 将整体覆盖从 89.41% 提到 95.88%，将 lying 从 42.86% 提到 95.24%；改善集中在 fall-01/02 已知漏检。
3. fall-01 的候选 lying 覆盖为 7/8，但 `>=0.5` 关键点可见比例为 0；人物框成功与关键点几何可用是两个不同验收门。
4. 候选 L40 推理 RTF 0.123668，慢于基线 0.079518，但两者都达到当前单路 5 fps 回放实时要求。
5. 0.05 检测阈值在本固定集扫描后确定，且固定集没有人物存在负标签；当前提升不是 held-out 泛化或误报结论。
6. 两 variant 的 tracker 不同；候选 100% tracking coverage 只证明每个框被分配了 ID，不能证明轨迹比 ByteTrack 更稳定。

### 决定

1. HumanArt + RTMPose 晋级为 V2 姿态有条件候选，YOLO26n-pose 保留为 V1 baseline；不在 V1-M2c 前冻结最终模型。
2. C6c 复测冻结 0.05 阈值，必须覆盖夜视、距离、遮挡、正常动作、横卧和空场负样本。
3. 跌倒特征设计同时保留 box-only 横卧/下降/静止代理和关键点分支；关键点分支设置质量门，禁止在 fall-01 类低质量帧上强算几何量。
4. V1-M3 姿态切片验收通过；本次不升级整体状态。语言对照和睡眠字段路线后来分别由 REV-007、REV-008 关闭。
5. 模型实现、训练数据和比赛分发许可证在 V1-R1 前单独审查；Apache-2.0 框架记录不代替数据条款审查。

### 验证

- 自动化：28 passed；`pip check` 无 broken requirements。
- Slurm：job `1760`，`COMPLETED`，exit `0:0`，NVIDIA L40，elapsed 00:00:19。
- 代码：`0674be9`；parent + 12 child manifests 全部 completed、`code_dirty=false`。
- 覆盖：baseline 152/170，candidate 163/170；lying 9/21 对 20/21。
- 性能：candidate inference RTF 0.123668；进程显存为推理后快照 1,124 MiB，不声明为采样峰值。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 按冻结阈值采集并评测 C6c 场景矩阵 | 待指定 | 2026-08-01 | Open |
| 增加空房、家具、宠物、局部人体负样本 | 待指定 | 2026-08-03 | Open |
| 实现并评测关键点质量门与 box-only fallback | 待指定 | 2026-08-05 | Open |
| 完成 OpenMMLab/训练数据/URFD/比赛分发审查 | 待指定 | 2026-08-09 | In progress（REV-009；HumanArt artifact 未清门） |

### 未决问题

1. C6c 实际夜视和目标机位下，fall-01 类型横卧是否仍只能得到低质量关键点？
2. 低至 0.05 的人物阈值在空场、家具和宠物场景会产生多少误报？
3. box-only fallback 与关键点分支怎样组合，才能提高召回而不把弯腰、躺床当成跌倒？

---

## REV-007 V1-M3 语音模型同集对比 Review

- 日期：2026-07-22
- 状态：Accepted for V1-M3 speech slice
- 参与人：项目组、Codex
- 评审范围：普通话 CER、静音误转写、性能/显存、隐私与 V2 候选状态
- 输入材料：[V1-M3 语音设计](v1-m3-speech-model-comparison.md)、[同集对比报告](reports/v1-m3-speech-model-comparison.md)、提交 `270fdc1`、Slurm job `1761`

### 发现

1. FunASR 在同一 audio-only runner 上复现 V1-M2b 的 `9/137 = 6.57%` 和 3/6 exact，证明新对比链路没有改变 baseline CER 口径。
2. Whisper small 为 `32/137 = 23.36%` 和 0/6 exact，较 baseline 劣化 16.788 个百分点；6/6 case 的编辑数都更高，不是单个离群句造成。
3. 两 variant 对 2 秒全零 PCM 都返回 0 segment、0 字符；这不能替代真实房间噪声、电视和非语音事件的误激活测试。
4. Whisper model load 2.51 秒、Torch peak 1,411 MiB，优于 FunASR 的 35.05 秒和 2,099 MiB；但 warm inference RTF 0.089950 慢于 0.037648。两者都达到当前单路实时要求。
5. Whisper segment coverage 较高不是 VAD 优势证据，因为它是集成解码段，FunASR 使用独立 FSMN-VAD，固定集没有共同人工 VAD 标签。
6. female/male 切片各只有三条且句子不同，只能作为错误定位线索，不能形成 gender 公平性结论。

### 决定

1. FunASR FSMN-VAD + SeACo Paraformer + CT-Punc 保留为 V2 普通话默认候选，最终采用仍受 C6c V1-M2c 门约束。
2. Whisper small 不晋级普通话主链路；保留 adapter 和固定权重，只有新多语种、方言、噪声或 C6c held-out 证据才重开。
3. 不在当前六条上继续调 beam、prompt、语言或后处理并回报同集提升；任何新候选先冻结新评测集和决定规则。
4. V1-M3 语言切片验收通过；本次不升级整体状态。睡眠字段路线后来由 REV-008 关闭，V1-M3 在 E1 探索范围转为 Done。
5. 报告继续只保存字符数、编辑数和聚合，完整转写只留在受控且被 Git 忽略的 FeatureEvent。

### 验证

- 自动化：35 passed；`pip check` 无 broken requirements。
- Slurm：job `1761`，`COMPLETED`，exit `0:0`，NVIDIA L40，elapsed 00:00:55。
- 代码：`270fdc1`；parent + 12 child manifests 全部 completed、`code_dirty=false`。
- 准确率：FunASR 9/137，Whisper 32/137；差 +23 edits / +16.788 pp。
- 静音：两个 variant 均 0 segment、0 字符。
- 隐私：15 份 JSON report 和 Slurm 日志均未出现完整参考或完整假设文本。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 按 M2c 规程采集 C6c 授权普通话、方言、电视背景、距离和静音/噪声样本 | 待指定 | 2026-08-01 | Open |
| 为真实设备集增加人工 VAD 区间或语音存在标签，分开评测 VAD 与 ASR | 待指定 | 2026-08-03 | Open |
| 完成 FunASR 模型、Whisper 权重和比赛分发条款审查 | 待指定 | 2026-08-09 | In progress（REV-009；模型卡已固定，打包未完成） |
| 在 V1-R1 前关闭 CS-EP-SDNL1 睡眠字段采用/接口保留/放弃决定 | Codex | 2026-07-22 | Done（REV-008；真机证据仍 Open） |

### 未决问题

1. C6c 麦克风在 1/3/5 米、电视背景和夜间环境下，FunASR 的 VAD 漏检、误激活和 CER 分别是多少？
2. 实际目标人群是否存在足够多的方言或中英混说，使多语种候选的价值超过当前普通话准确率损失？
3. V2 是否允许常驻加载 FunASR，还是需要进程预热/模型服务来隐藏约 35 秒冷启动？

---

## REV-008 V1-M3 睡眠字段路线 Review

- 日期：2026-07-22
- 状态：Accepted for V1-M3 sleep field slice
- 参与人：项目组、Codex
- 评审范围：《监测方案》指标分层、目标设备公开证据、字段发现、语义门、多夜派生前置条件与隐私
- 输入材料：[睡眠字段路线设计](v1-m3-sleep-field-route.md)、[正式评审报告](reports/v1-m3-sleep-field-route.md)、提交 `5635e95`、正式运行 `20260722T072520Z-77a0f3b6`

### 发现

1. 《监测方案》要求的生理、睡眠和节律指标明显宽于当前 synthetic fixture；聚合心率/呼吸不能推出 HRV、SpO2、AHI 或连续活动节律。
2. CS-EP-SDNL1 官方商品页只证明产品参数，通用雷达套件和睡觉检测服务也不能证明目标型号 API schema；公开产品文档未取得请求响应、单位、时间粒度和兼容型号证据。
3. 正式 E1 运行在 19 个 direct-if-exposed 字段中得到 4 个名称候选、15 个未观察字段和 0 个 ready 字段；候选是时间、心率、呼吸率和在床状态。
4. fixture 或 E1 输入即使伪造 confirmed mapping 也会被拒绝；只有 E2/E3 非 fixture 数据与单位、时间、值域、缺失语义全部确认，单字段才可 `ready_for_adapter`。
5. 5 组多夜派生全部 `blocked_source_fields`，11 个 not-assumed 字段保持关闭；adapter ready 也不等于派生 ready 或医学准确率通过。
6. 两份正式 JSON 报告未持久化原始值；身份、设备序列号和 8 个完整原始字段值片段泄漏计数均为 0。

### 决定

1. 睡眠信息不选模型，采用 SleepProfile v0.2 + fail-closed route gate。
2. 固定 19 个 direct-if-exposed、5 组 multi-night derived 和 11 个 not-assumed；策略绑定《监测方案》摘要，源文件漂移即阻断。
3. `ready_for_adapter` 只授权后续单字段 adapter，不授权值输出、派生计算或准确率声明。
4. V1-M3 睡眠字段切片通过；姿态、语言、睡眠三条 E1 路线均已决策，V1-M3 在 E1 探索范围标记 Done。
5. V1-M1 与 V1-M2c 状态不提升，仍需 C6c 和 CS-EP-SDNL1 的 E2/E3 真机证据。

### 验证

- 自动化：40 passed；`pip check` 无 broken requirements。
- 代码：`5635e95`；正式 manifest completed、`code_dirty=false`。
- 输入：E1 fixture，2 records、4 fields；fixture SHA-256 `9e43065c24f020ccdb56e12f38a4c1571eefe8d9d7d6c0d0b9989a927b0e7b2a`。
- 策略：19 direct、5 derived、11 not-assumed；policy SHA-256 `a696329e2e66efbc9091ee305aae38410c5bccfcd2def39cb6f577357a06aece`。
- 来源：《监测方案》SHA-256 `1f094fe453ce32de7dc3dcb0935b7dd3036e36495140639ec36a6279361fccb0`。
- 隐私：`values_persisted=false`；身份和完整原始值片段泄漏计数均为 0。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 使用有权限账号读取并版本化保存目标产品接口文档 | 待指定 | 2026-07-26 | Open |
| 向萤石确认 CS-EP-SDNL1 与睡觉检测/健康服务的兼容性、固件和权限条件 | 待指定 | 2026-07-26 | Open |
| 取得至少一晚脱敏 E2 API/SDK/导出样例并完成字段语义 mapping | 待指定 | 2026-08-01 | Open |
| 完成至少连续三晚 E3 完整率、重复、断点和延迟审计 | 待指定 | 2026-08-04 | Open |

### 未决问题

1. CS-EP-SDNL1 当前下架后，开放平台兼容性、服务授权和技术支持是否仍可获得？
2. 目标账号实际可取得的是 50 ms 原始/近实时数据、分钟聚合、日级睡眠报告，还是只允许 App 查看？
3. 睡眠分期、awake、翻身和体动分别使用什么 epoch、日界线、算法版本与缺失语义？

---

## REV-009 V1-R1 E1 探索收敛预 Review

- 日期：2026-07-22
- 状态：Accepted as E1 pre-review；V1-R1 milestone remains In progress
- 参与人：项目组、Codex
- 评审范围：V1-M1～M3 证据、模型/字段采用状态、许可证边界与 V2-D1 输入门
- 输入材料：[V1-R1 探索收敛与 V2 输入清单](v1-r1-exploration-review.md)、REV-003～REV-008、许可证修正 `f4aa1c5`

### 发现

1. 设备无关 Pipeline、固定集评测、姿态/语音对比和睡眠字段 gate 都已得到可复现 E1 证据，但 C6c 与 CS-EP-SDNL1 仍只有 E0；模型表现不能替代目标设备接入。
2. M2a/M2b 的独立视频/WAV 共享零点只能验证窗口契约，不能进入 V2 自然音视频同步声明；REV-009 时容器 track/PTS、offset 和 drift 仍未实现。REV-010 随后关闭 E1 探针工具缺口，但真实 G2 仍 Open。
3. HumanArt + RTMPose 的 lying 覆盖显著优于 YOLO26n，但 fall-01 关键点仍不可用；V2 跌倒特征需要 box-only fallback 和显式 keypoint quality gate。
4. 历史 HumanArt ModelBinding 将 MMPose 实现 Apache-2.0 写成模型 artifact license，语义过宽。Human-Art 官方数据授权限定非商业使用且 annotations 为 CC-BY-NC-SA-4.0，最终权重分发不能自动继承框架许可证。
5. FunASR 三个冻结 model card 记录 Apache License 2.0，Whisper 代码与权重为 MIT；但项目本身没有顶层 LICENSE 或最终第三方 NOTICE。
6. 《监测方案》中的 HRV、SpO2、AHI、体温、血压、原始雷达以及自动诈骗/认知/抑郁评分都没有当前设备或评测证据，不能进入 V2 已实现清单。

### 决定

1. Adopt 公共契约、运行 provenance、离线回放/评测接口、E0～E4、隐私边界和睡眠 fail-closed gate。
2. HumanArt + RTMPose 与 FunASR 只作为 V2 有条件候选；YOLO26n 和 Whisper small 分别只保留为姿态/普通话实验对照。
3. 不选择睡眠模型；direct fields 逐字段等待 E2/E3 mapping，multi-night derived 与 not-assumed 保持关闭。
4. 跌倒作为 V2 P0，但下一实现先输出 box/keypoint 时序特征与 fallback reason，不提前冻结 RiskAssessment 或告警分数。
5. MediaPipe、openSMILE、Face/OpenFace、YAMNet、骨架时序模型以及诈骗/认知/抑郁自动评分当前 Defer。
6. V1-R1 的 E1 决策基线验收通过；里程碑保持 In progress，等待真机分类、最终姿态分发路线和负责人关闭。

### 验证

- 自动化：41 passed；`pip check` 无 broken requirements。
- 许可证 fail-closed：`f4aa1c5` 将两个 HumanArt ModelBinding 改为 `model-artifact-license-review-required`，并新增回归测试。
- 姿态：candidate overall 163/170、lying 20/21；fall-01 lying `>=0.5` 关键点可见率仍为 0。
- 语音：FunASR 9/137，Whisper 32/137；两者全零静音探针通过。
- 睡眠：19 direct 中 0 ready，5 derived disabled，11 not-assumed closed。
- 设备：C6c 与 SDNL1 能力矩阵最高仍为 E0。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 实现 ffprobe/PyAV 容器轨道与 PTS 探针 | Codex | 2026-07-22 | Done（REV-010；仅 E1 工具，C6c G2 仍 Open） |
| 实现 box-only 跌倒特征、关键点质量门和 fallback reason 的 E1 离线实验 | Codex | 2026-07-24 | Done（REV-011；仅 E1，真实 G4 仍 Open） |
| 评测一个不依赖 Human-Art 训练条款的姿态候选 | Codex | 2026-07-25 | Done（REV-013；保留 fallback，分发仍 Open） |
| 取得 C6c/SDNL1 E2/E3 或可复核 blocked 证据 | 待指定 | 2026-08-01 | Open |
| 决定项目 LICENSE、最终模型分发路线并生成 THIRD_PARTY_NOTICES | 待指定 | 2026-08-09 | Open |
| 为 V2 硬门指定最终负责人和演示降级声明 | 待指定 | 2026-08-09 | Open |

### 未决问题

1. 比赛提交物是否公开源代码、是否允许非商业权重、是否要求分发模型文件？
2. 不依赖 Human-Art 的姿态候选在 lying 和空场负样本上的性能是否仍足够？
3. C6c 原始媒体能否同时取得视频、音频和可用 PTS，还是必须设计分流降级？
4. SDNL1 无开发接口时，比赛演示是否接受明确 blocked 并仅保留接口契约？

---

## REV-010 V1-M2c 容器时间戳探针 E1 Review

- 日期：2026-07-22
- 状态：Accepted for V1-M2c E1 timing-probe slice；V1-M2c milestone remains In progress
- 参与人：项目组、Codex
- 评审范围：容器轨道、逐包 PTS/DTS、required audio、资源上限、时间语义、确定性与隐私
- 输入材料：[探针设计](v1-m2c-media-timing-probe.md)、[初测报告](reports/v1-m2c-media-timing-smoke.md)、提交 `4a65630`、正式运行 `20260722T095247Z-b49f532e`

### 发现

1. 本机没有系统 `ffprobe`/`ffmpeg`；固定 PyAV 18.0.0 可以直接读取容器、stream、packet PTS/DTS/duration/time base，不需要 shell 外部进程。
2. Matroska 会生成随机 SegmentUID，不适合作为字节级 provenance 夹具；AVI + FFV1 + PCM S16LE 两次独立生成得到相同的 66,044 bytes 和 SHA-256。
3. 正式 E1 运行识别 1 条视频轨与 1 条音频轨，两轨各 30 包，PTS/DTS 均完整，无负值、后退或扫描截断；首尾 offset 与 duration delta 均为 0 ms。
4. 容器 start/end/duration 只描述时间戳范围，不能证明采集时钟、物理声画同步或 drift；当前契约正确保持 `drift_estimate_available=false`。
5. `--require-audio-track` 能区分 missing 与 unverified 并 fail；packet 扫描达到上限时 partial，不允许用截断数据关闭 G2。
6. 正式报告不保存容器 metadata value 或源路径；synthetic 元数据值、完整文件名、`data/raw` 和本地绝对路径扫描均为 0 命中。

### 决定

1. 接受 PyAV 18.0.0、MediaStreamTiming 与 ContainerTimingReport 作为 V1-M2c 原始媒体探针。
2. 接受确定性 AVI 作为 E1 回归夹具；它不属于 C6c 设备证据。
3. 每个含语音的 C6c 原始 clip 强制使用 `--require-audio-track`，缺失、不可验证和扫描截断均保留失败/降级 manifest。
4. G2 必须对真实原始容器检测开始和结束附近的两个可见/可听同步事件；不从 duration delta 推导 drift。
5. V1-M2c 从 Planned 转为 In progress；C6c 与 CS-EP-SDNL1 能力等级保持 E0，里程碑不能进入 Review。

### 验证

- 自动化：46 passed；`pip check` 无 broken requirements；`compileall`、`git diff --check` 通过。
- 代码：`4a65630`；正式 manifest completed、`code_dirty=false`、`source_type=fixture`、E1。
- 输入：deterministic AVI，66,044 bytes，SHA-256 `0b3bd01c83cc138780b4f3fd809798413ba8885f5ee0770a467a3bac17f24672`。
- 轨道：FFV1 `1/10`、PCM S16LE `1/8000`，各 30 个 PTS/DTS 完整 packet。
- 偏移：start 0 ms、end 0 ms、duration delta 0 ms；drift unavailable。
- 隐私：metadata value 和 source path 不持久化，五类敏感字符串扫描 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 取得 C6c 原始同容器媒体并执行 required-audio 探针 | 待指定 | 2026-07-29 | Open |
| 在真实 clip 开始/结束各录一次可见/可听同步事件 | 待指定 | 2026-07-29 | Open |
| 实现或复核双事件定位，形成真实 offset/drift 报告 | Codex | 2026-07-30 | Blocked on consented C6c media |
| 将 C6c 多轨、缺 PTS、断流/重连和无音频结果写入 G2 决定 | 待指定 | 2026-08-01 | Open |

### 未决问题

1. C6c 的直播录制、回放导出或 SDK 导出哪一种能保留原始音频轨与时间戳？
2. 真实容器是否有多音轨、B-frame 重排、首包负 PTS 或重连后的时间轴跳变？
3. 无法取得同容器音频时，比赛演示是否按 G2 预案明确降级为视频与语言分开展示？

---

## REV-011 V1-R1 G4 跌倒运动特征 E1 Review

- 日期：2026-07-22
- 状态：Accepted for E1 offline feature slice；V1-R1 milestone remains In progress
- 参与人：项目组、Codex
- 评审范围：box-only 时序特征、COCO-17 关键点质量门、track/history fail-closed、标签隔离、许可证纠偏与隐私
- 输入材料：[G4 设计](v1-g4-fall-motion-features.md)、[正式报告](reports/v1-g4-fall-motion-features.md)、提交 `782026b`、正式运行 `20260722T103206Z-671bfb95` / `20260722T103206Z-aa69e875`

### 发现

1. RTMPose 主候选在 21 个 lying 采样帧中有 20 帧 bbox、17 帧横卧代理、11 帧关键点门通过和 9 帧 box-only；YOLO 对照分别为 9、8、3 和 6。绝对覆盖差异不能被各自分母下的比例掩盖。
2. fall-01 lying 虽有 7/8 帧 bbox，但 0/7 通过关键点门、5 次 track reset；box-only 是必要 fallback，却不能修复轨迹碎片或单独形成跌倒判断。
3. 三段现有 ADL 的两个变体均有 82 个可用框且横卧代理为 0，但下降和低运动代理仍会激活。该集合没有空房、家具、弯腰、床上躺卧、宠物和真实多人，不能据此声称误报率为 0。
4. 最大有效 bbox 只适用于当前单主目标探索；低阈值多框会触发 `multiple_people_largest_bbox_only`，不等于画面一定存在多人，也不能作为正式身份策略。
5. 派生器不读取 URFD phase label；标签只由 evaluator 对齐。正式 JSONL 不复制原始 bbox、关键点、phase label、参考转写或本地路径。
6. 历史姿态报告中 HumanArt artifact 的 Apache-2.0 绑定被当前 digest-bound policy 纠正为 `model-artifact-license-review-required`；这只是 fail-closed 修正，不代表权重分发通过。

### 决定

1. 接受 `FallMotionFrameValue`、`FallKeypointGate`、`FallFeatureBenchmarkReport` 和冻结配置作为 V2-D1 的条件输入契约。
2. 接受 `box_plus_keypoints`、`box_only` 和 `unavailable` 三条显式路径；关键点门失败时禁止强算躯干角。
3. 接受 no detection、invalid bbox、missing/change track、frame gap、history warm-up 和 multi-person ambiguity 的 fail-closed fallback。
4. `risk_assessment_emitted=false` 与 `alert_emitted=false` 继续作为契约硬约束；当前代理不得用于跌倒分类、风险分数或告警。
5. G4 E1 工具切片验收通过；目标 C6c、扩展负样本、多人策略、事件指标和 G5 许可证仍 Open，V1-R1 保持 In progress。

### 验证

- 自动化：53 passed；`pip check` 无 broken requirements；`compileall`、`git diff --check` 通过。
- 来源：姿态 parent `20260722T053908Z-9b8096cd`，代码 `0674be9`，parent/child 均 clean、completed、E1。
- G4：两个正式 run 均在 `782026b` 上 clean、completed、E1，各处理 170 帧并生成 170 个无风险/告警 FeatureEvent。
- RTMPose 产物：manifest `c73aeb311b9cc3624ad544f272dc924ea3439e3724e152ce930c9254d560a237`；report `98f316b836aa145a4ca4d90ee1276a39580b2f0d989ab9ce11aaf156a2f058af`。
- YOLO 产物：manifest `8e839fa6fb1b2dc0de79481671d49bc878a910abb3852348b8fdc032b1524366`；report `171d5e30d5bde28be58a93d92c649d69a34acd98eb44ece1b9322d808f6891f5`。
- 隐私：340 个派生事件中原始 bbox/keypoints/phase label 为 0；本地绝对路径、`data/processed` 和完整 source report path 扫描均为 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 增加许可证可审计的空房、家具、弯腰、坐下、床上躺卧和多人负样本来源 | Codex | 2026-07-25 | Partial：REV-012 已补 ADL；REV-015 已补静态 furniture/pet/multi-person 人物检测；空场视频与床上躺卧仍 Open |
| 用同一冻结配置复跑 C6c 白天/夜视、距离、遮挡和安全模拟跌倒场景 | 待指定 | 2026-08-01 | Open |
| 为 C6c 集增加 person-presence、动作区间和事件时刻人工标注并冻结事件指标 | 待指定 | 2026-08-03 | Open |
| 评测一个不依赖 Human-Art 训练条款的姿态候选 | Codex | 2026-07-25 | Done（REV-013；保留 fallback，分发仍 Open） |

### 未决问题

1. 空房、床上躺卧与家具负样本采用哪个可用于比赛研究和报告展示的数据源？
2. C6c 目标机位下 bbox 横卧阈值和时间窗是否需按距离/俯仰角分组，而不是全局固定？
3. 多人片段使用检测追踪、区域约束还是人工选定主目标，才能保持可解释且不串人？

---

## REV-012 V1-R1 G4 CAUCAFall ADL 压力 Review

- 日期：2026-07-22
- 状态：Accepted for E1 public-data stress slice；V1-R1 milestone remains In progress
- 参与人：项目组、Codex
- 评审范围：公开负样本来源/许可、确定性准备、双变体姿态覆盖、代理混淆、性能和 parent/child 隐私边界
- 输入材料：[压力集设计](v1-g4-caucafall-adl-stress.md)、[正式报告](reports/v1-g4-caucafall-adl-stress.md)、实现提交 `336bbe9`、正式运行 `20260722T112332Z-f7970d63`

### 发现

1. CAUCAFall V4 以 CC-BY-4.0 提供；固定清单的 12 个 AVI 和元数据表均通过 file ID/URL、大小、SHA-256 与解码校验，prepared suite/lock 二次生成不漂移。
2. RTMPose person-box coverage 为 602/661（91.07%），高于 YOLO 的 540/661（81.69%）；但其关键点 gate 只通过 298/602（49.50%），304 帧必须 box-only。
3. RTMPose 在 clip-level no-fall ADL 中出现 17 个 horizontal bbox 帧，全部为关键点门失败的 box-only，最长 1000 ms；10 帧来自 kneel，其余涉及拾物、坐下、行走或画面边缘截断。YOLO 为 0。
4. 两个变体在无跌倒动作中都会激活 rapid descent 和 low motion。代理激活不是误报；当前没有 classifier、event label 或 alert 输出，禁止计算 false-positive rate。
5. 两个变体均快于实时。RTMPose pose RTF 为 0.125457，YOLO 为 0.061888；覆盖收益伴随约 2 倍纯推理成本。
6. Parent、24 个 child 和 1322 个 fall-motion events 均通过隐私审计；原始 bbox/keypoints 只存在于被忽略的 child pose events，风险/告警全为 false。

### 决定

1. 接受 CAUCAFall 12-case source manifest、准备器、dataset lock 和 `FallAdl*` 契约作为 G4 E1 回归资产。
2. 冻结“单帧 bbox horizontal 不得直接触发风险或告警”为 V2-D1 约束；所有组合逻辑必须在独立 held-out 集设计和验收。
3. 保留 RTMPose 为 conditional accuracy candidate，不因更高框覆盖晋级；关键点质量、C6c 域、剩余负样本和 HumanArt 分发仍是硬门。
4. 将拾物、坐下、跪地、行走和三档光照的公开 E1 压力子门标记完成；不将其外推到老人、C6c、空房、床上躺卧、宠物或多人。
5. G4 继续只发布可解释 feature/fallback；V1-R1 保持 In progress。

### 验证

- 自动化：59 passed；`pip check` 无 broken requirements；`compileall`、`bash -n`、CLI help 和 `git diff --check` 通过。
- 正式执行：Slurm job `1762`，L40，completed，exit `0:0`；parent 与 24 child 均为代码 `336bbe9`、clean、E1、completed。
- 数据：suite `37cf32e26361f679eb15528856e82e1014bc6e8c1257edcf9dea3079a0cf8277`；lock `f8bb837c07bb354beacb3cc51013b42edd10e54432ea25abd1def565e7c2f4b8`。
- 产物：parent manifest `95456e8424c26a15f0e13e8c0d0ea79c4602cf9661146f0a16986868cc107214`；report `455be03ab06dea4d99efc5eeedbd62c8680d2feed119f5eaa6bbe3d1fdbef331`。
- 隐私：父级敏感字段/绝对路径 0 命中；1322 个 fall-motion events 的原始框、关键点、phase label、参考转写、本地路径和 risk/alert true 均为 0。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 补空房、纯家具、床上躺卧、宠物和多人负样本；许可证不清时转为受控自采 | Codex / 待指定采集人 | 2026-07-27 | Partial：REV-015 已补静态 furniture/pet/multi-person；空场视频、躺卧、宠物移动和多人 tracking 仍 Open |
| 用 C6c 采集同配置白天/夜视、距离、遮挡和安全模拟跌倒正负样本 | 待指定 | 2026-08-01 | Open |
| 冻结 held-out 事件标注、组合决策和误触发/延迟口径 | 待指定 | 2026-08-03 | Open |
| 评测不依赖 HumanArt 训练条款的姿态候选 | Codex | 2026-07-25 | Done（REV-013；保留 fallback，分发仍 Open） |

### 未决问题

1. 床上躺卧、纯家具和 person-absent 数据应继续找明确许可的公开源，还是直接转为 C6c 受控自采？
2. C6c 固定机位是否需要 ROI/地面区域约束，且如何避免把该约束过拟合到单个房间？
3. 横卧持续、下降、低运动和人工确认应如何组合，才能在 held-out 集上形成可审计事件，而不是事后调阈值？

---

## REV-013 V1-M3/G4 Keypoint R-CNN 独立候选 Review

- 日期：2026-07-22
- 状态：Accepted E1 evidence；candidate retained as fallback；V1-R1 milestone remains In progress
- 参与人：项目组、Codex
- 评审范围：非 HumanArt 姿态候选、权重血缘、M2b 横卧覆盖、G4 关键点门、CAUCAFall no-fall 混淆、性能与隐私
- 输入材料：[候选设计](v1-m3-torchvision-keypointrcnn-candidate.md)、[正式报告](reports/v1-m3-torchvision-keypointrcnn-candidate.md)、提交 `eae5f56` / `d956203`、正式运行 `20260722T120654Z-d1d51960` / `20260722T120722Z-10fe9abb` / `20260722T121434Z-2e11f559`

### 发现

1. Keypoint R-CNN 在 M2b 为 163/170，lying 21/21；与 RTMPose 总覆盖相同，并多覆盖 1 个 lying 帧，但 ADL 少 1 帧。
2. 覆盖未转化为横卧关键点优势：候选 lying gate 仅 4/21，17 帧 box-only；RTMPose 为 11/20 和 9 帧 box-only。候选问题集中在横卧必需肩/髋点，而不是 not-lying。
3. CAUCAFall 上候选 coverage 为 621/661、gate 523/621，优于 RTMPose 的 602/661、298/602；但候选仍有 7 个 horizontal bbox、46 个 torso-horizontal、10 个 rapid-descent 和 313 个 low-motion 激活。
4. 候选 7 个 horizontal bbox 中有 5 个同时通过关键点门且 torso-horizontal，动作是无跌倒 kneel/walk。关键点门只证明几何字段可用，不证明事件为跌倒。
5. 候选 L40 推理 RTF 在 M2b/G4 分别为 0.100451/0.105836，满足 E1 实时回放；速度不是当前阻断项。
6. TorchVision 实现为 BSD-3-Clause，但官方预训练模型条款要求使用者审查关联数据集。COCO 逐图许可、ImageNet access/use 和比赛包权重再分发均未关闭；移除 HumanArt 不等于 license-cleared。

### 决定

1. 接受 Keypoint R-CNN frozen policy、adapter、三模型 runner、G4 派生接入和正式 E1 证据。
2. 候选状态固定为 `Conditional fallback / not selected`，不替换 RTMPose 当前条件参考，也不进入最终比赛包。
3. 不在 M2b 或 CAUCAFall 上继续调 0.5、800/1333 或 G4 阈值；下一轮只在预先冻结的 C6c held-out 集检验。
4. V2-D1 增加硬约束：单一 bbox-horizontal 不得告警；即使关键点门通过且 torso-horizontal，也不得直接告警。
5. HumanArt 与 Keypoint R-CNN 两条公开预训练路线的分发门都保持 Open；若不能关闭，转向权利清晰的数据和自有训练/导出权重。
6. V1-R1 继续 In progress，等待 C6c、剩余负样本、事件指标、最终分发路线和负责人。

### 验证

- 自动化：65 passed；`pip check` 无 broken requirements；`compileall`、`bash -n`、离线权重校验和 `git diff --check` 通过。
- 权重：237,034,793 bytes，SHA-256 `fc266e953d2b302cdcbb9ae66f71f6b0d4649928bf02dc573961e361e4918926`；policy `921883358f6f2b23f0760d9f9612213adb044f54c9ac3e6ae24c8225e186f8db`。
- M2b：job `1763`，L40，completed 0:0；parent + 18 child clean/E1/completed；report `9c2264b14140f4923c2ed28b6a5ec79ddffea6477f402822746137e05a6c964f`。
- CAUCAFall：job `1764`，L40，completed 0:0；parent + 36 child clean/E1/completed；report `369275b58a9148e32a58c25f36abefc8b566bd57be4533dea8684f991b3aaef4`。
- G4 派生：run `20260722T121434Z-2e11f559`，代码/source 均 clean、E1、completed；report `87a90bf1b8cb327e41702a2f8414bc237998e290a5775fa9a198bfb2b71d72c1`。
- 隐私：CAUCAFall 1983 个 fall-motion events 与 M2b 170 个派生 events 均无原始框、关键点或本地路径，risk/alert true 为 0。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 冻结 C6c held-out 场景/事件标注后复跑三候选，不在目标集调阈值 | 待指定采集人 / Codex | 2026-08-03 | Open |
| 确认比赛提交物是否包含权重及 COCO/ImageNet/HumanArt 再分发要求 | 待指定许可证负责人 | 2026-07-29 | Open |
| 若公开 checkpoint 均不能关闭分发门，冻结自有训练数据/模型路线 | 项目组 | 2026-08-05 | Open |
| 补空房、床上躺卧、家具、宠物和真实多人负样本 | 待指定采集人 / Codex | 2026-08-03 | Partial：REV-015 已补公开静态检测压力；C6c 视频与时序仍 Open |

### 未决问题

1. 比赛是否允许运行时下载但不随包分发权重，且该方式是否满足离线演示要求？
2. C6c 固定机位是否需要预先冻结 ROI/地面几何，还是先评测无 ROI 的域偏移？
3. 自有训练路线优先使用姿态估计 + 事件规则，还是直接训练带时间上下文的事件模型？

---

## REV-014 V1-M2c 采集包、标注与 Held-out Readiness Review

- 日期：2026-07-22
- 状态：Accepted for E1 tooling slice；V1-M2c / V1-R1 remain In progress
- 参与人：项目组、Codex
- 评审范围：manifest 1.1、场景/动作标注、包内文件完整性、媒体探针编排、双同步事件、三模型 held-out 冻结、两级 readiness 与隐私
- 输入材料：[采集包就绪门设计](v1-m2c-capture-readiness-gate.md)、[正式 E1 报告](reports/v1-m2c-capture-readiness-smoke.md)、实现提交 `8838168` / `6928ac8` / `542bddf`、文档提交 `6f1c02a`、正式运行 `20260722T131022Z-9e3b47dc`

### 发现

1. 原采集规程和 JSON 模板能指导人工，但不能阻止路径越界、占位摘要、场景元数据漂移、事后划分 held-out 或任意三个模型文件冒充冻结策略。
2. 新 gate 将 C01～C12 的 scenario、光照、夜视、距离、遮挡、person-presence 和必需动作标签绑定到 digest-bound policy；person-absent 不允许人物窗口，模拟跌倒必须同时具备安全垫、保护人员和清场。
3. 当前 E1 包的 C01～C10 均通过路径、摘要、媒体轨道、标注和策略结构检查，核心/full-matrix 缺口为 0；C02 的两个合成同步事件产生 start/end offset 0 ms 和 drift 0 ms/min。
4. 十个场景实际复用同一段无人合成 AVI，`duplicate_media_content_count=9`。这只证明结构代码；真实 manifest 中重复媒体摘要会阻断，工具也不检查画面是否真的发生标签动作。
5. 三个 variant 不再只按数量判断，而是分别绑定 YOLO、RTMPose 和 Keypoint R-CNN 的 ID 与当前 policy SHA-256；目标集首次推理必须晚于分区和标签冻结。
6. 子项名称固定为 `structurally_usable`，避免 E1 clip 被误读为已授权模型复测。父级四个真机门在正式 E1 run 中全部为 false，最终决定为 `tooling_only` / `partial`。
7. Readiness report 不复制输入路径、身份 ref、标注窗口或睡眠值；schema/路径失败也使用脱敏错误，不把 Pydantic 输入写入 failed manifest。

### 决定

1. 接受 manifest 1.1、`v1-m2c-capture-policy-v0.1.0`、`M2cCaptureReadinessReport` 和 `assess-m2c-capture` 作为 V1-M2c 真实采集入口。
2. 冻结两级推进：8 个核心 E2 clip + 双同步事件 + 三模型摘要打开 `camera_ready_for_model_retest`；C01～C10 与真实 SDNL1 样本再打开 `capture_bundle_ready_for_review`。后者只验收采集输入，不替代下游报告或 M2c 里程碑门。
3. 达到摄像头核心门后可先跑三姿态/FunASR，不等待睡眠字段医学语义；但不能把“可以复测”写成“M2c 已验收”。
4. E1、fixture、template、synthetic、fixture-marked JSON 或 synthetic acquisition 永远不能打开真机门；设备能力等级保持 E0。
5. 目标 held-out 集禁止按结果调现有阈值。任何阈值/模型策略变更必须形成新 policy revision，并把旧结果与新结果分开。
6. 本次只验收工具切片；标注内容抽查、三模型/ASR 实测、事件指标和设备字段仍 Open。

### 验证

- 自动化：70 passed；`pip check` 无 broken requirements；`git diff --check` 通过。
- 代码：`6f1c02a`，正式 run completed、E1、fixture、`code_dirty=false`，耗时 444 ms。
- 输入：capture manifest `d70a26f98a64f567c89ebb55dd19f46a4c40c49630a1b66c3df0a26a22608d6b`；policy `6c4fa5f4aa87fe2cb250c9645afff16f983271f4907fc293175fb0b224043384`。
- 产物：manifest `a8f8145036984f269f469a186ec45c200fd281c757223a99030c4701a159c246`；readiness report `2bd9595a4bad8b23331f1cc7ed2955fec0d5d254530e9c0548cdf274a9d5958d`。
- 结果：10/10 结构可用、1 个双事件 clip、3/3 模型策略、1/1 睡眠文件引用、0 error / 0 warning；四个真机门 false。
- 隐私：operator/participant ref、原始 clip 名、`data/raw`、本地绝对路径、fixture 姓名和设备序列号扫描均为 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 在首次模型推理前复制模板/策略并冻结 C6c held-out 分区 | 待指定采集人 | 2026-07-26 | Open |
| 按 C01～C10 取得同意媒体，先完成 8 clip 核心 gate | 待指定采集人 | 2026-08-01 | Open |
| 人工复核至少一个真实 clip 的开始/结束同步事件并形成 offset/drift | 待指定采集人 / Codex | 2026-08-01 | Open |
| `camera_ready_for_model_retest=true` 后按冻结参数复跑三姿态与 FunASR | Codex | 2026-08-03 | Blocked on E2 capture bundle |
| 获取真实 SDNL1 导出并依次运行 capture gate、profile 与 route gate | 待指定设备负责人 / Codex | 2026-08-01 | Open |
| 建立双人一致性/裁决/事件级误触发与检出延迟 E1 工具口径 | Codex | 2026-07-22 | Done（REV-016；真实内容抽查与指标仍 Open） |

### 未决问题

1. C6c 首批采集由谁执行，受控目录、同意记录和删除责任人分别是谁？
2. 真实容器双事件采用逐帧/波形人工标注，还是补自动峰值候选后人工确认？
3. 多人和宠物作为 C13+ 扩展场景加入同一 manifest revision，还是独立负样本包？

---

## REV-015 V1-R1 G4 Open Images 静态居家人物检测压力 Review

- 日期：2026-07-22
- 状态：Accepted for E1 static person-detection stress slice；V1-R1 milestone remains In progress
- 参与人：项目组、Codex
- 评审范围：公开来源/逐图许可、Person 负标签与多人框、人工对齐 Review、确定性准备、三模型 L40 结果、失败证据拒绝、隐私与能力边界
- 输入材料：[静态压力集设计](v1-g4-openimages-static-home-stress.md)、[正式报告](reports/v1-g4-openimages-static-home-stress.md)、实现提交 `40359c1`、标注审计修正 `fad9491`、报告提交 `c77525e`、正式 run `20260722T151348Z-a34b37b3`

### 发现

1. Open Images 标注固定为 Google LLC / CC BY 4.0；12 张 validation 图片逐一固定作者、标题、原始 Flickr landing page、CC BY 2.0 URL、页面检查日期、像素字节数和 SHA-256。官方免责声明意味着比赛展示/再分发前仍须逐图重审。
2. job `1765` 虽然执行成功，但 post-run 视觉复核发现 wheelchair case 有一个明显人物未被 Person boxes 覆盖，会把正确检出误计为 FP。本次 Review 拒绝该 run，并以 r2 suite ID/source digest 隔离替换数据；“程序 completed”不等于“证据可接受”。
3. r2 新增 `visible_person_count == expected_person_box_count` 和多人逐框视觉对齐硬门。12-case、16 个 source file、14 个 processed artifact 连续准备两次摘要不漂移。
4. 正式 job `1766` 中，RTMPose / YOLO / Keypoint R-CNN 的 person-absent 激活分别为 2/8、3/8、3/8；家具组分别为 2/4、2/4、1/4，宠物组为 0/4、1/4、2/4。三模型都不是静态负样本零激活。
5. 多人子集共有 11 个框。RTMPose 与 Keypoint R-CNN 均 matched 11/11，但分别有 2、3 个多人 FP；YOLO 为 9/11、0 FP，远距离会议室 case 输出 0 框。覆盖、干净度和远距离检测存在明确权衡。
6. sofa-toy 使三模型都激活；报告不保存预测坐标，因此其他 case 的具体误检对象不能从汇总反推。该设计保护隐私但限制错误可视化，后续 C6c 受控 Review 需另设短期、受限访问的可视化流程。
7. 三模型冻结阈值没有针对 12 图调整。RTMPose 当前结果最好地平衡了静态负激活与多人召回，但 HumanArt 分发、C6c、床上躺卧、宠物移动、多人 tracking 和事件指标仍未关闭，不能据此晋级最终比赛模型。

### 决定

1. 接受 r2 source manifest、attribution、dataset lock、`StaticHome*` 契约、静态 runner 和 job `1766` 为 G4 E1 静态人物检测回归资产。
2. job `1765` 固定为 rejected evidence：保留审计记录但不进入正式指标、模型比较或里程碑数值。
3. RTMPose 继续作为 conditional accuracy candidate，Keypoint R-CNN 继续作为 fallback，YOLO 继续作为 V1 对照；本轮不改变 REV-013 的最终选型状态。
4. 不在本 12 图上调整 0.35 / 0.05 / 0.5 阈值或增加 checkpoint；下一次参数决定只能在预先冻结的 C6c held-out 视频上形成新 policy revision。
5. 静态 false activation 与 IoU box matching 不得写成跌倒误报率、事件 recall、多人 tracking 或 C6c 精度；所有 risk/alert 字段继续硬编码为 false。
6. 将 furniture/pet/multi-person 静态人物检测子门标记完成；空场持续、床上躺卧、宠物移动、真实多人 tracking、跌倒正样本和事件指标仍 Open，V1-R1 保持 In progress。

### 验证

- 自动化：78 passed；`pip check` 无 broken requirements；`compileall`、`bash -n` 与 `git diff --check` 通过。
- 正式执行：Slurm job `1766`，L40，completed `0:0`，16 s；parent + 36 child 均为 `fad9491`、clean、E1、completed，36/36 tracking false。
- 数据：source manifest `434126ff0919dabed9ee40d702d71993fd8b5866d6c46162fa1441c8c2acfcd0`；suite `e62b34dbf093253e240bf780a85105caaf0ade09e722415a85136ba330340470`；attribution `fbcbec44f0276e09f6567d2c00d5c4cae0a9529de59ebf8e6e10c4f072e55efd`；lock `7568e4b8c49f4e8629a151c9dd05d2ff67ff08a030b1e84ec16bfa8c647b3f94`。
- 产物：parent manifest `6e3e3ef711cc9f70edd9e8b57b698f3dc734d5c669a29fb5b36e6dadfd590aed`；report `fafafe109afcfafe5c946653371db4a06418399aa14664c1506c34dc2f777945`；41/41 parent steps completed，0 error / 0 warning。
- 性能：YOLO / RTMPose / Keypoint R-CNN mean inference 115.749 / 88.695 / 63.434 ms；peak CUDA allocation 65.532 / 43.137 / 742.249 MiB；静态值不替代视频 RTF。
- 隐私：parent + 36 child report/SourceAsset 中 bbox、keypoints、track ID、绝对路径、原始 landing/作者页、risk/alert true 均为 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 按 REV-014 获取 C6c 核心包并在首次推理前冻结 held-out 与三模型 policy | 待指定采集人 / Codex | 2026-08-01 | Open |
| 在 C6c 扩展包增加空场持续、床上躺卧、宠物移动和真实多人 tracking 场景 | 待指定采集人 | 2026-08-03 | Open |
| 为受控错误可视化定义最小留存期、访问人和删除审计，不把 bbox 发布到父报告 | 项目组 | 2026-08-03 | Open |
| 比赛展示/再分发前重新访问 12 个 landing page 并生成最终 attribution / NOTICE | 待指定许可证负责人 | 2026-08-29 | Open |

### 未决问题

1. C6c 视频 person-absent 口径按每帧、每分钟激活还是持续事件计数，如何避免把单帧静态比例误搬到时序？
2. 多人策略采用全体风险候选、区域主目标还是 track-aware 人工确认，怎样处理进出画与遮挡？
3. 若低阈值 RTMPose 在 C6c 继续保持召回但产生更多 FP，应先做场景/时序过滤，还是重新训练许可清晰的 detector？

---

## REV-016 V1-R1 G4 双标注、裁决与事件评估工具 Review

- 日期：2026-07-22
- 状态：Accepted for E1 tooling slice；真实 C6c 事件指标与 V1-R1 milestone remain In progress
- 参与人：项目组、Codex
- 评审范围：独立动作区间、pairwise agreement、裁决、held-out 顺序、candidate episode 评测、来源血缘、事件指标、隐私与 Risk/Alert 边界
- 输入材料：[事件评估设计](v1-g4-event-evaluation-readiness.md)、[正式 E1 报告](reports/v1-g4-event-evaluation-smoke.md)、实现提交 `b0b2e97`、正式 run `20260722T160819Z-854d8845`

### 发现

1. M2c capture/readiness 与 G4 feature 之间原先缺少事件评测层。本轮形成严格 bundle：capture manifest/readiness/clean assessor run、两份以上 independent annotation、adjudication、candidate-generator policy、三路 predictions/clean source runs 都以相对路径、大小和 SHA-256 绑定。
2. 当前 policy 比较 `bend_pick`、`bed_lie`、`simulated_fall`；interval IoU 0.5、overall/fall pairwise F1 0.8、fall 平均绝对 onset 差 500 ms。正式 fixture 两份标注 5/5 匹配，overall/fall F1 均 1.0，fall onset 平均/最大差均 100 ms。
3. Event matching 使用 candidate `detected_at` 与 adjudicated fall 一对一匹配，冻结 early 500 ms / late 2000 ms。父报告同时发布原始 TP/FP/FN、总暴露 false activations/hour、negative-clip activation 和 delay 摘要，避免只展示一个比例。
4. Fixture 的 12 clip/36 秒包含 2 fall 与 10 negative。手工固定候选被准确还原为 RTMPose 2TP/1FP/0FN、Keypoint R-CNN 2/2/0、YOLO 1/1/1。它们只验证 scorer 公式，没有运行三种模型，不能进入模型比较。
5. Candidate generation 与 evaluator 已分离。三路预测必须绑定同一 candidate-policy 摘要和各自 frozen model policy；本轮 candidate policy 明确为 synthetic/no-inference，未把横卧/下降/静止组合规则偷渡成最终跌倒判定。
6. annotation、agreement、adjudication、minimum-data 和 provenance 五个工具门均 true；M2c camera gate 因 E1 synthetic 为 false，最终固定 `tooling_only`、`event_metrics_ready_for_review=false`。0 error、2 个 warning 都是预期证据边界。
7. 父报告不含 annotation/candidate 时间、candidate ID、annotator/adjudicator ref、输入路径、bbox/keypoints/track ID；RiskAssessment 与 Alert 继续 Literal false。

### 决定

1. 接受 `FallEventAnnotationAgreement`、`FallEventCaseEvaluation`、`FallEventVariantEvaluation`、`FallEventEvaluationReadinessReport`、CLI 和 evaluation policy，作为 C6c E2 数据到位后的 M7 统一入口。
2. 接受 v0.1.0 的 interval/onset agreement、one-to-one detection-time matching、总暴露 FP/hour 与 negative-clip activation 口径。修改 tolerance、去重 episode 语义或分母必须升级 policy/version 并全量重跑。
3. 保持 candidate-generator policy 独立；只有其完成真实规则 Review 后才能生成可解释的 C6c candidate stream，evaluator 不负责设计或调参规则。
4. E1 fixture 三行指标不得写入姿态模型选型、跌倒性能、C6c 域内表现或比赛宣传；本 Review 只关闭 scorer tooling 子门。
5. `event_metrics_ready_for_review` 只表示真实指标可交人工 Review，不等于模型采用、RiskAssessment 设计完成或 Alert 授权。
6. V1-R1 保持 In progress：真实 C6c 正负视频、内容抽查/裁决责任、真实 candidate policy/指标、多人 tracking、分发许可证和责任人仍 Open。

### 验证

- 自动化：85 passed；`pip check` 无 broken requirements；`compileall` 与 `git diff --check` 通过。
- 正式执行：run `20260722T160819Z-854d8845`，commit `b0b2e97`、clean、completed、E1、fixture；scorer step 18 ms，15 个摘要化 SourceAsset。
- 可重复性：独立生成两份完整 fixture，32/32 相对路径与 32/32 SHA-256 一致。
- 输入：bundle `d68376b30b5ff9bec52a36d892a93f074c338647fb1ef812870d089c455aa8dd`；evaluation policy `91e35f8637ea2520e07f07b65f5f3fac2122fd399dd53bb921839594480283d8`；capture `8bf5af9ad0c08a6c65ef799d04fbe098f3937f9a1b2299f6167054157a815595`；candidate policy `dae72d3a967cd752ebc3100b13f04a073ff79bd4cd3ef3574322630c0082bfdc`。
- 产物：formal manifest `3e064dd6df04d047236b6ad9b53202e4db97bd7a97ffd127e220a7c95f3ec75d`；readiness report `8cde985ce61970d5b86c7042400c351b98b0615fc0bc6b4812d6829380865915`。
- 隐私：原始时间字段、candidate/annotator/adjudicator ref、相对/绝对路径、risk/alert true 均为 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 按 REV-014 取得含 C11/C12、弯腰、床上躺卧和空场持续的 C6c E2 held-out 包 | 待指定采集人 | 2026-08-01 | Open |
| 指定两名独立标注者与裁决人，完成内容抽查、访问控制和删除责任记录 | 项目组 | 2026-08-02 | Open |
| 在不查看 held-out 输出的前提下设计并 Review 第一版真实 candidate-generator policy | Codex / 项目组 | 2026-08-02 | Blocked on E2 capture and owner decision |
| 用同一 candidate policy 生成三路 clean candidate run 并执行真实 event evaluation | Codex | 2026-08-03 | Blocked on prior actions |
| 将真实多人 tracking/身份切换策略与事件 episode 去重规则一起评审 | 项目组 | 2026-08-04 | Open |

### 未决问题

1. 真实 candidate episode 的触发点取首次满足规则、持续确认完成还是回溯 onset；三者会直接改变 delay 语义，必须在看 held-out 结果前冻结。
2. 多人在同一 clip 中是每人独立 candidate、场景级 candidate，还是人工确认队列；当前单路 episode 契约尚未表达 person/track 归属。
3. 比赛验收更关注每小时 FP、每夜/每日 FP，还是 negative-clip activation；C6c 真实暴露时长到位后再冻结对外主指标。

---

## REV-017 首版 G4 Candidate Episode Policy 与公开压力 Review

- 日期：2026-07-23
- 状态：Accepted
- 参与人：项目组、Codex
- 评审范围：首版非 fixture 候选生成策略、episode 状态机、来源 fail-closed、公开开发压力与 C6c held-out 前冻结边界
- 输入材料：[候选 episode 设计](v1-g4-fall-event-candidates.md)、[正式公开压力报告](reports/v1-g4-fall-candidate-public-stress.md)、实现提交 `dc6cace`、正式运行 `20260722T165156Z-3dd84457`

### 发现

1. Candidate generation 已从 event evaluator 中保持独立。生成 API 只接收 `FallMotionFrameValue`，不接收 benchmark case、phase annotation 或 action label；标签在全部 episode 生成后才进入 E1 汇总。
2. Policy 在查看未来 C6c held-out 输出前冻结：transition 为 600 ms horizontal + 1500 ms 内 rapid descent；settled fallback 为 1200 ms horizontal + low motion；gap 450 ms、release 600 ms、refractory 3000 ms，track 缺失/变化清空时序状态。
3. 三模型 × 18 case 共 54 项公开压力中，YOLO/RTMPose/Keypoint R-CNN 的 URFD simulated-fall 激活分别为 0/3、1/3、3/3。结果强依赖上游姿态/track，不支持把一个规则的表现外推到另一 variant。
4. 15 个 negative case/variant、149,868 ms 曝光中，YOLO 和 Keypoint R-CNN 都是 0 episode；RTMPose 在 CAUCAFall `s01-walk` 产生 1 个 transition episode，即 24.021139 episodes/hour。分母只有约 2.5 分钟，不能称长期家庭误报率。
5. 5 个 episode 全部来自 transition 路径，settled fallback 为 0。该结果不构成删除或采用 settled 路径的依据，后续必须在床上躺卧、地面停留和 C6c 困难负样本上原样评估。
6. Keypoint R-CNN 的 3/3 不能覆盖 lying keypoint gate 4/21、CAUCAFall torso-horizontal no-fall 反例和权重分发门；RTMPose 的 1/3 + 行走负候选也不能推翻其现有条件准确率候选身份。公开开发压力不用于最终模型排名。
7. 正式 run 为 clean、completed、E1、0 issue；登记 127 个摘要化 SourceAsset，生成 5 个可反查来源 feature 的 derived-sensitive episode。三次独立执行的父报告 SHA-256 完全一致。
8. 父 manifest/report/SourceAsset 不含本地路径、候选窗口、candidate ID、track ID、bbox 或 keypoints；RiskAssessment 与 Alert 继续 Literal false。

### 决定

1. 接受 `v1-g4-event-candidate-policy-v0.1.0`、`FallEventCandidatePolicy`、`FallEventCandidateEpisode`、状态机、公开压力报告契约、CLI/Make 入口和严格 source hierarchy 校验，作为 V1 首个非 fixture candidate-generator 基线。
2. 冻结 transition/settled 路径、起点回溯、release、refractory、track/gap reset 和 transition 优先语义。修改任一语义必须升级 policy/version 并全量重跑，禁止在看到 C6c held-out 输出后原地调参。
3. 将 REV-016 中“设计并 Review 第一版真实 candidate-generator policy”行动项标记为已由本 Review 关闭；它不再 blocked on E2 capture。目标域准确性与事件指标仍 blocked on C6c E2 capture/annotation。
4. C6c 首轮三路 G4 feature 必须原样使用 policy digest `380151c86ddaf6b79328ca516a778111fe8a7b2c2caa61e209a055bc8942dd08`，再以同一 digest 进入 REV-016 event evaluator。
5. 保持模型决定不变：YOLO 为 V1 对照，RTMPose 为有条件准确率候选，Keypoint R-CNN 为未选 fallback；本切片不授权最终选型或权重分发。
6. 不将公开结果表述为 precision、recall、F1、灵敏度、特异度、C6c 准确率或独立泛化；candidate episode 也不授权 RiskAssessment 或 Alert。
7. V1-R1 保持 In progress；C6c 正负/床上躺卧/空场持续/宠物/多人、双标注裁决后的事件指标、许可证和负责人仍是硬门。

### 验证

- 自动化：94 passed；`pip check` 无 broken requirements；`compileall` 与 `git diff --check` 通过。
- 正式执行：run `20260722T165156Z-3dd84457`，commit `dc6cace`、clean、completed、E1、0 issue；54 个 variant/case evaluation，127 个 SourceAsset，5 个 episode。
- 策略摘要：candidate policy `380151c86ddaf6b79328ca516a778111fe8a7b2c2caa61e209a055bc8942dd08`；fall feature policy `3bedf218e9e413c1ab168134b8333db5cdebf764d5f8c9ece65ba212ea9d5eda`。
- 正式产物：manifest `19abd1d4776450022b350497c52bbb12aa55629d46666a1038323999317c42d6`；父报告 `797974b75b6e16be86d4e836d8045ec2c6ca5dc2b53d0631c9a80759735e7d83`。
- 可重复性：两次开发运行与一次正式运行的父报告 3/3 SHA-256 一致。
- 隐私：manifest/report/SourceAsset 中本地路径、候选 start/end/detected、candidate/track ID、bbox/keypoints、risk/alert true 均为 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 按 REV-014 取得含 C11/C12、床上躺卧、空场持续与安全模拟跌倒的 C6c E2 held-out 包 | 待指定采集人 | 2026-08-01 | Open |
| 指定两名独立标注者与裁决人，完成内容抽查、访问控制和删除责任记录 | 项目组 | 2026-08-02 | Open |
| 对 C6c 三路 clean G4 feature 原样执行 frozen candidate policy | Codex | 2026-08-03 | Blocked on E2 capture |
| 以同一 candidate-policy digest 生成 event bundle 并执行 REV-016 scorer | Codex | 2026-08-03 | Blocked on capture and annotation |
| 单独评审多人 candidate 归属、身份切换和跨 track episode 去重 | 项目组 | 2026-08-04 | Open |

### 未决问题

1. 当前 largest-bbox 只能形成场景级单主目标 candidate；C6c 多人数据到位后，是升级为 per-person episode 还是继续场景级人工确认队列？
2. 比赛对外主指标最终采用 episodes/hour、negative-clip activation 还是每夜/每日误触发；必须在真实曝光和评分细则到位后冻结。
3. 如果 frozen policy 在 C6c 上失败，是降级为人工姿态证据工具，还是在独立开发集上设计 v0.2.0 并保留 C6c held-out；不能用同一 held-out 既调参又报最终指标。

---

## REV-018 G4 Capture Feature 到 Candidate Export Bridge Review

- 日期：2026-07-23
- 状态：Accepted for E1 production-interface tooling；V1-R1 remains In progress
- 参与人：项目组、Codex
- 评审范围：capture-bound feature/prediction 公共契约、candidate exporter、上游来源门、rule-bearing fixture、REV-016 scorer 兼容、隐私与真实设备边界
- 输入材料：[导出桥接设计](v1-g4-candidate-export-bridge.md)、[正式 E1 报告](reports/v1-g4-candidate-export-bridge.md)、实现提交 `a57b8ee`、正式 scorer run `20260722T172634Z-59174d4c`

### 发现

1. REV-016 的 prediction schema 原为 evaluator 私有类，REV-017 public runner 又绑定 URFD/CAUCAFall 专用来源，真实 C6c feature 到位后仍需人工拼 candidate JSON/run manifest。本轮将 exact prediction 提升为公共 `FallCandidatePredictionSet`，字段与 scorer 保持兼容。
2. `FallFeatureCaptureSet` 将一个姿态 variant 的 capture/model/feature policy、source run、clip order/duration、observation、逐流相对路径/大小/摘要/frame count 固定成显式契约。路径越界、artifact 未绑定、时间顺序、证据、代码或配置漂移均 fail closed。
3. Exporter 不读取 annotation/adjudication，只把经验证的 `FallMotionFrameValue` 送入已冻结状态机；输出 source manifest 自动绑定 scorer 所需六项摘要和上游 feature run/set。评测层继续不执行候选规则，两侧责任仍分离。
4. Fixture policy 现在区分 scorer-only 与 rule-bearing：前者可无规则但不能生成；后者必须同时具备 transition/settled/state-machine。正式 bridge fixture 使用与真实 v0.1.0 相同的规则值，但 fixture marker 使其 policy SHA-256 独立为 `b426f823eb72f034b2bd1f2f6613b2c1c86be5d005680e0cd0d8334da04124a3`，没有伪装成真实 policy evidence。
5. 干净提交 `a57b8ee` 上，YOLO/RTMPose/Keypoint R-CNN fixture source 分别提供 92/96/100 个 frame，真实 exporter 生成 2/3/4 个 episode。三个 candidate run 均 clean/completed/E1、0 issue、各 16 个 SourceAsset。
6. 原 REV-016 scorer 无需特殊分支即读取新 prediction/source run，输出 TP/FP/FN 为 1/1/1、2/1/0、2/2/0；annotation、agreement、adjudication、minimum-data 和 provenance 五门通过。camera/E2 门按设计关闭，最终仍为 `tooling_only`。
7. 篡改 JSONL 会在下游 run 创建前失败。12 个聚合 manifest/report/assets 的隐私扫描中，绝对路径、candidate 时间/ID、observation/track、bbox/keypoints 和 risk/alert true 均为 0；exact episode 仅留在被忽略的 derived-sensitive prediction。
8. 该 fixture 不运行任何 pose backend；三模型名只验证 variant/model-policy binding，2/3/4 候选是预构造 activation layout，不能解释为模型差异或 C6c 性能。

### 决定

1. 接受 `FallFeatureCaptureSet`、公共 `FallCandidatePredictionSet`、timestamp-free `FallCandidateExportSummary`、`export-fall-candidates` CLI、strict provenance 和 rule-bearing 三路 fixture，作为 G4 production interface 基线。
2. 冻结上游 stage `v1-g4-fall-feature-capture`、下游 stage `v1-g4-fall-event-candidates`、source-run 根目录相对路径语义，以及 capture/model/feature/candidate/prediction 摘要绑定；修改时必须走契约版本升级。
3. 保持 scorer-only fixture，不用 rule-bearing fixture 替换公式级回归。前者验证评分边界，后者验证生产接口；两者都只属于 E1 tooling。
4. 真实 C6c 执行必须使用非 fixture candidate policy SHA-256 `380151c86ddaf6b79328ca516a778111fe8a7b2c2caa61e209a055bc8942dd08`；不得复用 fixture policy digest，也不得看到 held-out 输出后改阈值。
5. 下一开发切片优先实现通用 capture G4 feature producer；之后补通用 event-bundle assembler。当前 bridge 完成不代表已有真实 video-to-feature 或完整真实 bundle 自动化。
6. 模型状态不变：YOLO 为 V1 对照，RTMPose 为有条件候选，Keypoint R-CNN 为未选 fallback；许可证、多人物和 C6c 事件指标仍是硬门。
7. RiskAssessment 与 Alert 继续 Literal false，V1-R1 保持 In progress。

### 验证

- 自动化：97 passed；`pip check` 无 broken requirements；`compileall`、全部 shell/sbatch `bash -n` 与 `git diff --check` 通过。
- Candidate runs：`20260722T172633Z-02e4b8ff`、`20260722T172633Z-c2ad7e03`、`20260722T172633Z-4ae20581`；均为 `a57b8ee`、clean、completed、E1、0 issue。
- Scorer：run `20260722T172634Z-59174d4c`；manifest `427f8c6beccdc047a81189cbb3c1efd20dd190e3f0e03b71e0791320dc83bdab`；report `ead63c22f96478f0a474cb37b30778c65bd6a0a48d6a7c56d4374e9efec82057`；provenance true、decision `tooling_only`。
- 输入：bundle `0937ee8031d796134de8cd3b14dad2308d0590cd457434a161be23d2c599a1e7`；fixture candidate policy `b426f823eb72f034b2bd1f2f6613b2c1c86be5d005680e0cd0d8334da04124a3`。
- 隐私：12 个聚合文件的本地路径、精确 episode/candidate/track/observation、bbox/keypoints 与 risk/alert true 均为 0；三 summary 时间字段为 0。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 实现通用 `v1-g4-fall-feature-capture` producer，消费 frozen capture/pose 输出并写本桥接 feature-set/JSONL | Codex | 2026-07-24 | Closed by REV-019；L40 evidence tracked there |
| 实现真实 event bundle 的通用组装/摘要验证入口 | Codex | 2026-07-25 | Closed by REV-020 |
| 按 REV-014 取得 C6c E2 held-out capture，并指定独立标注/裁决责任人 | 待指定采集人 / 项目组 | 2026-08-02 | Open |
| 对三路真实 clean feature run 原样执行 frozen candidate policy 与 REV-016 scorer | Codex | 2026-08-03 | Blocked on capture and annotation |
| 评审多人 per-person/场景级 candidate 归属与跨 track 去重 | 项目组 | 2026-08-04 | Open |

### 未决问题

1. 通用 capture producer 是直接重放原始 clip，还是先消费一个独立 pose-capture run；必须保证 pose policy、feature policy 和 clip 时序只计算一次且可审计。
2. 真实 bundle assembler 是否复制 derived-sensitive prediction 到受控 bundle，还是只允许同一受控根目录内引用；需要结合数据保留策略冻结。
3. C6c 多人物场景是否继续 largest-bbox 场景级候选；本桥接保持现有语义，没有提前替项目组做身份策略决定。

---

## REV-019 G4 Capture Pose 到 Fall Feature Producer Review

- 日期：2026-07-23
- 状态：Accepted for E1 production-interface tooling；V1-R1 remains In progress
- 参与人：项目组、Codex
- 评审范围：capture/readiness 到真实姿态 backend、G4 frame feature、`FallFeatureCaptureSet`、tracker reset、来源/标签隔离、三模型绑定、隐私与 C6c 边界
- 输入材料：[producer 设计](v1-g4-fall-feature-capture.md)、[正式 E1 报告](reports/v1-g4-fall-feature-capture.md)、实现/修复 `7a8dc23` / `b233abe` / `b4b72f7` / `243cef3` / `d1d4b5a` / `8b4b52d`、L40 job `1776`

### 发现

1. REV-018 已冻结 exporter 的 `FallFeatureCaptureSet` 输入，但当时三路 feature source 是预构造 fixture，没有从 capture media 执行真实 pose backend。本 producer 补齐“verified capture clip → pose event → G4 fall-motion frame → feature set/report”，不改变 candidate/evaluator 契约。
2. `load_m2c_inference_context` 只向推理层暴露 opaque clip/scenario、duration、媒体 path/size/digest 和当前 variant policy；participant/operator、场景文字、expected-person、annotation window 与同步标签不进入 backend 或 extractor。
3. Readiness report/run、capture/model/feature policy、媒体路径/大小/摘要在下游 run 前严格重验。fixture 必须 E1；真实输入还必须打开 E2 camera gate；dirty/unknown/不完整 assessor、不可用 clip 和 first-inference 顺序漂移均失败。
4. 每个 clip 前强制 `backend.reset()`，逐采样帧先写 `video.pose_frame`，再调用现有 `FallMotionFeatureExtractor` 写 `video.fall_motion_frame`。精确 bbox/keypoints/track 仅留在 derived-sensitive run；父 report/set 只保存摘要与 artifact digest。
5. YOLO 与 Keypoint R-CNN 的 tracking 在 pose binding 内声明；RTMPose 使用独立 `short_term_pose_tracking` binding。初版 producer 只接受 inline `tracking=true`，导致 RTMPose CPU preflight 在模型推理前被误拒；`b233abe` 接入 explicit 表示，`b4b72f7` 再冻结为“一个 inline 或一个 enabled explicit”的互斥门，同时拒绝无、混合或多个 tracker。
6. Fake backend 集成验证 12 个 clip、180 帧、12 次 tracker reset，生成 feature set 后可被 REV-018 exporter 原样消费且 0 candidate。媒体/模型摘要漂移和任一 unusable clip 均在 run 前 fail closed。
7. YOLO、RTMPose、Keypoint R-CNN 三个真实 CPU backend 已分别完成 12 clip / 180 frame preflight；synthetic timing clip 不含人物，因此 people/tracked 为 0，结果只验证 adapter 和 artifact，不是模型覆盖率。
8. clean `d1d4b5a` / job `1776` 在同一 NVIDIA L40 上完成三个独立 run：均 completed、E1、0 issue、180 frame、0 people/tracked；replay RTF 为 0.088889～0.114637。0-person 是输入事实，只能验证 replay/backend/artifact。
9. job `1769` 因 cuDNN 动态链接失败；job `1772` 虽功能完成，但 run/JSONL 为 `0755/0644`，两者均未被接受。`243cef3` 关闭 runtime 问题，`d1d4b5a` 关闭单个 run 内权限。正式 job `1776` 的三 run 树与 stdout 才通过 owner-only 门；RTMPose 的 Torch peak 0 不代表 ONNX Runtime 或整卡峰值。
10. 三个 job `1776` feature set 随后由 clean `8b4b52d` 原样进入 exporter、assembler 和独立 scorer。`8b4b52d` 是审计发现 `--runs-dir` 根仍为 `0755` 后的修复；旧下游结果不通过事后 chmod 升级。正式三路均 0 candidate；owner-only bundle 16 个文件，provenance true、preflight 与 scorer report 同 SHA，decision 仍为 `tooling_only`。

### 决定

1. 接受 `v1-g4-fall-feature-capture` stage、单 variant run、每 clip tracker reset、pose/fall 双事件与 `FallFeatureCaptureSet`，作为 E1 production-interface tooling 基线。
2. 冻结 label-blind inference context；producer 不得读取 annotation/adjudication、expected-person 或 candidate policy，也不得根据输出自动调阈值。
3. 接受 inline/explicit 两种 tracking binding 表达，但必须恰好形成一个短时 tracking 能力；缺失或含糊 tracker 继续 fail closed。
4. fixture producer 输出只能作为 E1 production-interface tooling。0-person synthetic 结果不得写成人物漏检、跌倒召回、模型排名或 C6c 性能。
5. 真实执行顺序保持：M2c camera gate → 三路 clean feature producer → frozen candidate exporter → REV-020 assembler → REV-016 scorer。任何一步不得绕过上游 digest。
6. 本层固定不执行 candidate、RiskAssessment 或 Alert；模型采用/许可证状态不改变，V1-R1 保持 In progress。

### 验证

- 自动化：最终代码 118 passed，tracker 定向回归 3 passed，权限/CLI/multimodal/producer 定向回归 26 passed；`compileall`、全部 shell/sbatch `bash -n`、`pip check` 与 `git diff --check` 通过。
- Fake integration：12 clips、180 frames、12 resets，feature-set → exporter 兼容，0 candidate。
- CPU real-backend preflight：YOLO / RTMPose / Keypoint R-CNN 均完成 12 clips / 180 frames；输入无人物，people/tracked 为 0。
- L40：job `1776`；run `20260722T203258Z-6dbbf02b` / `20260722T203304Z-f054ad75` / `20260722T203311Z-1bbc5123`；均为 clean `d1d4b5a`、completed、E1、0 issue、12 clips / 180 frames，run/文件/stdout 权限为 `0700/0600/0600`。
- 端到端工程链：clean `8b4b52d` candidate runs `20260722T204234Z-8c8c1b75` / `20260722T204234Z-7e1eca98` / `20260722T204234Z-135cad7f`；bundle `1126a3a274696aa930cd7d4d5dd808ee156bbc0ae95417b38b8f75bc03aa459b`；scorer `20260722T204309Z-8b5b09f3`，report/preflight `26b58c13b41ed1313082508ca91586c50b289c0e136e5b6361ecd41dfb9bc3e9`。
- 隐私：三 producer 聚合产物及下游 aggregate 对本地路径、用户名、精确姿态与 Risk/Alert true 均 0 命中；exact feature/prediction/annotation 留在 ignored 或 owner-only 边界。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 完成三真实 backend L40 clean smoke 与正式报告 | Codex | 2026-07-23 | Closed；owner-only job `1776` |
| 将三路 clean feature set 原样送入 REV-018 exporter | Codex | 2026-07-24 | Closed for E1 tooling；3 clean candidate runs |
| 用 REV-020 assembler 组装 exporter 输出并复跑 REV-016 scorer | Codex | 2026-07-24 | Closed for E1 tooling；preflight/scorer identical |
| 取得 C6c E2 held-out capture 与独立 annotation/adjudication | 待指定采集人 / 项目组 | 2026-08-02 | Open |

### 未决问题

1. 真实多人 clip 是否继续 largest-bbox 场景级单目标，还是升级 per-track feature set；当前 producer 保留既有单主目标 G4 语义。
2. 真实长视频按 clip reset 可避免跨场景身份污染，但连续直播的 tracker/session reset 条件仍需 V2-D1 冻结。
3. 三模型在真实 C6c 上若产生不同有效帧数，先按哪个 upstream quality gate 判定“可评分”；不能用 event 结果反向修改 held-out 门。

---

## REV-020 G4 Event Evaluation Bundle Assembler Review

- 日期：2026-07-23
- 状态：Accepted for E1 controlled assembly tooling；V1-R1 remains In progress
- 参与人：项目组、Codex
- 评审范围：真实 event evaluator 输入组装、相对路径/摘要、owner-only staging、原子发布、原 evaluator preflight、隐私与 readiness 边界
- 输入材料：[组装器设计](v1-g4-event-bundle-assembly.md)、[正式 E1 报告](reports/v1-g4-event-bundle-assembly.md)、实现提交 `7b64719`、证据提交 `07d7edd`

### 发现

1. REV-018 关闭了 feature-to-candidate 接口，但真实 scorer 仍需人工把 capture/readiness、两份标注、裁决、candidate policy 与三路 prediction/source manifest 拼成 bundle。人工复制容易产生路径越界、摘要漂移、variant 重复或 prediction/run 错配。
2. Assembler 先在随机 staging 中复制 13 个显式输入，统一生成规范化 bundle-relative 路径、SHA-256 和大小；不复制 capture 原媒体，也不从输入内容推断额外文件。全部目录固定 0700、文件固定 0600。
3. staging 必须调用 REV-016 原 evaluator 完成 strict preflight 后才能原子发布；失败时删除 staging，不保留半成品，不覆盖已存在输出。Assembler 没有复制或弱化 evaluator 的 annotation、agreement、adjudication、minimum-data、provenance、camera/E2 gate。
4. clean `7b64719` 正式组装生成 16 个文件，bundle SHA-256 `3a8c7be99b4946f99780793ff761b99e1a7bb1794e1c6a137eb2a9ea7b842331`，assembly report SHA-256 `8d1216dda24d30ecaf4dbb9bfda8c4239f2b5c33bde2b7916861de0dc77cb5f2`；权限审计为 16/16 文件 0600、全部目录 0700。
5. 内置 preflight 为 `tooling_only`、provenance true、event ready false。随后从独立 clean main `b233abe` 对发布 bundle 复跑 scorer，run `20260722T182727Z-5e95a5f8` completed、0 issue、15 个 SourceAsset，report SHA-256 `e96d676cf17aa92b639c65cc41602a536e95d774368bb0fa906a0321d5965327` 与内置 preflight 逐字节一致。
6. annotation 顺序按内容摘要稳定化；重复 variant、prediction/source run ID 错配、capture/policy/source type 漂移、已存在输出和 late preflight failure 均 fail closed。聚合 report 不含 annotation/candidate window、annotator ref、本地路径、bbox 或 keypoints。
7. 本轮输入仍是 deterministic fixture。组装成功只表示 bundle 结构和来源可被原 evaluator 接受，不表示 camera gate、真实事件指标、模型晋级、RiskAssessment 或 Alert 已授权。

### 决定

1. 接受 `assemble-event-evaluation-bundle` CLI、`FallEventBundleAssemblyReport`、owner-only staging、原子发布和 evaluator preflight 复用，作为 REV-016/018 的受控输入组装基线。
2. 冻结“只复制显式证据、不复制原媒体、不覆盖输出、preflight 后发布”的边界。不得增加跳过摘要、跳过权限或 `--force` 快捷路径。
3. Readiness 的唯一语义来源继续是 REV-016 evaluator。Assembler report 只能镜像 preflight decision，不能自行把 fixture、partial 或 camera-failed 输入升级为 ready。
4. 真实 C6c 路线按“clean feature producer → frozen candidate export → 本 assembler → 原 evaluator”执行；candidate policy digest 与三路 variant/source provenance 必须保持一致。
5. RiskAssessment 与 Alert 继续 Literal false；V1-R1、M2c 和最终模型/许可证状态不因本 Review 改变。

### 验证

- 自动化：105 passed；`compileall`、全部 shell/sbatch `bash -n`、`pip check` 与 `git diff --check` 通过。
- 正式 assembly：13 个 copied input、16 个 total file、owner-only 权限、0 raw media。
- 独立复跑：run `20260722T182727Z-5e95a5f8`；manifest `a9dc01e0faeb6f4528208a96344d51b9567378f5df1d0570a9fe018d40e8ecb8`；report/preflight `e96d676cf17aa92b639c65cc41602a536e95d774368bb0fa906a0321d5965327`。
- 边界：decision `tooling_only`、provenance gate true、camera gate/event ready false、Risk/Alert false。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 使用通用 capture producer 完成三姿态 clean feature/candidate run | Codex | 2026-07-24 | Closed for E1 tooling by REV-019；job `1776` + clean `8b4b52d` candidate runs |
| 取得 C6c E2 held-out capture，并冻结独立标注/裁决责任人 | 待指定采集人 / 项目组 | 2026-08-02 | Open |
| 对真实三路 candidate 调用 assembler 与原 scorer，不手工改写 bundle | Codex | 2026-08-03 | Blocked on capture and annotation |
| 冻结真实 derived-sensitive prediction/bundle 的保留、访问和删除责任 | 项目组 | 2026-08-03 | Open |

### 未决问题

1. 比赛环境中 owner-only bundle 的物理根目录、备份与删除责任由谁承担？
2. derived-sensitive prediction 是否保留完整比赛周期，还是 scorer 后只保留摘要与审计 receipt？
3. 多人 per-person/场景级 candidate 语义改变时，prediction schema 与 assembler 是否需要新版本；不能在现有版本中静默扩展。

---

## REV-021 V1-M2a 同容器音轨 PTS Adapter Review

- 日期：2026-07-23
- 状态：Accepted for offline same-container E1 tooling；真实 C6c 音轨仍 Open
- 参与人：项目组、Codex
- 评审范围：同容器音轨解码、PTS 起点对齐、SpeechBackend 时间语义、来源去重、CLI/Slurm、故障门、隐私与 C6c 边界
- 输入材料：[多模态 Pipeline](v1-multimodal-pipeline.md)、[同容器初测报告](reports/v1-m2a-same-container-audio-smoke.md)、实现/修复 `8c6df2d` / `15406db` / `eca6231` / `243cef3` / `195c966` / `d1d4b5a`、CPU run `20260722T190551Z-29f7f25c`、L40 job `1777`

### 发现

1. REV-004/M2a 只支持独立 video + PCM WAV，共享零点明确属于 synthetic harness；REV-009 已 Reject 其作为真实同步依据。REV-010 虽能测同容器 track/PTS，却尚未把音轨送入 VAD/ASR，真实摄像头适配仍断在 probe 与 SpeechBackend 之间。
2. 新路径要求同一 resolved container，复用 `ContainerTimingReport.audio_minus_video_start_ms`，再由 PyAV 解码唯一音轨、下混/重采样至 16 kHz。音频晚开始时保留 timeline start，早开始时裁掉视频零点之前的样本，包 PTS gap 以静音保留。
3. 缺/多音轨、多视频轨、起点不可测、packet 缺 PTS、scan truncated、音频 PTS 逆序或无重叠窗口均 fail closed。Pipeline 不自行选择轨道，也不回退为 common zero。
4. `MultimodalPipelineReport` 新增兼容默认字段 `input_layout`、`same_container_av`、`audio_start_offset_ms`，并校验同容器必须只有一个 asset identity。Run ledger 相应只登记 1 个 SourceAsset、1 个 Observation 和 1 个 container probe。
5. bitexact 准备器把既有公开视频/WAV 合成 FFV1 + PCM16 Matroska，固定 +250 ms 起点。相同输入两次输出 SHA-256 均为 `c989405d3c4b8cacb3418df919da6530335399b33f3e5e52b9bb307e48dcad80`；这是 engineered E1 alignment，不是自然同步。
6. clean CPU run `20260722T190551Z-29f7f25c` 在真实 YOLO/FunASR 后端上得到 25/25 有人姿态帧、100 个实例、1 个 VAD/转写段和 6 个窗口。容器 offset 为 +250 ms，两个语言 FeatureEvent 均落在视频轴 `1130–5445 ms`；报告不复制 20 字转写。
7. CPU processing RTF 0.615406、cold-start RTF 6.750615；只说明模型常驻后的离线处理快于媒体时长。离线 replay 不包含取流、网络、缓冲和断流恢复。
8. 单个起点 offset 和首尾 duration delta 都不能估计 capture clock drift。C6c 是否开放带音频流、实际 codec/time base 与两次同步事件仍是 M2c E2/E3 门。
9. L40 预运行暴露了三类工程失败：`/tmp` worktree 不在计算节点共享文件系统；本地模型绝对目录曾进入 manifest；derived-sensitive JSONL 曾继承默认 `0644`。前两项由 `243cef3` / `195c966` 关闭，`d1d4b5a` 将 run/子目录与 JSON/JSONL 固定为 `0700`/`0600`，旧 run 不手工改权限冒充新证据。
10. clean `d1d4b5a` / job `1777` 在 L40 上 completed/0 issue；功能与 PTS 投影和 CPU run 逐字段一致，processing/cold-start RTF 为 0.413989/6.808901。run 树、JSON/JSONL 和 stdout 为 `0700/0600/0600`，聚合路径/文本隐私扫描 0 命中。

### 决定

1. 接受 `same_container_pts` 作为真实录制 A/V 的唯一多模态文件入口 seam；该决定只覆盖离线 E1 tooling，不证明 C6c 开放音轨或自然 capture clock。
2. 保留 `separate_files_synthetic_common_zero` 只用于历史 public benchmark/单元测试；不得将该布局写成自然音视频同步或 C6c 能力。
3. 冻结 fail-closed timing gate、单 asset/observation provenance 和 SpeechBackend-relative/Pipeline-shifted 的时间责任。模型后端不得读取容器或自行补 offset。
4. `audio_start_offset_ms` 保存 probe 的有符号原值；FeatureEvent 使用 16 kHz sample-grid 后的非负 timeline start。修改精度或 drift 表达必须升级契约。
5. Slurm 必须显式绑定 submit checkout `src/` 和 source type，避免 editable install 与 manifest code version 分叉。
6. 本轮不改变 YOLO/RTMPose/Keypoint R-CNN 或 FunASR 的 V2 候选/许可证状态，也不授权 RiskAssessment/Alert。

### 验证

- 自动化：118 passed；权限/CLI/multimodal/producer 定向回归 26 passed；`compileall`、全部 shell/sbatch `bash -n`、`pip check` 与 `git diff --check` 通过。
- 准备器：50 视频帧、88,747 个 16 kHz sample、250 ms offset、28,741,707 bytes；两次输出逐字节一致。
- CPU run：`eca6231`、clean、completed、E1、0 issue；manifest `7e82b911b94134a0c5da0e1aecc7fc229b4c108911411df6c1c03d2931d3d32a`；pipeline report `7ebe3d49d5bcfe9be0760f3af0461ddc6e5324a9c849e4f379d6e2b5f9b7a784`。
- 隐私：manifest/report/probe/asset/observation 对绝对路径、用户名、原始文件名与完整转写 0 命中；敏感文本只在 ignored FeatureEvent。
- L40：job `1777`，run `20260722T203326Z-8421f5b9`，clean `d1d4b5a`、completed、E1、0 issue；manifest `a69792c502d2a7e631011816b7a0f3e447e33ad6a715ea8f654556c7164ef357`，pipeline report `6925fe9b1cba2a2d1400cf5659a7310f6daebfb7d32629ab019393e8cb4d68dd`，processing/cold RTF 0.413989/6.808901，Torch allocator peak 2,128.785 MB；该 peak 不冒充整进程/整卡峰值。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 完成 L40 正偏移真实后端 smoke 并核对 clean provenance/owner-only 权限 | Codex | 2026-07-23 | Closed；job `1777` |
| 取得 C6c 原始同容器或平台可靠同步导出 | 待指定采集人 | 2026-08-01 | Open |
| 对真实容器人工定位两次拍手/击板，计算 offset/drift 并与 PTS 对照 | 项目组 / Codex | 2026-08-02 | Blocked on capture |
| 加入远场、电视背景和夜间真实音频，按冻结 FunASR 口径报告 CER/VAD | 项目组 / Codex | 2026-08-04 | Blocked on capture/transcript |

### 未决问题

1. C6c SDK/回放最终返回单复用容器、分离 elementary stream，还是只开放视频；三者决定 LiveTransport adapter 形态，但不能改变核心时间契约。
2. 真实长录制需要按多长窗口做 drift 重估；当前离线一次 start offset 不表达动态 clock correction。
3. 若平台重封装时丢弃原 PTS，是要求本地录制保留，还是按 G2 预案分开展示视频与语言；必须在 V2-D1 前决定。

---

## REV-022 V1 Run Artifact 与 Slurm Provenance/Permission Review

- 日期：2026-07-23
- 状态：Accepted for V1 file-artifact seam；V2 service ACL design remains Open
- 参与人：项目组、Codex
- 评审范围：共享 checkout、submit/execution commit、CUDA runtime、manifest 本地路径、run/JSONL/Slurm stdout 权限、失败证据处置与 V2 继承边界
- 输入材料：修复提交 `243cef3` / `195c966` / `d1d4b5a` / `8b4b52d`，共享 Slurm 契约 `673560d` / `667ad8d` / `b54d8b8`，失败/拒绝 jobs `1769` / `1771` / `1772` / `1773` / `1774`，正式 jobs `1776` / `1777` / `1780`，[Slurm Runtime Preflight 报告](reports/v1-slurm-runtime-preflight.md)

### 发现

1. `/tmp` worktree 只存在于提交节点，compute node 无法进入该 workdir；job `1771` 在脚本执行前退出。Slurm 正式执行必须来自计算节点可见的共享 checkout，不能仅凭登录节点 Git clean 推断可运行。
2. ONNX Runtime CUDA provider 已注册并不等于 session 能建立。job `1769` 的 YOLO 子 run 成功，RTMPose 才暴露 cuDNN 9 未进入动态链接路径；失败后没有静默回退 CPU，也没有把单路成功冒充三路证据。
3. job `1773` 功能完成，但 Slurm 传入的绝对 `pose_model` 被原样写进 manifest。`195c966` 只保存公开文件名与 `pose_model_path_persisted=false`；model digest 继续由 ModelBinding 承担。
4. 原子 JSON 由临时文件产生时已为 `0600`，但追加 JSONL 与目录曾继承默认 umask 为 `0644/0755`。其中 `features.jsonl` 可包含 bbox/keypoints/track 与完整转写，因此功能成功也不能通过正式隐私门。
5. `d1d4b5a` 将每个 run 及 `reports/logs/artifacts` 强制为 `0700`，`append_jsonl` 使用 `os.open(..., 0600)` 并校正既有目标模式；两条正式 Slurm 脚本同时设置 `umask 077` 并把 stdout 收紧为 `0600`。
6. jobs `1776` / `1777` 通过后，本地下游复跑又暴露 `RunArtifacts` 只加固 run 子树、未加固新建 `--runs-dir` 根目录。首次结果根目录为 `0755` 并被拒绝；`8b4b52d` 将根目录也强制为 `0700`，用全新路径复跑 candidate/scorer 后通过，旧结果未通过 chmod 升级。
7. 各正式 sbatch 曾各自复制 checkout、代理、权限和 CUDA 准备逻辑，容易随入口增加而漂移。`673560d` 将七个业务入口和一个轻量 preflight 入口统一到 `runtime.sh`，并在业务输入前执行同一 fail-closed 门。
8. 只在作业启动时检查 clean checkout 仍存在排队竞态：提交后、启动前 `HEAD` 可能变化。`667ad8d` 增加统一提交器，冻结完整 40 位 submit commit；`slurm-runtime-v0.2.0` 要求 execution commit 相同，裸 `sbatch` 因缺少绑定而失败。
9. 节点级 `nvidia-smi` 会列出两张物理 L40，不能据此声称作业占用两卡。job `1780` 的 Slurm/CUDA 环境和 Torch 均只暴露分配的 GPU `1`，并实际完成最小 CUDA tensor。

### 决定

1. 冻结 V1 本地运行的 owner-only 基线：`--runs-dir` 根、run 及子目录 `0700`，JSON/JSONL `0600`；正式 Slurm stdout `0600`。不得以 home 目录当前为 `0700` 代替文件自身权限。
2. 权限或路径隐私门失败的旧 run 保留为诊断证据，但不能手工 chmod 后升级成原始正式证据；必须在修复后的 clean commit 上重跑。
3. Slurm 脚本必须绑定 shared submit checkout 的 `src/`、显式 source type、离线模型缓存和可加载的 cuDNN runtime。任何 CUDA provider fallback 都必须失败，而非记录为 GPU run。
4. 本轮只冻结 V1 文件式 artifact seam。V2 对象存储、数据库与日志平台必须另行定义 service identity、ACL、审计、备份、留存和删除责任。
5. V1 正式 Slurm 证据只接受 `scripts/slurm/submit.sh` + `slurm-runtime-v0.2.0`：提交与执行 commit 必须一致，全部入口复用同一 preflight；裸 `sbatch` 或调用方覆盖 `--export` 不构成正式证据。

### 验证

- 自动化：129 passed；新增 Slurm runtime/submit 契约定向 11 passed；`compileall`、全部 shell/sbatch `bash -n`、`pip check` 与 `git diff --check` 通过。
- CUDA runtime：`libcudnn.so.9` 可由 venv Python 发现并加载；ONNX Runtime provider `ldd` 无 unresolved dependency。
- Owner-only formal reruns：job `1776` 三路 producer 与 job `1777` 同容器 run 均 clean `d1d4b5a`、completed/0 issue；run 树、全部 JSON/JSONL、stdout 与 aggregate path scan 通过。
- 下游根目录复跑：clean `8b4b52d` 的三 candidate run、16-file bundle 和独立 scorer 均通过全树 `0700/0600`；scorer report 与 assembler preflight SHA-256 同为 `26b58c13b41ed1313082508ca91586c50b289c0e136e5b6361ecd41dfb9bc3e9`。
- 统一 runtime 预检：job `1779` 在 clean `673560d` 验证 v0.1 基线；最终 job `1780` 在 clean `b54d8b8` 验证 `slurm-runtime-v0.2.0`、submit/execution commit 绑定、owner-only、cuDNN/ORT CUDA、单张分配 L40 和最小 tensor，completed `0:0`，stdout SHA-256 为 `e208492910043e9bf383dcb106e70d9b7fc4c3ae8e113140ffb458e818b68cc4`。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 完成 producer、同容器与下游全链 owner-only clean rerun | Codex | 2026-07-23 | Closed；jobs `1776` / `1777` + clean `8b4b52d` downstream |
| 在 V2-D1 定义对象存储/数据库/日志 ACL、审计和删除责任 | 项目组 | 2026-08-12 | Open |
| 将其他正式 Slurm 入口逐项迁移到同一 stdout/shared-checkout preflight | Codex | 2026-08-12 | Closed；八个入口统一到 v0.2，job `1780` |

### 未决问题

1. 比赛部署是否继续使用单用户文件系统，还是切换服务账户与对象存储？
2. Slurm stdout 是否保留到 V1-R1 结束，还是验收摘要完成后删除；需要数据保留责任人决定。
3. 是否为所有下游 source-run validator 增加 POSIX mode gate，还是由统一 artifact registry/receipt 负责；V2-D1 前必须选定单一责任层。

---

## REV-023 V1-R1 比赛提交分发就绪 Review

- 日期：2026-07-23
- 状态：Accepted for E1 release-gate tooling；submission bundle remains Blocked
- 参与人：项目组、Codex
- 评审范围：项目代码、Python 依赖、姿态/语言模型 artifact、公开评测数据、比赛包 disposition、owner decision、发布文件、fail-closed gate、CLI/CI 语义、provenance 与隐私
- 输入材料：[分发就绪门设计](v1-r1-distribution-readiness.md)、[正式 E1 报告](reports/v1-r1-distribution-readiness.md)、实现提交 `6c32364`、run `20260722T214700Z-958cd4fb`

### 发现

1. 许可证事实此前分散在 `pyproject.toml`、姿态/语言模型配置、公开数据集配置与 R1 Review 中。只依赖文字清单时，模型替换、依赖升级或打包方式变化可能不触发同一套检查。
2. 当前比赛 draft profile 共 13 项资产：项目代码和依赖闭包计划 include；HumanArt detector/pose、Keypoint R-CNN 和 FunASR 共 4 项 undecided；Ultralytics/YOLO、Whisper 与 4 个公开评测数据源共 7 项 exclude。
3. 当前 6 个阻断资产是项目代码、依赖闭包、三个姿态 artifact 和 FunASR 模型栈。excluded 资产不阻断只因为当前包明确不携带它们，不能解释为允许重新分发。
4. 框架实现许可证、预训练权重、训练/评测数据和提交包是四个不同判断对象。MMPose Apache-2.0 不能自动清除 HumanArt artifact；TorchVision 实现许可也不能自动清除预训练权重及关联数据条款。
5. 仓库仍没有顶层 `LICENSE`、`THIRD_PARTY_NOTICES.md` 和 `requirements/competition.lock`。即使随后创建，未在 policy 中绑定最终 SHA-256 也必须保持 fail closed。
6. 项目许可证、源码分发方式、最终姿态 variant、模型 artifact 打包方式和 NOTICE owner 都需要人工责任人确认。工具不能根据技术偏好或比赛非商业语境自动填入答案。
7. 七个冻结事实来源在 clean run 中全部 matched；五个人工决定全部 Open，三个 required file 全部 missing，五个 readiness gate 全部 false。`blocked_pending_distribution_review` 是正确评估结果，不是 assessor 失败。
8. 普通审计需要返回 `0` 以持续生成状态报告；Release Candidate 的 `--require-ready` 必须先落盘报告再返回 `2`，防止 CI 只看到失败而丢失阻断证据。

### 决定

1. 接受 `configs/v1-r1-distribution-readiness.json` + `distribution-readiness-v0.1.0` 作为 V1-R1 G5 的机器可读工程门；事实来源仍由七个仓库配置承担，并以 SHA-256 防漂移。
2. 冻结 `include`、`exclude`、`undecided` 三态：excluded 不进入当前提交包；undecided 始终阻断；非排除资产只有 clearance 和来源证据同时通过才可打开 gate。
3. 不由工程工具选择项目许可证、解释比赛规则或给出法律意见。所有 confirmed decision 必须包含值、具名 owner role 和非本机路径的审计引用。
4. `LICENSE`、NOTICE 和 competition lock 只有在非空、人工审查并绑定摘要后才算 ready。只创建占位文件、修改 expected digest 或口头豁免都不能替代 Review。
5. V1 开发/评测可以继续使用 policy 中的 excluded 资产，但 V2 提交包和演示分发不得携带；重新引入任何一项必须修改 disposition、重审上游条款并重新运行 gate。
6. V2 Release Candidate 必须在干净提交、最终依赖/模型 profile 上运行 `assess-distribution-readiness --require-ready`。G5 工具通过不提升设备、模型、RiskAssessment 或 Alert 的证据等级。

### 验证

- 自动化：137 passed；distribution/CLI 定向 24 passed。
- 静态检查：`compileall`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。
- 正式 run：`20260722T214700Z-958cd4fb`，clean `6c32364`、completed、E1、0 issue；policy SHA-256 `456b18d3b571682b36bfe2681c5559e0232c933ef471df1869c451dc50a7d7eb`。
- 结果：source 7/7 matched；required file 0/3；decision 0/5；blocking asset 6/13；gate 0/5；`submission_bundle_ready=false`。
- 产物：manifest/report SHA-256 分别为 `6a789be873900e2d1f074ddd89a221dfe4b87e56a5f851793e42dcc6b4889771` / `6dbb82849a28a73f08f059cc564a00f47549c678bba5a9b02fdf6daa4ecaab8b`；目录/JSON 权限为 `0700/0600`，本地路径、Risk/Alert true 扫描 0 命中。
- 故障/正向门：来源漂移、路径/symlink 越界、文件 missing/too-small/unbound/mismatch、非法 decision 和 action/clearance 不一致均被拒绝；完整 confirmed fixture 能打开全部 gate，证明结果不是硬编码 blocked。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 实现机器可读资产清单、五级 gate、CLI、测试与 E1 报告 | Codex | 2026-07-23 | Closed；`6c32364` / REV-023 |
| 确认项目许可证、源码分发方式和 NOTICE owner | 项目负责人 | 2026-08-02 | Open |
| 确认最终姿态 variant 与所有模型 artifact 的取得/携带方式 | 模型负责人 / 项目负责人 | 2026-08-03 | Open |
| 生成最终 competition lock，盘点直接/传递依赖和 native runtime | 工程负责人 | 2026-08-05 | Blocked on final runtime profile |
| 生成并复核 `THIRD_PARTY_NOTICES.md`，绑定三个发布文件摘要 | NOTICE owner / 项目负责人 | 2026-08-07 | Blocked on owner/model/dependency decisions |
| 在最终 RC 上复查上游条款和比赛规则，并通过 `--require-ready` | 项目组 | 2026-08-15 | Blocked on preceding actions |

### 未决问题

1. 比赛提交是否包含项目源码、仅包含容器/可执行物，还是两者都包含；该选择直接影响项目许可证与 NOTICE 边界。
2. 最终姿态和语言权重是随包携带、镜像构建时取得、部署时取得，还是由比赛环境预置？四种模式不能共享同一 clearance 结论。
3. V2 是否继续依赖当前 Python extras 全集，还是建立最小 competition runtime profile；只有后者冻结后才能生成有意义的传递依赖清单。
4. 最终许可证/NOTICE/lock 的审查人和 Release Candidate 签字责任尚未指定到具体姓名。

---

## REV-024 V1-R1 候选 Runtime 依赖闭包 Review

- 日期：2026-07-23
- 状态：Accepted for E1 pre-lock tooling；current candidate environment remains Blocked
- 参与人：项目组、Codex
- 评审范围：候选直接依赖、PEP 508 extras/marker 传递闭包、目标平台、禁入包、安装 provenance、环境纯净度、许可证 metadata、脱敏快照、CLI/CI 语义及与分发门的边界
- 输入材料：[候选 Runtime 依赖闭包门](v1-r1-runtime-closure.md)、[正式 E1 报告](reports/v1-r1-runtime-closure.md)、实现提交 `876ce07`、runtime run `20260722T222305Z-2b36b79b`、distribution follow-up run `20260722T222307Z-254cb0ca`

### 发现

1. 当前共享 `.venv` 能完成既有 L40 功能 smoke，但混合了开发工具、多个模型候选、Conda/Python 包与本地安装来源，不能直接解释成最小比赛环境。
2. 候选 `v1-r1-l40-rtmpose-funasr-candidate` profile 固定 8 个直接根。现有环境只有 7/8 匹配，缺 `opencv-python-headless==4.13.0.92`；已安装 GUI OpenCV 不能用相同 import 名冒充 profile 满足。
3. 根 requirement 显式请求 `onnxruntime-gpu[cuda,cudnn]==1.27.0`。传播 extras 后缺 4 个 `*-cu13` Python distributions；此前 CUDA 动态库 loadability 证据不等于 metadata 依赖闭包完整。
4. 5 个禁入包均未进入计算闭包，`prohibited-closure-absent=true`；但它们连同其他开发包形成 76 个 extraneous distribution，因此 isolation gate 仍关闭。
5. 安装来源有 26 个阻断：KangShield editable 与 25 个未批准 direct URL 记录。许可证 metadata 另有 3 个缺口：KangShield、CUDA toolkit、KaldiIO。
6. 脱敏 inventory 不保存 metadata location、URL/editable path、`PYTHONPATH` 内容或许可证正文；报告中的 metadata present 只提供 NOTICE 复核线索，不等于分发 clearance。
7. runtime 八门仅 target environment、repository source、prohibited closure 三门通过，正确得到 `blocked_runtime_closure_review`。接入 runtime profile 后，distribution follow-up 的八个 source binding 全部匹配，但其 owner/file/asset 阻断不变，仍为 0/5。

### 决定

1. 接受 `configs/v1-r1-runtime-profile-rtmpose-funasr.json` + `runtime-closure-v0.1.0` 作为 G5 生成 competition lock/NOTICE 前的机器可读工程门。
2. 当前 profile 只代表 RTMPose + FunASR 的 L40 候选路线，不代表最终模型或比赛平台。切换 Keypoint R-CNN、CPU fallback、Python/平台或 native-runtime 提供方式时必须新建/升级 profile。
3. 根 extras 必须传播到实际闭包，不能只凭 `pip check` 或模型功能 smoke 跳过可选 metadata 依赖。
4. 正式候选环境必须安装非 editable KangShield 构建产物、不设置 `PYTHONPATH`，并从已安装 `kangshield-info` 入口运行；Make 的 `PYTHONPATH=src` 入口只用于开发盘点。
5. closure 8/8 只允许进入人工 lock/NOTICE Review；工具不自动生成最终文件、不选择许可证、不提供法律意见，也不改变 HumanArt/FunASR clearance。

### 验证

- 自动化：147 passed；runtime closure 新增 10 项测试，覆盖完整正向门、八类故障、extras/marker、隐私、live/replay CLI、权限和 `--require-ready` 退出码。
- 静态检查：`compileall`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。
- 正式 runtime run：clean `876ce07`、completed、E1、0 issue；profile/inventory/report SHA-256 分别为 `a1ef8ef46caf5002cd9e5fdaf461c7aeb09e0ac4b55cb0fc36f5ec7f69d10823` / `95feddb3e64c35da30578c616c78745676203d462849fda26af3aefb63119322` / `e683bb64e33cac573bed040065585ed1c732bfc77e9e7116845151a8da5f2f34`。
- Runtime 结果：installed 189、closure 111、direct 7/8、dependency issue 4、prohibited-in-closure 0、provenance violation 26、extraneous 76、license metadata missing 3、gate 3/8。
- Distribution follow-up：clean `876ce07`、8/8 source matched、0/3 file、0/5 decision、6/13 blocking asset、0/5 gate；policy/report SHA-256 分别为 `e5916a8c6f55209c40bb97f0872c5dddd2db33f0ec8a903e7d29990f3c723b32` / `3a22916af9b981cd2acf99b1e907a647c4237471253506bfd6d8d4e62a836651`。
- 两个 run 的目录/JSON/JSONL 均为 `0700/0600`；本地 home path、用户名和 Risk/Alert true 扫描 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 实现候选 profile、闭包 assessor、CLI、测试与正式 E1 报告 | Codex | 2026-07-23 | Closed；`876ce07` / REV-024 |
| 确认最终姿态/语言模型、artifact 获取方式和目标比赛平台 | 模型负责人 / 项目负责人 | 2026-08-03 | Open |
| 按最终选择创建非 editable、无 `PYTHONPATH` 的隔离候选环境并关闭八门 | 工程负责人 | 2026-08-05 | Blocked on model/platform decision |
| 决定 ORT CUDA extras 使用 Python distributions 还是平台 native receipt，并冻结对应 profile | 工程负责人 | 2026-08-05 | Open |
| 人工复核全部闭包包许可证证据，补齐 KangShield/CUDA toolkit/KaldiIO 缺口 | NOTICE owner / 项目负责人 | 2026-08-07 | Blocked on owner assignment |
| closure 8/8 后生成并复核 competition lock 与 NOTICE，再运行 distribution `--require-ready` | 工程负责人 / NOTICE owner | 2026-08-15 | Blocked on preceding actions |

### 未决问题

1. 最终比赛运行平台是否与当前 Linux x86_64 / CPython 3.13.13 / L40 候选一致？
2. ONNX Runtime 的 CUDA/CUDNN 依赖由 Python distributions、基础镜像还是比赛平台提供；其可审计 receipt 如何进入 profile？
3. 最终是否采用 RTMPose + FunASR 主路径；若模型选择变化，哪个 profile 取代当前候选？
4. 项目许可证、NOTICE 和依赖闭包的签字责任人尚未指定到具体姓名。

---

## REV-025 V1-M1 有界网络音视频流采集接缝 Review

- 日期：2026-07-23
- 状态：Accepted for E1 adapter seam；C6c / RTSP / platform verification remains Open
- 参与人：项目组、Codex
- 评审范围：端点凭据边界、RTSP/HTTP 有界采集、轨道/关键帧/timeout/packet gate、owner-only 原始媒体、输出容器探针、失败清理、下游多模态消费与证据晋级边界
- 输入材料：[有界流采集设计](v1-m1-bounded-stream-capture.md)、[正式 E1 报告](reports/v1-m1-bounded-stream-capture-smoke.md)、实现提交 `8cbd91f`、capture run `20260722T225832Z-cfed1858`、Pipeline run `20260722T225924Z-c98c3772`、Slurm job `1782`

### 发现

1. 既有系统已能导入本地同容器媒体，但网络 endpoint 到“可控同容器 raw artifact”之间没有正式 adapter；操作者只能在系统外录制，无法审计 timeout、termination、权限和失败清理。
2. endpoint 常含账号、密码、token 或签名。新入口只从环境读取值，manifest/report 固定不保存 endpoint value/digest、环境变量名或 PyAV/FFmpeg 原生日志；进程环境本身仍须作为敏感边界管理。
3. 采集器要求恰好一条视频、默认恰好一条音频，从首个视频关键帧开始 codec-copy，并由 open/read timeout、媒体时长、wall time 和 packet cap 共同限制。输出重新经过逐包 PTS gate；partial、raw 和 post-probe 失败产物会删除。
4. 首轮测试实际触发 PyAV native segfault：输入 container 关闭后仍读取 `Stream.codec_context`。实现已改为在 container 存活期间复制 stream type/codec 的纯 Python 值，关闭后不再访问 FFmpeg-backed 对象。
5. 正式 E1 capture 在 clean `8cbd91f` 上 completed、0 issue：4050 ms，79 inspected / 78 copied，40 video + 38 audio packets，首包关键帧，两个 readiness 均 true。audio start/end offset 为 +250/+50 ms、duration delta -200 ms；这些是 packet span，不是 drift。
6. raw SHA-256 为 `53ae54598f6ded0bfba5a59b3c14d0a9d2ca5bf77a2a3eda3b781bb7082bb0ed`。job `1782` 以完全相同输入摘要完成真实 YOLO/FunASR：20/20 sampled/people pose frames、80 detections、1 speech segment、4 windows，warm 2295.910 ms / RTF 0.573977；cold RTF 9.886770 包含 37251.170 ms 模型加载。
7. E1 输入是 loopback HTTP fixture。它没有覆盖 RTSP TCP/UDP、真实鉴权、C6c 麦克风音轨、长稳/重连、丢包抖动、设备 clock、双同步事件或萤石平台调用，因此不能提升 G1/G2 或 C6c evidence。

### 决定

1. 接受 `stream-capture-v0.1.0` 作为网络输入到现有同容器 Pipeline 的 E1 adapter seam；它可以直接进入 V2-D1 输入契约。
2. 新增 `network_stream` source type，最高证据为 E2；E2 必须携带 opaque `device_ref`。无论 clip 是否成功，`device_platform_integration_proven` 固定为 false，平台 E3 另行评审。
3. endpoint 继续只允许通过环境变量输入，不保存值、摘要、变量名或底层日志。若未来接入 secret manager，应替换值注入机制，不放宽报告边界。
4. raw artifact 必须位于 run 的 `artifacts/`、以 `0600` 原子发布；运行前必须有同意、访问、留存和删除约束，失败时清理未登记媒体。
5. 下一次真机实验先做短时 C6c RTSP/E2 与音轨检查，再做故障/长稳矩阵，最后按 M2c C01～C12 和双同步事件规程采集；不得直接从 E1 跳到“实时萤石接入”。

### 验证

- 自动化：154 passed；覆盖真实 loopback HTTP/PyAV remux、下游 fake backend、CLI owner-only、短流 exit 2、缺音频、证据伪造、凭据不落盘、post-probe 清理与 parser 默认值。
- 静态检查：`compileall`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。
- Capture：clean `8cbd91f`，run `20260722T225832Z-cfed1858`，artifact/report SHA-256 分别为 `53ae54598f6ded0bfba5a59b3c14d0a9d2ca5bf77a2a3eda3b781bb7082bb0ed` / `dd958f4352706bcc9fb78dad6ef0507d9df124ac8d6c8dd4ceaa1f5b2779848e`。
- Pipeline：job `1782` completed `0:0`，clean `8cbd91f`，run `20260722T225924Z-c98c3772`，report SHA-256 `e68d1ab2ada07f01e51fba7bed3e63bb7454bb6890f2d24c6aa83b8b05418484`。
- 两个 run 的目录/文件及 Slurm stdout 分别为 `0700/0600/0600`；endpoint、源名、本地 home、用户名、secret 和 Risk/Alert true 扫描均 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 实现有界采集器、契约、CLI、故障测试与 E1 → L40 正式证据 | Codex | 2026-07-23 | Closed；`8cbd91f` / REV-025 |
| 获取 C6c 脱敏 RTSP/平台取流方式并确认麦克风音轨 | 设备负责人 | 2026-07-28 | Open |
| 运行短时 E2，复核鉴权不落盘、轨道、PTS、权限和 raw 删除流程 | 工程负责人 / 数据负责人 | 2026-07-29 | Blocked on endpoint/device access |
| 执行 RTSP TCP/UDP、鉴权失败、timeout、短流、断流、重连、丢包/抖动和长稳矩阵 | 工程负责人 | 2026-07-31 | Blocked on E2 stream |
| 按 C01～C12 与双同步事件规程完成采集包并进入三模型 held-out | 数据负责人 / 模型负责人 | 2026-08-01 | Blocked on consent and E2 stream |

### 未决问题

1. C6c 的可复核取流入口来自萤石 SDK、平台 API、RTSP 还是本地回放；凭据刷新周期如何管理？
2. 目标流是否稳定包含单音轨，codec/time base 是否随清晰度、夜视或回放模式改变？
3. 断流后由 adapter 内重连还是由外部 supervisor 新建 run；跨连接是否允许合成同一 artifact？
4. 真实人物音视频的同意、30 日暂定留存、访问人与可审计删除责任由谁签字？

---

## REV-026 V1-M1 重复开流与格式稳定资格门 Review

- 日期：2026-07-23
- 状态：Accepted for E1 repeated-open tooling；C6c / involuntary reconnect / long-run remains Open
- 参与人：项目组、Codex
- 评审范围：多次独立 open、父/子 provenance、失败继续与固定错误码、完整轨道签名、gate/路径防篡改、owner-only raw、单次采集异常脱敏和与真实重连/长稳的边界
- 输入材料：[重复开流资格门](v1-m1-stream-qualification.md)、[正式 E1 报告](reports/v1-m1-stream-qualification-smoke.md)、实现提交 `fea40f7`、签名加固 `c8bda16`、qualification run `20260722T234430Z-1f2b14c9`、Slurm job `1785`

### 发现

1. REV-025 只证明一次有界接收；它不能回答同一 endpoint 能否重复建连，以及不同连接的清晰度、帧率或音频格式是否漂移。
2. 在单个 Matroska 内自动重连并拼接会模糊连接边界、时间轴和 source provenance。V1 更安全的策略是每次独立 open 生成一个 raw/child report，由父报告做资格判断。
3. 只比较 codec/time-base 不足以检测 1080p→720p、帧率变化或 16 kHz mono→其他音频布局。首轮实现 review 后，`c8bda16` 将视频宽高/pixel format/rate 和音频 sample rate/channels/layout 纳入签名。
4. 连接错误可能含 endpoint 或底层 message。父报告只接受固定 failure code，未批准 code 降级为 `stream_capture_failed`；原单次 post-probe 异常也改为固定 `output_verification_failed`。
5. clean `c8bda16` 的三次 loopback HTTP 均为 captured-ready：每次跨度 2050 ms、音频起点 +250 ms，完整签名唯一；父 gate true。
6. 三次 artifact 分别拥有独立 SHA-256。Matroska mux 字节不要求相同，稳定性应比较媒体事实而非 byte equality。
7. 计划性关闭后重新打开不等于流在非自愿断开后恢复；三段短 clip 也不能证明长稳或丢包/抖动容忍。三个声明在契约中固定 false。

### 决定

1. 接受 `stream-qualification-v0.1.0` 作为真实 C6c 短 E2 前的重复开流工程 gate；默认 3 次，允许 2～20 次。
2. 不在 V1 raw 内跨连接拼接时间轴。每次连接保留独立 SourceAsset、Observation、StreamCaptureReport 和 owner-only Matroska。
3. 父 gate 要求所有尝试满足请求 readiness、没有 failed/not-ready、每次都有签名且唯一完整签名数为 1。
4. qualification run 完成但 gate=false 是合法审计；`--require-ready` 在报告写完后返回 2。预期连接失败不使父 run failed，非预期内部错误仍 fail run。
5. `scheduled_reopen_sequence_proven`、`involuntary_disconnect_recovery_proven`、`long_running_stability_proven` 和 `network_impairment_tolerance_proven` 必须分开；后面三项本版本固定 false。
6. 下一真机顺序冻结为：单次短 E2 → 三次 qualification → 鉴权/断流/损伤矩阵 → 30～60 分钟长稳 → M2c 场景包。

### 验证

- 自动化：160 passed；新增 6 项覆盖多次真实 remux、父/子 ledger、固定失败码后继续、格式签名漂移、计数/gate/路径篡改、video-only fail-closed 和 parser。
- 静态检查：`compileall`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。
- Qualification：clean `c8bda16`、completed、0 issue；3/3 ready，2050 ms × 3，唯一签名 1，gate true；manifest/父报告 SHA-256 为 `aa6d83c295f3410970767c553ee68856a3a77250ed4d61022a1e7292b48846f3` / `e077a2f25e46f19f2c8e66a790d6d3a14034f8ee0e2cd7da02222382f4538e2b`。
- L40 child：job `1785` 在 clean `c8bda16` 上 `COMPLETED/0:0`（45 s）；输入 SHA-256 与 qualification 第 3 个 raw 一致，NVIDIA L40 产出 10 帧、40 个姿态检测、1 个语音段和 2 个窗口，processing/cold-start RTF 为 1.018485/19.744673。run 完成且 0 issue，目录/文件 `0700/0600`，隐私扫描 0 命中；只证明 child 可被下游消费，不证明实时性或三次推理稳定性。
- run 的目录/文件为 `0700/0600`；endpoint/端口、环境变量名、fixture 文件名、本地 home/用户名、secret 和 Risk/Alert true 扫描 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 实现重复开流契约、CLI、失败码、完整格式签名、测试和正式 E1 | Codex | 2026-07-23 | Closed；`fea40f7` / `c8bda16` / REV-026 |
| 用 C6c endpoint 执行三次 TCP E2 qualification 并确认格式签名 | 设备负责人 / 工程负责人 | 2026-07-29 | Blocked on endpoint/device access |
| 记录有效、无权限、过期凭据和无音轨的固定失败码 | 工程负责人 | 2026-07-29 | Blocked on test credentials |
| 以受控代理/网络仿真执行 stall、断流、丢包、抖动与恢复矩阵 | 工程负责人 | 2026-07-31 | E1 loopback safety gate Closed by REV-027；RTSP/packet loss/recovery Blocked on E2 stream |
| 执行 30～60 分钟长稳并决定外部 supervisor 的新 run 策略 | 工程负责人 | 2026-07-31 | Blocked on E2 stream |

### 未决问题

1. C6c endpoint 的凭据有效期是否允许三次独立 open；token 刷新由谁负责？
2. 清晰度、夜视或直播/回放切换时，轨道签名的哪些变化属于预期 profile，哪些必须阻断？
3. 非自愿断流后由外部 supervisor 新建 run，还是未来协议允许同一 session 下多个独立 artifact；演示 UI 如何表达间断？
4. 网络故障矩阵使用哪种可审计代理/仿真工具，目标延迟、丢包、抖动和恢复阈值由谁冻结？

---

## REV-027 V1-M1 受控流故障识别矩阵 Review

- 日期：2026-07-23
- 状态：Accepted for E1 adapter fault-detection tooling；RTSP / packet loss / recovery / long-run remains Open
- 参与人：项目组、Codex
- 评审范围：固定故障 taxonomy、真实 loopback socket 行为、服务端实际注入遥测、有界返回、状态/错误码、partial 清理、父子 ledger、防篡改、owner-only 和与恢复/容忍/长稳的边界
- 输入材料：[受控流故障矩阵](v1-m1-stream-fault-matrix.md)、[正式 E1 报告](reports/v1-m1-stream-fault-matrix-smoke.md)、实现提交 `4e637a1`、run `20260723T003417Z-2f683f0f`

### 发现

1. REV-025/026 已证明一次有界接收和计划性 reopen，但没有真实执行 stall、截断或 reset；因此不能证明异常输入不会被误报 ready。
2. 只在配置里写“注入故障”证据不足。最终实现记录 server 实际 request/body chunk、delay、stall、503、reset 和提前关闭事件，父 gate 要求 7/7 `scenario_exercised=true`。
3. clean `4e637a1` 上健康/分块延迟两例均 ready；503、首包 stall、部分 body stall、截断和 TCP reset 五例均失败，固定 code 为 `open_failed` 或 `remux_failed`，0 unexpected ready。
4. 分块延迟实际发送 44 chunks、执行 43 次 5/20 ms 交替 delay，仍 ready；这是应用层 delivery schedule，不是 packet-level jitter 或 packet loss。
5. 两个 stall 分别在 open/read timeout 约 1000 ms 返回；截断/reset 在 5/6 ms 返回。全部低于 7000 ms case limit。
6. 五个失败 case 没有 raw、child report 或 partial；两个正向 raw/child report、SourceAsset 和 Observation 一一对应并保持 owner-only。
7. 父契约会重算场景顺序、注入参数、实际遥测、elapsed、预期状态、计数、精确 artifact 名和 gate；私有 failure code、路径跳转或伪造事件被拒绝。
8. 本工具只运行 loopback HTTP/PyAV，不调用模型或 GPU。clean 本地 E1 比提交无关 Slurm 作业更符合验证范围。

### 决定

1. 接受 `stream-fault-matrix-v0.1.0` 作为真机故障实验前的 E1 adapter safety gate。
2. 固定七场景顺序：healthy、chunk-delay、503、initial stall、midstream stall、truncate、reset；变更场景或状态语义需新版本。
3. 父 gate 必须同时满足 7/7 实际执行、7/7 有界、7/7 符合预期和 0 unexpected ready；配置存在不能替代实际事件遥测。
4. 失败继续清理 partial，不在单 raw 中自动 reconnect 或拼接；若未来支持恢复，由外部 supervisor 新建 run 或新协议显式表达 session。
5. 真机升级使用外部受控代理或 OS 网络仿真层，另补 RTSP TCP/UDP、鉴权过期、packet loss、packet-level jitter 和恢复时间；不得把 fixture CLI 指向真实 endpoint。
6. `packet_loss_injected`、RTSP、reconnect、恢复、网络容忍、长稳、平台、M2c、Risk 和 Alert 在本版本固定 false。

### 验证

- 自动化：164 passed；新增 4 项覆盖真实七场景 socket、实际注入遥测、配置拒绝、父子 ledger、owner-only、计数/gate/遥测/路径/私有失败码防篡改和 parser。
- 静态检查：`compileall`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。
- 正式 E1：clean `4e637a1`、completed、0 issue；7/7 bounded/expected/exercised，2 ready、5 failed、0 unexpected ready；manifest/父报告 SHA-256 为 `9175c7236ec06f872a2949e9f4344201dcf8832f4a844ec3baf9e89221526116` / `0ccc2efb336e96e8821d2d6b2e14870f4a4bf2a73bce4de85ae7faa324a528f1`。
- run/子目录和文件为 `0700/0600`；endpoint/端口、fixture 原文件名、本地 home/用户名、环境变量、secret 和 Risk/Alert true 扫描 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 实现七场景、实际遥测、严格契约/CLI、测试和正式 E1 | Codex | 2026-07-23 | Closed；`4e637a1` / REV-027 |
| 用 C6c 完成单次短 E2 与三次 qualification，确认音轨和格式 | 设备负责人 / 工程负责人 | 2026-07-29 | Blocked on endpoint/device access |
| 冻结真机故障代理、RTSP TCP/UDP、鉴权过期与恢复 session 方案 | 工程负责人 | 2026-07-30 | Blocked on E2 stream and credentials |
| 由产品/工程 owner 冻结 packet loss、delay、jitter、恢复时间阈值 | 产品负责人 / 工程负责人 | 2026-07-30 | Open owner decision |
| 执行 E2 故障矩阵与 30～60 分钟长稳，独立记录恢复时间 | 工程负责人 | 2026-07-31 | Blocked on E2 stream |

### 未决问题

1. 真机实验采用 Toxiproxy、Linux netem 还是 RTSP-aware proxy；工具版本和命令如何进入不可变 provenance？
2. C6c endpoint/token 是否允许代理转发和重复建连；鉴权过期场景由谁提供测试凭据？
3. TCP/UDP 两种 RTSP transport 的 loss/delay/jitter 阈值和允许降级行为是什么？
4. 非自愿断流后的 supervisor 是否总是新建 run；演示 UI 如何表达 gap、恢复尝试和失败？

---

## REV-028 V1-M1 流会话 Supervisor 与恢复账本 Review

- 日期：2026-07-23
- 状态：Accepted for E1 segmented-session supervisor tooling；C6c / involuntary disconnect / network impairment / long-run remains Open
- 参与人：项目组、Codex
- 评审范围：独立 segment artifact、start/finish/gap ledger、失败继续与 backoff、interruption streak、恢复事件、轨道签名、通用/专用 gate、受控 HTTP 503 注入、owner-only、隐私和长稳证据边界
- 输入材料：[流会话 Supervisor 设计](v1-m1-stream-session-supervisor.md)、[正式 E1 报告](reports/v1-m1-stream-session-supervisor-smoke.md)、实现提交 `6a68371`、healthy run `20260723T011139Z-558b1b7b`、recovery run `20260723T011205Z-46d42c9b`

### 发现

1. REV-025～027 已有单次 capture、计划性 qualification 和故障识别，但无法在同一审计对象中表达“第几段失败、间断多久、何时重新取得独立可用媒体”。
2. V1 不应在同一个 raw 内静默重连或拼接时间轴。最终 supervisor 在同一 run 下为每次 open 生成精确索引的独立 artifact/child report，failed segment 不引用 raw，父报告保留 gap。
3. `StreamSessionReport` 会重算 segment index、start/finish/elapsed/gap、requested readiness、计数、轨道签名、独立路径、最长 interruption streak、recovery event 和三层 gate；路径、时间或 gate 防篡改已覆盖。
4. clean healthy run 为 3/3 ready、唯一轨道签名 1、session elapsed 2118 ms，`all_segment_capture_gate_ready` / duration / session gate 均为 true；没有 interruption 时 recovery 字段保持 false。
5. clean recovery run 在同一 loopback endpoint 实际观察 full 11,504,831 B / HTTP 503 rejection / full 11,504,831 B。segment 状态为 ready / `open_failed` / ready，100 ms 后重新 open，690 ms 后形成新 ready artifact。
6. 专用恢复 gate 为 true 时，通用 all-segment/session gate 按设计保持 false。这样“恢复成功”不会覆盖中间失败，也不会让运行者误以为全程可用。
7. `supervisor_reopen_recovery_observed` 只说明外部重开后得到新 artifact。HTTP 503 是受控拒绝，不是非自愿断流；same-connection reconnect、RTSP/packet loss 容忍和 C6c 都未验证。
8. segmented-session 长稳必须同时声明并实际达到至少 1,800,000 ms，且全部 segment ready、签名一致。两次短 run 的 segmented/single-connection 长稳字段均为 false。

### 决定

1. 接受 `stream-session-v0.1.0` 作为多个有界 capture 的 E1 supervisor ledger，接受 `stream-recovery-exercise-v0.1.0` 作为真机恢复实验前的 fixture-only 状态机 gate。
2. V1 固定“同一 run、多份独立 artifact”语义；禁止在同一 raw 内隐藏 reconnect、删除 gap 或跨段拼接。V2 若需要连续播放，UI 也必须显式显示缺口和 segment 边界。
3. 通用 `session_gate_ready` 只接受全段 ready + 独立 artifact + 唯一完整轨道签名 + 声明 wall time；专用 controlled recovery gate 独立发布，二者不得互相替代。
4. 30 分钟是 segmented-session 长稳的最小硬阈值，不代表 60 分钟或 single-connection 稳定性。操作者必须根据 segment duration/count 显式声明并实际达到目标。
5. 真机恢复证据必须把外部代理/网络仿真的版本、配置、实际注入 receipt 与 session report 绑定；未知根因的普通失败后 ready 仍不得晋级为非自愿断流恢复。
6. 设备平台、M2c bundle、RiskAssessment 和 Alert 不由 supervisor 打开；每个 ready/not-ready raw 继续执行同意、访问、留存和删除控制。

### 验证

- 自动化：clean `6a68371` 全量 170 passed；新增 6 项覆盖配置上限、健康/恢复实际运行、两条 CLI、owner-only、duration/long-run、时间/gap、注入、路径和 gate 防篡改。
- 静态检查：`compileall`、全部 shell/sbatch `bash -n`、`pip check`、Markdown 相对链接、`git diff --check` 通过。
- Healthy：completed、clean、0 issue；3 ready、0 interruption、1 unique signature、2118 ms；manifest/父报告 SHA-256 为 `4896a09a02f097dc4050546eca8781ef844ecd7cd85a95a1131243c6f61dc87c` / `a67f6819235b200ae75ff8af2c1f2d1c31e0b5213af842f7a3e0900ad59c1368`。
- Recovery：completed、clean、0 issue；2 ready + 1 `open_failed`、3/3 injection exercised、1 recovery event、100 ms reopen、690 ms ready artifact；manifest/父报告 SHA-256 为 `4a165eb43a106d4f7cd4e2d2e21a6ee5ee0010a0165465a3fc91d2797acc3b00` / `986bb71ffa928f8f646c270c6aba6b5981f9905f94a6b1a987246ed2d701e59b`。
- 两个 run 的目录/文件均为 `0700/0600`；failed segment 无 raw/child/partial。endpoint/端口、fixture 原名/路径、本地 home/用户名、环境变量、secret 和 Risk/Alert true 扫描 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 实现 session/recovery 契约、runner、CLI、测试和正式 E1 | Codex | 2026-07-23 | Closed；`6a68371` / REV-028 |
| 用 C6c 执行短时 3-segment E2，确认真实 endpoint、音轨、签名和外部重开 | 设备负责人 / 工程负责人 | 2026-07-29 | Blocked on endpoint/device access |
| 冻结 RTSP-aware proxy/netem 工具、版本、注入 receipt 和故障阈值 | 工程负责人 / 产品负责人 | 2026-07-30 | Blocked on E2 stream and owner decision |
| 注入鉴权过期、非自愿断流、packet loss/delay/jitter，并记录真实恢复时间 | 工程负责人 | 2026-07-31 | Blocked on preceding actions |
| 执行至少 30～60 分钟 segmented-session 长稳并单列 single-connection 结论 | 工程负责人 | 2026-07-31 | Blocked on E2 stream |
| 在演示 UI 明示 segment、gap、恢复中和最终失败，不把断点渲染为连续 | V2 前端 / 工程负责人 | 2026-08-12 | Open for V2-D1 |

### 未决问题

1. C6c 的可代理 endpoint 和鉴权刷新是否允许连续多次 open；平台限流或 token 刷新应由哪个组件拥有？
2. 真机 non-ready streak 到几次后应停止重试并升级为人工处置；backoff 是否需要指数策略和 jitter？
3. packet loss、delay、jitter、恢复时间和 30/60 分钟通过阈值由产品、设备还是工程 owner 最终签字？
4. V2 是否需要把跨 segment 的姿态 track、ASR 上下文和融合窗口重置规则升级为独立协议版本？

---

## REV-029 V1-M1 Stream Session 媒体时长门加固 Review

- 日期：2026-07-30
- 状态：Accepted for E1 long-run gate semantics；actual 30～60 minute run / C6c remains Open
- 参与人：项目组、Codex
- 评审范围：v0.1 长稳假阳性、累计 ready media 重算、wall/media 双 gate、组合 session gate、30 分钟契约正反例、恢复兼容性、owner-only、隐私和设备证据边界
- 输入材料：[Supervisor 设计](v1-m1-stream-session-supervisor.md)、[媒体时长门加固 E1 报告](reports/v1-m1-stream-session-media-duration-gate-smoke.md)、实现提交 `ab1f366`、healthy run `20260730T072716Z-fb419398`、recovery run `20260730T072946Z-5d163ce2`

### 发现

1. v0.1 只要求声明/实际 wall time 达到 1,800,000 ms；open、stall、gap 或 backoff 理论上可能撑大 wall，而有效 ready 媒体不足，存在 long-run 假阳性。
2. v0.2 增加独立 `minimum_ready_media_ms`、可重算 `ready_media_span_ms` 和 `session_media_duration_gate_ready`。failed / captured-not-ready segment 不贡献 ready 媒体。
3. 父契约从 segment ledger 重算 ready media；手工放大父汇总会被拒绝。通用 session gate 现在要求 all-segment、wall duration 与 media duration 三门同时通过。
4. long-run 只有在 wall / ready media 的声明值和实际值分别达到 1,800,000 ms 时成立。测试中 wall 达标但媒体不足必须为 false；四项都达标的相干构造才为 true。
5. 上述 30 分钟正反例是契约测试，不是实际 30 分钟运行。`segmented_session_long_running_stability_proven` 在两个正式短 run 中均保持 false。
6. clean healthy run 显式声明 ready media 下限 1,500 ms，三段各 850 ms，父级重算 2,550 ms；media/session gate 均为 true。
7. clean recovery run 为 ready / `open_failed` / ready，父级重算 ready media 1,700 ms；专用恢复 gate true，通用 session gate 因中间失败保持 false。
8. 第一次 loopback 预检被环境 socket 权限拒绝，形成 failed/0-artifact ledger；解除环境限制后的 completed clean run 才进入正式证据。

### 决定

1. 接受 `stream-session-v0.2.0` 和 `stream-recovery-exercise-v0.2.0` 作为后续 E2 的最低 session 契约，v0.1 不再用于新长稳结论。
2. E2 长稳命令必须显式设置 `--minimum-session-wall-s` 与 `--minimum-ready-media-s`；30 分钟门要求两者声明值和两项实际值分别不少于 1,800 秒。
3. `session_duration_gate_ready` 继续只表达 wall；`session_media_duration_gate_ready` 只表达 ready media；`session_gate_ready` 组合全段与两项时长，不得互相替代。
4. 契约构造测试只能作为公式证据，不得写成运行稳定性。实际 30～60 分钟结论仍须 completed E2 run、真实媒体和留存/删除审计。
5. C6c、RTSP、same-connection、非自愿断流、network impairment、设备平台、M2c、RiskAssessment 和 Alert 不因本次加固晋级。

### 验证

- 自动化：clean `ab1f366` 全量 170 passed；覆盖 wall/media 独立阻断、父媒体汇总防篡改、30 分钟正反例、CLI、健康 session 和恢复兼容。
- 静态检查：核心/脚本 `py_compile`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。
- Healthy：completed、clean、0 issue；3/3 ready，declared/actual ready media 1,500/2,550 ms，media/session gate true，long-run false；manifest/父报告摘要为 `145aa6a2e28db0b288b23daf8c3bd73bf61cfbedccc073252680e8183b3c0b23` / `4e68af59cac4a7011cb25b3d2a9ef46158495e8d63c359a7c484cc005c58f952`。
- Recovery：completed、clean、0 issue；2 ready + 1 `open_failed`，ready media 1,700 ms，专用 gate true、通用 session gate false、long-run false；manifest/父报告摘要为 `9f9eaf61d08ff5ae7652bf71c005854a8685a79d37afdaa2186f35c34bd77cf8` / `ce32af1f480cbbec16c5dab46d17e4909572451af55368b72d7bd5a21075f8c1`。
- 两个正式 run 的目录/文件为 `0700/0600`；endpoint/host/port、fixture path/name、本地 home/用户名、环境变量、secret 和 Risk/Alert true 扫描 0 命中。

### 行动项

| 行动 | 负责人 | 截止日期 | 状态 |
|---|---|---|---|
| 实现 wall/media 双门、契约防篡改、CLI、测试和 clean E1 | Codex | 2026-07-30 | Closed；`ab1f366` / REV-029 |
| 用 C6c 执行短时 E2、qualification 与 short session | 设备负责人 / 工程负责人 | 2026-07-31 | Blocked on endpoint/device access |
| 冻结外部故障工具、阈值、receipt 和非 ready 重试策略 | 工程负责人 / 产品负责人 | 2026-07-31 | Blocked on E2 stream and owner decision |
| 执行 wall/media 双声明的 30～60 分钟 E2，并单列 single-connection | 工程负责人 | 2026-08-01 | Blocked on E2 stream |

### 未决问题

1. 30/60 分钟 ready media 是否允许小于 wall 的容器/关键帧误差，若允许，阈值由谁签字并如何显式进入新协议？
2. 非 ready streak 的停止次数、backoff 指数策略和 jitter 是否应在 E2 前冻结为 v0.3？
3. V2 UI 如何同时展示 wall elapsed、ready media coverage、gap 和最终 gate，避免把 segmented run 渲染为单连接连续流？
