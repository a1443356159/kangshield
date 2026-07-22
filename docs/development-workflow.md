# 开发与证据晋级流程

状态：Active v0.6

## 1. 开发顺序

每项信息能力遵循相同流程：

1. 在《监测方案》中定位目标指标。
2. 在设备能力矩阵中确认数据来源和当前证据等级。
3. 准备最小、脱敏、可回放输入。
4. 先运行无模型 Probe，确认格式、时间和质量。
5. 再接入一个最小模型基线。
6. 固定输入、配置、模型版本和运行目录。
7. 记录覆盖率、耗时、错误案例和限制。
8. 通过 Review 后，才更新 V2 正式能力清单。

## 2. 环境

信息采集核心支持 Python 3.11 及以上。模型探索使用独立虚拟环境；当前 Slurm 集群的 Python 3.13.13 + CUDA Torch 已通过 smoke，但这不是对所有模型库的通用兼容承诺。

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -e ".[dev,media]"
```

Slurm 已提供 CUDA Torch 时，不重新安装 CPU Torch。安装模型栈并检查 ABI：

```bash
python -m pip install -r requirements/slurm-models.txt
python -m pip install -e ".[dev]"
python -m pip check
python -c 'import torch, torchaudio; print(torch.__version__, torchaudio.__version__)'
```

`torchaudio` 必须与集群 Torch/CUDA 构建兼容；不能只依据 Python 包版本号假定 ABI 一致。

## 3. 密钥和真实数据

禁止提交：

- AppKey、AccessToken、验证码、设备序列号。
- 真实姓名、手机号和量表原始记录。
- 原始视频、音频和睡眠导出。
- 真实运行目录和模型缓存。

本机要求：

```bash
export KANGSHIELD_REF_SALT="<local-random-secret>"
```

该盐只用于把真实设备序列号转换成稳定的 device_ref，不得写入仓库或日志。

## 4. 当前命令

### 媒体事实探测

```bash
kangshield-info probe-media sample.wav --evidence-level E2
kangshield-info probe-media sample.mp4 \
  --evidence-level E2 \
  --device-ref camera_demo_01 \
  --require-audio-track
```

E2 只表示文件来自一次真实录制；它不证明直播接口稳定。含语音的 C6c clip 必须启用 `--require-audio-track`。报告中的 start/end offset 与 duration delta 是容器 PTS 诊断，不是物理同步或 drift；后两者需要录制开始和结束附近各一次可见/可听同步事件。

设备到位前可先验证 E1 契约：

```bash
make prepare-m2c-timing-fixture
kangshield-info probe-media \
  data/raw/public-smoke/v1-m2c-timing.synthetic.avi \
  --evidence-level E1 \
  --source-type fixture \
  --require-audio-track
```

完整采集包在任何模型复测前运行：

```bash
kangshield-info assess-m2c-capture \
  data/raw/v1-m2c/<capture_id>/capture-manifest.json \
  --evidence-level E2 \
  --source-type local_file
```

该命令同时检查同意/能力快照引用、包内路径和摘要、C01～C12 场景/动作窗口、双同步事件和三姿态 held-out policy。只看子 clip 的 `structurally_usable` 不足以授权模型复测；必须读取父级 `camera_ready_for_model_retest`。Fixture 的父级门固定为 false。

### 睡眠字段发现

```bash
kangshield-info profile-sleep sleep-export.json \
  --evidence-level E2 \
  --source-type sdk_export
```

报告只保留字段路径、类型和计数，不保留字段值。自动映射只是候选，必须确认单位、时间粒度和含义。

对照《监测方案》形成 fail-closed 路线报告：

```bash
kangshield-info assess-sleep-route sleep-export.json \
  --evidence-level E2 \
  --source-type sdk_export \
  --mapping-config local-confirmed-sdnl1-map.json
```

mapping 标记 `confirmed` 仍不够：输入和 mapping 都必须达到 E2，且 source path、单位、时间、值域和缺失语义完整，才会得到 `ready_for_adapter`。该命令不输出标准化数值；多夜派生仍需连续覆盖 Review。设计见 [V1-M3 睡眠字段路线](v1-m3-sleep-field-route.md)。

### 萤石快照分析

```bash
kangshield-info inspect-ezviz device-snapshot.json \
  --evidence-level E2 \
  --source-type sdk_export
```

输入可以是 SDK/API 的本地脱敏快照。即使出现 support/capability 字段，也只能说明“字段出现”；直播、回放、抓图和音频仍需功能调用才能达到 E3。

### 视频 + 语言回放

```bash
kangshield-info run-multimodal sample.mp4 sample.wav \
  --pose-model models/yolo26n-pose.pt \
  --offline-models \
  --pose-sample-fps 5 \
  --fusion-window-ms 1000
```

当前音频输入必须是无压缩 PCM WAV。独立视频和音频被假设共享零时刻；真实 C6c 需要优先保留同容器时间基，或在适配器中显式记录时钟偏差。

### Slurm GPU

模型先在可联网登录节点进入本地缓存；计算节点使用 `--offline-models`：

```bash
.venv/bin/python scripts/prepare_multimodal_models.py
export KANG_VIDEO_INPUT="$PWD/sample.mp4"
export KANG_AUDIO_INPUT="$PWD/sample.wav"
sbatch scripts/slurm/v1_multimodal_smoke.sbatch
squeue -j <job_id>
sacct -j <job_id> --format=JobID,State,ExitCode,Elapsed,NodeList
```

脚本会清除指向 `127.0.0.1` 的代理变量，避免计算节点尝试连接登录节点本地代理。权重和运行目录不进入 Git；报告必须保存权重摘要和 Slurm job_id。

### V1-M2b 公开固定集

先阅读 URFD 的 CC-BY-NC-SA-4.0 和 FLEURS 的 CC-BY-4.0 条款，再显式准备固定集：

```bash
python scripts/prepare_v1_m2b_data.py \
  --accept-urfd-noncommercial-license
kangshield-info benchmark-dataset \
  data/processed/v1-m2b/benchmark-cases.json \
  --offline-models
```

下载清单固定 URL/revision、大小和 SHA-256；原始/派生媒体均被 Git 忽略。视频与音频是跨数据集配对，只有各自模态的标签有效。详细边界和指标见 [V1-M2b 数据集评测设计](v1-m2b-public-dataset-benchmark.md)。

### V1-M3 姿态同集对比

Python 3.13 的当前 Slurm 环境不安装完整 MMCV/MMPose 栈；候选使用官方 ONNX 导出和 ONNXRuntime GPU：

```bash
python -m pip install -r requirements/slurm-rtmpose.txt
python scripts/prepare_v1_m3_pose_models.py
python scripts/prepare_v1_m3_pose_models.py --offline
PYTHONPATH=src python scripts/prepare_v1_m3_torchvision_pose_model.py --offline
make submit-m3-pose-comparison
```

计算节点不得下载权重。父报告默认记录三个 variant 的模型摘要、阶段覆盖、关键点质量、耗时和显存口径；Keypoint R-CNN 的 logit 质量代理禁止跨模型作概率比较。详细设计见 [V1-M3 姿态模型对比](v1-m3-pose-model-comparison.md)和[独立候选扩展](v1-m3-torchvision-keypointrcnn-candidate.md)。

### V1-R1 G4 跌倒运动特征

从干净、completed、E1 的姿态父报告复用 child `video.pose_frame`，不重新运行姿态模型：

```bash
kangshield-info benchmark-fall-features \
  data/processed/v1-m2b/benchmark-cases.json \
  runs/<clean-pose-parent>/reports/pose-model-comparison-report.json \
  --variant rtmpose-m-humanart
```

runner 会校验 parent/child 代码版本、输入摘要、模型 digest、case order、annotation 和当前模型许可证 policy。默认拒绝 dirty、未完成或来源漂移的运行。输出只包含 box/keypoint 运动代理、质量门和 fallback reason；`risk_assessment_emitted` 与 `alert_emitted` 必须为 false。设计和正式 E1 证据见 [G4 设计](v1-g4-fall-motion-features.md)与[正式报告](reports/v1-g4-fall-motion-features.md)。

扩展公开 ADL 压力集保持独立 schema，先在联网节点准备并校验 12 个 CAUCAFall AVI，再提交三变体 L40 job：

```bash
make prepare-g4-caucafall
make submit-g4-adl-benchmark
```

准备器冻结 DOI/版本/许可、Mendeley file ID、大小、SHA-256、subject/activity 矩阵和三档光照；评测器再次校验 prepared suite、模型摘要和 COCO-17 布局。每个 case 使用 child run 保存敏感 pose events，父报告只按动作/光照发布摘要。详见 [CAUCAFall 压力设计](v1-g4-caucafall-adl-stress.md)与[正式报告](reports/v1-g4-caucafall-adl-stress.md)。

已有三路 clean URFD fall-feature run 和一个三路 CAUCAFall parent 后，可在 CPU 上生成并压力测试去重候选 episode：

```bash
kangshield-info benchmark-fall-candidates \
  --urfd-run runs/<clean-yolo-fall-feature-run> \
  --urfd-run runs/<clean-rtmpose-fall-feature-run> \
  --urfd-run runs/<clean-keypointrcnn-fall-feature-run> \
  --caucafall-run runs/<clean-three-variant-adl-parent>
```

生成阶段只接收 `FallMotionFrameValue`；URFD phase 与 CAUCAFall action label 在全部 episode 生成后才进入汇总。精确候选窗口只留在被忽略的 derived-sensitive FeatureEvent，父报告不发布 candidate/track/路径。策略、来源门和口径见[跌倒候选 episode 设计](v1-g4-fall-event-candidates.md)。

真实 capture-bound feature run 不走公开数据专用 parent/child loader，而使用公共导出桥接：

```bash
kangshield-info export-fall-candidates \
  <capture-manifest.json> \
  <fall-feature-capture-set.json> \
  <feature-source-run/manifest.json> \
  --policy configs/v1-g4-event-candidate-policy.json
```

feature source 必须是 clean/completed、代码版本已知、stage 为 `v1-g4-fall-feature-capture`，并把 feature set 与每个 clip JSONL 列入 artifacts。导出器在创建 candidate run 前校验 capture/model/feature/policy 摘要、held-out 时间、clip order/duration、observation、frame count、时间轴和 privacy。产出的 prediction/source run 可直接进入 REV-016 bundle；详细契约见 [G4 Candidate Export Bridge](v1-g4-candidate-export-bridge.md)。

家具/宠物人物负标签与多人框采用独立的 Open Images 静态 suite，不把图片重复成视频：

```bash
make PYTHON=.venv/bin/python prepare-g4-static-home
kangshield-info benchmark-static-home \
  data/processed/v1-g4-openimages-static-home/static-home-cases.json
make submit-g4-static-home-benchmark
```

准备器同时冻结 4 个官方 provenance CSV、12 张图片的字节摘要、Open Images Person 标签/框、逐图作者/标题/CC BY 2.0 landing-page 审计，以及 Google LLC / CC BY 4.0 标注归因。runner 对每张图独立推理且 `tracking=false`，person-absent 预测全部计 FP，多人物按 IoU 0.5 一对一匹配。该结果只能称为静态人物检测压力，不能写成跌倒误报率或 C6c 结果。详见[静态压力集设计](v1-g4-openimages-static-home-stress.md)与[正式报告](reports/v1-g4-openimages-static-home-stress.md)。

### V1-M3 语音同集对比

在登录节点固定并校验 OpenAI Whisper small 和已有 FunASR 权重，再由同一 L40 job 顺序运行两个 variant：

```bash
python -m pip install -r requirements/slurm-speech-comparison.txt
python scripts/prepare_v1_m3_speech_models.py
python scripts/prepare_v1_m3_speech_models.py --offline
make submit-m3-speech-comparison
```

计算节点不得下载权重或改变解码参数。父报告以 corpus CER 为主指标，另记录静音探针、按 gender 的诊断切片、纯推理 RTF 和显存口径；逐句转写不得进入 case/variant/comparison JSON。详细设计见 [V1-M3 语音模型同集对比](v1-m3-speech-model-comparison.md)。

### V1-R1 决策与许可证门

V1-R1 的当前采用/候选/放弃状态见 [探索收敛与 V2 输入清单](v1-r1-exploration-review.md)。框架许可证、预训练权重、训练数据和比赛提交物必须分别记录；HumanArt + RTMPose 与 Keypoint R-CNN 的 ModelBinding 均为 `model-artifact-license-review-required`，不能分别因 MMPose Apache-2.0 或 TorchVision BSD-3-Clause 自动解锁权重分发。

## 5. 运行检查

每次运行后检查：

1. manifest.status 是否 completed。
2. manifest.code_version 和 code_dirty 是否符合预期。
3. source_assets.jsonl 中 evidence_level 是否正确。
4. reports 中是否出现原始密钥、序列号、姓名或电话。
5. warning/error 是否被解释，而不是静默忽略。
6. 输入文件哈希是否与原始文件一致。
7. processing 与 cold-start 实时系数是否分开解释。
8. 完整转写是否只存在于受控 FeatureEvent，而未复制到汇总报告。
9. 容器探针的 `scan_truncated`、PTS/DTS 缺失和 required audio 状态是否允许使用该报告。
10. 是否错误地把容器首尾偏移或 duration delta 写成 drift。
11. G4 runner 的姿态 parent/child 是否 clean、completed、E1，且代码、输入与模型摘要完全匹配。
12. G4 parent/case report 的 `risk_assessment_emitted` 和 `alert_emitted` 是否都为 false。
13. G4 派生 JSONL 是否没有原始 bbox、keypoints、阶段标签、参考转写或本地源路径。
14. CAUCAFall source manifest、prepared suite、dataset lock 和 12 个 AVI 的摘要是否一致且二次准备不漂移。
15. G4 ADL 父报告是否只含 aggregate/case 摘要，原始 pose fields 是否只留在被忽略的 child run。
16. ADL 中的 horizontal/descent/low-motion 是否只写成代理激活，而没有误写成 false-positive rate 或告警。
17. Open Images source manifest、4 个 provenance CSV、12 张图片、attribution、prepared suite 与 dataset lock 是否全部摘要一致且二次准备不漂移。
18. 每张 Open Images 图片是否保留作者、标题、原始 landing page、CC BY 2.0 URL、未改动声明和复审日期；比赛提交前是否计划逐图重审。
19. 静态 runner 是否关闭 tracking，parent/case report 是否无预测坐标、绝对路径、逐图作者信息及 risk/alert true。
20. 静态 false activation 与 IoU box 指标是否只按人物检测解释，没有外推到视频、床上躺卧、跌倒事件或目标 C6c。
21. Capture G4 feature source 是否为 `v1-g4-fall-feature-capture`、clean/completed、代码版本已知，并绑定 feature-set 与全部 JSONL artifact。
22. Feature set 的 capture/model/feature-policy、clip order/duration、observation、摘要/大小/frame count 是否全部通过。
23. Candidate prediction/source run 是否绑定同一 frozen candidate policy 和准确的 `candidate_events_sha256`，且 generated time 位于 run 内。
24. Export summary 是否不含时间、窗口、candidate/track/observation ID 或本地路径，Risk/Alert 是否仍为 false。

快速检查：

```bash
make test
make info-fixtures
```

## 6. 新增设备适配器

新增适配器必须：

- 输出 SourceAsset 和 Observation。
- 将设备原字段保留在受控适配器内部。
- 明确设备时间、接收时间和媒体偏移。
- 对离线、权限不足、无数据和解析失败分别编码。
- 提供 E1 Fixture 测试。
- 提供至少一份 E2 脱敏结构报告后才能合并真实字段映射。

睡眠仪 LiveTransport 只有在获得确认过的接口/SDK 后实现，不能根据合成 Fixture 猜测 URL 和字段。

## 7. 新增模型提取器

模型插件实现 FeatureExtractor，并记录：

- name、version、权重摘要和许可证。
- 输入模态和质量门。
- 输出 FeatureEvent 与 limitations。
- CPU/GPU、批量大小、FPS/实时系数。
- 固定样本测试与失败样本。

模型不得直接写 runs；统一由 RunArtifacts 落盘。

## 8. Review 与证据晋级

晋级申请至少包含：

| 项目 | 要求 |
|---|---|
| 能力 | 明确到接口或特征，不写宽泛的“支持 AI” |
| 当前等级 | E0～E4 |
| 目标等级 | 本次希望晋级到的等级 |
| 运行证据 | run_id 和报告路径 |
| 环境 | 固件、SDK/API、代码、模型和硬件版本 |
| 结果 | 成功率、覆盖率、延迟和错误 |
| 限制 | 场景、权限、质量、许可证和隐私 |

Review 接受后同步更新：

- device-capability-matrix.md。
- milestones.md。
- review-log.md。
- V2 能力清单或淘汰清单。

## 9. Git 里程碑规则

每个里程碑至少有一个可独立回退的提交：

- D0：文档、原始设计输入与架构基线。
- V1-M1：采集契约、探针、Fixture 与测试。
- V1-M2a：设备无关视频/语言模型链路与 E1 性能证据。
- V1-M2b：公开真实录制固定集、批量评测与 E1 Slurm 证据。
- V1-M2c：E1 容器时间戳与采集包 readiness 工具，以及真实设备 E2/E3 证据、字段映射、held-out 复测与音视频对齐。
- V1-M3：模型对比代码、固定样本清单和报告。
- V1-R1：晋级/淘汰决定、G4 离线特征/fallback 契约与 V2 输入冻结。

提交前必须执行：

```bash
make test
git diff --check
git status --short
```

push 后在 milestones.md 记录提交哈希和远端分支。
