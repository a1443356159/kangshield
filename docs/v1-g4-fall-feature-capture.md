# V1-R1 G4 Capture Pose 到 Fall Feature Producer

状态：Implemented for E1 integration；真实 C6c E2 运行与事件指标仍 Open

基准日期：2026-07-23

关联输入：[M2c 采集包就绪门](v1-m2c-capture-readiness-gate.md)、[G4 跌倒运动特征](v1-g4-fall-motion-features.md)、[Capture Feature 到 Candidate 导出](v1-g4-candidate-export-bridge.md)

## 1. 目标与边界

REV-018 已冻结 `FallFeatureCaptureSet`，但此前只有手工构造的 feature fixture，没有从受控 capture 媒体运行真实姿态 backend 的通用 producer。本切片补齐：

```text
capture manifest + clean readiness
  -> verified media/model-policy context
  -> one frozen pose variant
  -> video.pose_frame
  -> FallMotionFeatureExtractor
  -> video.fall_motion_frame
  -> FallFeatureCaptureSet + aggregate report
```

producer 只负责逐帧姿态与 G4 派生特征，不执行 candidate、事件评分、RiskAssessment 或 Alert。它不读取 annotation/adjudication 文件，也不根据动作标签改变推理、阈值或输出。

## 2. 输入信任边界

### 2.1 Capture context

`load_m2c_inference_context` 严格解析 manifest 后，只向推理层暴露：

- capture manifest/ref 与 synthetic/template 状态；
- frozen-label / first-inference 时间；
- 当前 variant 的 model-policy 路径与摘要；
- 每个 clip 的 opaque ref、scenario ID、duration、媒体路径、大小和摘要。

participant/operator、设备 ref、场景文字、expected-person、annotation window 和同步事件均不进入该 context。媒体和 model policy 在创建下游 run 前重新校验规范化路径、文件存在性、大小及 SHA-256。

### 2.2 Readiness gate

输入 readiness report 与 assessor run 必须满足：

- capture ref/digest、fixture/source/evidence 和 clip 顺序完全一致；
- 全部待运行 clip 均 `structurally_usable=true`，且 report/run 无 error；
- assessor run stage 为 `v1-m2c-capture-readiness`，状态 completed、版本已知、有时区且不早于 frozen labels；
- manifest configuration 绑定 capture 与 readiness-report digest；
- 正式输入默认要求 clean；仅本地排错可显式使用 `--allow-dirty-readiness`；
- 非 fixture 的目标设备输入还必须打开 `camera_ready_for_model_retest`。

readiness 文件包含的采集质量事实只用于上述门控；pose backend 与 G4 extractor 不获得 readiness object 或动作标签。

## 3. 模型与特征约束

每个 run 只允许一个 variant：

| Variant | Backend | 额外约束 |
|---|---|---|
| `yolo26n-pose` | Ultralytics + ByteTrack | 权重摘要必须等于冻结 V1 baseline |
| `rtmpose-m-humanart` | YOLOX + RTMPose + IoU tracker | detector/pose binding 按 capture 内 policy 校正并核验 |
| `torchvision-keypointrcnn` | TorchVision + IoU tracker | 权重、框架、预处理和许可证 binding 按独立 policy 核验 |

三个 backend 都必须输出 COCO-17、启用 tracking、提供 digest-bound pose model，并在每个独立 clip 前 reset tracker。阈值由 CLI 显式记录；本 producer 不自动搜索或根据输出调参。

每个采样帧先落一条 `video.pose_frame`，保留 bbox/keypoints/track 等 derived-sensitive 调试证据；随后复用冻结的 `FallMotionFeatureExtractor` 生成 `video.fall_motion_frame`。逐 clip G4 stream 单独写入 `artifacts/fall-motion-NNN.jsonl`，同时写入 run 级 `features.jsonl`。原媒体只登记安全 URI，不复制到 run。

## 4. 输出契约

### 4.1 `FallFeatureCaptureSet`

索引只包含 capture/model/feature policy 摘要、variant、feature version、run ID，以及每个 clip 的 scenario、duration、opaque observation、相对 artifact 路径、SHA-256、大小和 frame 数。它是 REV-018 exporter 的正式输入。

### 4.2 `FallFeatureCaptureReport`

父报告只发布：

- 逐 clip sampled/person/tracked frame 和 unique-track 计数；
- G4 path/keypoint gate/代理特征聚合；
- pose 与 feature 耗时、实时系数；
- model binding、policy/capture/readiness/feature-set 摘要；
- 运行环境与限制。

报告不保存路径、bbox、keypoints、track ID、annotation window 或 candidate 时间。`raw_media_copied=false`、`labels_read_during_generation=false`、`risk_assessment_emitted=false`、`alert_emitted=false` 为硬约束。

### 4.3 Run provenance

stage 固定为 `v1-g4-fall-feature-capture`。manifest 必须绑定 capture/readiness/assessor/model/feature policy 摘要、sample FPS、feature version 和输出 report/set 摘要。所有逐 clip stream 与两个报告都进入 artifacts；重复媒体内容只登记一个 SourceAsset。

## 5. 命令与 Slurm 入口

单 variant：

```bash
kangshield-info capture-fall-features \
  <capture-manifest.json> \
  <m2c-capture-readiness.json> \
  <m2c-capture-run-manifest.json> \
  --variant rtmpose-m-humanart \
  --source-type local_file \
  --evidence-level E2 \
  --runs-dir runs
```

E1 三 backend integration smoke：

```bash
make PYTHON=.venv/bin/python prepare-g4-candidate-export-fixture
make PYTHON=.venv/bin/python submit-g4-feature-capture-smoke
```

Slurm job 在同一张 L40 上为三个 variant 分别启动独立进程，离线核验模型文件，并把每个 run 写入统一 `runs/`。E1 fixture 只验证真实 backend、媒体 replay、G4 extractor、artifact 和 exporter 接口；不代表人体覆盖、跌倒召回或 C6c 域性能。

## 6. 验收与 fail-closed 条件

实现切片至少满足：

1. deterministic fake backend 对 12 个 clip 逐一 reset，并形成完整 feature set；
2. producer 输出可被 `export-fall-candidates` 原样消费；
3. readiness 中任一 clip 不可用、模型摘要漂移、媒体摘要漂移、路径越界或 first-inference 顺序错误时失败；
4. 父报告/source ledger 不泄漏本地路径、annotation window、bbox/keypoints；
5. 三个真实 backend 在 L40 上完成 clean E1 run；
6. 全量测试、compileall、shell syntax、pip check 与 diff check 通过。

## 7. 真实 C6c 推进顺序

1. 按 REV-014 采集并冻结 C6c 包，在任何模型查看前完成 held-out/policy 绑定。
2. readiness camera gate 通过后，三个 variant 分别运行本 producer；禁止看标签调阈值。
3. 对每个 clean feature run 执行 REV-018 candidate exporter。
4. 将三路 prediction/source run 与独立 annotation/adjudication 组装进 REV-016 evaluator。
5. 先 Review provenance 和数据门，再解释事件指标；feature/candidate policy 如需修改，必须升级版本并换开发/验证分区。

当前 producer 完成不会关闭 C6c 数据、多人归属、床上躺卧、最终权重许可证或 Risk/Alert 任何一门。
