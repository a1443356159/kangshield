# V1-R1 G4 事件评估 E1 初测报告

状态：Accepted for E1 tooling slice；真实 C6c 事件指标与 G4 仍 Open

基准日期：2026-07-22

实现提交：`b0b2e97`

正式运行：`20260722T160819Z-854d8845`

## 1. 结论

双人独立动作区间、pairwise interval/onset agreement、裁决真值、三路 candidate episode、held-out/source provenance 和事件级 TP/FP/FN/误触发/延迟已经通过同一条离线评测链。正式 run 为 `completed`、E1、fixture、`code_dirty=false`，scorer step 18 ms。

本次 12 个 synthetic clip 共 36 秒，包含 2 个 `simulated_fall` 和 10 个 negative clip。两份标注的 5/5 动作区间全部匹配，整体与 fall interval F1 均为 1.0，匹配 fall 平均/最大绝对起点差均为 100 ms。annotation、agreement、adjudication、minimum-data 和 provenance 五个工具门均通过。

结果固定为 `decision=tooling_only`、`quality_status=partial`：M2c `camera_ready_for_model_retest=false`，因此 `capture_camera_gate_passed=false`、`event_metrics_ready_for_review=false`。所有候选是手工固定的 scorer 回归输入，没有执行 YOLO、RTMPose 或 Keypoint R-CNN 推理，以下数值不能解释为模型性能或选型证据。

## 2. Fixture 与冻结口径

| 项目 | 结果 |
|---|---|
| Clips / exposure | 12 / 36,000 ms |
| Independent annotations | 2，annotator ref 唯一但不进入报告 |
| Compared actions | `bend_pick`、`bed_lie`、`simulated_fall` |
| Adjudicated fall / negative clip | 2 / 10 |
| Hard negatives | C05 bend、C06/C10 bed-lie |
| Candidate streams | YOLO26n、RTMPose、Keypoint R-CNN；同一 synthetic candidate policy |
| Interval agreement | IoU `>=0.5`；overall/fall F1 `>=0.8`；fall mean onset diff `<=500 ms` |
| Event match | truth start 前 500 ms 至 truth end 后 2000 ms；按绝对 onset delay 一对一匹配 |
| False activation/hour | 全部未匹配候选 / 全部 36 秒 held-out exposure |

候选 episode、标注和裁决时间只在输入 bundle 中使用。父报告不包含 start/end/detected time、candidate ID、annotator/adjudicator ref 或路径。

## 3. 确定性 scorer 结果

| Variant | TP | FP | FN | Precision | Recall | F1 | FP/hour | Negative clip activation | Median delay | P95 delay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RTMPose fixture stream | 2 | 1 | 0 | 0.666667 | 1.0 | 0.8 | 100.0 | 1/10 | 200 ms | 290 ms |
| Keypoint R-CNN fixture stream | 2 | 2 | 0 | 0.5 | 1.0 | 0.666667 | 200.0 | 2/10 | 100 ms | 145 ms |
| YOLO26n fixture stream | 1 | 1 | 1 | 0.5 | 0.5 | 0.5 | 100.0 | 1/10 | 200 ms | 200 ms |

这些值与 fixture 中手工放置的候选完全一致：RTMPose 两个 TP 加一个 bed-lie FP；Keypoint R-CNN 两个 TP 加 bend/bed 两个 FP；YOLO 一个 TP、一个 bend FP 并漏掉一个 fall。每小时换算分母只有 0.01 小时，因此 1 个 FP 即为 100 FP/hour；该数值只验证公式。

## 4. Gate 结果

| Gate | 结果 | 说明 |
|---|---|---|
| `annotations_complete` | true | 2 份独立标注、全 clip、2 fall、bend/bed hard negative |
| `agreement_gate_passed` | true | 5/5 overall、2/2 fall 匹配；onset 差 100 ms |
| `adjudication_complete` | true | 绑定两份 annotation SHA；争议已解决；最终区间均 certain |
| `minimum_data_gate_passed` | true | 12 clip、2 fall、10 negative，超过 E1 policy 最低数 |
| `provenance_gate_passed` | true | capture assessor 与三 candidate source run 均 clean/completed/摘要与时间顺序一致 |
| `capture_camera_gate_passed` | false | synthetic M2c report，未取得真实 C6c E2 证据 |
| `event_metrics_ready_for_review` | false | fixture/E1 永远不能打开真实指标门 |
| Risk / alert | false / false | 契约 Literal false |

父报告有 0 error、2 个预期 warning：`capture_camera_gate_closed` 与 `fixture_or_sub_e2_evidence`。这两个 warning 是证据边界，不是工具失败。

## 5. 来源、摘要与可重复性

| 对象 | SHA-256 |
|---|---|
| Event evaluation bundle | `d68376b30b5ff9bec52a36d892a93f074c338647fb1ef812870d089c455aa8dd` |
| Evaluation policy | `91e35f8637ea2520e07f07b65f5f3fac2122fd399dd53bb921839594480283d8` |
| M2c capture manifest | `8bf5af9ad0c08a6c65ef799d04fbe098f3937f9a1b2299f6167054157a815595` |
| M2c readiness report | `2c809e22df2be6fe781e73291e90e2443dcb1953fc80711d01424f192642f270` |
| Synthetic candidate policy | `dae72d3a967cd752ebc3100b13f04a073ff79bd4cd3ef3574322630c0082bfdc` |
| Formal run manifest | `3e064dd6df04d047236b6ad9b53202e4db97bd7a97ffd127e220a7c95f3ec75d` |
| Formal readiness report | `8cde985ce61970d5b86c7042400c351b98b0615fc0bc6b4812d6829380865915` |

准备器连续生成两份完整 fixture：32/32 相对路径一致，32/32 文件 SHA-256 一致。正式 run 登记 15 个摘要化 SourceAsset；run configuration 保存 bundle、policy、capture、candidate-policy 和 output report 摘要，不保存输入路径。

## 6. 自动化、失败门与隐私

- 自动化：85 passed；`pip check` 无 broken requirements；`compileall` 与 `git diff --check` 通过。
- 回归覆盖：路径越界/摘要漂移拒绝、dirty candidate source 关闭 provenance、低双标注一致性关闭 gate、确定性 32-file 复现、`--require-ready` 返回 2 但 run completed。
- Strict schema：bundle、annotation、adjudication、candidate policy/predictions 与 source run 都拒绝未知字段；同标签标注区间和去重 candidate episode 均禁止重叠。
- 正式 report/run 扫描 `start_ms`、`end_ms`、`detected_at_ms`、`candidate_id`、实际 annotator/adjudicator ref、bundle 相对路径、`/home/yyy`、`data/raw`、risk/alert true，均为 0 命中。
- Scorer step 的 18 ms 只包含 JSON 校验、来源检查与指标计算，不含 fixture 准备、媒体探针或任何模型推理。

## 7. Review 决定

1. 接受 `FallEventAnnotationAgreement`、`FallEventCaseEvaluation`、`FallEventVariantEvaluation`、`FallEventEvaluationReadinessReport` 和冻结 evaluation policy 作为真实 C6c 到位后的 M7 入口。
2. 接受“候选生成与事件评分分离”：evaluator 只绑定 candidate-policy 摘要，不在本切片定义跌倒决策规则。
3. 接受 interval IoU/onset、one-to-one detection-time matching、总暴露 FP/hour 和 negative-clip activation 作为 v0.1.0 口径；修改任何口径必须升级 policy/version 并全量重跑。
4. 不接受 fixture 三行结果作为姿态模型比较、跌倒 precision/recall、C6c 域内表现或阈值调优依据。
5. 本轮只关闭“双人一致性/裁决/事件 scorer E1 工具”子门。真实候选策略、C6c 正负视频、内容抽查、多人 tracking、许可证、RiskAssessment 和 Alert 仍 Open，V1-R1 保持 In progress。

后续 REV-017 已在查看 C6c held-out 输出前冻结首版非 fixture candidate policy，并完成公开 E1 压力；该后续进展不改变本 fixture scorer 报告的历史结论。C6c 真实候选/事件指标仍 Open，见[候选公开压力报告](v1-g4-fall-candidate-public-stress.md)。

## 8. 下一步

1. 按 REV-014 取得 C6c E2 核心包，并把 C11/C12 安全模拟跌倒、弯腰、床上躺卧和空场持续纳入同一 held-out revision。
2. 在首次推理前完成两份独立标注、内容抽查、裁决和 `first_inference_at` 冻结。
3. 另行设计并 Review 第一版真实 candidate-generator policy；三姿态流使用同一规则摘要生成去重 episode。
4. 用本 evaluator 形成真实按光照/距离/遮挡/场景的 event report；指标通过后仍需独立决定模型和 M5/M6 业务语义。
