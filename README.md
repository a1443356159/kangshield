# KangShield

独居老人单机位跌倒风险指标与事件评估工程。

当前硬件：

- 1 × `CS-C6c-V101-1J4WF` 摄像头，单机位。
- 1 × `CS-EP-SDHY1` 睡眠仪。

当前指标需求源为 [跌倒新指标](docs/references/fall-risk-indicators.docx)。工程范围包括步速、步频、5xSTS、转身、睡眠时间/时长、心率/呼吸趋势、跌倒候选，以及 C6c 语音的 VAD、普通话 ASR、求助/跌倒相关 candidate 与音视频人工复核。诈骗、情绪、认知、抑郁、表情和社交评分不在范围内。

## 文档

- [文档中心](docs/README.md)
- [跌倒指标需求](docs/design/fall-risk-indicators.md)
- [系统架构](docs/design/system-architecture.md)
- [指标、模型与语音实现方案](docs/design/indicator-implementation.md)
- [当前状态](docs/governance/current-status.md)
- [里程碑](docs/governance/milestones.md)

## 开发

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,media]"
make test
```

主要 CLI：

```bash
kangshield-info capture-stream ...
kangshield-info qualify-stream ...
kangshield-info run-stream-session ...
kangshield-info profile-sleep ...
kangshield-info assess-sleep-route ...
kangshield-info extract-video-indicators ...
kangshield-info extract-sleep-indicators ...
kangshield-info build-indicator-report ...
kangshield-info capture-fall-features ...
kangshield-info export-fall-candidates ...
kangshield-info assess-event-evaluation ...
```

原始数据、模型、运行产物和日志分别位于被 Git 忽略的 `data/`、`models/`、`runs/` 和 `logs/`。凭据、设备序列号、签名 URL、原始健康值和敏感媒体不得进入 Git。
