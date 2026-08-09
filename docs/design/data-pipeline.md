# 数据与跌倒事件 Pipeline

状态：Implementation Baseline v2.0
更新时间：2026-08-08

## 输入

| 输入 | 当前形式 | 证据边界 |
|---|---|---|
| C6c 视频 | FLV/同容器 HEVC + AAC | 已有短 E2；夜视、完整场景和长稳未关闭 |
| C6c 音频 | 同容器 AAC 16 kHz mono | 已有短 E2 和历史回放；目标语音 A/B 未关闭 |
| SDHY1 | huayi/whst 组件仓响应 | 已有 E2 字段；缺失值和完整夜语义未关闭 |
| 公开回归集 | URFD、CAUCAFall、Open Images | 仅 E1 工程回归，不代表目标域 |
| Fixture | synthetic 媒体/JSON | 仅验证契约和失败路径 |

## 视频主链

```text
capture-stream / run-stream-session
  -> media timing probe
  -> pose backend
  -> frame-level fall features
  -> label-blind candidate episode
  -> candidate export
  -> owner-only event bundle
  -> annotation/adjudication scorer
```

关键入口包括 `capture-stream`、`qualify-stream`、`run-stream-session`、`capture-fall-features`、`export-fall-candidates` 和 `assess-event-evaluation`。

## 指标链

姿态输出先经过可见率、关键点质量、标定、时间戳连续性和动作完整性门，再计算：

- 步速：必须有地面尺度或已 Review 的标定映射。
- 步频：从完整步态周期计算，记录有效步数。
- 坐站用时：必须定义动作开始/结束状态。
- 转身用时：必须区分 180° 与 360°，动作不完整时不可评估。

现有 G4 横卧、下降、静止特征服务于跌倒候选，不直接等同于新需求中的风险评分。

当前 `extract-video-indicators` 已用 fixture 打通质量门与公共契约；它消费已测量的重复值，不把 fixture 写成像素级姿态算法证据。

## 语音辅助链

```text
same-container AAC + media PTS
  -> PCM 16 kHz mono
  -> FSMN-VAD
  -> Paraformer-zh ASR
  -> CT-Punc
  -> help_request / fall_related candidate
  -> PTS window alignment with fall candidate
  -> owner-only review bundle + public aggregate
```

SenseVoiceSmall 只作为 A 集 challenger。完整转写不进入 public evidence；语音 candidate 不进入指标风险总分。音频不可用时语音显式不可评估，视频与睡眠链继续运行。详见[指标、模型与语音实现方案](indicator-implementation.md)。

## 睡眠链

```text
sanitized SDHY1 response
  -> profile-sleep
  -> confirmed mapping
  -> assess-sleep-route
  -> field adapter
  -> completeness/timezone/missing audit
  -> sleep indicators
```

只有 E2/E3 真实输入且单位、时间、值域、缺失语义齐全的字段可以进入 adapter。心率和呼吸率当前没有跌倒评分阈值，只输出趋势与质量。

`extract-sleep-indicators` 已对 fixture 打通趋势输出，并令完整夜语义不足的就寝、起床和时长返回 `blocked_semantics`。

## 策略链

`normalized indicators + quality -> assessability gate -> score 0..3 -> percentage/color -> group/global aggregation -> result + policy digest + limitations`

在 [跌倒指标需求](fall-risk-indicators.md)列出的冲突关闭前，最终节点只能返回 `policy_not_frozen`。

`build-indicator-report` 同时生成 owner-only 和 public evidence 的 JSON/Markdown；后者不含真实分项值，两个版本的 `global_score` 都固定为 `null`。

## 运行、权限与证据

- 每次运行使用独立目录和 `RunManifest`。
- run/子目录为 `0700`，JSON/JSONL 和正式 stdout 为 `0600`。
- 配置、代码提交、输入摘要、模型摘要和父子 run 必须可追溯。
- token、签名 URL、设备序列号、姓名和原始健康值不得进入公开报告。
- E0=说明/假设，E1=fixture/公开集，E2=真实脱敏样本，E3=真实可重复验证，E4=多周期稳定验收。
- 输出能力不得高于输入、模型、策略和评估证据中的最低等级。
