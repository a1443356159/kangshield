# V1-M3 姿态模型同集对比报告

状态：Accepted for V1-M3 pose slice

日期：2026-07-22

## 1. 结论

YOLOX-m HumanArt + RTMPose-m HumanArt 在当前固定 URFD 六段视频上显著补足了横卧人体框覆盖：整体从 152/170（89.41%）提高到 163/170（95.88%），`lying` 从 9/21（42.86%）提高到 20/21（95.24%）。候选在 L40 上推理 RTF 为 0.123668，满足这组 5 fps 回放的实时要求。

该链路只晋级为“V2 有条件候选”，不冻结为最终比赛模型。最困难的 fall-01 中，候选虽然把 `lying` 覆盖从 2/8 提高到 7/8，但这些横卧帧的平均 `>=0.5` 关键点可见比例仍为 0；返回人物框不代表髋、肩和踝点足以支持跌倒规则。

## 2. 可追溯运行

| 项目 | 值 |
|---|---|
| 代码提交 | `0674be9` |
| Git 状态 | parent + 12 child 全部 `code_dirty=false` |
| Slurm | job `1760`, `COMPLETED`, exit `0:0`, elapsed 00:00:19 |
| 节点 / GPU | `hepnode1` / NVIDIA L40 46,068 MiB |
| 父 run | `20260722T053908Z-9b8096cd` |
| 固定集 | `v1-m2b-public-fixed-6`, 6 case, 170 sampled frames |
| case manifest SHA-256 | `da41471e2577efe6f8d4f859319c59daddfcd778fdeed6e89cfaeb09b20e9265` |
| Python / Torch / ORT | 3.13.13 / 2.13.0+cu130 / ONNXRuntime 1.27.0 |
| ONNX provider | detector 与 pose 均为 `CUDAExecutionProvider`，CPU 仅列为 fallback provider |
| `/usr/bin/time` | command wall 14.55 s；MaxRSS 1,921,468 KiB；exit 0 |

父报告位于本机受控运行目录：

```text
runs/20260722T053908Z-9b8096cd/reports/pose-model-comparison-report.json
```

`runs/`、模型和固定集媒体均被 Git 忽略，不作为仓库分发内容。

## 3. 覆盖率

| 分组 | YOLO26n-pose | HumanArt + RTMPose | 差值 |
|---|---:|---:|---:|
| 全部 | 152/170 = 89.41% | 163/170 = 95.88% | +6.47 pp |
| fall class | 70/82 = 85.37% | 81/82 = 98.78% | +13.41 pp |
| ADL class | 82/88 = 93.18% | 82/88 = 93.18% | 0 pp |
| not_lying | 127/127 = 100% | 127/127 = 100% | 0 pp |
| falling_transition | 15/15 = 100% | 15/15 = 100% | 0 pp |
| lying | 9/21 = 42.86% | 20/21 = 95.24% | +52.38 pp |
| unlabeled | 1/7 = 14.29% | 1/7 = 14.29% | 0 pp |

改善集中在已知失败点，没有通过改变 ADL 或未标注帧数量制造整体提升。固定集没有人物存在负标签，因此本表不能给出人物检测误报率。

## 4. 横卧错误分析

| Sequence | YOLO lying | Candidate lying | YOLO `>=0.5` keypoint ratio | Candidate `>=0.5` keypoint ratio | 解释 |
|---|---:|---:|---:|---:|---|
| fall-01 | 2/8 | 7/8 | 17.65% | 0% | 框覆盖改善，但关键点不可用于稳定几何规则 |
| fall-02 | 0/6 | 6/6 | 无输出 | 73.53% | 候选实质补足已知漏检 |
| fall-03 | 7/7 | 7/7 | 48.74% | 79.41% | 覆盖相同，候选关键点可见性更高 |

全体人物阳性帧上，候选平均 `>=0.3` 关键点可见比例为 95.16%，基线为 87.42%；`>=0.5` 分别为 87.64% 与 84.09%。不同模型的分数未做概率校准，这些阈值只作同一工程 Pipeline 的质量门观察，不能当作跨模型 AP。

候选每个检测框都会获得 IoU track ID，因此 tracking coverage 为 100%；基线 ByteTrack 为 97.37%。两者算法不同，tracking coverage 不是本轮选型指标。fall-01/02 各出现 3 个候选 track ID，说明短时 IoU ID 仍存在碎片。

## 5. 性能

| 指标 | YOLO26n-pose | HumanArt + RTMPose |
|---|---:|---:|
| 模型加载 wall | 616.073 ms | 499.640 ms |
| 首帧 | 999.402 ms | 537.705 ms |
| 平均帧推理 | 15.961 ms | 24.822 ms |
| P95 帧推理 | 10.369 ms | 107.635 ms |
| 最大帧推理 | 999.402 ms | 537.705 ms |
| 推理 RTF | 0.079518 | 0.123668 |
| 回放 Pipeline RTF | 0.128630 | 0.171755 |
| 进程 GPU 显存快照 | 622 MiB | 1,124 MiB |

平均值包含各 variant 的首次冷启动离群点，因此可以出现 mean 大于 P95。GPU 数值是在各 variant 推理结束、模型仍驻留时读取的当前进程快照，不是高频采样峰值；Torch allocator 的峰值也不包含 ONNXRuntime 分配，报告没有把二者混成同一“峰值显存”。

候选比基线慢，但仍远低于 1.0 RTF。V2 demo 应保持模型常驻并预热；在 C6c 真实分辨率、多人和并发流确认前，不据此承诺生产吞吐。

## 6. Review 决定

1. YOLOX-m HumanArt + RTMPose-m HumanArt 晋级为 V2 姿态“有条件候选”；YOLO26n-pose 保留为 V1 对照，不再默认视为最终模型。
2. 最终模型门仍关闭：需要 V1-M2c C6c 白天/夜视、距离、遮挡、起坐/弯腰/横卧样本复测。
3. fall-01 类困难横卧不能只使用关键点规则。后续同时保留人体框宽高比、框中心下降、横卧持续时间和静止特征，并为关键点设置显式质量门。
4. 0.05 检测阈值是在同一固定集扫描后选定，后续 C6c/held-out 集必须冻结此值，不能继续按结果调参。
5. 增加空房、家具、宠物和局部人体负样本，测量低阈值带来的误报；当前固定集无法完成这项结论。
6. Apache-2.0 实现记录不自动解决 Human-Art/组成训练集、URFD 派生数据和最终比赛分发条款；V1-R1 前完成许可证 Review。
7. V1-M3 姿态切片通过 Review，但整个 V1-M3 仍为 In progress；语言对照和睡眠字段路线尚未关闭。

## 7. 下一步

1. 执行 V1-M2c 受控 C6c 采集，不等待睡眠仪字段即可先录视频/音频时间基样本。
2. 在相同 5 fps、0.05 阈值下复跑候选，按白天/夜视、距离、遮挡和动作分组。
3. 增加关键点质量门和 box-only 横卧 fallback 的离线特征实验，不直接生成告警。
4. 取得 CS-EP-SDNL1 脱敏 API/SDK/导出样例后，再决定睡眠字段映射，不训练不存在的睡眠模型。
