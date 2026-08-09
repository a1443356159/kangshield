# 指标、模型与语音实现方案

状态：Active baseline v0.2
更新时间：2026-08-09

本文合并原“新增指标技术调研”“模型选型与输出规范”“视频与语音处理方案”，作为 D1 唯一的指标实现与模型选择入口。公共数据结构见[指标公共契约](indicator-contracts.md)，采集要求见[数据采集详细清单](../device-data/data-collection-checklist.md)。

## 1. 范围与结论

当前实现包括：

- C6c 视频的人体检测、姿态、跟踪、步速、步频、5xSTS、C13/C14 转身和跌倒 candidate；
- C6c 同容器音频的时间基检查、VAD、普通话 ASR、标点、`help_request` / `fall_related` candidate；
- SDHY1 心率、呼吸率趋势，以及语义通过后的就寝、起床和睡眠时长；
- owner-only 结果与脱敏 public evidence。

当前只冻结原始指标提取、质量门、candidate 和报告结构，不冻结 0～3 分段或全局风险总分。诈骗、声纹、情绪、认知、抑郁、临床语音结论和自动告警不在范围内。

## 2. 统一链路

```text
C6c HEVC + AAC
  -> container/media PTS probe
  -> video: detector -> pose -> tracker -> ActionEpisode
           -> gait/posture observations + fall candidate
  -> audio: PCM 16 kHz mono -> VAD -> ASR -> punctuation
           -> help/fall voice candidate
  -> PTS window alignment -> owner-only review evidence

SDHY1 response
  -> source adapter -> mapping/unit/time/missing normalization
  -> complete-night gate -> sleep observations

all observations
  -> quality gate -> owner/public report
  -> assessment=policy_not_frozen, global_score=null
```

视频、语音和睡眠保留独立来源、模型、算法、质量和失败状态。融合层只建立引用，不修改上游值，也不把单独语音 candidate 解释为跌倒事实。

## 3. 内部绑定

像素到公共 Observation 之间至少保留：

- `CalibrationBinding`：图像/地面点、单应矩阵、重投影误差、有效区域、机位与 revision；
- `PoseTrackFrame`：media time、track、bbox、关键点、模型、可见率、遮挡和插值标记；
- `ActionEpisode`：场景、动作类型、track、开始/结束、阶段、方向、完整性和人工参考；
- `NormalizedSleepSample`：接口族、mapping、时间/时区、present/null/absent/empty/offline、值与单位；
- `SpeechSegment`：VAD 起止、语言、owner-only transcript 引用、模型绑定、质量和 finalized 状态；
- `VoiceCandidate`：`help_request|fall_related`、起止、segment、matcher revision、复核状态，且 `risk_assessment_emitted=false`。

正式 Observation 还应显式绑定 `protocol_revision`、`model_binding_ref`、`algorithm_revision`、可选 `calibration_ref`、`aggregation`、有效/排除样本数和 owner-only episode summary。

## 4. 视频模型

### 4.1 开发集 A

| 角色 | 候选 | 用途 |
|---|---|---|
| 工程参考 | YOLOX-m HumanArt + RTMPose-m HumanArt COCO-17 | 延续已有横卧、ADL 和 L40 证据 |
| 步态 challenger | 同 detector + RTMPose-m COCO-WholeBody | 验证 heel/toe 是否改善步速、步频 |
| 回归基线 | YOLO pose + ByteTrack | 检查新链没有相对旧实现退化 |
| fallback | Keypoint R-CNN | 独立对照，不按人物框覆盖自动接管 |
| 可选诊断 | MediaPipe BlazePose Heavy | whole-body runtime 受阻时，仅用于单人步态 |

RTMW3D 和 ViTPose 不进入首轮 B：前者没有消除单目尺度/遮挡歧义，后者没有直接补足脚点和时序问题。A 集结束后最多让主候选、互补 fallback 和回归基线进入 B。

### 4.2 共同处理规则

1. 所有时间来自媒体 PTS，不使用推理墙钟。
2. 候选尽量共享 detector、tracker、采样帧率和输入框，避免混淆模型收益。
3. 先以 5 fps 验证实时门；A 集比较 10 fps 是否显著降低步事件与动作边界 MAE。
4. 只允许短缺口平滑；长缺口、左右交换、track break 或 ID switch 触发降级。
5. C16 单独统计多人交叉的 track break 和 ID switch。

## 5. 视频指标算法

### 步速

- 只处理完整穿过 C02/C03 标定区的 episode；
- 通过地面单应性把 ankle/heel/toe 接地点投影为米制距离；
- 每次通过计算 `distance_m / duration_s`，公共值为有效 trial 的 median；
- 无标定、越界、脚部长时间不可见、PTS/track 中断或未完整穿线时 `not_assessable`。

### 步频

- 显式左右步事件与踝/膝/髋去趋势周期信号交叉检查；
- 固定计算 `valid_step_count / valid_duration_s * 60`；
- 不计往返端点调整步或 C13/C14 转身步；
- 两条信号不一致、步数不足或左右点不可区分时不输出值。

### 5xSTS

状态机为 `seated_stable -> rising -> standing_stable -> descending -> seated_stable`，连续完成五次站起。协议必须绑定椅高、扶手/手臂、起始坐姿和第五次结束边界。公共值为一组完整任务总用时或多组有效 trial median；少做、多做、中断、扶手违规、椅面/核心关节不可见均不可评估。

### C13/C14 转身

- C13 是行走中 180° 转身，完成后反向离开；
- C14 是原地 360° 转身，完成后回到初始朝向；
- 自动边界可组合肩髋宽度、左右点顺序、脚步和移动方向变化；
- 输出协议化任务用时，不把未验证的单目角度估计作为正式指标；
- 顺/逆时针分别汇总 MAE、完整率和不可评估率。

## 6. 睡眠指标

已观察 mapping 包括 `heartRate`、`breathRate` 和测量时间。心率/呼吸只输出夜间 median、覆盖、缺口和 owner-only trend，不评分。

连续三晚必须区分：在床/短暂离床/整晚离床/无人，在线无测量/离线/API 失败，字段 absent/null/empty/zero/invalid，观察/报告/查询时间，本地时区和跨午夜归属，以及入睡/醒来/上下床定义。任一关键语义未关闭时，就寝、起床和时长均为 `value=null`、`blocked_semantics`，不得用插值伪造连续睡眠。

## 7. 语音模型与输出

主候选链：

```text
AAC 16 kHz mono
  -> PTS-aware PCM decode
  -> FSMN-VAD
  -> SeACo Paraformer-zh
  -> CT-Punc
  -> versioned deterministic matcher
```

FunASR 作为现有工程参考；SenseVoiceSmall + FSMN-VAD 作为 A 集远场、噪声和口音 challenger；Whisper small 只保留历史回归。任何 checkpoint 都需单独审查来源、摘要、许可证和携带方式。

首版 matcher 不接 LLM。否定、转述、电视/手机播放、ASR 错词、多人重叠和环境噪声必须作为 hard negative。完整逐字稿只存 owner-only artifact；public evidence 只保存类别、时间、计数、质量、状态和限制。

音视频融合只生成复核候选：视频与语音 candidate 临近时提高人工复核优先级；只有语音时独立复核，不确认跌倒。音轨缺失、PTS 中断或模型失败时语音 `not_assessable`，视频与睡眠继续。

## 8. 输出与质量门

公共值采用有效 trial median；owner-only 保留逐 trial 值、动作边界、方向、质量和排除原因。`sample_count`、`valid_sample_count` 和 `excluded_sample_count` 不得混用。

| 层级 | 必查项 | 失败处理 |
|---|---|---|
| 媒体 | PTS、帧率、分辨率、片段/音轨完整 | 对应模态 `not_assessable` |
| 标定 | revision、重投影误差、有效区域、机位漂移 | 步速不可评估 |
| 姿态/跟踪 | 关键点可见率、抖动、左右交换、track break/ID switch | 降质量或中断 episode |
| 动作 | 协议、完整重复、边界、人工参考 | 不生成正式值 |
| 睡眠 | mapping、单位、时区、完整夜、缺失/离线语义 | `blocked_semantics` |
| 语音 | VAD、CER、audio PTS、距离/噪声、回放/否定 | 降质量或不可评估 |

public evidence 只含 assessability/质量计数、失败原因、模型/runtime/许可证状态、A/B 覆盖和聚合误差，不含个人指标值、关键点、录音、逐字稿或健康时序。

## 9. A/B 选择门

A 集用于冻结模型、tracker、帧率、关键点 gate、平滑、动作边界、aggregation、VAD/ASR/matcher、融合窗口和质量策略。B 在冻结后运行；任何 B 后调整都建立新 revision 与 B2。

模型硬门：

1. 实现、checkpoint、训练数据血缘和比赛使用方式可关闭；
2. L40 单路 5 fps、RTF < 1；
3. 输出拓扑和坐标语义可稳定归一化；
4. 必要场景无系统性失败；
5. public 输出可脱敏。

比较指标包括：每项可评估率和相对人工参考 MAE，步事件 F1，5xSTS/转身边界误差，关键点连续缺失、静止抖动、左右交换、track break/ID switch，跌倒 TP/FP/FN、FP/hour 和延迟，语音 CER、VAD F1、两类 candidate P/R/F1、Voice FP/hour、音视频对齐误差，以及 RTF/P95/CPU/GPU 内存。

选择顺序为许可证与使用方式、实时门、系统性失败、held-out 可评估率，再比较漏报、FP/hour、延迟和资源。不得用单一姿态 AP 或人物框覆盖率直接定案。

## 10. 阈值边界

- 步速 `<=0.8 m/s`、5xSTS `>=13.93 s`、C13 `>=2.45 s`、C14 `>=3.46 s` 仅作为候选 policy；任务协议和本地测量误差必须绑定。
- `13.93 s` 只对应连续五次坐站，不适用于单次坐站。
- `<80 steps/min`、固定 21:00～23:00 就寝窗口、睡眠 `<7 h`/`>9 h` 和心率/呼吸跌倒阈值证据不足，保持 `policy_not_frozen`。
- 所有工程输出均不构成临床诊断、治疗或个体健康结论。

## 11. 参考入口

- [MMPose / RTMPose](https://github.com/open-mmlab/mmpose)与 [COCO-WholeBody](https://arxiv.org/abs/2007.11858)
- [ByteTrack](https://github.com/FoundationVision/ByteTrack)
- [OpenCV Homography](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html)
- [Marker-free gait review](https://pmc.ncbi.nlm.nih.gov/articles/PMC8884063/)与[自动步态研究](https://pmc.ncbi.nlm.nih.gov/articles/PMC10384445/)
- [5xSTS cutoff study](https://pubmed.ncbi.nlm.nih.gov/36701043/)
- [Turning and frailty study](https://www.sciencedirect.com/science/article/pii/S0966636221001260)
- [FunASR](https://github.com/modelscope/FunASR)与[SenseVoice](https://github.com/QwenAudio/SenseVoice)
