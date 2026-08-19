# 三域风险产品 MVP

状态：本地试点（`pilot_unvalidated`）

策略：`configs/v2-multidomain-risk-policy.json`

范围：单老人、目标 C6c 单机位；辅助采集设备不进入评分

## 1. 产品边界

本地链路为：定时采集 → 增量姿态/VAD/ASR 分析 → 跌倒、心理健康、诈骗三域规则等级 → 每老人 SQLite → localhost 看板 → 人工复核 → owner/public 离线导出。

三个域各自输出 0–3 或 `null`，`global_score` 永远为 `null`。等级不是概率、临床诊断、诈骗确认或已验证预测结论；不自动对外告警。证据不足、数据过期或模型失败时 fail closed。服务固定绑定 `127.0.0.1`，页面不提供媒体或任意文件路由。

## 2. 数据与契约

正式契约为 `RiskDomain`、`DomainRiskAssessment`、`DomainCandidate`、`MultidomainSnapshotReport` 和 `CandidateReviewDecision`。每项 assessment 绑定策略 revision、SHA-256、摘要、覆盖和限制；snapshot 必须恰好包含三个域。

SQLite schema v2 在原 L1 库上向前迁移，新增分析 ledger、日级行为特征、三域 candidate/assessment 历史和复核审计。数据库不保存原始媒体或完整逐字稿；失败按媒体摘要重试，成功记录按媒体摘要幂等。删除 `data/processed/longitudinal/<elder_ref>/` 仍是单老人完整删除路径。

public 导出只保留脱敏域等级、策略绑定和按日趋势，不包含老人/设备标识、原始覆盖指标、逐字稿、备注、本地路径、candidate 时间线或精确事件时间。owner 导出可包含原因、事件、趋势与复核审计。

## 3. 冻结规则

- 跌倒：人工确认或跌倒 candidate 与求助/跌倒语音 ±10 秒共现为 3；未驳回 candidate 或严重行动偏离为 2；轻/中度行动偏离为 1；24 小时合格姿态至少 10 分钟且无证据为 0，否则 `null`。
- 心理健康：只使用日间出现率、活动、语言互动和已确认睡眠规律。28 天基线至少 7 个日期、每天 3 个合格片段；`|z|>=1.5`/`2.5` 为轻/重变化。一个轻变化为 1，两个轻或一个重为 2，两个重或 2 级连续三天为 3，无变化为 0，基线不足为 `null`。不做表情或声学情绪识别。
- 诈骗：ASR 后匹配凭证索取、转账投资、身份冒充、紧迫保密和远控五类上下文。单类为 1，30 秒内两类互补为 2，转账/凭证/远控与冒充/紧迫组合为 3。反诈宣传、新闻电视、转述和明确否定是 hard negative。无 candidate 时须有 24 小时内 10 分钟有效音频才输出 0。只覆盖摄像头实际听到的环境对话，不覆盖听不到的电话另一端。

最近一次成功分析超过 6 小时时，原 0 分变为 `data_stale/null`；已确认或未关闭 candidate 继续展示。驳回后即时重算，原 candidate 和复核审计不删除。

## 4. 运行

```bash
kangshield-info serve-product \
  --elder-ref elder_demo \
  --device-ref c6c_target_01 \
  --host 127.0.0.1 \
  --port 8765

kangshield-info export-product-report \
  --elder-ref elder_demo \
  --visibility owner_only \
  --output reports/owner

kangshield-info export-product-report \
  --elder-ref elder_demo \
  --visibility public_evidence \
  --output reports/public
```

服务启动后立即回溯 14 天内合格 capture run，之后默认每 300 秒扫描一次；模型在单工作线程中复用。模型/权重不可用会写失败 ledger 并在后续周期重试，看板继续服务且返回 `model_unavailable/null`，不得伪造分数。
