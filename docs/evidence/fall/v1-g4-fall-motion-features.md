# V1-R1 G4 跌倒运动特征 E1 报告

状态：Accepted for E1 offline feature slice；真实设备 G4 remains Open

基准日期：2026-07-22

实现提交：`782026b`

正式运行：RTMPose `20260722T103206Z-671bfb95`；YOLO26n `20260722T103206Z-aa69e875`

## 1. 结论

box-only 横卧/下降/低运动特征、COCO-17 关键点质量门和 fallback reason 已在既有六段 URFD 姿态事件上打通。两次正式运行均从干净 L40 姿态源派生 170 个 `video.fall_motion_frame`，不重新推理模型，不输出 RiskAssessment 或 Alert。

RTMPose 主候选在 lying 阶段提供 20/21 个框，其中 17 个满足 bbox 横卧代理；只有 11/20 通过关键点门，剩余 9 帧明确进入 box-only。最困难的 fall-01 为 7/8 有框、4/7 横卧代理、0/7 关键点门通过，证明 fallback 不是理论分支，而是主链路必要能力。

本报告没有形成跌倒分类精度。URFD 标签只描述姿态阶段，且三条 ADL 不覆盖目标居家负样本；所有阈值仍是 E1 工程代理。

## 2. 来源与可复现性

| 项目 | 结果 |
|---|---|
| Benchmark | `v1-m2b-public-fixed-6`，6 cases，170 sampled frames |
| Source pose parent | `20260722T053908Z-9b8096cd` |
| Source pose code | `0674be9`，parent/child 均 clean、completed、E1 |
| Fall feature code | `782026b`，两次 formal run 均 `code_dirty=false` |
| Feature version | `fall-motion-features-v0.1.0` |
| Report version | `fall-feature-benchmark-v0.1.0` |
| Derived events | 每个变体 170；无原始 bbox/keypoints/phase label |
| Risk / alert | false / false，parent 与 6 个 case 均固定 |

### 输入摘要

| 对象 | SHA-256 |
|---|---|
| G4 feature config | `3bedf218e9e413c1ab168134b8333db5cdebf764d5f8c9ece65ba212ea9d5eda` |
| Current pose model policy | `b5b4bcbf908221c7057794962c2cfd37a2d728c6f6b98695efbe2be73d1deeed` |
| Benchmark cases | `da41471e2577efe6f8d4f859319c59daddfcd778fdeed6e89cfaeb09b20e9265` |
| Source pose manifest | `13db3c7395aa5ef32b0e44294c3c8c9287003ab0dba1e7a4d51d6da4c765b922` |
| Source pose report | `3ab724917a8148b80d07ab60441346adb45bd242cdab7590371b5e1ddc16df36` |

每个 case report 另保存 source child manifest、features JSONL 和 annotation SHA-256。parent manifest 共登记 23 个摘要化输入资产。

## 3. 主结果

### 3.1 Lying 与 transition

| 指标 | RTMPose candidate | YOLO26n control | 解释 |
|---|---:|---:|---|
| Lying sampled frames | 21 | 21 | 相同标签时间点 |
| Lying bbox available | 20 | 9 | 候选绝对覆盖明显更高 |
| Lying horizontal bbox | 17 | 8 | 分母不同，不只比较百分比 |
| Horizontal / available bbox | 85.00% | 88.89% | 不能据此说 YOLO 更好 |
| Keypoint gate passed | 11/20 | 3/9 | 候选仍有 9 帧必须 box-only |
| Box-only frames | 9 | 6 | 关键点门失败但框可用 |
| Unavailable frames | 1 | 12 | 无有效框就不伪造特征 |
| Transition descent available | 11/15 | 15/15 | 候选受 track reset 影响 |
| Transition rapid-descent proxy | 3/11 | 4/15 | 仅代理激活，不是召回率 |

RTMPose lying 中下降和低运动历史各只有 9 帧可用：6/9 为 rapid-descent proxy，3/9 为 low-motion proxy。其余不是 false，而是 track fragmentation、历史不足或无框导致 unavailable。

### 3.2 RTMPose 分序列定位

| Sequence | Sampled | Lying bbox | Lying horizontal | Lying keypoint gate | Lying box-only | Transition rapid descent | Lying track resets |
|---|---:|---:|---:|---:|---:|---:|---:|
| fall-01 | 27 | 7/8 | 4/7 | 0/7 | 7 | 2/5 | 5 |
| fall-02 | 18 | 6/6 | 6/6 | 5/6 | 1 | 0/1 | 0 |
| fall-03 | 37 | 7/7 | 7/7 | 6/7 | 1 | 1/5 | 3 |

fall-01 同时暴露三个独立问题：关键点完全不达门、横卧框比例不是 100%、短时 track ID 在 lying 中重置 5 次。box-only 能保留部分形状证据，但不会自动修复跟踪或产生风险结论。

### 3.3 ADL 与未标注尾帧

| 指标 | RTMPose | YOLO26n |
|---|---:|---:|
| ADL sampled frames | 88 | 88 |
| ADL bbox available | 82 | 82 |
| ADL horizontal bbox | 0 | 0 |
| ADL rapid descent | 2/73 | 1/70 |
| ADL low motion | 42/76 | 41/74 |

这说明 horizontal、descent 和 low-motion 必须分开：ADL 中下降/低运动代理会出现，但当前横卧框代理没有出现。另有 7 个 `unlabeled` 尾帧，其中 6 帧无检测；它们保留在 class/overall 统计，但不进入三个已标注 phase 的结论。

## 4. Fallback 审计

RTMPose lying 的主要 fallback：

| Reason | 帧数 |
|---|---:|
| `keypoint_gate_failed_required_points_use_box_only` | 9 |
| `track_changed_history_reset` | 8 |
| `descent_history_not_ready` | 11 |
| `stationary_history_not_ready` | 11 |
| `multiple_people_largest_bbox_only` | 6 |
| `no_person_detection` | 1 |

“multiple people”主要来自低阈值候选在困难帧返回多个框，不代表真实画面确有多人。当前 largest-bbox 只是一条显式探索策略；真实多人场景必须另做身份和轨迹 Review。

## 5. 许可证与来源门

RTMPose formal report 检测到历史姿态报告仍含两个过宽绑定，并记录纠偏：

```text
rtmpose_m_humanart.onnx: Apache-2.0 -> model-artifact-license-review-required
yolox_m_humanart.onnx: Apache-2.0 -> model-artifact-license-review-required
```

两项 digest 与当前 policy 完全匹配，report 中实现许可、训练条款和 artifact distribution status 分开保存。该纠偏不等于许可证通过；HumanArt 权重分发仍 `blocked_pending_review`。YOLO 对照继续记录 `AGPL-3.0-or-Ultralytics-Enterprise`。

## 6. 性能、自动化与隐私

- RTMPose 派生运行总 wall 约 80.9 ms；YOLO 约 77.5 ms。它们只读取既有 JSONL 并计算规则，不包含姿态模型推理时间。
- 自动化：53 passed；`pip check` 无 broken requirements；`compileall` 与 `git diff --check` 通过。
- 两个 formal run 的 340 条派生 FeatureEvent 均不含 `bbox_xyxy`、`keypoints_xyc`、`posture_label` 或参考转写。
- 对两个正式运行扫描 `/home/yyy`、`data/processed` 和源 report 完整路径均为 0 命中；SourceAsset 只保存摘要 URI。

### 正式产物摘要

| 对象 | SHA-256 |
|---|---|
| RTMPose manifest | `c73aeb311b9cc3624ad544f272dc924ea3439e3724e152ce930c9254d560a237` |
| RTMPose report | `98f316b836aa145a4ca4d90ee1276a39580b2f0d989ab9ce11aaf156a2f058af` |
| YOLO manifest | `8e839fa6fb1b2dc0de79481671d49bc878a910abb3852348b8fdc032b1524366` |
| YOLO report | `171d5e30d5bde28be58a93d92c649d69a34acd98eb44ece1b9322d808f6891f5` |

## 7. Review 决定

1. 接受 `FallMotionFrameValue`、`FallKeypointGate` 和 versioned config 作为 V2-D1 的条件输入契约。
2. 接受 box-only 作为关键点不达门时的必要 feature path；不允许跳过 gate 强算躯干角。
3. 接受 no detection、track missing/change、frame gap、history warm-up 和 multi-person ambiguity 的 fail-closed 状态。
4. 不接受任何当前代理作为跌倒分类器、风险分数或告警条件。
5. G4 E1 离线实现完成；真实 G4、G3 和 G5 仍 Open，V1-R1 保持 In progress。

## 8. 下一步

1. REV-012 已用 CAUCAFall 补拾物/坐下/跪地/行走和三档光照；REV-015 又以 Open Images r2 补静态 furniture/pet/multi-person 人物检测压力。继续增加 C6c 空场视频、床上躺卧、宠物移动和多人 tracking，并完成交付时许可证复审。
2. 取得 C6c 场景矩阵后以同一配置复跑，并报告按光照/距离/遮挡的 available、fallback 和代理激活。
3. REV-016 已实现双人动作区间、裁决、误触发/小时和检出延迟的 E1 scorer；真实设备集仍须在首次推理前冻结标注、candidate policy 与内容抽查，然后复用该口径。
4. REV-013 已评估不依赖 Human-Art 的 Keypoint R-CNN；因 lying gate 仅 4/21 和 COCO/ImageNet 分发仍 Open，只保留 fallback。最终模型与项目 LICENSE/NOTICE 仍需独立决定。

## 9. REV-013 候选派生补充

Keypoint R-CNN 来源 parent `20260722T120654Z-d1d51960` 为 clean/E1/completed；派生 run `20260722T121434Z-2e11f559` 使用代码 `d956203`，同样 clean/E1/completed。候选 lying 21/21 有框、21 个 horizontal bbox，但只有 4 帧通过关键点门，17 帧进入 box-only；not-lying 则为 126/127 有框且 126 帧全部过门。

该分裂说明候选的困难点特定于横卧几何。它不推翻 box-only fallback，反而强化“覆盖、质量门和事件语义必须分层”。正式 report SHA-256 为 `87a90bf1b8cb327e41702a2f8414bc237998e290a5775fa9a198bfb2b71d72c1`；170 个派生事件仍无原始坐标、风险或告警。完整三模型比较见 [Keypoint R-CNN 候选报告](../models/v1-m3-torchvision-keypointrcnn-candidate.md)。
