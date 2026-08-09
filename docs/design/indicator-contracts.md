# 指标公共契约与静态报告

状态：Implementation Baseline v0.1
更新时间：2026-08-08

## 冻结契约

`IndicatorObservation` 是评分前的标准化观测，固定包含指标 ID、分组、来源模态与摘要引用、可选场景、值、单位、时间范围、可评估状态、质量、样本数和限制。约束如下：

- `assessable` 必须有值，且质量不能为 `fail`。
- `not_assessable` 与 `blocked_semantics` 必须令值为 `null`。
- 步速额外要求地面标定和脚点可见率；视频指标统一要求时间戳、关键点、track、动作完整性及至少三次完整重复。

`IndicatorAssessment` 与原始观测分离。状态为 `assessed` 时必须同时绑定 `0..3` 分、policy revision 和 SHA-256；其他状态严禁带分数。当前 owner 尚未冻结阈值，所以可评估分项统一返回 `policy_not_frozen`。

`IndicatorSummaryReport` 固定 `global_score=null`。`owner_only` 版本包含真实分项值；`public_evidence` 版本不含 observation，只保留指标/质量/状态计数和限制。跌倒 candidate 与人工裁决只允许作为独立摘要，不能并入全局风险分。

## CLI

```bash
kangshield-info extract-video-indicators \
  tests/fixtures/indicators/video-indicators.synthetic.json

kangshield-info extract-sleep-indicators \
  tests/fixtures/sleep/sdhy1-export.synthetic.json

kangshield-info build-indicator-report \
  runs/<video-run>/reports/video-indicator-observations.json \
  runs/<sleep-run>/reports/sleep-indicator-observations.json
```

最后一条命令生成 owner/public 两套 JSON 与 Markdown。初版视频 adapter 接受确定性的测量 fixture，并真实执行公共质量门；它不声称已经从像素或姿态关键点计算指标。睡眠 adapter 可输出带时区时间戳的心率/呼吸均值趋势；完整夜、时区和缺失语义未全部确认时，就寝、起床和时长保持 `blocked_semantics`。

## 后续兼容边界

姿态状态机与 SDHY1 E2 adapter 必须输出相同契约，不得为后端增加私有公共字段。评分阈值冻结属于新的 policy revision；任何 held-out B 后的参数变化必须另建 revision 和 B2，不能覆盖旧结果。

## 像素级实现前的 v1.1 研究项

[指标、模型与语音实现方案](indicator-implementation.md)确认，当前 v1.0 还不足以完整审计像素级指标。v1.1 建议显式增加 protocol、model binding、algorithm、calibration、episode summary、aggregation、valid/excluded sample count；并修正以下语义：

- 视频重复任务的聚合策略必须显式绑定 revision，不能隐式使用算术均值；
- C04 改用 `five_times_sit_to_stand_duration`，一项样本是一组完整五次坐站，不套用通用“三次重复”质量门；
- 心率/呼吸的夜间摘要值与 owner-only 趋势 artifact 分离；
- 就寝/起床输出完整带时区 datetime，而不是失去日期和偏移的时钟字符串。

这些内容当前是下一版契约建议，不改变已发布 v1.0 fixture 行为；实现时必须先增加契约测试和兼容入口。
