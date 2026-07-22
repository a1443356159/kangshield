# V1-R1 G4 Open Images 静态居家人物检测压力报告

状态：Accepted for E1 static person-detection stress slice；V1-R1 与真实 G4 仍 In progress

运行日期：2026-07-22

## 1. 结论

修正版 12-case suite 已在干净提交 `fad9491` 和 NVIDIA L40 上完成三模型正式运行。该结果关闭“许可证可审计的静态家具/宠物 person-absent 与室内多人框压力链路”这个 E1 子门，但没有关闭视频、tracking、床上躺卧、跌倒事件或 C6c 目标域。

RTMPose 在本小集合上取得最低的 person-absent false activation（2/8）并匹配 11/11 多人框；Keypoint R-CNN 也匹配 11/11，但 person-absent 激活为 3/8，且多人子集多 3 个未匹配预测；YOLO 的多人预测没有 FP，但远距离会议室两人均漏检，匹配 9/11，同时 person-absent 激活为 3/8。三条路线都暴露出不同失败面，结果不支持直接冻结最终比赛模型。

## 2. 数据与运行绑定

| 项目 | 正式值 |
|---|---|
| Suite | `v1-g4-openimages-static-home-negative-12-r2` |
| Source manifest | `434126ff0919dabed9ee40d702d71993fd8b5866d6c46162fa1441c8c2acfcd0` |
| Prepared suite | `e62b34dbf093253e240bf780a85105caaf0ade09e722415a85136ba330340470` |
| Attribution | `fbcbec44f0276e09f6567d2c00d5c4cae0a9529de59ebf8e6e10c4f072e55efd` |
| Dataset lock | `7568e4b8c49f4e8629a151c9dd05d2ff67ff08a030b1e84ec16bfa8c647b3f94` |
| Model policy | `b5b4bcbf908221c7057794962c2cfd37a2d728c6f6b98695efbe2be73d1deeed` |
| TorchVision policy | `921883358f6f2b23f0760d9f9612213adb044f54c9ac3e6ae24c8225e186f8db` |
| Commit | `fad9491`，`code_dirty=false` |
| Slurm | job `1766`，`hepnode1`，NVIDIA L40 46,068 MiB，completed `0:0`，16 s |
| Parent run | `20260722T151348Z-a34b37b3` |
| Parent report | `fafafe109afcfafe5c946653371db4a06418399aa14664c1506c34dc2f777945` |

Open Images annotations 固定为 Google LLC / CC BY 4.0；12 张图分别固定作者、标题、原始 landing page 与 CC BY 2.0。图片从 CVDF validation 下载源逐字节复制。当前逐图页面检查日期为 2026-07-22，比赛展示或再分发前仍须重新审计。

## 3. 主要指标

### 3.1 Person-absent 与多人分开解释

| Variant | 无人激活 | 家具无人 | 宠物无人 | 多人匹配 | 多人 FP / FN | 多人 P / R | 至少一人 / 全部匹配 case |
|---|---:|---:|---:|---:|---:|---:|---:|
| YOLO26n-pose | 3/8，37.5% | 2/4 | 1/4 | 9/11 | 0 / 2 | 100.00% / 81.82% | 3/4 / 3/4 |
| RTMPose-m HumanArt | 2/8，25.0% | 2/4 | 0/4 | 11/11 | 2 / 0 | 84.62% / 100.00% | 4/4 / 4/4 |
| Keypoint R-CNN | 3/8，37.5% | 1/4 | 2/4 | 11/11 | 3 / 0 | 78.57% / 100.00% | 4/4 / 4/4 |

无人激活比例按 case 计算；多人 precision/recall 只使用 4 张多人图片的框级 IoU 0.5 一对一匹配。两者不能混成事件误报率。

### 3.2 全套聚合

| Variant | 预测框 | Matched | FP | FN | Overall precision | Overall recall |
|---|---:|---:|---:|---:|---:|---:|
| YOLO26n-pose | 12 | 9 | 3 | 2 | 75.00% | 81.82% |
| RTMPose-m HumanArt | 16 | 11 | 5 | 0 | 68.75% | 100.00% |
| Keypoint R-CNN | 17 | 11 | 6 | 0 | 64.71% | 100.00% |

Overall FP 同时包含 person-absent 图片中的全部预测和多人图片中未匹配预测，所以不能用它替代分场景结果。12 张图片规模过小，也未审计与预训练数据是否重叠；这些数值只用于定位与回归，不是可泛化准确率。

## 4. Case 级发现

1. 三个 variant 都在 `oi-furniture-sofa-toy` 激活人物；画面含坐姿人形玩偶，是必须保留的静态困难负样本。
2. YOLO 还在 `oi-furniture-man-cave` 与 `oi-pet-cat-reclining` 激活；RTMPose 在 `oi-furniture-bedroom` 输出 2 框、在 sofa-toy 输出 1 框，但 4 个宠物 case 均未激活；Keypoint R-CNN 在 sofa-toy、dog-on-bed 和 cat-on-bed 激活。
3. `oi-multi-conference-room-distance` 中 YOLO 输出 0 框，漏掉两个远距离人物；RTMPose 与 Keypoint R-CNN 都匹配两人，同时分别产生 2 个额外预测。报告不保存预测坐标，因此额外预测究竟对应椅背、远景纹理还是其他结构仍不能确认。
4. 其余三张多人图片上，YOLO 为 9/9 matched、0 FP；RTMPose 为 9/9、0 FP；Keypoint R-CNN 为 9/9、1 FP。多人完整匹配不能外推为多人 track 不串人，因为每张图只推理一次且 tracking 已关闭。

这些结果来自冻结阈值：YOLO `0.35`、RTMPose detector `0.05`、Keypoint R-CNN `0.5`。本轮没有按结果调阈值，也不会在这 12 张图上调完再报告同集性能。

## 5. 性能

| Variant | Model load | First inference | Mean inference | P95 inference | Peak CUDA allocation |
|---|---:|---:|---:|---:|---:|
| YOLO26n-pose | 601.328 ms | 873.970 ms | 115.749 ms | 114.214 ms | 65.532 MiB |
| RTMPose-m HumanArt | 416.426 ms | 372.025 ms | 88.695 ms | 143.135 ms | 43.137 MiB |
| Keypoint R-CNN | 1119.551 ms | 129.492 ms | 63.434 ms | 120.243 ms | 742.249 MiB |

Mean 包含首张冷启动，P95 是 12 张图的观测分位。整个命令 wall time 为 11.17 s，`/usr/bin/time` 最大 RSS 为 2,448,508 KiB。静态单图耗时不能直接替代 C6c 视频实时系数。

## 6. 首轮证据拒绝

job `1765` / run `20260722T142224Z-f6769569` 在提交 `40359c1` 上执行成功，但 post-run 视觉 Review 发现 `oi-multi-wheelchair-occlusion` 的 Person boxes 未覆盖画面中一个明显人物；正确检出会被误计为 FP。该 run 因真值边界不可靠被拒绝，不进入本报告指标。

修正提交 `fad9491` 做了三件事：

1. suite ID 升为 r2，替换为可见两人与两个 Person 框一致的远距离会议室图片；
2. 每个 case 固定 `visible_person_count`，并要求它与 Person box 数一致；
3. 多人 case 必须显式通过 `person_box_alignment=passed` 与逐框视觉对齐 finding，否则准备器 fail closed。

这次拒绝说明“官方框存在”仍不能取代当前任务的样本级 Review；也说明 source digest 和 suite revision 必须共同进入正式报告。

## 7. 可复现性与隐私审计

- parent manifest：E1、completed、`fad9491`、`code_dirty=false`、0 error / 0 warning；41/41 step completed。
- child：36 个唯一 run，36/36 E1、completed、`fad9491`、clean、0 error / 0 warning；36/36 `tracking_enabled=false`。
- parent 输入：suite、attribution、dataset lock、pose policy、TorchVision policy 共 5 个 aggregate SourceAsset，摘要与本报告一致。
- 准备器连续两次生成相同 suite、attribution 与 lock。
- parent + 36 child reports 与 SourceAsset 扫描：`bbox_norm_xyxy`、`bbox_xyxy`、`keypoints_xyc`、`track_id`、`/home/`、原始 landing/作者页和 risk/alert true 均为 0 命中。
- parent、variant 与 36 个 case report 的 `risk_assessment_emitted=false`、`alert_emitted=false`。

## 8. Review 决定与下一步

1. 接受 r2 source manifest、逐图 attribution、dataset lock、静态 runner、严格契约和 job `1766` 作为 G4 的 E1 静态人物检测压力证据。
2. RTMPose 保持准确率条件参考；本切片的 2/8 false activation 与 11/11 matched 是积极证据，但低阈值导致 5 个 overall FP，且 HumanArt 分发门、C6c 与时序门均未关闭。
3. Keypoint R-CNN 继续只保留 fallback；它没有因 11/11 matched 晋级，宠物误激活和最高 overall FP 仍需目标集验证。
4. YOLO 继续只作为 V1 对照；它在多人 matched prediction 上最干净，但远距离两人全部漏检，且许可证路线仍未关闭。
5. 不在本 12 图上调检测阈值或增加 checkpoint。下一轮只在预先冻结的 C6c held-out 视频上验证空场持续误触发、宠物移动、床上躺卧、多人 tracking 和跌倒事件。
6. V1-R1 保持 In progress；本报告不授权 RiskAssessment、Alert 或比赛模型最终选型。
