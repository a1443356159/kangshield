# V1-M2b 公开真实场景固定集初测报告

状态：Accepted for V1-M2b

日期：2026-07-22

## 1. 结论

V1-M2b 已完成六个固定 case 的数据准备、批量 Pipeline、帧阶段对齐、ASR CER、覆盖率与 Slurm L40 验证：

- 6/6 child run 和 parent run 全部 `completed`。
- 170 个抽样视频帧中 152 帧检出人物，姿态帧覆盖率 89.41%。
- 152 个人物阳性帧中 148 帧含 track_id，跟踪覆盖率 97.37%。
- 137 个参考字符上有 9 次编辑，corpus CER 为 6.57%；6 条中 3 条完全匹配。
- 六个 case 的 processing 合计 6.412 秒，对 42.830 秒媒体的合并 RTF 为 0.150。
- 整套 wall time 45.242 秒，主要由共享 FunASR 冷启动 36.228 秒构成。
- 汇总报告没有复制六条参考或识别全文；输入、运行目录和媒体均未进入 Git。

本结果通过 V1-M2b 的 E1 工程验收，但不支持以下结论：目标设备已接入、自然音视频已同步、跌倒分类精度合格或当前模型已晋级 V2。

## 2. 固定输入与准备结果

| 项目 | 值 |
|---|---|
| Benchmark | `v1-m2b-public-fixed-6` |
| 视频 | URFD camera 0：fall-01/02/03、adl-01/02/03 |
| 语言 | FLEURS `cmn_hans_cn/dev`：3 female + 3 male |
| 配对 | `cross_dataset_synthetic_common_zero` |
| 证据 | E1 |
| 原始固定文件 | 16 个，636,206,634 bytes |
| URFD RGB 帧 | 995 |
| 有姿态阶段标签的帧 | 959 |
| 数据源 manifest SHA-256 | `11108991e5058c3298970bb47f3a863705e40d8974f81967889df782429e7f04` |
| benchmark-cases SHA-256 | `da41471e2577efe6f8d4f859319c59daddfcd778fdeed6e89cfaeb09b20e9265` |
| dataset-lock SHA-256 | `8fa58d178896d40ef218fc8a8b51e1057999725ed232f3a9d0a41b5e4a2e6ed5` |

准备命令连续运行两次，`dataset-lock.json` 摘要一致。FLEURS 原始 float WAV 已稳定归一化为 16 kHz、单声道、PCM16。URFD 恒帧率 replay 相对源同步 CSV 的最大累计误差为 69 ms；评测时使用 replay sidecar，所以抽样 FeatureEvent 对 sidecar 的最大匹配误差为 0 ms。这两个误差口径不能混写。

URFD 使用 CC-BY-NC-SA-4.0，FLEURS 使用 CC-BY-4.0。原始数据未提交，任何比赛材料中的媒体再使用仍需单独完成署名、非商业、相同方式共享和分发审查。

## 3. 运行证据

| 项目 | 值 |
|---|---|
| 实现提交 | `93f7d09` |
| Slurm job | `1759` |
| 状态 | `COMPLETED`，exit `0:0` |
| 节点 / GPU | `hepnode1` / NVIDIA L40 |
| Slurm elapsed | 00:00:51 |
| Parent run | `20260722T014243Z-a817b90f` |
| 运行代码 | `code_version=93f7d09`，`code_dirty=false` |
| Python / Torch | 3.13.13 / 2.13.0+cu130 |
| CUDA 峰值 allocated | 2,134.469 MiB |
| 自动化测试 | 22 passed |

Child runs：

| Case | run_id | 状态 |
|---|---|---|
| fall-01-fleurs-f01 | `20260722T014320Z-92899852` | completed |
| fall-02-fleurs-m01 | `20260722T014322Z-3301887d` | completed |
| fall-03-fleurs-f02 | `20260722T014323Z-5c4f9cd8` | completed |
| adl-01-fleurs-f03 | `20260722T014324Z-29c8c6de` | completed |
| adl-02-fleurs-m02 | `20260722T014325Z-84c3fbd8` | completed |
| adl-03-fleurs-m03 | `20260722T014327Z-26dd4fd7` | completed |

## 4. 单 case 结果

`Pose cov.` 的分母是抽样帧；`Track cov.` 的分母是人物阳性帧；CER 使用标准化后的参考字符数。

| Case | Pose cov. | Track cov. | Pose quality | Speech cov. | Ref chars | Edits | CER | Exact | Processing RTF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fall-01-fleurs-f01 | 77.78% | 95.24% | 0.866 | 72.05% | 18 | 0 | 0.00% | yes | 0.336 |
| fall-02-fleurs-m01 | 66.67% | 100.00% | 0.882 | 72.47% | 26 | 1 | 3.85% | no | 0.081 |
| fall-03-fleurs-f02 | 100.00% | 97.30% | 0.765 | 64.05% | 20 | 7 | 35.00% | no | 0.144 |
| adl-01-fleurs-f03 | 96.15% | 96.00% | 0.871 | 70.49% | 17 | 1 | 5.88% | no | 0.170 |
| adl-02-fleurs-m02 | 83.87% | 96.15% | 0.905 | 67.78% | 28 | 0 | 0.00% | yes | 0.117 |
| adl-03-fleurs-m03 | 100.00% | 100.00% | 0.822 | 80.56% | 28 | 0 | 0.00% | yes | 0.130 |

分类聚合：

| 视频类 | 抽样帧 | 人物阳性帧 | Pose cov. | Track cov. |
|---|---:|---:|---:|---:|
| fall | 82 | 70 | 85.37% | 97.14% |
| adl | 88 | 82 | 93.18% | 97.56% |

## 5. 视频阶段分析

| URFD 阶段 | 抽样帧 | 人物阳性帧 | Pose cov. | Track cov. |
|---|---:|---:|---:|---:|
| not_lying | 127 | 127 | 100.00% | 99.21% |
| falling_transition | 15 | 15 | 100.00% | 100.00% |
| lying | 21 | 9 | 42.86% | 77.78% |
| unlabeled | 7 | 1 | 14.29% | 0.00% |

关键失败不在站立或跌落过渡，而在倒地后的横卧人体：

- fall-01 的 8 个 lying 抽样帧只检出 2 帧。
- fall-02 的 6 个 lying 抽样帧全部漏检。
- fall-03 的 7 个 lying 抽样帧全部检出，但其中 1 帧没有稳定 track_id。

这说明当前 YOLO26n-pose 对画面、距离和人体横卧形态敏感。仅靠“姿态模型持续有框”会在最需要确认倒地持续性的阶段断链，不能直接作为 V2 跌倒确认器。M3 至少要在同一固定集比较 RTMPose/MMPose，并评估人体检测 fallback、短时轨迹容错和横卧持续规则。

`unlabeled` 主要来自 URFD ADL 全局特征 CSV 没有覆盖的源帧，不应被解释为新的动作类别，也不能用来计算误报率。

## 6. 语言错误分析

九次字符编辑由三类错误构成：

1. 一条中英混合样本省略了括号内的 `Moldova`，产生 7 次删除；中文主体正确。
2. 一次同音代词替换，产生 1 次替换。
3. 一处“半小时/半个小时”表达差异，产生 1 次插入。

因此官方 corpus CER 仍为 6.57%，不能为了得到更好数值删除中英混合参考。但诊断上，9 次编辑中的 7 次来自中文模型省略拉丁词，而不是普通话主体识别失败。后续报告应同时保留完整固定集 CER 和“中英混合/纯中文”分层，不应只报更有利的子集。

VAD 合并后的语音覆盖为 28.160 / 39.180 秒，即 71.87%。这只能描述当前 FLEURS 读句中的有效语音比例，不代表远场、电视背景、方言或目标老人语音性能。

## 7. 性能

| 指标 | 值 |
|---|---:|
| 六 case 媒体总时长 | 42.830 s |
| 共享语音模型加载 | 36.228 s |
| 六次 pose 模型加载合计 | 1.156 s |
| 六 case processing 合计 | 6.412 s |
| processing 合并 RTF | 0.150 |
| 整套 benchmark wall | 45.242 s |
| 含冷启动整套 wall / 媒体 | 1.056 |
| 峰值 CUDA allocated | 2,134.469 MiB |

模型加载后有明显实时余量；首个 case 的 processing RTF 仍高于后续 case，包含 CUDA/模型首轮运行开销。V1 demo 应继续使用常驻模型进程。整套 benchmark 的冷启动几乎等于一次共享 FunASR 加载，而不是六次重复加载，符合批量设计目标。

## 8. 模型与许可证

本次模型与 V1-M2a 相同：

- YOLO26n-pose + ByteTrack：Ultralytics 8.4.90，权重 SHA-256 `eb3bb826...522a9`，AGPL-3.0/Enterprise 路线。
- FSMN-VAD：权重 SHA-256 `b3be75be...25fc5`，Apache-2.0。
- SeACo Paraformer：权重 SHA-256 `3d491689...946d1`，Apache-2.0。
- CT-Punc：权重 SHA-256 `7176cae9...d6f81`，Apache-2.0。

YOLO 的横卧漏检和许可证均未关闭，当前只能保持 V1 baseline，不能在本 Review 中晋级为 V2 正式模型。

## 9. Review 结论与下一步

V1-M2b 标记 Done，完成定义是“公开真实录制固定集、可重复准备与分模态评测链路”，不是“真实设备样本完成”。后续顺序：

1. V1-M2c：获取 C6c 同意录制样本、音视频 PTS/时钟偏差和 CS-EP-SDNL1 真实字段证据。
2. V1-M3：在当前六段视频上比较 RTMPose/MMPose，优先修复 lying 阶段的 42.86% 覆盖率。
3. 在目标设备样本加入远场、夜视、遮挡、电视背景和目标人群语音，重新计算相同指标。
4. 只有模型精度、目标设备覆盖、性能和许可证均通过 Review 后，才进入 V2。

完整决定见 [REV-005](../review-log.md#rev-005-v1-m2b-公开固定集与评测-review)。
