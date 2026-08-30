# KangShield 文档中心

状态：三域 MVP，本地试点
更新时间：2026-08-31

仓库文档只保留最终产品需要的设计、运行、状态、决策与发布边界。用户可直接在看板底部打开 `/docs` 阅读服务条款和技术说明，无需访问仓库文件。

## 阅读顺序

1. [三域风险产品 MVP](design/multidomain-risk-mvp.md)：产品边界、评分规则、问卷、前端、复核和导出。
2. [系统架构](design/system-architecture.md)：连续处理、轻量门、模型、存储和展示的职责。
3. [连续取流与异常回看](device-data/streaming-and-media.md)：连续流不落盘、异常归档、云端回退与运维。
4. [当前状态](governance/current-status.md)：已完成能力、验证结果和仍待关闭事项。
5. [有效决策](governance/decisions.md)：当前设计不可随意漂移的决定。
6. [发布门](governance/release-readiness.md)：许可证、模型、锁文件和真实校准要求。
7. [公开数据集交付验证报告](governance/delivery-validation-report.md)：公开样本、固定划分、策略绑定与最终盲测。

## 源材料

- [跌倒风险指标需求源](references/fall-risk-indicators.docx)

## 维护规则

- 设计只描述当前产品，不恢复历史实验手册或运行证据副本。
- 所有等级必须保持 `pilot_unvalidated`，三个域独立，`global_score=null`。
- public 导出不得包含身份、设备、原始覆盖、转写、备注、路径或精确事件时间。
- 连续原始音视频不在本机落盘；owner-only 异常窗口按留存策略归档，并与个人数据库一起删除。
- 需求、实现、页面 `/docs` 和本目录口径必须同步。
