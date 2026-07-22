# V1-M3 TorchVision Keypoint R-CNN 独立姿态候选

状态：Accepted for E1 comparison；未选为主候选；权重分发仍 Blocked

基准日期：2026-07-22

## 1. 目标

REV-012 要求继续评测一个不依赖 HumanArt 训练条款的姿态路线。本切片选择 TorchVision `KeypointRCNN_ResNet50_FPN_Weights.COCO_V1`，复用现有 `PoseDetection`、V1-M2b 固定集和 CAUCAFall G4 压力集，回答三个问题：

1. 是否能补足横卧和 ADL 人体框覆盖；
2. 覆盖是否能转化为冻结 COCO-17 关键点门可用性；
3. 去掉 HumanArt 依赖后，比赛分发许可证是否已经关闭。

本切片不训练模型、不扫描当前测试集阈值、不实现跌倒分类器，也不把公开 E1 结果外推为 C6c 实机性能。

## 2. 冻结模型与来源

模型策略位于 `configs/v1-m3-torchvision-pose-model.json`。

| 项目 | 冻结值 |
|---|---|
| Variant | `torchvision-keypointrcnn` |
| Weight enum | `KeypointRCNN_ResNet50_FPN_Weights.COCO_V1` |
| Weight SHA-256 | `fc266e953d2b302cdcbb9ae66f71f6b0d4649928bf02dc573961e361e4918926` |
| Byte size | 237,034,793 |
| Parameters / reference GFLOPs | 59,137,258 / 137.42 |
| Output | person bbox + COCO-17 keypoints |
| Detection threshold | 0.5 |
| Resize | min 800 / max 1333 |
| Tracking | greedy IoU，阈值 0.2，最多丢失 2 帧 |
| Implementation license | BSD-3-Clause |
| Artifact status | `model-artifact-license-review-required` / `blocked_pending_review` |

官方实现与指标见 [TorchVision Keypoint R-CNN 文档](https://docs.pytorch.org/vision/stable/models/keypoint_rcnn.html)，实现许可证见 [TorchVision LICENSE](https://github.com/pytorch/vision/blob/main/LICENSE)。TorchVision 的[预训练模型总说明](https://docs.pytorch.org/vision/master/models.html)明确要求使用者自行确认权重所依赖数据集的许可条件。

当前权重血缘记录为 COCO 2017 keypoints 训练和 ImageNet-1K backbone 初始化。该路线去掉了 HumanArt 依赖，但没有自动取得最终权重再分发许可：[COCO Terms of Use](https://cocodataset.org/#termsofuse)要求继续检查图像各自许可，[ImageNet access agreement](https://image-net.org/accessagreement)也必须单独审查。因此实现许可证不能覆盖权重和训练数据血缘，最终比赛包继续 fail closed。

## 3. Adapter 与分数语义

```text
BGR frame
   └── RGB float tensor [0, 1]
          └── Keypoint R-CNN COCO_V1
                 ├── person score >= 0.5
                 ├── clipped bbox
                 ├── COCO-17 coordinates
                 └── raw keypoint heatmap-max logit
                        └── sigmoid quality proxy
                               └── PoseDetection + greedy IoU track
```

TorchVision 返回的 `keypoints_scores` 在当前实现中包含可正可负的 heatmap 最大 logit。本 adapter 使用数值稳定 sigmoid 将其压到 `[0, 1]`，仅为了复用现有质量门；ModelBinding 固定记录 `keypoint_confidence_is_calibrated_probability=false`。

因此：

- 该值不是概率，不能与 YOLO 或 RTMPose 的关键点分数直接排名；
- `>=0.3` / `>=0.5` 只表示本候选在冻结变换下的工程质量代理；
- 真正选型必须同时看人物框覆盖、必需肩/髋点门、动作混淆和目标域证据。

## 4. 统一评测链路

```text
V1-M2b six-video fixed suite
   └── three PoseBackend variants
          └── same sampled timestamps / phase evaluator
                 └── PoseModelComparisonReport
                        └── clean child pose events
                               └── FallMotionFeatureExtractor
                                      └── URFD phase feature report

CAUCAFall 12 no-fall ADL clips
   └── three PoseBackend variants
          └── pose + fall-motion child events
                 └── activity / illumination aggregate
```

三模型直接推理使用相同 5 FPS 和未针对本轮结果调整的候选参数。M2b 派生 G4 运行只读取已完成的 candidate child events，不重复模型推理；候选 policy SHA-256 必须与 ModelBinding 完全一致，否则失败。

## 5. 运行

准备和离线校验：

```bash
PYTHONPATH=src python scripts/prepare_v1_m3_torchvision_pose_model.py
PYTHONPATH=src python scripts/prepare_v1_m3_torchvision_pose_model.py --offline
```

三模型正式回放：

```bash
make submit-m3-pose-comparison
make submit-g4-adl-benchmark
```

从干净 M2b 姿态父报告派生候选 G4 特征：

```bash
kangshield-info benchmark-fall-features \
  data/processed/v1-m2b/benchmark-cases.json \
  runs/<pose-parent>/reports/pose-model-comparison-report.json \
  --variant torchvision-keypointrcnn
```

正式结果见 [TorchVision Keypoint R-CNN 候选报告](reports/v1-m3-torchvision-keypointrcnn-candidate.md)。

## 6. 验收与决定边界

本轮只有在以下条件同时成立时才允许把候选提升到当前主候选：

1. M2b 横卧覆盖提升，同时必需肩/髋关键点门不劣于 RTMPose；
2. CAUCAFall no-fall ADL 不出现无法解释的单代理优势；
3. L40 实时系数小于 1；
4. 权重、COCO、ImageNet 和比赛包分发审查关闭；
5. C6c 白天/夜视/遮挡/多人和 held-out 正负样本通过。

当前仅满足覆盖和 L40 实时性。URFD 横卧关键点门、ADL 代理混淆、最终分发与 C6c 门均未关闭，因此结论固定为“保留独立备选，不替换当前 RTMPose 条件参考，也不进入最终比赛包”。
