# V1-R1 G4 CAUCAFall ADL 负样本压力报告

状态：Accepted for E1 public-data stress slice；真实设备 G4 remains Open

基准日期：2026-07-22

实现提交：`336bbe9`

Slurm：job `1762`，L40，completed，exit `0:0`

正式运行：`20260722T112332Z-f7970d63`

## 1. 结论

12 段 CAUCAFall 无跌倒 ADL 已完成可重复准备和双姿态变体全量回放。RTMPose 的 person-box 覆盖为 602/661（91.07%），高于 YOLO 的 540/661（81.69%）；两者推理均快于实时。

更重要的结果是：YOLO 没有激活横卧框代理，RTMPose 激活 17/602 帧，最长连续 1000 ms。17 帧全部处于关键点门失败的 `box_only` 路径：10 帧来自 kneel，其余出现在弯腰或人物位于画面边缘的片段。它们不是 17 次“误报”，因为系统没有分类器或告警判定；但它们直接否定“单帧宽高比即可报警”的设计。

下降和低运动在无跌倒 ADL 中同样会自然出现。V2 只能把这些字段作为条件输入，必须继续结合持续时间、轨迹/关键点质量、场景覆盖和人工确认，当前仍固定不输出 RiskAssessment 或 Alert。

## 2. 数据与可复现性

数据来自 [CAUCAFall V4](https://data.mendeley.com/datasets/7w7fccy7ky/4)，DOI `10.17632/7w7fccy7ky.4`，许可证 `CC-BY-4.0`。选择 3 个光照 subject × 4 个 ADL，共 12 个原始 AVI；不做转码。

| 对象 | SHA-256 |
|---|---|
| Frozen source manifest | `3e173cef85b611fb038dc714592ee5350e9048313982b9ae3f17090816904b69` |
| Prepared suite | `37cf32e26361f679eb15528856e82e1014bc6e8c1257edcf9dea3079a0cf8277` |
| Dataset lock | `f8bb837c07bb354beacb3cc51013b42edd10e54432ea25abd1def565e7c2f4b8` |
| G4 feature config | `3bedf218e9e413c1ab168134b8333db5cdebf764d5f8c9ece65ba212ea9d5eda` |
| Pose model policy | `b5b4bcbf908221c7057794962c2cfd37a2d728c6f6b98695efbe2be73d1deeed` |

父 run 与 24 个 variant/case child run 均为 `code_version=336bbe9`、`code_dirty=false`、E1、completed。共采样 661 帧/variant，生成 1322 个 pose events 和 1322 个 fall-motion events。

## 3. 总体结果

| 指标 | YOLO26n | RTMPose-m HumanArt |
|---|---:|---:|
| Cases / sampled frames | 12 / 661 | 12 / 661 |
| Person-box frames | 540 | 602 |
| Pose frame coverage | 81.69% | 91.07% |
| Unavailable frames | 121 | 59 |
| Box + keypoints | 526 | 298 |
| Box-only | 14 | 304 |
| Keypoint gate pass / box | 97.41% | 49.50% |
| Horizontal bbox frames | 0 | 17 |
| Maximum horizontal duration | 0 ms | 1000 ms |
| Rapid descent | 4 / 403 | 6 / 447 |
| Low motion | 224 / 436 | 265 / 493 |
| Risk / alert emitted | false / false | false / false |

RTMPose 的更高框覆盖没有转化成更高关键点门通过率。其 304 个 box-only 帧证明“有框”和“几何可用”必须继续分开汇报；YOLO 的较高 gate pass rate 只在其成功检测的 540 帧上成立，不能掩盖 121 个 unavailable 帧。

## 4. 按动作与光照

### 4.1 按动作

表内格式为 pose coverage / horizontal frames / rapid descent frames / low-motion frames。

| Activity | YOLO26n | RTMPose |
|---|---:|---:|
| Kneel | 76.33% / 0 / 0 / 70 | 87.57% / 10 / 0 / 90 |
| Pick up object | 74.03% / 0 / 0 / 39 | 85.06% / 1 / 3 / 48 |
| Sit down | 77.27% / 0 / 0 / 68 | 92.86% / 1 / 0 / 79 |
| Walk | 96.74% / 0 / 4 / 47 | 97.83% / 5 / 3 / 48 |

低运动在所有动作中都会激活；下降也会出现在普通行走或拾物片段。任何把单个代理直接映射到跌倒的规则都会产生结构性混淆。

### 4.2 按光照

| Illumination | Frames | YOLO coverage / horizontal | RTMPose coverage / horizontal |
|---|---:|---:|---:|
| Natural ~210 lux | 193 | 79.27% / 0 | 89.12% / 4 |
| 0 lux IR | 214 | 86.45% / 0 | 100.00% / 3 |
| Artificial ~130 lux | 254 | 79.53% / 0 | 85.04% / 10 |

本切片显示 RTMPose 在 0 lux IR 的 person-box coverage 为 100%，但只有一个 subject/房间，不能据此宣称通用夜视性能。

## 5. 横卧代理定位

RTMPose 的 17 帧全部为 `keypoint_gate=failed_required_points`，因此躯干几何不可用：

| Case | Activity / light | Horizontal frames | Longest duration | E1 定位 |
|---|---|---:|---:|---|
| s10-kneel | kneel / artificial | 10 | 1000 ms | 跪地/俯身形成宽框；中途 track 2→3，历史重置 |
| s01-walk | walk / natural | 4 | 600 ms | 人物接近画面边缘，框受截断和姿态影响 |
| s06-pick-up-object | pickup / IR | 1 | 0 ms | 弯腰拾物 |
| s06-sit-down | sit / IR | 1 | 0 ms | 坐下过程单帧 |
| s06-walk | walk / IR | 1 | 0 ms | 行走过程单帧 |

人工抽查只用于定位错误形态，不形成新标签或定量准确率。结论是：box-only 保留了可解释性，但不能作为自动决策捷径；在关键点门失败时尤其必须保留不确定性。

## 6. 性能与模型绑定

| 指标 | YOLO26n | RTMPose |
|---|---:|---:|
| Model load wall | 646.752 ms | 451.763 ms |
| Pose inference total | 8181.631 ms | 16585.453 ms |
| Mean / p95 | 12.378 / 13.097 ms | 25.091 / 108.742 ms |
| Pose inference RTF | 0.061888 | 0.125457 |
| Replay pipeline RTF | 0.076963 | 0.140938 |
| Cold-start pipeline RTF | 0.081855 | 0.144355 |
| Torch peak allocation snapshot | 65.532 MiB | 43.137 MiB |

两者在当前 L40 上均明显快于实时；RTMPose 推理 RTF 约为 YOLO 的 2.03 倍，但覆盖更高。Torch 指标不包含 ONNXRuntime 分配，不能作为 RTMPose 总显存峰值。

YOLO 权重摘要为 `eb3bb826...14522a9`，绑定继续记录 `AGPL-3.0-or-Ultralytics-Enterprise`。RTMPose pose/detector 摘要分别为 `12e1b9fc...758316c` / `3dea6513...2f5f23`，两项 artifact 均为 `model-artifact-license-review-required`；本次结果不解锁比赛分发。

## 7. 自动化、隐私与产物

- 自动化：59 passed；`pip check` 无 broken requirements；`compileall`、`bash -n`、CLI help 和 `git diff --check` 通过。
- Parent run 的 `bbox_xyxy`、`keypoints_xyc`、`/home/yyy`、`data/raw` 和 `data/processed` 均为 0 命中。
- 24 个 child case report 同样无框、关键点和本地路径；原始 pose events 只留在被忽略的 child JSONL。
- 1322 个 fall-motion events 均无原始框、关键点、phase label、参考转写或本地路径，且 risk/alert 全为 false。
- 24 个视频 SourceAsset 均使用摘要 URI，`contains_raw_media=true`、`source_path_persisted=false`。

| 正式产物 | SHA-256 |
|---|---|
| Parent manifest | `95456e8424c26a15f0e13e8c0d0ea79c4602cf9661146f0a16986868cc107214` |
| Parent report | `455be03ab06dea4d99efc5eeedbd62c8680d2feed119f5eaa6bbe3d1fdbef331` |

Slurm accounting elapsed 38 秒；`/usr/bin/time` wall 33.58 秒，最大 RSS 1,962,332 KiB。两个时间口径分别保留，不混写。

## 8. Review 决定

1. 接受 CAUCAFall 12-case 清单、准备器、dataset lock 和独立 child/parent benchmark 作为 G4 E1 回归资产。
2. 接受 RTMPose 在该集上的更高 person-box coverage，但不据此冻结最终姿态模型；关键点 gate pass 只有 49.50%，HumanArt 分发门仍 Open。
3. 将“单帧 bbox horizontal 不得直接触发告警”冻结为 V2-D1 约束；17 个无跌倒 ADL 激活是直接反例。
4. 不计算 false-positive rate、precision、recall 或 F1；当前没有 held-out 分类器、事件标签或告警输出。
5. CAUCAFall 关闭弯腰/坐下/跪地/行走和三种光照的公开 E1 压力子门；空房、床上躺卧、家具、宠物、多人、C6c 正负样本和事件指标仍 Open。

## 9. 下一步

1. 优先补空房/家具/床上躺卧/person-absent 数据；若许可证仍不明确，改为团队受控采集并记录同意与留存。
2. 用 C6c 按同一 5 FPS 配置采集白天/夜视、距离、遮挡和安全模拟跌倒，先保持阈值冻结以观察域偏移。
3. 另设 held-out 决策集后才设计横卧持续 + 下降 + 低运动 + 质量/区域约束的候选规则，并报告事件级误触发与延迟。
4. 继续评测一个不依赖 HumanArt 训练条款的姿态候选；RTMPose 仍是条件候选，不是最终提交模型。

## 10. REV-013 三模型补充证据

后续 job `1764` 在干净提交 `eae5f56` 上增加 Keypoint R-CNN：person-box 为 621/661（93.95%），box + keypoints 为 523，keypoint gate 为 523/621（84.22%），推理 RTF 为 0.105836。它出现 7 个 horizontal bbox 帧，最长 200 ms；其中 5 帧同时通过关键点门且 torso-horizontal，动作仍是 no-fall kneel/walk。

这项补充把原决定加强为：“单帧 bbox horizontal 不得告警”之外，“关键点门通过 + torso-horizontal 也不得直接告警”。候选移除了 HumanArt 依赖，但 URFD lying gate 仅通过 4/21，且 COCO/ImageNet 权重分发仍待审查，因此只保留为 fallback。完整运行、哈希和错误定位见 [Keypoint R-CNN 独立候选报告](../models/v1-m3-torchvision-keypointrcnn-candidate.md)。
