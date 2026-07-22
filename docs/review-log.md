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
