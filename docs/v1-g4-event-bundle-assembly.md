# V1-R1 G4 Event Evaluation Bundle 组装

状态：Implemented for contract validation；真实 C6c bundle 与 E2 event review 仍 Open

基准日期：2026-07-23

关联输入：[M2c 采集包就绪门](v1-m2c-capture-readiness-gate.md)、[Capture Feature Producer](v1-g4-fall-feature-capture.md)、[Candidate Export Bridge](v1-g4-candidate-export-bridge.md)、[事件评估就绪门](v1-g4-event-evaluation-readiness.md)

## 1. 要关闭的缺口

现有 evaluator 的输入契约严格，但真实执行仍需人工把 capture/readiness、双标注、裁决、candidate policy、三路 prediction 和 source manifest 复制到一个目录，再手工计算每个 relative path、大小和 SHA-256。这个步骤一旦复制错 variant 或留下半成品目录，评估入口虽然会 fail closed，却缺少可复用的生产组装流程。

本切片增加原子组装器：

```text
capture/readiness provenance
  + independent annotations/adjudication
  + frozen candidate policy
  + 3 x prediction/source-run
  -> private staging directory
  -> strict evaluator preflight
  -> atomic publish of self-contained bundle
```

组装器不生成或修改 annotation、adjudication、candidate episode，也不计算风险或告警。

## 2. 输入契约

CLI 要求显式提供：

- capture manifest、readiness report 和对应 assessor run manifest；
- candidate-generator policy；
- 至少两份 independent annotation 与一份 adjudication；
- 每个 pose variant 的 prediction JSON 和 candidate source-run manifest；
- evaluator policy、evidence level 与 source type。

组装前先验证所有输入存在，capture 可被 strict event context 解析，candidate policy schema 有效，fixture/synthetic/source-type 一致。每份 prediction 必须符合公共 `FallCandidatePredictionSet`，source run 必须符合 `RunManifest`，二者 run ID 一致；variant ID 必须唯一且可安全用作文件名。

动作窗口与 candidate 时间不会被组装器解释或改写。它们只在 staging 中由原 evaluator 完整验证 capture/policy/variant、clip coverage、摘要、held-out 顺序、标注一致性、裁决和 source provenance。

## 3. 原子发布与隐私

输出目录必须不存在。组装器在同一父目录创建权限 `0700` 的随机 staging，按内容摘要排序 annotation，并把输入复制到固定布局：

```text
<bundle>/
├── event-evaluation-bundle.json
├── event-evaluation-preflight.json
├── bundle-assembly-report.json
├── capture/capture-manifest.json
├── evidence/
├── policies/
├── annotations/
├── predictions/
└── source-runs/
```

所有复制文件和三个顶层 JSON 固定为 owner-only `0600`。bundle 内只保存规范化相对路径、大小和 SHA-256，不保存原始 source path。组装器不复制 capture 原媒体；媒体继续留在原受控存储。

只有 evaluator preflight 完整返回后，staging 才通过同文件系统 rename 原子发布。任一 schema、摘要、路径、标注、裁决或 candidate provenance 校验抛错时，staging 会被删除，目标目录保持不存在。组装器不提供 `--force`，不会覆盖既有 bundle。

## 4. 输出

### 4.1 `event-evaluation-bundle.json`

完全兼容现有 REV-016 `_EvaluationBundle`：capture/readiness/policy/annotation/adjudication 和每路 prediction/source manifest 都有独立 file reference。variant binding 按 ID 排序，annotation 按摘要排序，因此调用参数顺序不会改变结果。

### 4.2 `event-evaluation-preflight.json`

这是原 `assess_fall_event_evaluation` 的 privacy-safe 报告。它保留 tooling-only / not-ready / ready 的真实 gate 状态，不因为“成功组装”而把 fixture、dirty source、camera gate 或数据不足升级成有效事件证据。

### 4.3 `FallEventBundleAssemblyReport`

路径无关的 receipt 保存 bundle/capture/candidate-policy 摘要、variant、annotation/复制文件数量、preflight decision/quality/provenance，以及：

- `source_paths_persisted=false`；
- `raw_media_copied=false`；
- `copied_sensitive_file_mode=0600`；
- `risk_assessment_emitted=false`；
- `alert_emitted=false`。

## 5. CLI

```bash
kangshield-info assemble-event-evaluation-bundle \
  <capture-manifest.json> \
  <m2c-capture-readiness.json> \
  <m2c-capture-run-manifest.json> \
  <candidate-policy.json> \
  <adjudication.json> \
  --annotation <annotation-a.json> \
  --annotation <annotation-b.json> \
  --prediction-source <yolo-prediction.json> <yolo-run/manifest.json> \
  --prediction-source <rtmpose-prediction.json> <rtmpose-run/manifest.json> \
  --prediction-source <keypointrcnn-prediction.json> <keypointrcnn-run/manifest.json> \
  --evaluation-policy configs/v1-g4-event-evaluation-policy.json \
  --source-type local_file \
  --evidence-level E2 \
  --output data/raw/v1-g4-event-bundles/<capture-ref>
```

成功只表示“bundle 完整且 evaluator 能解释”。是否可进入事件指标 Review 仍完全由 preflight 的真实 evidence、camera、annotation、adjudication、minimum-data 和 clean-provenance 门决定。

## 6. 验收

1. 确定性 E1 fixture 重组后仍得到三 variant、`tooling_only` 和 provenance gate true。
2. bundle JSON 不包含绝对路径或 `..`，全部引用可在输出根内解析。
3. 每个 copied input 权限为 `0600`，不复制媒体。
4. 对已发布 bundle 再运行 evaluator，报告与组装时 preflight 逐字段一致。
5. 在复制完成后的 preflight 注入 capture-binding 错误，目标与 staging 均不残留。
6. 输出目录已存在、variant 重复、prediction/run ID 不一致或 fixture marker 漂移时 fail closed。

该工具关闭的是人工拼 bundle 的工程风险，不关闭真实 C6c 数据、标注责任、事件性能、最终模型许可证或 Risk/Alert。
