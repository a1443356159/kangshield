# V1-R1 G4 Capture Fall Feature Producer 初测报告

状态：L40 三后端与下游 E1 工程链 Passed；真实 C6c E2/事件性能仍 Open

日期：2026-07-23

本报告验证“capture/readiness → 三姿态真实 backend → pose FeatureEvent → G4 fall-motion FeatureEvent → `FallFeatureCaptureSet`”生产接口。输入是 12 个场景引用同一无人物 synthetic A/V 的 E1 fixture；它不提供人物覆盖、跌倒召回、模型排名或 C6c 性能证据。

## 1. 实现与信任边界

实现提交 `7a8dc23`，explicit tracker binding 修复 `b233abe`，歧义 binding fail-closed 加固 `b4b72f7`，Slurm cuDNN runtime 绑定修复 `243cef3`，run 内权限修复 `d1d4b5a`，`--runs-dir` 根目录权限修复 `8b4b52d`。Producer 固定 stage `v1-g4-fall-feature-capture`，每个 run 只允许一个 pose variant，并执行：

```text
capture manifest + clean readiness report/run
  -> 路径/大小/SHA/held-out/model-policy gate
  -> 每 clip reset tracker
  -> video.pose_frame
  -> frozen FallMotionFeatureExtractor
  -> video.fall_motion_frame
  -> FallFeatureCaptureSet + aggregate report
```

推理 context 不包含 participant/operator、场景文字、expected-person、annotation window、同步事件或裁决。Producer 不读取 candidate policy，不执行 candidate/evaluator/RiskAssessment/Alert；父 report 不保存 bbox、keypoints、track ID 或本地路径。

## 2. 固定输入

| 输入 | SHA-256 / 状态 |
|---|---|
| capture manifest | `8bf5af9ad0c08a6c65ef799d04fbe098f3937f9a1b2299f6167054157a815595` |
| readiness report | `2c809e22df2be6fe781e73291e90e2443dcb1953fc80711d01424f192642f270` |
| readiness source manifest | `97e51c1a7bf59b933754acee34f647a7a1fcb088aabbcf6729421e2397b889dc` |
| fall feature policy | `3bedf218e9e413c1ab168134b8333db5cdebf764d5f8c9ece65ba212ea9d5eda` |
| YOLO/RTMPose policy | `b5b4bcbf908221c7057794962c2cfd37a2d728c6f6b98695efbe2be73d1deeed` |
| Keypoint R-CNN policy | `921883358f6f2b23f0760d9f9612213adb044f54c9ac3e6ae24c8225e186f8db` |
| 场景 | C01～C12；12/12 structurally usable；每段 3,000 ms |
| 媒体 | 12 个 clip 引用同一 SHA `0b3bd01c83cc138780b4f3fd809798413ba8885f5ee0770a467a3bac17f24672` |
| readiness | `tooling_only` / partial；camera gate false |

重复媒体是 fixture 的显式限制；SourceAsset ledger 按内容去重。每个 variant 应产生 12 × 15 = 180 个采样帧，但不能把重复内容解释为 12 个独立视频样本。

## 3. 开发与 CPU preflight

- Fake backend：12 clip、180 frame、12 次 reset，完整 feature set 可被 `export-fall-candidates` 原样消费；固定输入未触发 candidate。
- YOLO26n-pose、RTMPose-m HumanArt 与 Keypoint R-CNN 三个真实 CPU backend 均完成 12 clip / 180 frame。
- synthetic timing media 没有人物，三个 preflight 的 people/tracked 均为 0；这只验证 adapter、binding、tracker reset、G4 fallback 和 artifact。
- 初版把 tracking 误限定为 pose binding 内 `tracking=true`，导致 RTMPose 在推理前失败。`b233abe` 接受显式 enabled `short_term_pose_tracking` binding；后续 `b4b72f7` 将门收紧为“一个 inline 或一个 explicit”的互斥表示，同时拒绝无、混合或多个 tracker。

## 4. L40 三后端结果

job `1776` 在 clean `d1d4b5a`、NVIDIA L40、driver `580.105.08` 上依次运行三个独立进程，28 秒完成且退出码为 0：

| Variant | run_id | status / issue | frame / people / tracked | model load | replay / pose RTF | Torch allocator peak |
|---|---|---|---:|---:|---:|---:|
| YOLO26n-pose | `20260722T203258Z-6dbbf02b` | completed / 0 | 180 / 0 / 0 | 2,187.879 ms | 0.091145 / 0.077607 | 65.532 MB |
| RTMPose-m HumanArt | `20260722T203304Z-f054ad75` | completed / 0 | 180 / 0 / 0 | 757.198 ms | 0.088889 / 0.074949 | 0.000 MB* |
| Keypoint R-CNN | `20260722T203311Z-1bbc5123` | completed / 0 | 180 / 0 / 0 | 4,312.840 ms | 0.114637 / 0.099558 | 683.415 MB |

`*` RTMPose 使用 ONNX Runtime CUDA allocator，Torch peak 为 0 只表示 Torch 未分配；它不是 RTMPose 或整卡峰值。三个 run 均为 E1、`code_dirty=false`、12 个 stream / 180 frame、6 个去重 SourceAsset，且共享 capture/readiness/feature 摘要。输入本来没有人物，0 people/tracked 不能解释为模型漏检率。

| Variant | manifest SHA-256 | report SHA-256 | feature-set SHA-256 |
|---|---|---|---|
| YOLO26n-pose | `c9ad223e89772063a68242790c2710d828b54e2fdab93712822759bc2278a536` | `a8d90e9174ef8bdc93bc81a72c31b4fec4d1744c38b9e47539e478955f711efd` | `dac2a6c275e666a6bb2c7465ce565cb41399f76e4f8e863dcc7b903b2934065b` |
| RTMPose-m HumanArt | `62d1db6842580fb81e8d028ea03199c5d43748f37dbb51daa2b3e47ccf8ef0fc` | `d2bbdaaa52ca44d307cd2ce759ee94a851005af68bdeee16d3ccf66fc60cb847` | `9543cb6be69ed165dd3e605ffd951d9f8e76e06c1686eb105e52df2cd306166a` |
| Keypoint R-CNN | `3ce9f46d2b37e0a3af91d572bab9b14bec16b7b882ecd5cf6b8bb08405224f90` | `366de1ab740d956cd0d67f165582e61a7e5e11132e20cb79974391a849778e77` | `100e249141168812502b0583beebe1e7065726da6065bceafd94d3df170ab591` |

## 5. Producer 到 Scorer 下游验证

三个 feature set 随后由 clean `8b4b52d` 原样进入 REV-018 exporter、REV-020 assembler 和 REV-016 scorer。`8b4b52d` 额外保证用户传入的 `--runs-dir` 根目录也是 `0700`，而不只保证单个 run 内部：

| Variant | candidate run_id | 输入帧 / candidate | manifest SHA-256 |
|---|---|---:|---|
| YOLO26n-pose | `20260722T204234Z-8c8c1b75` | 180 / 0 | `ebe980b4c8222304fb860cc67a649bc2dc0535609c0aea02979894e73ddda5fa` |
| RTMPose-m HumanArt | `20260722T204234Z-7e1eca98` | 180 / 0 | `236374c2c044a4615e8690c5526707ca066d5c81a4a0fb74ff364692aea5e062` |
| Keypoint R-CNN | `20260722T204234Z-135cad7f` | 180 / 0 | `476330b830f729ad24175cb91331c9664305fd8dd6c837482056424ab75f411e` |

fixture 输入没有人物，三路 0 candidate 是预期工程结果。新 bundle SHA-256 为 `1126a3a274696aa930cd7d4d5dd808ee156bbc0ae95417b38b8f75bc03aa459b`，assembly report 为 `cff16227a849468de9b8d76cdacf882830c6366e47a859489c2f9067ab657fd6`；16 个文件全部 `0600`、7 个目录全部 `0700`。独立 scorer run `20260722T204309Z-8b5b09f3` 的 report SHA-256 为 `26b58c13b41ed1313082508ca91586c50b289c0e136e5b6361ecd41dfb9bc3e9`，与 assembler preflight 逐字节一致；candidate 与 scorer 的两个 `--runs-dir` 根及全部子目录同样为 `0700`。

两份 fixture annotation 含 2 个裁决事件，因此三路都得到 TP/FP/FN = 0/0/2。该结果只证明真实 backend 产物可穿过完整接口；无人物合成媒体与外置 fixture 标签并不构成模型 recall。最终 decision 仍为 `tooling_only`，provenance gate true、camera/event-ready false、Risk/Alert false。fixture 使用 policy `b426f823eb72f034b2bd1f2f6613b2c1c86be5d005680e0cd0d8334da04124a3`；真实 C6c 必须改用已冻结的非 fixture policy，不得复用本摘要。

## 6. Fail-closed 与隐私验证

- readiness 任一 clip unusable、report/run error、dirty/unknown source 或 camera gate 不满足时拒绝；
- media/model/feature/readiness 摘要、路径、大小、clip 顺序或 first-inference 时间漂移时拒绝；
- pose binding 必须 COCO-17、digest-bound 且具备唯一 tracking 能力；
- 每个 clip 强制 reset；无 reset API 时拒绝；
- 原始 pose 只在 ignored derived-sensitive `features.jsonl`，G4 stream 以相对 artifact path + SHA/size/frame count 绑定；
- report/set/manifest/SourceAsset 不复制 annotation、bbox/keypoints、track ID、本地路径或身份；
- `labels_read_during_generation=false`、`raw_media_copied=false`、`risk_assessment_emitted=false`、`alert_emitted=false`。
- 三 producer 的 manifest/report/set/SourceAsset 聚合扫描对绝对路径、用户名、participant/operator、annotation window、bbox/keypoints、track ID 与 risk/alert true 均为 0 命中；精确特征仍只留在 ignored derived-sensitive 文件。
- 下游 aggregate manifest/summary/assembly/scorer 对绝对路径、用户名、bbox/keypoints 与 risk/alert true 同样为 0 命中；exact prediction/annotation 只存在 owner-only bundle。

## 7. 自动化与失败恢复

- 最终代码：118 passed；tracker 定向回归 3 passed，权限/CLI/multimodal/producer 定向回归 26 passed；
- `compileall`、全部 shell/sbatch `bash -n`、`pip check` 与 `git diff --check` 通过；
- 真实三后端 CPU preflight 通过；
- job `1768` 在实际运行前取消，因为 CPU preflight 先发现 explicit tracker binding bug；没有把已知错误写成 GPU 证据。
- job `1769` 的 YOLO 子 run 成功，但 RTMPose 因 cuDNN 已安装却未进入动态链接路径而失败；整项被拒绝。`243cef3` 显式发现并验证 `libcudnn.so.9`，`ldd` 无 unresolved dependency 后才提交 job `1772`。
- job `1772` 三路在功能上 completed/0 issue，但其 run 目录/JSONL 仍为 `0755/0644`，因此连同当时的 exporter → assembler → scorer 结果只保留为诊断证据。
- job `1776` 在 `d1d4b5a` 重跑并通过三路 feature run、Slurm stdout 和聚合隐私门。首次在 `d1d4b5a` 手工复跑下游时又发现 `--runs-dir` 根目录为 `0755`；这些本地结果同样被拒绝。`8b4b52d` 修复根目录后使用全新路径重跑 exporter → assembler → scorer，才形成本文正式全链证据；没有对旧目录事后改权限并升级证据。

## 8. 尚未关闭

1. 无人物重复 fixture 不能提供 pose accuracy、漏检、tracking stability 或 G4 event 指标。
2. 真实 C6c 仍需 E2 camera gate、正负/床上横卧/空场持续/宠物/多人、独立标注与裁决。
3. 三模型采用和权重分发状态不因本 producer 改变；YOLO 为 V1 对照、RTMPose 为条件准确率候选、Keypoint R-CNN 为未选 fallback。
4. C6c 三路 feature 必须原样执行非 fixture frozen policy，再经 assembler/scorer；不得从 frame feature 或本 E1 fixture 结果直接生成告警。
