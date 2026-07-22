# V1-R1 G4 跌倒运动特征与关键点质量门

状态：Accepted for E1 offline feature slice；真实设备 G4 仍 Open

基准日期：2026-07-22

主输入：V1-M3 RTMPose / YOLO26n / Keypoint R-CNN 干净姿态事件、V1-M2b URFD 固定集

## 1. 目标与非目标

本切片把姿态检测结果转换为可审计的运动代理特征，解决两个已确认问题：

1. fall-01 横卧阶段经常有可用人体框，但 COCO-17 关键点不足以支持稳定几何规则。
2. 单帧“像横卧”不能证明跌倒，需要把框形状、中心下降、短时低运动和轨迹连续性分开表达。

输出固定为 `video.fall_motion_frame` FeatureEvent。每帧明确选择 `box_plus_keypoints`、`box_only` 或 `unavailable`，并列出 fallback reason。契约硬编码 `risk_assessment_emitted=false`、`alert_emitted=false`；本轮不定义 RiskAssessment、跌倒分数、阈值告警、precision、recall 或 F1。

## 2. 数据流与标签隔离

```text
干净 PoseModelComparisonReport + child video.pose_frame
        │
        ├── 来源 run/代码/digest/模型绑定 fail-closed 校验
        ├── 每帧最大有效 bbox（单主目标探索假设）
        │       ├── 形状、中心、底边、面积
        │       └── 同 track 历史：下降、低运动、横卧持续
        ├── COCO-17 质量门：肩 5/6、髋 11/12、全局可见率
        └── video.fall_motion_frame（不含原始 bbox/keypoints/阶段标签）

URFD annotation sidecar ──仅由 evaluator 读取──> phase/class 汇总报告
```

提取器不读取 `not_lying`、`falling_transition` 或 `lying` 标签；标签只在后处理评测中按时间戳匹配。由此避免把真值泄漏进在线特征。派生 JSONL 不复制原始 bbox、关键点、参考转写或本地路径，只保留归一化标量、布尔代理、质量门和 source feature ref。

## 3. 冻结配置

配置位于 `configs/v1-g4-fall-features.json`，SHA-256 为 `3bedf218e9e413c1ab168134b8333db5cdebf764d5f8c9ece65ba212ea9d5eda`。

| 参数 | 冻结值 | 语义 |
|---|---:|---|
| Primary selection | largest valid bbox | 只用于当前单主目标探索；不是身份跟踪 |
| Bbox horizontal | width / height `>= 1.0` | “框比高更宽”的图像代理，不等于人在地面 |
| Descent window / min span | 1000 / 600 ms | 只比较同一非空 track_id |
| Rapid descent | center-y 增量 `>= 0.15` frame height | 正值表示图像中向下；无相机标定 |
| Stationary window / min span | 600 / 400 ms | 只比较同一 track |
| Low motion | 窗口内最大中心位移 `<= 0.03` frame diagonal | 框中心静止代理，不是人体完全静止 |
| Maximum frame gap | 450 ms | 超过即重置历史 |
| Keypoint confidence | `>= 0.5` | 单点可见门 |
| Visible ratio | `>= 0.5` | 至少 9/17 点可见 |
| Required torso points | shoulders 5/6 + hips 11/12 全部可见 | 否则禁止计算躯干角 |
| Torso horizontal | 相对水平夹角 `<= 45°` | 只在质量门通过时输出 |
| Annotation tolerance | 120 ms | 仅用于 5 fps 特征与 URFD sidecar 对齐 |

这些数值是冻结的 E1 工程代理，不是临床阈值，也没有在 C6c 机位上调优。配置关系、COCO-17 点位和时间窗均由 Pydantic 严格校验，不能静默漂移。

## 4. 每帧特征

### 4.1 Box-only 始终可用部分

只要存在有效人体框，即输出：

- bbox 宽高比；
- 中心 x/y、底边 y 和面积相对画面的归一化值；
- `bbox_horizontal_proxy`；
- 同 track 的 `horizontal_duration_ms`；
- 历史足够时的中心下降比例与 `rapid_descent_proxy`；
- 历史足够时的最大中心位移比例与 `low_motion_proxy`。

这些字段彼此独立，不在提取层合成为“疑似跌倒”。特别是 low motion 在站立或静坐时也可能出现，rapid descent 在坐下/弯腰时也可能出现。

### 4.2 关键点门

Keypoint gate 状态只有：

- `passed`；
- `failed_no_detection`；
- `failed_layout`；
- `failed_required_points`；
- `failed_visible_ratio`；
- `failed_degenerate_geometry`。

只有 `passed` 才计算肩中点到髋中点的躯干角，并选择 `box_plus_keypoints`。其余有框情况统一选择 `box_only`，绝不以低置信关键点强算几何量。无有效框时选择 `unavailable`。

## 5. Temporal fail-closed

下降、低运动与持续时间必须依赖同一 track 的有序历史；以下情况重置或阻断：

| Fallback reason | 行为 |
|---|---|
| `no_person_detection` / `no_valid_bbox` | 本帧 unavailable，清空历史 |
| `track_id_missing_temporal_features_unavailable` | 保留单帧 box/keypoint，时间特征 unavailable |
| `track_changed_history_reset` | 不跨 track 拼接人物运动 |
| `frame_gap_history_reset` | 不跨长间断计算速度/静止 |
| `descent_history_not_ready` | 历史不足 600 ms，不输出下降判断 |
| `stationary_history_not_ready` | 历史不足 400 ms，不输出低运动判断 |
| `multiple_people_largest_bbox_only` | 当前只选择最大框；显式声明多人不安全 |
| `keypoint_gate_*_use_box_only` | 有框但关键点门失败，只使用框路径 |

提取器拒绝倒序/重复时间戳、person_count 与 detections 不一致、非 `video.pose_frame` 输入以及来源模型 digest 不一致。正式 runner 默认拒绝 dirty、未完成或非 E1 的姿态 parent/child run。

## 6. 来源与许可证纠偏

```bash
kangshield-info benchmark-fall-features \
  data/processed/v1-m2b/benchmark-cases.json \
  runs/<clean-pose-parent>/reports/pose-model-comparison-report.json \
  --variant rtmpose-m-humanart
```

runner 校验 benchmark ID/digest/case order、parent/child run 状态与代码版本、每个 features JSONL 摘要、annotation 摘要和每帧 pose model digest。所有输入以摘要 URI 写入 SourceAsset，不持久化本地路径。

历史 `0674be9` 姿态报告生成于许可证纠偏之前，里面的 HumanArt binding 仍写成过宽的 Apache-2.0。G4 不继承该值，而是用当前 `configs/v1-m3-pose-models.json` 的模型 digest 逐项匹配，将 detector/pose artifact 重新绑定为 `model-artifact-license-review-required`，保存策略 SHA-256 和 correction ledger。digest 不匹配即失败。

REV-013 后 runner 也接受 `torchvision-keypointrcnn`。该路线不做历史 license correction，而是要求来源 ModelBinding 的权重 digest、`model-artifact-license-review-required` 和 `configs/v1-m3-torchvision-pose-model.json` 策略摘要逐项一致；关键点分数仍是未校准质量代理。

## 7. E1 验收

干净实现提交 `782026b` 上完成两个正式运行：

- RTMPose 主候选：`20260722T103206Z-671bfb95`；
- YOLO26n 对照：`20260722T103206Z-aa69e875`。

两者都处理 170 帧、输出 170 个无风险 FeatureEvent，manifest completed、`code_dirty=false`。候选在 21 个 lying 采样帧中有 20 帧 bbox、17 帧横卧代理、11 帧关键点门通过和 9 帧 box-only；YOLO 分别为 9、8、3 和 6。既有 URFD 三段 ADL 的两个变体各有 82 个可用框且横卧代理为 0。

随后新增的 [CAUCAFall ADL 压力集](v1-g4-caucafall-adl-stress.md)覆盖拾物、坐下、跪地、行走和三种光照。RTMPose 在 602 个有框帧中出现 17 个横卧框代理，全部为关键点门失败的 box-only，最长连续 1000 ms；YOLO 为 0。该结果进一步证明“URFD ADL 横卧为 0”不能外推为误报率，也不能把单一宽高比接到告警。完整压力结果见[CAUCAFall 正式报告](reports/v1-g4-caucafall-adl-stress.md)。

Keypoint R-CNN 后续在 URFD lying 为 21/21 有框，但只有 4/21 通过关键点门；CAUCAFall 又出现 5 个 gate-passed + torso-horizontal 的 no-fall kneel/walk 帧。因此质量门是字段可用门，不是事件决策门。完整证据见[独立候选报告](reports/v1-m3-torchvision-keypointrcnn-candidate.md)。

[Open Images 静态居家压力集](v1-g4-openimages-static-home-stress.md)进一步冻结 4 张家具无人、4 张宠物无人和 4 张室内多人图片，只评测 person-absent false activation 与 IoU 0.5 人物框匹配。job `1766` 中 RTMPose 的无人激活最低（2/8）且多人匹配 11/11，但仍有 5 个 overall FP；该结果不运行本节时序特征，不能补床上躺卧、宠物移动、多人 tracking 或事件级指标。完整结果见[静态压力报告](reports/v1-g4-openimages-static-home-stress.md)。

## 8. V2 前的剩余门

1. 对 C6c 白天/夜视、距离、遮挡、弯腰、坐下、床上躺卧和安全模拟跌倒复跑同一冻结配置。
2. CAUCAFall 已补弯腰/坐下/跪地/行走和三档光照；Open Images 静态子集补 furniture/pet/multi-person 的人物检测压力。继续增加空房视频、床上躺卧、宠物移动和真实多人片段，多人出现时替换 largest-bbox 探索策略。
3. 用人工 person-presence、动作区间和事件起点标注，另行冻结误触发、检出延迟和 track fragmentation 指标。
4. 只有 G3/G4/G5 共同关闭后，V2-D1 才能设计 RiskAssessment；本 E1 FeatureEvent 不直接触发告警。
