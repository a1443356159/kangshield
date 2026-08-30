# 三域风险产品 MVP

状态：本地试点（`pilot_unvalidated`）

策略：`configs/v2-multidomain-risk-policy.json`

范围：单老人、目标 C6c 单机位；辅助采集设备不进入评分

## 1. 产品边界

本地链路为：定时采集 → 增量姿态/VAD/ASR 分析 → 跌倒、心理健康、诈骗三域规则等级 → 每老人 SQLite → localhost 看板 → 人工复核 → owner/public 离线导出。

三个域各自输出 0–3 或 `null`，`global_score` 永远为 `null`。等级不是概率、临床诊断、诈骗确认或已验证预测结论；不自动对外告警。证据不足、数据过期或模型失败时 fail closed。服务固定绑定 `127.0.0.1`，页面不提供媒体或任意文件路由。

## 2. 数据与契约

正式契约为 `RiskDomain`、`DomainRiskAssessment`、`DomainCandidate`、`MultidomainSnapshotReport` 和 `CandidateReviewDecision`。每项 assessment 绑定策略 revision、SHA-256、摘要、覆盖和限制；snapshot 必须恰好包含三个域。

SQLite schema v3 在原 L1 库上向前迁移，保留 schema v2 的分析 ledger、日级行为特征、三域 candidate/assessment 历史和复核审计，并增加月度 WHO-5 自评。数据库不保存原始媒体或完整逐字稿；失败按媒体摘要重试，成功记录按媒体摘要幂等。删除 `data/processed/longitudinal/<elder_ref>/` 仍是单老人完整删除路径。

public 导出只保留脱敏域等级、策略绑定和按日趋势，不包含老人/设备标识、原始覆盖指标、逐字稿、备注、本地路径、candidate 时间线或精确事件时间。owner 导出可包含原因、事件、趋势与复核审计。

## 3. 冻结规则

- 跌倒：人工确认或跌倒 candidate 与求助/跌倒语音 ±10 秒共现为 3；未驳回 candidate 或严重行动偏离为 2；轻/中度行动偏离为 1；24 小时合格姿态至少 10 分钟且无证据为 0，否则 `null`。
- 心理健康：合并本人每月填写的 [WHO-5](https://www.who.int/publications/m/item/WHO-UCN-MSD-MHE-2024.01) 与日间出现率、活动、语言互动和已确认睡眠规律。行为侧 28 天基线至少 7 个日期、每天 3 个合格片段；`|z|>=1.5`/`2.5` 为轻/重变化。一个轻变化为 1，两个轻或一个重为 2，两个重或 2 级连续三天为 3，无变化为 0。WHO-5 五项各 0–5 分，原始分低于 13 时按 WHO 建议进一步评估的界线使本域至少为 2；原始分 13–25 只提供本月未命中该界线的证据，不降低行为规则已经给出的等级。两路取较高等级。本月未填时不推测答案，行为基线不足时仍为 `null`；不做表情或声学情绪识别，不把问卷解释成临床诊断。
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

## 5. 提交演示

展示页是标准库 HTTP 服务内嵌的独立 HTML/CSS/JS，不依赖 CDN、Node 或前端构建链。用户侧品牌只显示“康盾”和盾牌叶片图标，不展示策略版本、模型名、接口状态、`pilot_unvalidated` 或 `global_score` 等工程字段。首屏固定呈现三域状态；后续区域提供 28 天按域趋势、个人基线摘要、按自然月提醒的 WHO-5 填写区、近期提醒筛选、确认弹窗和仅照护者可见备注。填写、覆盖修改或删除本月问卷都会持久化新的 assessment 并立即刷新风险卡。所有动态文本通过 DOM `textContent` 写入，不将候选内容拼入 HTML。

前端每 30 秒只请求一次 `/api/dashboard`。后端在单个 SQLite 连接内构建一次 snapshot，并读取事件、全量复核审计、28 天趋势、个人基线和月度问卷，避免原先五个并行接口造成的重复连接与重复评分；旧分项 GET 保留用于兼容和诊断。事件复核、问卷写入与删除由运行时互斥锁串行化，SQLite 继续使用 WAL 和事务保证持久化一致性。

首页底部提供 `/docs` 本机文档入口。文档页与看板使用同一品牌视觉，但承担服务条款、隐私与留存、风险等级、技术路线、安全设计、局限和第三方许可说明，不把这些工程与治理内容堆到主看板。该路由只返回内嵌静态内容，不读取仓库 Markdown 或接受任意路径参数。

个人基线接口只返回有效观察天数、基线是否建立，以及日间活动规律、活动量、语言互动和睡眠规律相对本人过去 28 天的“平稳/轻度变化/明显变化”和方向，不返回原始健康数值。前端必须持续解释“和过去的自己比较”，不得改造成同龄人排名或人群概率。

问卷接口只接受恰好五个 0–5 整数，并与 candidate 复核共用 localhost、同源和 CSRF 门。当前月答案、原始分及百分制分仅用于 owner 本地页面和重填；public 导出不含问卷答案、分数或填写时间。页面标注 WHO-5 2024 版本与 CC BY-NC-SA 3.0 IGO 来源，不暗示 WHO 对康盾的认可。

ASR 命中求助、跌倒或诈骗规则时，可在 candidate `payload_json` 中保留规范化、最长 120 字的 `transcript_excerpt`，用于本机照护者查看和复核。不得保存整段逐字稿；页面用 `textContent` 显示片段。owner 离线报告只提取这一受限片段，不携带其余 payload；public 继续禁止字段名和任何转写文字。

使用合成数据的一键演示：

```bash
kangshield-info serve-product \
  --elder-ref demo-elder \
  --device-ref demo-c6c \
  --store-root /tmp/kangshield-submission-demo \
  --runs-dir /tmp/kangshield-submission-runs \
  --demo
```

`--demo` 强制老人和设备引用均以 `demo-` 开头，按启动墙钟时间生成 24 小时覆盖、11 天个人基线、三域等级、候选事件和历史趋势。演示仍经过真实 SQLite、正式评分器和复核 API，不读取真实媒体或逐字稿，也不是写死在页面中的展示值。

界面参考实时守护产品常用的首屏导览、状态分区和事件队列表达，但不提供实时画面或语音记录路由，不建设公网隧道。`fall-detection` 当前无项目 LICENSE，因此本页没有复制其 HTML/CSS/JS；已有预测算法同步仍受 `prediction_sync/SYNC_MANIFEST.json` 和发布许可证门约束。
