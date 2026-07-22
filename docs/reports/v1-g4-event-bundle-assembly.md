# V1-R1 G4 Event Bundle Assembly E1 报告

日期：2026-07-23

结论：三路 candidate prediction/source run、capture readiness、双标注与裁决已通过新组装器形成 self-contained event bundle。组装在 clean 实现提交 `7b64719` 上完成；全部敏感 JSON 为 owner-only `0600`，不含 source path、不复制原媒体。组装时 preflight 与主树 evaluator 复跑逐字段一致，provenance gate 通过，按 E1 synthetic 边界保持 `tooling_only`、Risk/Alert false。

## 1. 实现范围

本轮新增：

- `assemble_fall_event_evaluation_bundle` 原子组装 API；
- `assemble-event-evaluation-bundle` CLI；
- `FallEventBundleAssemblyReport` 路径无关 receipt；
- 固定 private layout、relative path/size/SHA-256 引用和 `0600` 权限；
- 原 evaluator preflight 后才发布，失败删除 staging，禁止覆盖既有目录；
- API、CLI、顺序确定性、权限、重评一致性与 late-preflight cleanup 回归。

完整边界见 [G4 Event Evaluation Bundle 组装](../v1-g4-event-bundle-assembly.md)。

## 2. 固定输入

本轮复用 REV-018 干净 candidate-export fixture，不重新生成标签或 candidate：

| 输入 | SHA-256 / 数量 |
|---|---|
| Capture manifest | `8bf5af9ad0c08a6c65ef799d04fbe098f3937f9a1b2299f6167054157a815595` |
| M2c readiness report | `2c809e22df2be6fe781e73291e90e2443dcb1953fc80711d01424f192642f270` |
| M2c assessor manifest | `97e51c1a7bf59b933754acee34f647a7a1fcb088aabbcf6729421e2397b889dc` |
| Rule-bearing candidate policy | `b426f823eb72f034b2bd1f2f6613b2c1c86be5d005680e0cd0d8334da04124a3` |
| Annotation / adjudication | 2 份 independent annotation + 1 份 adjudication |
| Candidate prediction/source | YOLO26n、RTMPose、Keypoint R-CNN 各 1 对；均来自 clean REV-018 exporter run |

输入仍是 12 个 3 s synthetic clip。candidate 数和事件分数是预构造 fixture layout，只验证接口，不代表姿态模型或 C6c 性能。

## 3. Assembly 结果

- 实现提交 `7b64719`，执行时 worktree clean；
- bundle SHA-256：`3a8c7be99b4946f99780793ff761b99e1a7bb1794e1c6a137eb2a9ea7b842331`；
- assembly report SHA-256：`8d1216dda24d30ecaf4dbb9bfda8c4239f2b5c33bde2b7916861de0dc77cb5f2`；
- 复制 source file 13 个，输出目录共 16 个文件；
- 3 个 variant 与 2 份 annotation 均按稳定规则排序；
- 16/16 文件权限为 `0600`；目录由 private staging 的 `0700` 权限继承；
- bundle JSON 中绝对 source path 为 0，`..` 引用为 0；
- `source_paths_persisted=false`、`raw_media_copied=false`；
- `risk_assessment_emitted=false`、`alert_emitted=false`。

组装 receipt 如实记录 `preflight_decision=tooling_only`、`preflight_quality_status=partial`、`provenance_gate_passed=true`、`event_metrics_ready_for_review=false`。

## 4. 独立 evaluator 复跑

组装器在 branch implementation 上先调用 evaluator 生成 `event-evaluation-preflight.json`；随后使用主树 clean 提交 `b233abe` 对发布后的 bundle 再运行原 CLI：

- evaluator run：`20260722T182727Z-5e95a5f8`；
- run status `completed`、`code_dirty=false`、0 issue、15 个 SourceAsset；
- run manifest SHA-256：`a9dc01e0faeb6f4528208a96344d51b9567378f5df1d0570a9fe018d40e8ecb8`；
- report SHA-256：`e96d676cf17aa92b639c65cc41602a536e95d774368bb0fa906a0321d5965327`；
- preflight SHA-256 同为 `e96d676cf17aa92b639c65cc41602a536e95d774368bb0fa906a0321d5965327`，逐字节一致；
- annotations、agreement、adjudication、minimum data、provenance 五门通过；
- camera gate 因 synthetic fixture 关闭，最终 `tooling_only`，不进入事件指标 Review。

三路 fixture TP/FP/FN 与 REV-018 原 bundle 完全一致，说明组装没有改写 prediction 或标签。数值不在本报告重复解释，也不得用于模型排名。

## 5. Fail-closed 验证

- annotation 顺序反转后按内容摘要稳定排序，不改变 bundle 结构；
- prediction variant 重复或 prediction/source run ID 不一致时在发布前拒绝；
- fixture/capture/policy/source-type 不一致时拒绝；
- 输出目录已存在时拒绝，不提供 `--force`；
- 测试在全部复制完成后注入 annotation capture digest 漂移，evaluator preflight 抛错，目标目录与随机 staging 均不存在；
- 已发布 bundle 再评估与内置 preflight 逐字段一致；
- bundle report 与 preflight 均不包含 annotation/candidate 窗口、annotator ref 或本地 source path。

## 6. 自动化验证

- 全量测试：105 passed；
- `compileall` 通过；
- 全部 Slurm shell syntax 通过；
- `pip check` 无 broken requirements；
- `git diff --check` 通过。

## 7. 下一步

真实 C6c 路线无需再手工拼 evaluator JSON：三路 clean feature run 经 REV-018 导出 candidate 后，直接调用本组装器并读取 preflight gate。仍需完成的硬门没有改变：C6c E2 capture、独立标注与责任人、真实正负暴露、床上躺卧/多人、最终权重许可证以及 RiskAssessment/Alert 设计。
