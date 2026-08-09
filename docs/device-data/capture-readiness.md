# 采集包就绪门

状态：Active v2.0
更新时间：2026-08-08

## 分门状态

| Gate | 条件 | 授权 |
|---|---|---|
| `camera_structure_ready` | 受控路径、摘要、C6c 能力快照、媒体可解码、场景与标注完整 | 可进行结构 Review |
| `camera_indicator_retest_ready` | C01～C10 核心覆盖、标定、真实帧时间、非重复媒体、质量信息齐全 | 可按冻结参数运行姿态与指标提取 |
| `speech_review_ready` | V01～V09 A/B 覆盖、音轨与 PTS 连续、owner-only 逐字稿、冻结模型/文本规范化/candidate policy、独立标签齐全 | 可运行语音 held-out 与音视频对齐评测 |
| `sleep_field_review_ready` | SDHY1 真实 E2+、接口/字段/单位/时间/值域/缺失语义齐全 | 可开始字段 adapter Review |
| `fall_event_review_ready` | 真机正负样本、冻结 candidate policy、独立标注与裁决齐全 | 可运行事件 scorer |
| `capture_bundle_ready_for_d1` | 上述适用门通过，隐私和 owner 完整 | 可作为 D1 输入；不代表风险策略或发布完成 |

Fixture、template、synthetic marker 或公开数据永远不能打开真机门。

## 必要内容

```text
capture/
  manifest.json
  capabilities/
  camera/
  speech/
  sleep/
  annotations/
  consent/
```

报告必须只保存摘要、路径、计数、质量、gate 与问题，不复制敏感内容。重复媒体、越界路径、缺失摘要、未知设备、fixture 标记、标注泄漏到推理上下文或权限不安全均 fail closed。

## 当前状态

- C01 真机空房已取得。
- C02～C10、夜视、长稳和完整标注仍 Open。
- C6c 音轨能力已有 E2 记录，但 V01～V09、逐字稿、语音 A/B 封存和 `speech_review_ready` 仍 Open。
- SDHY1 心率/呼吸已有 E2 路径，但缺失值和完整夜语义仍 Open。
- 因此当前只能使用已有证据做工具和局部字段 Review，不能发布 `capture_bundle_ready_for_d1=true`。
