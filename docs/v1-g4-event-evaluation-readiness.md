# V1-R1 G4 事件标注、候选评测与就绪门

状态：Implemented for E1 tooling validation；真实 C6c 事件指标仍 Open

基准日期：2026-07-22

关联输入：[M2c 采集包就绪门](v1-m2c-capture-readiness-gate.md)、[G4 跌倒运动特征](v1-g4-fall-motion-features.md)

## 1. 目标与边界

本模块补齐 M2c 采集和 G4 特征之间的评测缺口：验证两份以上独立动作区间标注、计算标注一致性、绑定裁决真值，并对外部生成的跌倒候选事件计算 TP/FP/FN、recall、误触发和检出延迟。

它不生成候选事件、不定义横卧/下降/静止如何合成跌倒，也不调姿态阈值。候选生成逻辑必须作为独立策略文件进入 bundle，其 SHA-256 同时绑定预测文件和来源 run。这样可以先把评测框架打通，又不把 synthetic fixture 的固定候选伪装成比赛版判定规则。

所有契约继续固定：

- `risk_assessment_emitted=false`；
- `alert_emitted=false`；
- E1/fixture 最多得到 `tooling_only`；
- 只有真实非模板 E2+ 数据才可能得到 `event_metrics_ready_for_review=true`，该状态仍不等于模型晋级或告警授权。

## 2. 数据流

```text
M2c capture manifest + readiness report + clean assessor run
        │
        ├── 独立 annotation A/B ── interval IoU / onset agreement
        │                              │
        │                              └── adjudication final labels
        │
        ├── candidate-generator policy（只绑定摘要，不由 evaluator 执行）
        │
        └── 三 variant candidate events + clean source runs
                                       │
                                       └── one-to-one event matching
                                              ├── TP / FP / FN
                                              ├── precision / recall / F1
                                              ├── false activations / hour
                                              └── detection delay

                    -> FallEventEvaluationReadinessReport
                       （无原始窗口、路径、annotator ref、风险或告警）
```

评测 bundle 的所有引用必须是 bundle 根目录内的规范化相对路径，并同时固定非零字节数和 SHA-256。路径越界、摘要漂移、未知字段、variant 漂移、model/feature/candidate policy 漂移或 run configuration 不一致均 fail closed。

## 3. 输入契约

### 3.1 Bundle

`event-evaluation-bundle.json` 固定以下对象：

| 对象 | 作用 |
|---|---|
| M2c capture manifest | 提供 sanitized clip index、duration、held-out 时间顺序和三模型 policy binding |
| M2c readiness report + run manifest | 证明采集包已由指定 stage 评估，并绑定 report/capture 摘要 |
| Candidate-generator policy | 声明候选是去重后的 event episode；保存决策逻辑摘要和 G4 feature policy 摘要 |
| Independent annotation sets | 每份覆盖相同 clip，保存动作区间、certainty、独立 annotator ref 和冻结时间 |
| Adjudication | 绑定全部 annotation SHA-256、最终区间和争议已解决状态 |
| Variant predictions + source runs | 每个姿态 variant 一份候选 episode 和一份 clean/completed 来源 run |

当前策略要求三个 held-out variant：`yolo26n-pose`、`rtmpose-m-humanart` 和 `torchvision-keypointrcnn`。预测流必须使用同一个 candidate-generator policy SHA-256；这样三者的指标才属于同一事件规则口径。

### 3.2 标注与 held-out 顺序

每份独立标注和裁决文件必须覆盖 capture manifest 的全部 scenario ID，duration 必须完全一致。只允许本策略比较的 `bend_pick`、`bed_lie` 和 `simulated_fall`；同一 clip 内同标签区间不得重叠。裁决动作区间必须全部为 `certain`。

时间顺序固定为：

```text
capture end
  <= independent annotations frozen
  <= adjudication frozen
  <= manifest labels_frozen_at
  <= first_inference_at
  <= candidate source run started/generated/finished
```

来源 run 必须 `completed`、`code_dirty=false`、代码版本非 `unknown`，evidence level 与本次评估一致。run configuration 逐项绑定 capture、pose model、G4 feature、candidate policy 和 candidate file SHA-256。

## 4. 冻结一致性门

策略文件为 `configs/v1-g4-event-evaluation-policy.json`。当前口径：

| 项目 | 值 |
|---|---:|
| 最少独立标注 | 2 |
| Interval IoU 匹配 | `>= 0.5` |
| 全动作 pairwise interval F1 | `>= 0.8` |
| `simulated_fall` pairwise interval F1 | `>= 0.8` |
| 匹配 fall 平均绝对起点差 | `<= 500 ms` |
| 最少 clip / fall / negative clip | 5 / 2 / 3 |
| 必需 hard negative 动作 | `bend_pick`、`bed_lie` |

对每个 annotator pair、每个 clip、每个比较标签做最大 IoU 的一对一匹配。若匹配数为 `M`，两侧窗口数为 `N1/N2`，interval F1 为 `2M/(N1+N2)`。报告只保存窗口数、匹配数、F1 和起点差摘要，不保存 annotator ref 或原始时间窗口。

一致性高不代表标注正确；真实数据还需要内容抽查和裁决人责任记录。该工具只验证约定的双人一致性与裁决链是否完整。

## 5. 事件指标口径

候选文件中的每条记录必须是已去重的 event episode，包含 episode start/end 和首次 `detected_at`。这些时间只在内存中参与匹配，不进入父报告。

对每个 clip 的 adjudicated `simulated_fall`：

1. 候选 `detected_at` 位于 `[truth.start - 500 ms, truth.end + 2000 ms]` 才有资格匹配。
2. 按相对 truth start 的绝对延迟从小到大做一对一匹配。
3. 匹配为 TP；未匹配候选为 FP；未匹配真值为 FN。
4. detection delay 为 `detected_at - truth.start`，因此允许负值。

父级口径如下：

- `precision = TP / (TP + FP)`；
- `recall = TP / (TP + FN)`；
- `false_activations_per_hour = 全部未匹配候选 / 全部 held-out clip 暴露小时数`；
- `negative_clip_false_activation_rate = 至少一个候选的无 fall clip / 全部无 fall clip`；
- delay 保存 mean、median、p95、min、max。

“每小时误触发”按短 E1 fixture 换算时数值会很大，只用于验证公式。真实报告必须同时给出原始 FP、暴露时长和 negative clip 分母，不能只展示比例。

## 6. Readiness 状态

`event_metrics_ready_for_review=true` 同时要求：

1. 非 fixture、非 synthetic、非 template，`source_type != fixture` 且 evidence `>= E2`；
2. M2c `camera_ready_for_model_retest=true`，且本次评测包含的全部 clip 都 `structurally_usable=true`；
3. 标注数量/动作覆盖、pairwise agreement、裁决和最低正负样本门均通过；
4. capture assessor 与三个 candidate source run 的 clean/completed/时间/摘要血缘全部通过。

状态区分：

| Decision | 含义 |
|---|---|
| `tooling_only` | 结构、公式与来源链通过，但属于 fixture 或 sub-E2 |
| `capture_gate_closed` | 真实输入的评测结构通过，但 M2c camera/clip gate 未开 |
| `not_ready` | 标注、裁决、样本或来源硬门失败 |
| `event_metrics_ready_for_review` | 指标可提交人工 Review；不是模型采用或告警授权 |

## 7. 隐私与产物

`FallEventEvaluationReadinessReport` 只保存 opaque case/evaluation ref、scenario、时长、计数、比例、延迟摘要、policy/run 摘要和 gate 状态。它不保存：

- bundle/媒体本地路径；
- annotator/adjudicator ref；
- annotation start/end；
- candidate ID、episode 或 detected time；
- bbox、keypoints、track ID；
- RiskAssessment 或 Alert。

原始标注、裁决、候选和 run manifest 只登记为摘要化 `SourceAsset`，仍按 raw sensitive 管理。

## 8. 命令与 E1 回归

```bash
make PYTHON=.venv/bin/python prepare-g4-event-evaluation-fixture
make PYTHON=.venv/bin/python assess-g4-event-evaluation-fixture
```

直接评估真实受控包：

```bash
kangshield-info assess-event-evaluation \
  data/raw/v1-m2c/<capture_id>/event-evaluation-bundle.json \
  --policy configs/v1-g4-event-evaluation-policy.json \
  --evidence-level E2 \
  --source-type local_file \
  --require-ready
```

`--require-ready` 在 gate 未开时返回 2，但成功完成的评估 run 仍为 `completed`。当前 E1 fixture 固定 12 clip、2 个 fall、10 个 negative clip，并人为放置可手算的 TP/FP/FN；它只验证 scorer，不使用模型推理，也不代表任何候选的真实性能。

## 9. 真实 C6c 到位后的执行顺序

1. 先用 REV-014 流程得到 `camera_ready_for_model_retest=true` 的冻结包，并纳入 C11/C12 安全模拟跌倒及 hard negatives。
2. 在首次推理前冻结最终裁决标签和 `first_inference_at`；不得看三模型输出后修改窗口。
3. 用待 Review 的同一 candidate-generator policy 从三姿态来源生成去重 event episode；来源 run 写齐六项摘要。
4. 运行本 evaluator，先 Review 双人一致性、裁决和来源门，再解释模型差异。
5. 若要修改组合逻辑、refractory、early/late tolerance 或样本口径，升级 policy/version 并重新跑全部 variant，不覆盖历史结果。
