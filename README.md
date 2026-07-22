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

输出默认写入被 Git 忽略的 runs 目录。Fixture 只能作为 E1 开发证据，不能写成真实设备已接通。

## 当前硬件边界

- 萤石摄像头：CS-C6c-V101-1J4WF，带麦克风。
- 萤石睡眠仪：CS-EP-SDNL1。

手环、门锁、红外/人体存在传感器不属于当前已提供设备，相关指标只能保留接口或明确为暂不可得。
