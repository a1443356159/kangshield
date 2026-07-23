# 开发与证据晋级流程

状态：Active v1.4

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

### 有界网络音视频流采集

端点必须通过环境变量提供，不能作为命令参数或脚本字面量：

```bash
read -rsp 'Stream endpoint: ' KANG_STREAM_ENDPOINT
printf '\n'
export KANG_STREAM_ENDPOINT

kangshield-info capture-stream \
  --evidence-level E2 \
  --source-type network_stream \
  --device-ref c6c_demo_01 \
  --duration-s 30 \
  --minimum-duration-s 20 \
  --transport tcp \
  --require-ready

unset KANG_STREAM_ENDPOINT
```

运行前确认录音录像同意、访问人、留存期和删除责任。端点值虽不进入 manifest/report，进程环境仍是敏感边界；禁止把凭据 URL 写入 shell 历史、Slurm 脚本、聊天或文档。输出 raw Matroska 会进入本次 run 的 `artifacts/`，权限固定 `0600`。

先用短时 E2 检查音轨、关键帧、PTS 与隐私扫描，再进入 C01～C12。一次 `same_container_multimodal_ready=true` 只允许把 artifact 交给 `run-multimodal --audio-from-video`，不证明平台 E3、长稳、重连或 drift。完整边界见[有界流采集适配器](v1-m1-bounded-stream-capture.md)。

单次短采集通过后，在同一受控环境执行重复开流 gate：

```bash
kangshield-info qualify-stream \
  --evidence-level E2 \
  --source-type network_stream \
  --device-ref c6c_demo_01 \
  --attempt-count 3 \
  --duration-s 10 \
  --minimum-duration-s 8 \
  --transport tcp \
  --require-ready
```

逐项查看 attempt status、固定 failure code、`unique_track_signature_count` 和 `repeated_capture_gate_ready`，不能只看进程退出。三次计划性 reopen 成功不等于断线恢复或长稳；后两者必须另做网络故障和 30～60 分钟运行。每次尝试都会保存 raw，采集同意与删除规则按 artifact 数量执行。完整契约见[重复开流资格门](v1-m1-stream-qualification.md)。

真机故障实验前先用本地 A/V fixture 验证 adapter 的 E1 fail-closed 行为：

```bash
kangshield-info exercise-stream-faults <local-av-fixture.mkv> \
  --require-ready
```

必须逐 case 检查实际 body/delay/stall/reject/reset/early-close 遥测、elapsed、状态和固定 failure code，不能只看父 gate。该命令禁止使用真实 endpoint，只关闭 loopback HTTP 故障识别工具门；RTSP、鉴权、packet loss、恢复和长稳仍需独立 E2/E3 实验。成功 case 会新增 raw，继续受同意、留存和删除规则约束。完整契约见[受控流故障矩阵](v1-m1-stream-fault-matrix.md)。

故障识别通过后，用显式 session ledger 组织多个独立 segment：

```bash
kangshield-info run-stream-session \
  --evidence-level E2 \
  --source-type network_stream \
  --device-ref c6c_demo_01 \
  --segment-count 3 \
  --duration-s 10 \
  --minimum-duration-s 8 \
  --failure-backoff-s 1 \
  --require-ready

kangshield-info exercise-stream-recovery <local-av-fixture.mkv> \
  --require-ready
```

逐段核对 status、gap、完整轨道签名、独立 raw 和 recovery event。受控恢复的固定结果是 ready/503-failed/ready：此时 `controlled_supervisor_recovery_gate_ready=true`，但通用 `session_gate_ready=false`，因为中间失败不能被“恢复成功”抵消。真实长稳必须显式设置 `--minimum-session-wall-s 1800` 并实际运行至少 30 分钟；短 session、HTTP 503 fixture、同连接 reconnect 和非自愿断流恢复是四种不同证据。完整契约见[流会话 Supervisor](v1-m1-stream-session-supervisor.md)。

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

独立音频输入必须是无压缩 PCM WAV，并明确假设与视频共享 synthetic zero。若媒体本身含音轨，使用：

```bash
kangshield-info run-multimodal capture.mkv \
  --audio-from-video \
  --pose-model models/yolo26n-pose.pt \
  --offline-models
```

同容器模式要求单视频/单音频轨及完整 PTS，按 timing probe 的起点 offset 映射语言事件；不会把多轨、缺 PTS 或扫描截断静默降级为共同零点。它仍是离线回放，且单个 offset 不能估计 drift。真实 C6c 需要保留原容器，并按采集规程人工定位两次同步事件。

### Slurm GPU

模型先在可联网登录节点进入本地缓存；计算节点使用 `--offline-models`：

```bash
make submit-runtime-preflight
```

首次使用新 checkout、Python/CUDA 环境或计算节点时，先运行该 5 分钟上限的轻量 preflight。它只验证 submit/execution commit 一致、shared clean checkout、owner-only stdout/runs、checkout-bound import、cuDNN 9、ONNX Runtime CUDA provider、Slurm/CUDA 可见设备和最小 CUDA tensor，不加载模型或数据。正式 L40 证据见 [V1 Slurm Runtime Preflight 报告](reports/v1-slurm-runtime-preflight.md)。

```bash
.venv/bin/python scripts/prepare_multimodal_models.py
export KANG_VIDEO_INPUT="$PWD/sample.mp4"
export KANG_AUDIO_INPUT="$PWD/sample.wav"
scripts/slurm/submit.sh scripts/slurm/v1_multimodal_smoke.sbatch
squeue -j <job_id>
sacct -j <job_id> --format=JobID,State,ExitCode,Elapsed,NodeList
```

确定性同容器 GPU smoke 使用 `make submit-mm-container-smoke`。Slurm 脚本通过 `KANG_AUDIO_FROM_VIDEO=1` 选择容器音轨，并拒绝同时传入非空 `KANG_AUDIO_INPUT`。

首次运行前执行 `make PYTHON=.venv/bin/python prepare-mm-container-smoke`。该准备器消费已下载的公开 video/WAV，以 bitexact Matroska 固定 250 ms 音轨 PTS 偏移；提交 target 默认显式记录 `source_type=fixture` 和 6 秒上限，不会把工程构造的对齐升级成自然同步证据。

八个 sbatch 入口统一由 `scripts/slurm/submit.sh` 提交，再执行 `slurm-runtime-v0.2.0`。提交器要求仓库 clean，并把完整 40 位 submit commit 注入作业；计算节点启动时必须仍处于同一 commit，从而拒绝排队期间的 checkout 漂移。运行层清除登录节点代理，要求计算节点可见的 Git 根提交，将 import 强制绑定到 submit checkout 的 `src/`，并在任何业务输入校验前把 stdout 与 runs 根收紧为 `0600/0700`。RTMPose 相关入口再从 Python NVIDIA runtime 包发现并实际加载 cuDNN 9，同时验证 ONNX Runtime CUDA provider 动态库可加载，避免“provider 已注册但 session 建立失败”或静默回退。

正式证据不得直接调用裸 `sbatch`，也不得设置 `KANG_REQUIRE_CLEAN_CHECKOUT=0`；后者只允许本地故障注入，输出会如实标记 `clean=false`。所有 `KANG_*` 业务参数通过提交器进程环境传入，禁止覆盖提交器生成的 `--export`。全部仓库脚本固定使用 `#SBATCH --output=slurm-%x-%j.out`；若调用方显式覆盖 Slurm stdout 路径，必须同步传入 `KANG_SLURM_OUTPUT_PATH`，否则 preflight fail closed。权重、运行目录和 stdout 不进入 Git；runs 根/run/子目录、JSON/JSONL 与 Slurm stdout 分别固定为 `0700/0700/0600/0600`，业务报告继续保存权重摘要和 Slurm job_id。

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

当前比赛包 profile 的日常审计：

```bash
make PYTHON=.venv/bin/python assess-distribution-readiness
```

Release Candidate 硬门：

```bash
kangshield-info assess-distribution-readiness --require-ready
```

普通审计的 blocked 是有效评估结果，会生成 owner-only 报告并返回 `0`；`--require-ready` 会在报告落盘后返回 `2`。修改 `pyproject.toml`、模型/数据配置、bundle disposition、项目许可证、最终权重或打包方式时，必须先复核资产清单，再更新 policy 摘要和 Review。`LICENSE`、`THIRD_PARTY_NOTICES.md`、`requirements/competition.lock` 只有在非空、人工审查且 SHA-256 已绑定后才算就绪。详细契约见[比赛提交分发就绪门](v1-r1-distribution-readiness.md)。

生成 competition lock 前，先盘点候选 Python 闭包：

```bash
make PYTHON=.venv/bin/python assess-runtime-closure
```

该 Make 入口为开发便利显式使用 `PYTHONPATH=src`，所以不能构成正式安装来源证明。候选/RC 环境必须安装非 editable 构建产物、不设置 `PYTHONPATH`，再从安装入口执行：

```bash
kangshield-info assess-runtime-closure --require-ready
```

只有 target/source/direct/dependency/prohibited/provenance/isolation/license metadata 八门全部通过，候选 snapshot 才能进入人工 lock/NOTICE Review；它本身不会生成最终文件或提供法律结论。依赖、extras、Python/平台、安装方式或 native runtime 变化时必须新增/升级 profile 并复跑。详细契约见[候选 Runtime 依赖闭包门](v1-r1-runtime-closure.md)。

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
25. 正式 runs 根/run/子目录、JSON/JSONL 与 Slurm stdout 是否分别保持 `0700`、`0600` 与 `0600`；任一权限漂移时是否拒绝旧 run 并用新路径重跑，而非手工改权限后冒充原始证据。
26. 正式 sbatch 是否经统一提交器冻结完整 commit，并通过 `slurm-runtime-v0.2.0` 的 submit/execution commit 一致性、Git 根、clean checkout、checkout import 与 CUDA runtime 门；stdout override 是否显式绑定，RTMPose 是否同时通过 cuDNN/ORT loadability，而非只检查 provider 名称。
27. 比赛提交 profile 的八个 source binding 是否全部 matched，所有 included/undecided 资产是否已清门，五个 owner decision 是否有可审计引用，三个 required release file 是否内容非空且摘要已绑定；RC 是否以 `assess-distribution-readiness --require-ready` 执行，而不是把普通 blocked 审计误写成可发布。
28. 候选 runtime 是否从非 editable、无 `PYTHONPATH` 的已安装入口审计，根 extras/目标 marker 是否进入实际闭包，八个 closure gate 是否全部通过；是否在此之前误生成 final lock/NOTICE 或把共享开发环境冒充比赛环境。
29. Stream capture 是否只从环境读取端点、从视频关键帧起录、在 timeout/时长/packet 上限内 clean termination，并经输出 timing probe；raw/report 权限、最短跨度、唯一音视频轨和凭据扫描是否通过；是否把 E1 HTTP 或单次 E2 clip 误写成 C6c 平台、重连或 drift 证据。
30. Stream qualification 是否为每次独立 open 保留 raw/child report，所有尝试均满足请求 readiness，轨道 codec/time-base/视频尺寸帧率/音频采样率声道是否一致；是否把 scheduled reopen 误写成非自愿断线恢复、长稳或网络损伤容忍。
31. Stream fault matrix 是否严格执行七个固定场景并记录实际注入遥测、7/7 有界/符合预期、0 unexpected ready、失败无 partial；是否把 chunk delay 写成 packet jitter，或把 E1 安全识别写成 RTSP、packet loss、自动恢复、网络容忍或长稳。
32. Stream session 是否为每段保留独立 raw/child report 和可重算 start/finish/gap，非 ready streak 与 recovery event 是否一致；是否把受控 HTTP 503 后的新 artifact 写成同连接重连/非自愿断流恢复，或在声明与实际均未达到 30 分钟时发布长稳。

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
