# 当前工程状态

状态：Active
更新时间：2026-08-08

## 范围

当前主线是单机位跌倒风险指标、跌倒/语音 candidate、SDHY1 睡眠数据和人工复核。指标需求源为 `fall-risk-indicators.docx`；owner 已明确将 C6c 的 VAD、普通话 ASR、求助/跌倒相关语音 candidate 和 PTS 对齐纳入 D1。诈骗、情绪、认知、抑郁、表情和社交评分仍不进入 D1。

## 已有基础

- C6c 已取得短 E2 主码流：HEVC 2560×1440@15fps + AAC 16 kHz mono。
- FunASR VAD/Paraformer/标点、Whisper 对照和同容器 multimodal replay 旧实现可复用；它们尚未形成现行语音契约或目标 C6c A/B 结论。
- 三次独立开流 3/3 ready，轨道签名一致。
- 单段取流、重复开流、受控故障和 session ledger 工具可用。
- SDHY1 的 huayi/whst 真实接口已返回心率、呼吸率、状态和睡眠相关数据。
- YOLO、RTMPose、Keypoint R-CNN 姿态候选与公开回归证据可复用。
- 跌倒帧特征、candidate episode、export、bundle、标注/裁决 scorer 已形成工程链。
- 全量自动化测试最近验证为 `184 passed`（2026-08-08）。
- 三个指标 CLI 已用 E1 fixture 打通：五项视频观测、心率/呼吸趋势、睡眠语义阻断，以及 owner/public 双版本静态报告。
- 公共契约强制不可评估值为 null；评分 policy 未冻结时不允许分项分数，`global_score` 固定为 null。
- C01～C12 保留既有语义，采集矩阵已增加 C13 180°、C14 360°、C15 跪地和 C16 多人交叉。

## 尚未关闭

- C02～C10、夜视、床边横卧、遮挡、多人和真实跌倒正负样本。
- 30 分钟真实 wall/media 长稳。
- 单机位步速标定误差、步频事件，以及 5xSTS/协议化转身动作边界的本地测量一致性。
- SDHY1 缺失值、完整夜、就寝/起床边界与长期覆盖。
- 新需求中的阈值冲突和总风险合成策略。
- 最终姿态模型、项目许可证、模型携带方式、NOTICE 和 runtime lock。
- 现行 SpeechSegment/VoiceCandidate 契约、SenseVoice A 对照、C6c 远场/噪声/多人 A/B、语音 public report 和 speech runtime/distribution 门。

## 当前资产

| 资产 | 用途 | Git 策略 |
|---|---|---|
| `data/` | 公开集、fixture、受控输入 | 忽略；按来源和摘要管理 |
| `models/` | 模型候选权重 | 忽略；D1 重新决定携带范围 |
| `runs/` | 本地与 L40 运行产物 | 忽略；正式结论提炼到 evidence |
| `logs/` | Slurm stdout | 忽略；不作为文档入口 |
| `configs/` | 模型、采集、事件和发布策略 | 跟踪；D1 新增指标 policy |

下一步在不等待评分 policy 的情况下采集视频/语音开发集 A、三晚 SDHY1 与 31 × 60 秒 wall/media 长稳，同时实现姿态状态机、现行语音契约、VoiceCandidate 和脱敏报告。详见[里程碑](milestones.md)、[指标、模型与语音实现方案](../design/indicator-implementation.md)和[测试矩阵](test-matrix.md)。
