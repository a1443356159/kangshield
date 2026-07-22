# 康盾 KangShield

社区独居老人多模态监测与风险预警项目。

当前采用两阶段交付：

- V1：快速探索信息采集、模型可行性和端到端数据形态。
- V2：基于 V1 结论设计并实现最终比赛提交版本。

当前阶段只建设文档和 V1 信息采集探索，不提前固化完整业务系统。

## 文档入口

- [工程架构与模块设计](docs/architecture.md)
- [信息侧详细技术路线](docs/information-side-technical-route.md)
- [设备能力矩阵](docs/device-capability-matrix.md)
- [开发与证据晋级流程](docs/development-workflow.md)
- [里程碑与验收门](docs/milestones.md)
- [Review 记录](docs/review-log.md)
- [V1 信息采集与模型探索](docs/v1-information-acquisition.md)
- [V1 视频与语言多模态 Pipeline](docs/v1-multimodal-pipeline.md)
- [V1-M2a 多模态 Pipeline 初测报告](docs/reports/v1-m2a-multimodal-smoke.md)
- [V1-M2b 公开真实场景固定集与对齐评测](docs/v1-m2b-public-dataset-benchmark.md)
- [V1-M2b 公开固定集初测报告](docs/reports/v1-m2b-public-dataset-benchmark.md)
- [V1-M3 姿态模型对比设计](docs/v1-m3-pose-model-comparison.md)
- [V1-M3 姿态模型同集对比报告](docs/reports/v1-m3-pose-model-comparison.md)
- [V1-M3 语音模型同集对比设计](docs/v1-m3-speech-model-comparison.md)
- [V1-M3 语音模型同集对比报告](docs/reports/v1-m3-speech-model-comparison.md)
- [V1-M2c 目标设备样本与时间基采集规程](docs/v1-m2c-device-sample-protocol.md)
- [V1-M2c 容器音视频时间戳探针](docs/v1-m2c-media-timing-probe.md)
- [V1-M2c 容器时间戳探针初测报告](docs/reports/v1-m2c-media-timing-smoke.md)
- [V1-M3 睡眠字段路线与 Fail-Closed Gate](docs/v1-m3-sleep-field-route.md)
- [V1-M3 睡眠字段路线评审报告](docs/reports/v1-m3-sleep-field-route.md)
- [V1-R1 探索收敛与 V2 输入清单](docs/v1-r1-exploration-review.md)
- [V1-R1 G4 跌倒运动特征与关键点质量门](docs/v1-g4-fall-motion-features.md)
- [V1-R1 G4 跌倒运动特征 E1 报告](docs/reports/v1-g4-fall-motion-features.md)

## V1 初步开发

V1 信息侧采用“运行目录 + JSON/JSONL 产物”的离线优先实现。开发入口、命令和产物结构见[信息侧详细技术路线](docs/information-side-technical-route.md)。

### 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,media]"
make test
make info-fixtures
```

不安装 media extra 时，WAV 与 JSON/CSV 探测仍可运行；视频命令会明确报告 OpenCV 不可用。

三条初始命令：

```bash
kangshield-info probe-media <video-or-wav>
kangshield-info profile-sleep <json-or-csv>
kangshield-info inspect-ezviz <sanitized-json> --evidence-level E1
```

生成并验证确定性同容器音视频时间戳夹具：

```bash
make prepare-m2c-timing-fixture
kangshield-info probe-media \
  data/raw/public-smoke/v1-m2c-timing.synthetic.avi \
  --source-type fixture \
  --require-audio-track
```

该命令检查 video/audio track、逐轨 time base 和逐包 PTS/DTS；容器首尾偏移不等于实际声画同步或漂移，真实 C6c 仍需两次可见/可听同步事件。

设备无关的视频 + 语言回放链路：

```bash
python -m pip install -e ".[dev,multimodal]"
kangshield-info run-multimodal <video> <pcm-wav> \
  --pose-model models/yolo26n-pose.pt \
  --offline-models
```

该命令输出姿态/跟踪、VAD、中文转写、词面标签和固定时间窗。Slurm 环境与模型准备见 [Pipeline 文档](docs/v1-multimodal-pipeline.md)和[开发流程](docs/development-workflow.md)。

准备并运行 V1-M2b 六 case 固定集：

```bash
python scripts/prepare_v1_m2b_data.py --accept-urfd-noncommercial-license
kangshield-info benchmark-dataset data/processed/v1-m2b/benchmark-cases.json \
  --pose-model models/yolo26n-pose.pt \
  --offline-models
```

URFD 与 FLEURS 的固定版本、许可证和 SHA-256 见[数据集评测设计](docs/v1-m2b-public-dataset-benchmark.md)。公开视频与语音是跨数据集配对，只用于 E1 工程和分模态精度基线，不能替代萤石目标设备验证。

运行 V1-M3 同集姿态对比：

```bash
python -m pip install -e ".[dev,rtmpose-gpu]"
python scripts/prepare_v1_m3_pose_models.py
kangshield-info benchmark-pose-models \
  data/processed/v1-m2b/benchmark-cases.json
```

该命令只重放六段视频，对比 YOLO26n-pose 与 YOLOX-m HumanArt + RTMPose-m HumanArt；不会重复运行语言模型。模型固定信息、阈值偏差和评测边界见[V1-M3 设计](docs/v1-m3-pose-model-comparison.md)。

从一份干净的姿态父报告离线派生 G4 运动特征：

```bash
kangshield-info benchmark-fall-features \
  data/processed/v1-m2b/benchmark-cases.json \
  runs/<clean-pose-parent>/reports/pose-model-comparison-report.json \
  --variant rtmpose-m-humanart
```

该命令输出 box-only 横卧/下降/低运动代理、关键点质量门和 fallback reason，并强制保持 `risk_assessment_emitted=false`、`alert_emitted=false`。它只属于 E1 特征链路，不代表已实现跌倒判定或报警；设计与结果见 [G4 设计](docs/v1-g4-fall-motion-features.md)和[正式报告](docs/reports/v1-g4-fall-motion-features.md)。

运行 V1-M3 同集语音对比：

```bash
python -m pip install -e ".[dev,multimodal,speech-compare]"
python scripts/prepare_v1_m3_speech_models.py
kangshield-info benchmark-speech-models \
  data/processed/v1-m2b/benchmark-cases.json \
  --offline-models
```

该命令只重放六条 FLEURS 普通话，对比 FunASR 基线与 Whisper small，并运行不落原文的静音探针；不会重复运行视频模型。固定解码、权重、CER 和隐私口径见[语音模型对比设计](docs/v1-m3-speech-model-comparison.md)。

评估睡眠字段路线（不持久化数值）：

```bash
kangshield-info assess-sleep-route \
  tests/fixtures/sleep/sdnl1-export.synthetic.json \
  --evidence-level E1 \
  --source-type fixture
```

该命令只判断字段路径、证据和语义是否足以开始 adapter 实现，不输出睡眠或生命体征值。真实 SDNL1 字段必须使用 E2/E3 导出/API 和本地 confirmed mapping 解锁；详细边界见[睡眠字段路线](docs/v1-m3-sleep-field-route.md)。

输出默认写入被 Git 忽略的 runs 目录。Fixture 只能作为 E1 开发证据，不能写成真实设备已接通。

## 当前硬件边界

- 萤石摄像头：CS-C6c-V101-1J4WF，带麦克风。
- 萤石睡眠仪：CS-EP-SDNL1。

手环、门锁、红外/人体存在传感器不属于当前已提供设备，相关指标只能保留接口或明确为暂不可得。
