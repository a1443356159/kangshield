# KangShield 文档中心

状态：Active v2.0
更新时间：2026-08-09

当前指标需求源为 [跌倒新指标](references/fall-risk-indicators.docx)，owner 已另行明确把 C6c 语音辅助链纳入 D1。项目范围为单机位跌倒风险指标、跌倒/语音 candidate、SDHY1 睡眠数据和音视频人工复核；不恢复诈骗、情绪、认知、抑郁、表情或社交评分。

## 推荐阅读顺序

1. [跌倒指标需求](design/fall-risk-indicators.md)
2. [系统架构](design/system-architecture.md)
3. [当前状态](governance/current-status.md)
4. [里程碑](governance/milestones.md)
5. [有效决策](governance/decisions.md)
6. [指标公共契约](design/indicator-contracts.md)
7. [指标、模型与语音实现方案](design/indicator-implementation.md)

## 设计

| 文档 | 内容 |
|---|---|
| [跌倒指标需求](design/fall-risk-indicators.md) | 新 DOCX 的结构化需求、冲突项和待验证阈值 |
| [系统架构](design/system-architecture.md) | 单机位 + SDHY1 的系统边界、模块和数据流 |
| [数据 Pipeline](design/data-pipeline.md) | 采集、姿态、跌倒候选、睡眠字段和评估链路 |
| [指标公共契约](design/indicator-contracts.md) | Observation、Assessment、双版本静态报告与 fail-closed 规则 |
| [指标、模型与语音实现方案](design/indicator-implementation.md) | 视频/睡眠指标算法、模型选择、语音 candidate、输出与 A/B 验收 |

## 开发治理

| 文档 | 内容 |
|---|---|
| [当前状态](governance/current-status.md) | 已完成能力、真实证据、阻断项和下一步 |
| [里程碑](governance/milestones.md) | 当前 D1 及后续交付门 |
| [有效决策](governance/decisions.md) | 仍然生效的范围和工程决定 |
| [开发流程](governance/development-workflow.md) | 变更、测试、证据、Review 和提交规则 |
| [测试矩阵](governance/test-matrix.md) | 契约、指标、场景、held-out、性能与发布检查 |
| [Review 记录](governance/review-log.md) | 每个功能门的结论、证据边界和遗留项 |
| [发布与 Runtime 就绪门](governance/release-readiness.md) | LICENSE、NOTICE、lock、模型资产和隔离运行环境 |

## 设备与数据采集

| 文档 | 内容 |
|---|---|
| [设备能力矩阵](device-data/capability-matrix.md) | C6c 与 SDHY1 的真实能力和证据等级 |
| [目标采集规程](device-data/capture-protocol.md) | 单机位场景、同意、标注与样本要求 |
| [数据采集详细清单](device-data/data-collection-checklist.md) | 视频 C01～C16、语音 V01～V09、A/B、长稳、三晚睡眠、标注与封存勾选表 |
| [2026-08-09 现场采集执行方案](device-data/field-collection-plan-2026-08-09.md) | 当天采集顺序、人员职责、命令、现场质检、夜间任务和停止条件 |
| [采集就绪门](device-data/capture-readiness.md) | manifest、媒体、场景与 held-out 验收 |
| [取流、媒体时间基与长稳](device-data/streaming-and-media.md) | 有界采集、重复开流、PTS/DTS、故障和 session 双时长门 |

## 证据与源材料

- [证据索引](evidence/README.md)：正式运行和评测报告，按设备、模型、跌倒、发布分类。
- [需求源文件](references/fall-risk-indicators.docx)：当前唯一需求 DOCX。

## 维护规则

1. 现行设计只放在 `design/`；治理与状态只放在 `governance/`。
2. 设备协议放在 `device-data/`；指标、模型和跌倒/语音算法统一放在 `design/indicator-implementation.md`。
3. 一次运行的报告只放在 `evidence/`，不得用历史报告覆盖现行状态。
4. 需求、架构、有效决策、里程碑四处口径必须同步。
5. 新指标阈值在来源和本地数据 Review 前只能标为候选，不得宣传为临床结论。
