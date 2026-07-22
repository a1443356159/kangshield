# V1-R1 G4 跌倒候选 episode 公开压力报告

状态：Accepted for E1 candidate-generation/public-data stress slice；真实 C6c 事件指标与 V1-R1 仍 In progress

运行日期：2026-07-23

实现提交：`dc6cace`

正式运行：`20260722T165156Z-3dd84457`

## 1. 结论

首版 label-blind 跌倒候选状态机已在查看未来 C6c held-out 输出前冻结，并完成三姿态 variant × 18 个公开 case、共 54 项 E1 压测。生成器只读取既有 G4 `FallMotionFrameValue`，全部 episode 生成后才由评测层读取 URFD posture phase 与 CAUCAFall action-level no-fall 标签。

结果没有形成一个可以直接选型的赢家：

| Variant | URFD simulated-fall 激活 | URFD ADL 激活 | CAUCAFall no-fall 激活 | Negative episodes/hour | Coarse onset delay |
|---|---:|---:|---:|---:|---:|
| YOLO26n-pose | 0/3 | 0/3 | 0/12 | 0.000 | 无候选 |
| RTMPose-m HumanArt | 1/3 | 0/3 | 1/12 | 24.021 | 1320 ms，n=1 |
| Keypoint R-CNN | 3/3 | 0/3 | 0/12 | 0.000 | mean 1622 ms，1518～1716 ms，n=3 |

YOLO 的 0 negative episode 不能解释为低误触发能力，因为它同时漏掉 3/3 个公开模拟跌倒。RTMPose 只激活 `fall-02`，漏掉另两个 fall，并在 CAUCAFall `s01-walk` 产生一个 negative candidate。Keypoint R-CNN 在本开发切片上激活 3/3 且无 negative candidate，但该数据已经参与策略探索，样本量很小，且其 lying keypoint gate 与权重分发问题均未关闭，因此仍只能是 fallback。

5 个 episode 全部来自 `rapid_descent_then_horizontal`，settled fallback 为 0。该事实不能证明 settled 路径无用，只说明当前公开切片未触发它。所有产物继续固定不生成 RiskAssessment 或 Alert。

## 2. 冻结策略

策略为 `v1-g4-event-candidate-policy-v0.1.0`：

- transition：同 track bbox-horizontal 持续 600 ms，且之前 1500 ms 内出现 rapid-descent；
- settled fallback：bbox-horizontal 持续 1200 ms，且当前 low-motion 为 true；
- 输入 gap 上限 450 ms，track 缺失/变化清空时序历史；
- 最后横卧证据后保留 600 ms release grace；
- episode 闭合后 3000 ms refractory；
- transition 起点回溯到 lookback 内最早 rapid-descent，settled 起点按 horizontal duration 回填；
- transition 路径优先，活动 episode 只延长、不重复发射。

Candidate policy SHA-256 为 `380151c86ddaf6b79328ca516a778111fe8a7b2c2caa61e209a055bc8942dd08`，绑定 G4 feature policy `3bedf218e9e413c1ab168134b8333db5cdebf764d5f8c9ece65ba212ea9d5eda`。修改阈值、路径顺序、回溯、闭合或 refractory 语义必须升级 policy/version 并全量重跑，不能在看到 C6c held-out 结果后原地调参。

## 3. 数据与来源绑定

### 3.1 URFD 三路 G4 source

| Variant | Source run | Manifest | Report | Feature stream |
|---|---|---|---|---|
| YOLO26n | `20260722T103206Z-aa69e875` | `8e839fa6...52b1524366` | `171d5e30...08f6891f5` | `9a72b867...7051bd8865` |
| RTMPose | `20260722T103206Z-671bfb95` | `c73aeb31...d560a237` | `98f316b8...a2f058af` | `8e9b99bb...d63646aea` |
| Keypoint R-CNN | `20260722T121434Z-2e11f559` | `88ba9af0...8f04208a` | `87a90bf1...b71d72c1` | `582b7386...dcc68b1f` |

三路均为 clean、completed、E1 的 `v1-g4-fall-feature-benchmark`，绑定同一 6-case benchmark 摘要 `da41471e2577efe6f8d4f859319c59daddfcd778fdeed6e89cfaeb09b20e9265`。每路严格分为 3 个 simulated-fall 和 3 个 ADL case。

### 3.2 CAUCAFall

三路共同复用 parent run `20260722T120722Z-10fe9abb`：

| 对象 | SHA-256 |
|---|---|
| Parent manifest | `c76f2b4258fd92f74cd01d37901fa6577571a85e083dd3c156604fc7b7b644b1` |
| Parent report | `369275b58a9148e32a58c25f36abefc8b566bd57be4533dea8684f991b3aaef4` |
| Prepared suite | `37cf32e26361f679eb15528856e82e1014bc6e8c1257edcf9dea3079a0cf8277` |

runner 逐个校验 36 个 child manifest/report/features：stage、run ID、代码版本、case/variant/video digest、父子 report 逐字段一致、frame count、duration 和 risk/alert 绑定均通过。数据为 CAUCAFall V4、DOI `10.17632/7w7fccy7ky.4`、CC-BY-4.0。

URFD 为 CC-BY-NC-SA-4.0，且 fall 是公共 subject 的模拟动作。两套数据都不是 C6c、目标老人或独立 held-out 证据。

## 4. 结果细节

### 4.1 Candidate 数与路径

| Variant | Total episodes | Positive episodes | Negative episodes | Transition path | Settled path |
|---|---:|---:|---:|---:|---:|
| YOLO26n | 0 | 0 | 0 | 0 | 0 |
| RTMPose | 2 | 1 | 1 | 2 | 0 |
| Keypoint R-CNN | 3 | 3 | 0 | 3 | 0 |

每个 variant 的 negative exposure 都是 149,868 ms，包含 3 个 URFD ADL 与 12 个 CAUCAFall no-fall clip。RTMPose 的 1 个 negative episode 因此换算为 24.021139 episodes/hour。该分母只有约 2.5 分钟，数值方差会非常大，不能写成长期家庭误报率。

### 4.2 Positive 激活与 delay

| Case | YOLO26n | RTMPose | Keypoint R-CNN |
|---|---:|---:|---:|
| URFD fall-01 | 未激活 | 未激活 | 激活，delay 1716 ms |
| URFD fall-02 | 未激活 | 激活，delay 1320 ms | 激活，delay 1518 ms |
| URFD fall-03 | 未激活 | 未激活 | 激活，delay 1632 ms |

delay 相对 URFD coarse `falling_transition` 首帧计算，不是双标注/裁决事件起点。Keypoint R-CNN 的 3/3 只能说明该实现与本状态机在这三段开发数据上更容易形成持续候选；它不能覆盖此前 lying gate 仅 4/21、CAUCAFall torso-horizontal no-fall 反例或 COCO/ImageNet 权重分发 Review。

### 4.3 Negative 激活

URFD 三个 ADL 对三个 variant 均为 0/3。CAUCAFall 中只有 RTMPose 在 `caucafall-s01-walk` 激活一次；该 episode 使用 transition 路径，而不是 settled fallback。这说明“横卧持续 + 近期下降”仍会在普通行走/画面边缘的 box-only 轨迹中成立，必须保留人物截断、身份与目标域困难负样本门。

本轮不会根据该单例修改阈值。它作为冻结策略的已知失败案例进入后续 C6c Review。

## 5. 可复现性、来源与隐私

正式 manifest 为 E1、completed、`code_version=dc6cace`、`code_dirty=false`、0 issue；五个步骤全部 completed。生成与评测不运行模型，整体 wall 约 96 ms，其中 127 个 SourceAsset 登记 74 ms、候选生成 5 ms、公开评测 7 ms。

父报告在两次开发运行和一次正式运行中的 SHA-256 完全相同：

`797974b75b6e16be86d4e836d8045ec2c6ca5dc2b53d0631c9a80759735e7d83`

正式产物：

| 对象 | SHA-256 |
|---|---|
| Manifest | `19abd1d4776450022b350497c52bbb12aa55629d46666a1038323999317c42d6` |
| Aggregate report | `797974b75b6e16be86d4e836d8045ec2c6ca5dc2b53d0631c9a80759735e7d83` |

隐私与完整性结果：

- 127 个来源资产全部使用摘要 URI，未保存本地源路径；
- 5 个精确 episode 只存在于被 Git 忽略的 derived-sensitive `features.jsonl`，且各自反查触发 G4 feature ID；
- manifest、父报告与 SourceAsset 对 `/home/`、`data/processed`、`start_ms`、`end_ms`、`detected_at_ms`、`candidate_id`、`selected_track_id`、bbox、keypoints 的扫描均为 0 命中；
- 5 个 episode 与全部 case/variant/parent report 的 risk/alert 均为 false。

自动化为 94 passed；`pip check` 无 broken requirements；`compileall` 与 `git diff --check` 通过。

## 6. Review 决定

1. 接受 `v1-g4-event-candidate-policy-v0.1.0`、状态机、契约、来源门、CLI/Make 入口和正式 run，作为首个非 fixture 的 G4 candidate-generator E1 基线。
2. 冻结 transition/settled、起点回溯、release、refractory、track/gap reset 和 label-blind 语义；未来 C6c 首轮必须原样使用。
3. 不依据本公开开发集冻结最终模型。YOLO 继续是 V1 对照；RTMPose 继续是有条件准确率候选；Keypoint R-CNN 继续是未选 fallback。
4. 公开 fall 激活覆盖、negative activation 和 episodes/hour 只用于回归与错误定位，不称 precision、recall、F1、灵敏度、特异度或 C6c 准确率。
5. Candidate episode 仍只是 M3/M7 工具产物，不进入 RiskAssessment 或 Alert；V1-R1 保持 In progress。

## 7. 下一步

1. C6c E2 capture 到位后，不修改本 policy，分别从三路 clean G4 feature run 生成 candidate stream。
2. 以相同 candidate-policy digest 导出事件 evaluator bundle，完成双人独立标注、裁决、TP/FP/FN、negative-clip activation、episodes/hour 和 delay。
3. 补床上躺卧、空场持续、宠物移动、画面边缘与真实多人身份切换；这些数据用于评估当前 policy，而不是静默调参。
4. 单独 Review 多人 candidate 的归属与去重语义；当前仍是 largest-bbox 场景级单 episode。
5. 继续关闭 HumanArt 与 Keypoint R-CNN 权重/训练数据分发门，再做最终比赛模型选择。
