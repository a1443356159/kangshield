# V1-M3 TorchVision Keypoint R-CNN 独立候选报告

状态：Accepted E1 evidence；Retain as fallback；Not selected；Distribution blocked

日期：2026-07-22

实现提交：`eae5f56` / `d956203`

## 1. 结论

TorchVision Keypoint R-CNN 在 V1-M2b 上返回 163/170 个人体帧，与 RTMPose 相同；`lying` 为 21/21，比 RTMPose 多 1 帧。CAUCAFall ADL 上覆盖 621/661（93.95%），高于 RTMPose 的 602/661（91.07%），L40 推理也保持明显快于实时。

这些覆盖收益没有形成稳定的横卧几何优势。复用同一 G4 质量门后，候选在 URFD `lying` 的 21 帧中只有 4 帧通过必需肩/髋点门，17 帧退化为 `box_only`；RTMPose 是 11/20 通过。CAUCAFall 中候选出现 7 个 horizontal bbox 帧，其中 5 帧的关键点门通过且躯干角也为 horizontal，动作却是无跌倒的 kneel 或 walk。这直接证明“有框 + 关键点门通过 + 横向躯干”仍不是跌倒事件。

因此本候选保留为独立 fallback 和后续目标域对照，不替换 RTMPose 条件参考，也不选为 V2 最终模型。其代码为 BSD-3-Clause，但 COCO/ImageNet 权重血缘和比赛分发审查仍未关闭，artifact 继续标记 `model-artifact-license-review-required`。

## 2. 可追溯运行

| 项目 | M2b 三模型 | CAUCAFall 三模型 | M2b 候选 G4 派生 |
|---|---|---|---|
| Code | `eae5f56`, clean | `eae5f56`, clean | `d956203`, clean；source `eae5f56`, clean |
| Job / execution | Slurm `1763`, L40, 0:0 | Slurm `1764`, L40, 0:0 | 本地纯派生，completed |
| Parent run | `20260722T120654Z-d1d51960` | `20260722T120722Z-10fe9abb` | `20260722T121434Z-2e11f559` |
| Cases / children | 6 × 3 / 18 | 12 × 3 / 36 | 6 source children |
| Evidence | E1 | E1 | E1 |
| Manifest SHA-256 | `4261237f73260fc941dfee8d9ea1e87073f43a9fdfee0f7a5bee1499cd3d7afd` | `c76f2b4258fd92f74cd01d37901fa6577571a85e083dd3c156604fc7b7b644b1` | `88ba9af03230216197814282d2bbeffbbc8d6d2eedf786a1a92b5b818f04208a` |
| Report SHA-256 | `9c2264b14140f4923c2ed28b6a5ec79ddffea6477f402822746137e05a6c964f` | `369275b58a9148e32a58c25f36abefc8b566bd57be4533dea8684f991b3aaef4` | `87a90bf1b8cb327e41702a2f8414bc237998e290a5775fa9a198bfb2b71d72c1` |

两个 Slurm parent、54 个 child 与派生 run 均 completed；对应 parent/child `code_dirty=false`。候选权重 SHA-256 为 `fc266e95...4918926`，策略 SHA-256 为 `92188335...186f8db`。

## 3. V1-M2b 姿态覆盖

| 指标 | YOLO26n | RTMPose HumanArt | Keypoint R-CNN |
|---|---:|---:|---:|
| Overall | 152/170 = 89.41% | 163/170 = 95.88% | 163/170 = 95.88% |
| Fall class | 70/82 = 85.37% | 81/82 = 98.78% | 82/82 = 100% |
| ADL class | 82/88 = 93.18% | 82/88 = 93.18% | 81/88 = 92.05% |
| Lying | 9/21 = 42.86% | 20/21 = 95.24% | 21/21 = 100% |
| Inference RTF | 0.076224 | 0.122077 | 0.100451 |

候选的覆盖优势来自 fall class，代价是 ADL 比 RTMPose 少 1 帧。其候选平均推理为 20.162 ms、P95 23.414 ms、model load 1133.261 ms。不同后端的检测和关键点分数没有概率校准，报告中的可见比例不能作为跨模型 AP 或置信度优劣。

## 4. URFD G4 横卧与质量门

| `lying` 指标 | RTMPose | Keypoint R-CNN |
|---|---:|---:|
| Sampled / box available | 21 / 20 | 21 / 21 |
| Horizontal bbox | 17/20 | 21/21 |
| Keypoint gate passed | 11/20 | 4/21 |
| Box-only | 9 | 17 |
| Torso horizontal among gate-passed | 5/11 | 2/4 |

候选在 not-lying 阶段为 126/127 有框且 126 帧全部通过关键点门；问题集中在横卧。它并不是“关键点整体差”，而是横卧时必需肩/髋点质量明显退化。fall class 还出现 14 帧 `multiple_people_largest_bbox_only`，其中 lying 为 10 帧；URFD 没有对应检测框真值，当前不能区分真实多人、重复框或背景误检。

候选 falling-transition 的 rapid descent 为 6/15，ADL class 也有 3/71；时序代理同样不能单独作事件判定。

## 5. CAUCAFall no-fall ADL 压力

| 指标 | YOLO26n | RTMPose | Keypoint R-CNN |
|---|---:|---:|---:|
| Person-box coverage | 540/661 = 81.69% | 602/661 = 91.07% | 621/661 = 93.95% |
| Box + keypoints | 526 | 298 | 523 |
| Box-only | 14 | 304 | 98 |
| Keypoint gate pass / box | 97.41% | 49.50% | 84.22% |
| Horizontal bbox frames | 0 | 17 | 7 |
| Torso-horizontal frames | 36 | 4 | 46 |
| Maximum bbox-horizontal duration | 0 ms | 1000 ms | 200 ms |
| Rapid descent | 4/403 | 6/447 | 10/533 |
| Low motion | 224/436 | 265/493 | 313/558 |
| Inference RTF | 0.062476 | 0.125566 | 0.105836 |

候选 7 个 horizontal bbox 帧中，6 帧来自 kneel、1 帧来自 walk；5 帧为 `box_plus_keypoints` 且躯干角也为 horizontal，另 2 帧为缺少必需点的 box-only。最长连续 200 ms。候选总计 46 个 torso-horizontal 帧，分布在 pick-up 24、kneel 11、sit 7、walk 4。

这些数字不是误报计数，因为没有分类器、事件阈值和 Alert。它们说明：

1. Keypoint R-CNN 比 RTMPose 有更高 box coverage 和 gate pass，但仍有动作相关的几何混淆；
2. 关键点门通过只说明字段可用，不说明姿态属于跌倒；
3. horizontal bbox、horizontal torso、rapid descent 和 low motion 在 no-fall ADL 中都会激活，必须在独立 held-out 决策层组合并验收。

## 6. 许可证与分发决定

| 层 | 当前结论 |
|---|---|
| TorchVision implementation | BSD-3-Clause |
| Frozen pretrained weight | review required |
| COCO image / annotation lineage | per-source terms review required |
| ImageNet backbone initialization | access/use terms review required |
| Competition bundle redistribution | blocked pending review |

候选成功移除了 HumanArt 依赖，但没有得到“可直接随比赛包分发”的结论。实现、权重、训练数据和比赛提交物必须分层审查，不能把 TorchVision 仓库 LICENSE 复制成权重许可证。

## 7. 自动化与隐私

- 65 tests passed；`pip check` 无 broken requirements；`compileall`、`bash -n` 和 `git diff --check` 通过。
- CAUCAFall parent report 无 bbox、关键点、本地路径或 risk/alert true。
- 36 个 child 共生成 1983 个 pose events 和 1983 个 fall-motion events；后者全部无原始框/关键点，风险与告警均为 false。
- M2b 候选派生报告与 170 个派生事件同样不保存原始框、关键点或 phase label。
- 原始坐标只保留在被 Git 忽略且受控的 pose child events。

## 8. Review 决定

1. 接受冻结权重、策略、adapter、三模型 runner、G4 接入和 E1 证据作为可重复资产。
2. Keypoint R-CNN 标记为 `Conditional fallback / not selected`；不替换 RTMPose 当前条件参考。
3. 不根据 M2b 或 CAUCAFall 重新调整 0.5、800/1333 或 G4 阈值，避免把公开固定集继续变成调参集。
4. 冻结“关键点门通过且躯干水平也不得直接告警”为 V2-D1 约束；CAUCAFall 的 5 帧 no-fall 反例已经证明该组合不足。
5. 最终模型必须在 C6c held-out 正负样本、多人/空房/床上躺卧、事件指标和分发审查全部关闭后再决定。
6. 若两条预训练路线都无法关闭分发门，V2 应转向权利清晰的数据和自有训练/导出权重，而不是继续增加未经审查的公开 checkpoint。
