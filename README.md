# KangShield

独居老人单机位三域风险本地试点与事件评估工程。

当前硬件：

- 1 × `CS-C6c-V101-1J4WF` 摄像头，单机位。
- 1 × `CS-EP-SDHY1` 睡眠仪。

当前指标需求源为 [跌倒新指标](docs/references/fall-risk-indicators.docx)。产品 MVP 在既有步态、睡眠、跌倒 candidate、VAD/普通话 ASR 和长程存储上增加跌倒、心理健康、诈骗三域 0–3/null 规则等级、本地 Web 人工复核和 owner/public 离线导出。分数固定标记 `pilot_unvalidated`，不合成总分，不构成概率、临床诊断或诈骗确认，不自动对外告警；心理域不使用表情或声学情绪识别。

## 文档

- [文档中心](docs/README.md)
- [跌倒指标需求](docs/design/fall-risk-indicators.md)
- [系统架构](docs/design/system-architecture.md)
- [指标、模型与语音实现方案](docs/design/indicator-implementation.md)
- [三域风险产品 MVP](docs/design/multidomain-risk-mvp.md)
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
kangshield-info serve-product --elder-ref ... --device-ref ... --host 127.0.0.1
kangshield-info export-product-report --elder-ref ... --visibility owner_only|public_evidence --output ...
```

原始数据、模型、运行产物和日志分别位于被 Git 忽略的 `data/`、`models/`、`runs/` 和 `logs/`。凭据、设备序列号、签名 URL、原始健康值和敏感媒体不得进入 Git。
