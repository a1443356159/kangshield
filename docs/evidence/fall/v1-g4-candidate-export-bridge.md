# V1-R1 G4 Candidate Export Bridge E1 报告

日期：2026-07-23

结论：capture-bound G4 feature set 到 REV-016 event evaluator 的接口已在干净提交 `a57b8ee` 上端到端打通。三路 rule-bearing synthetic feature source 真实执行 REV-017 状态机，分别导出 2、3、4 个 candidate episode；scorer 直接消费公共 prediction/source-run 契约，provenance gate 通过，最终按证据边界保持 `tooling_only`。本结果只验证生产接口，不包含姿态模型推理，也不代表 C6c 事件性能。

## 1. 本轮关闭的工程缺口

REV-016 scorer 原先使用私有 prediction schema，fixture 通过手写 JSON 验证公式；REV-017 public stress runner 又依赖 URFD/CAUCAFall 专用父子结构。因此 C6c frame feature 到位后仍无法直接生成 scorer 所需的 prediction 和严格 source manifest。

本轮新增：

- `FallFeatureClipStream` / `FallFeatureCaptureSet`：capture-bound、单 variant、逐 clip JSONL 索引；
- 公共 `FallCandidatePredictionEvent/Clip/Set`：与 scorer 原输入逐字段兼容；
- `FallCandidateExportSummary`：不含时间和路径的聚合摘要；
- `export-fall-candidates`：校验 capture、上游 feature run、artifact、policy 和 frame stream，再执行冻结状态机；
- rule-bearing 三 variant fixture：真实生成 prediction/source run 并进入原 evaluator；
- scorer-only fixture 与 rule-bearing fixture 的明确分工。

现行设计入口见[指标、模型与语音实现方案](../../design/indicator-implementation.md)；本报告保留该历史切片的完整实现细节。

## 2. 正式输入与运行

实现提交：`a57b8ee`，正式运行前工作树 clean。

固定输入：

| 输入 | SHA-256 / 说明 |
|---|---|
| Event bundle | `0937ee8031d796134de8cd3b14dad2308d0590cd457434a161be23d2c599a1e7` |
| Rule-bearing fixture candidate policy | `b426f823eb72f034b2bd1f2f6613b2c1c86be5d005680e0cd0d8334da04124a3` |
| Frozen real candidate policy | `380151c86ddaf6b79328ca516a778111fe8a7b2c2caa61e209a055bc8942dd08`；fixture 只复用相同规则值，因 fixture marker 不共享摘要 |
| Fall feature policy | `3bedf218e9e413c1ab168134b8333db5cdebf764d5f8c9ece65ba212ea9d5eda` |
| Capture | 12 个 3 s synthetic clip；2 个 simulated fall、10 个 negative；不含真人或设备数据 |

三个 feature source 的 clip/frame coverage：

| Variant | Feature source run | Manifest SHA-256 | Feature-set SHA-256 | Clip / frame |
|---|---|---|---|---:|
| YOLO26n-pose | `fixture-features-yolo26n-pose` | `1f1fe9e23dc3904e0ad981fc3aeed972f478e872f99ef926bd5a2f40d9fe08e1` | `eb9cf86dc594410ae81f7698296afe679e7b4bfa1a8f02958e69f636edb2f4ca` | 12 / 92 |
| RTMPose-m HumanArt | `fixture-features-rtmpose-m-humanart` | `637718edc8a0c6a3cd50944cda5bdff1127cf4573f1693f9db0cde6eda226ad2` | `8dc75eeb593545a202dcdc4c6290ad57a3437113aa01b30e5aea328dd8310636` | 12 / 96 |
| Keypoint R-CNN | `fixture-features-torchvision-keypointrcnn` | `8814e0e8e85a73b4331c34cd73a5540d21081e857bc4bab08a5dc403c0ad06a9` | `bcefbb9e2d54ce65630fa2efd31024e85f58cef409396854b6781d71c750e6bf` | 12 / 100 |

这些 feature source 是契约夹具，不运行 pose backend。不同 frame 数和 activation scenario 是预先构造的接口测试布局，不是模型输出或精度证据。

## 3. Candidate exporter 结果

三个 exporter run 均为 `a57b8ee`、clean、completed、E1、0 issue；每个登记 16 个摘要化 SourceAsset。

| Variant | Candidate run | 输入 frame | 激活 clip / episode | Prediction SHA-256 | Summary SHA-256 |
|---|---|---:|---:|---|---|
| YOLO26n-pose | `20260722T172633Z-02e4b8ff` | 92 | 2 / 2 | `73b3c08f99ce8a527b4711e12bc146e8694dfd88b26f92c075ee7e16160cd188` | `d5a7cafc127ffd3bdda661d419c72aaec0698d578b6acd47b5761efd21f36bd7` |
| RTMPose-m HumanArt | `20260722T172633Z-c2ad7e03` | 96 | 3 / 3 | `dd0f4a57b347145f112a90cb944f4577f00af78736f10447fff8ed3b847a4b1b` | `6ffcf94cd1aa50bf8e04d945eb642dc9c81d83389c3e22e628b03a5ed5c42422` |
| Keypoint R-CNN | `20260722T172633Z-4ae20581` | 100 | 4 / 4 | `55b2f23347f4166793194b08c70fba91721d58fc70a5ef8cafa2043f2023f160` | `5b2749ab1c4a22de343b7e6721bb9b83e659aaaa8183ea3ee71686d5bd60a6ac` |

对应 source manifest SHA-256 分别为：

- YOLO：`50292cfb2a400131dda3fd9981fad3d3e60b490d39ccc47a34ec302ea7629871`；
- RTMPose：`266258fc58401a9141dbd351f3bdda4ad484c385d31f9538922b751ca8ffb50b`；
- Keypoint R-CNN：`cb7b97952cdabe0c32a73609eeea065c7d9cc7efd372f34e1876ec510ac037bd`。

每个 manifest 的 `candidate_events_sha256` 与实际 prediction 完全一致，并继续绑定 capture、model、fall-feature、candidate policy、上游 feature run/set 和 label-access false。prediction 的 `generated_at` 位于 candidate run start/finish 内。

## 4. Event evaluator 结果

正式 scorer run：`20260722T172634Z-59174d4c`。

- commit `a57b8ee`、clean、completed、E1、0 issue；
- manifest SHA-256 `427f8c6beccdc047a81189cbb3c1efd20dd190e3f0e03b71e0791320dc83bdab`；
- report SHA-256 `ead63c22f96478f0a474cb37b30778c65bd6a0a48d6a7c56d4374e9efec82057`；
- 15 个输入 SourceAsset；12 clip、36,000 ms 暴露、2 个 ground-truth fall、10 个 negative clip；
- annotation completeness、pairwise agreement、adjudication、minimum-data、provenance 五门均通过；
- camera gate 因 synthetic E1 固定关闭，最终 `quality_status=partial`、`decision=tooling_only`、`event_metrics_ready_for_review=false`；
- 唯二 warning 为 `capture_camera_gate_closed` 与 `fixture_or_sub_e2_evidence`，符合预期边界。

公式输出如下，仅用于确认 exporter episode 被原 scorer 正确消费：

| Variant | Candidate | TP / FP / FN | Precision / Recall / F1 | FP/hour | Negative clip activation | Median delay |
|---|---:|---:|---:|---:|---:|---:|
| YOLO26n-pose | 2 | 1 / 1 / 1 | 0.5 / 0.5 / 0.5 | 100.0 | 0.1 | 250 ms |
| RTMPose-m HumanArt | 3 | 2 / 1 / 0 | 0.666667 / 1.0 / 0.8 | 100.0 | 0.1 | 250 ms |
| Keypoint R-CNN | 4 | 2 / 2 / 0 | 0.5 / 1.0 / 0.666667 | 200.0 | 0.2 | 250 ms |

这些数值由 synthetic activation layout 预先构造，禁止用于模型排名、C6c recall/误触发声明或最终权重决定。

## 5. Fail-closed 与隐私验证

- 修改任一 clip JSONL 后，导出器在创建下游 run 前因 byte-size/SHA-256 漂移失败。
- 绝对路径、`..`、反斜杠、路径越界、feature-set/source-run/config/artifact 漂移均由契约或 loader 拒绝。
- scorer-only fixture policy 无规则时仍可验证固定 prediction，但调用 generator 会失败；rule-bearing fixture 必须三组规则全有或全无。
- 12 个聚合文件（assessment manifest/report/assets 与三个 candidate manifest/summary/assets）扫描结果：原始绝对路径 0、candidate start/end/detected/ID 0、observation/track ID 0、bbox/keypoints 0、Risk/Alert true 0。
- 三份 export summary 均无 `*_at` 或 timestamp 字段；精确 episode 只存在于被 Git 忽略的 derived-sensitive prediction。
- `data/raw/` 与 `runs/` 均由 Git ignore 覆盖，正式生成物未进入提交。

## 6. 自动化验证

- 全量：97 passed；
- `compileall` 通过；
- 全部 shell/sbatch `bash -n` 通过；
- `pip check` 无 broken requirements；
- `git diff --check` 通过；
- clean commit 上 Make prepare + assess 端到端通过。

## 7. 结论与下一步

本切片关闭“C6c frame feature 到 scorer prediction/source run 需要临时拼 JSON”的工程缺口。它没有关闭“如何从 capture 视频产生三路 clean G4 feature”这一上游缺口。

下一实现顺序：

1. 实现通用 `v1-g4-fall-feature-capture` producer，复用冻结姿态 backend 与 G4 extractor，按 capture clip 输出本桥接所需 feature set/JSONL；
2. 为真实 bundle 增加通用组装/验证入口，避免人工复制 annotation/prediction 引用；
3. C6c E2 held-out、双标注/裁决到位后，三路原样执行真实 policy digest，再运行 REV-016 scorer；
4. 继续保持多人 candidate 归属、最终模型许可证和 RiskAssessment/Alert 为独立硬门。
