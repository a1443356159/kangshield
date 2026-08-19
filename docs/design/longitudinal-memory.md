# 以人为中心的长程记忆库（L0 + L1）

状态：Implementation Baseline v0.1
更新时间：2026-08-11

本文定义三链路指标数据的分层存储，以及以 `elder_ref`（化名）为主键的长程记忆库：指标观测序列、L0 事件 candidate 的持久化，和 L1 个人基线偏离检测（纯统计）。L2 时序预测模型暂不考虑。

## 治理约束

- 所有输出 candidate-only：L1 偏离 candidate 是 owner-only 的 0–3 分，绑定 policy revision 与 sha256；`global_score` 固定 null；语音/偏离 candidate 永远不单独确认跌倒。
- 长程库不存原始媒体、不存逐字稿文本，只存指标值、状态、限制与溯源（run_id、报告 digest、policy revision）。
- fail-closed：`not_assessable`/`blocked_semantics`/非数值/无带时区时间戳的观测 `baseline_eligible=0`，只计数，绝不插值。
- 库文件 owner-only（0700 目录、0600 文件）；按人删除 = 删除 `data/processed/longitudinal/<elder_ref>/` 整个目录。
- L1 参数集中在 `configs/v1-l1-longitudinal-policy.json`（带 revision）；held-out B 之后的任何调整新建 revision，遵循 DEC-013。

## 三链路指标数据的分层存储

| 层 | 位置 | 内容 | 保留策略 |
|---|---|---|---|
| 原始层 | `runs/<run>/artifacts/`；`data/raw/` | 同容器 mkv、姿态/特征 jsonl、multimodal windows、SDHY1 平台 JSON 导出、采集 ledger | runs/ 短期人工清理；data/raw/ owner-only 长期 |
| 报告层 | `runs/<run>/reports/*.json` | 各链路契约报告（入库唯一入口） | 随 run 保留 |
| 长程层 | `data/processed/longitudinal/<elder_ref>/longitudinal.sqlite` | 指标观测序列、L0 episodes、L1 基线与偏离 candidate | 长期 append-only，按人可删 |

各链路入库路径：

- **视频**：`extract-video-indicators`（`IndicatorExtractionReport`，当前 fixture 测量值；像素级落地后走同一入口）与 `FallCandidatePredictionSet`（L0 跌倒 candidate，clip 内相对毫秒，暂无绝对时间，入库时挂 `fall_candidate_episode_timing_is_clip_relative_only` limitation）。
- **语音**：`SpeechSegment`/`VoiceCandidate` matcher 未实现，v1 只预留 `episodes.kind="voice_candidate"` 表结构，不写 ingest；将来入库也只存 category/onset/质量，不存逐字稿。
- **睡眠**：平台 JSON 导出手工落盘（owner-only）→ `extract-sleep-indicators` → ingest。心率/呼吸趋势入 observations；就寝/起床/时长在 `blocked_semantics` 解除前只计数。真实 huayi 响应需要先经过 SDHY1 E2 adapter 转成契约报告（adapter 仍是已知缺口，见[指标公共契约](indicator-contracts.md)）。

## 库结构

`data/processed/longitudinal/<elder_ref>/longitudinal.sqlite`（WAL，schema v2 向前迁移）：

- `ingest_ledger`：报告 sha256 为主键，重复 ingest 是 no-op（行级 UNIQUE 约束兜底部分重试）。
- `observations`：观测时间（带时区）、day/night 分桶、指标、值（不可评估存 NULL）、质量、样本数、场景、溯源、`baseline_eligible`；`device_ref` 记录来源设备（`ingest-longitudinal --device-ref` 写入），多机位基线分开计算前，生产库只接目标 C6c 的数据（DEC-002 补充：辅助设备数据不进生产基线）。
- `episodes`：L0 candidate（`kind="fall_candidate"`，预留 `voice_candidate`），clip 相对时间放 payload。
- `baselines`：(indicator, bucket) 主键，median/MAD/EWMA、`ready|insufficient_samples`。
- `deviation_candidates`：owner-only 0–3 分，candidate_id 由 elder|indicator|bucket|观测时间派生，重复运行幂等。
- `analysis_ledger` / `daily_features`：按媒体摘要幂等的采集分析与心理域日级特征，不保存原始媒体或完整逐字稿。
- `domain_candidates` / `domain_assessments` / `candidate_reviews`：三域候选、历史 assessment 与复核审计；驳回只改变当前复核状态，不删除原始事件。

分桶 v1 固定 day（06:00–18:00）/night，按观测时间戳自身 offset 判定（`longitudinal/ingest.py` 常量与 policy 默认值一致）。

## L1 基线偏离引擎

`longitudinal/baseline.py`：

- 基线：policy 白名单内每个 (indicator, bucket) 取 window（默认 28 天）内 eligible 值；样本数 < `min_baseline_samples`（默认 10）只记 `insufficient_samples`，不出分；否则写 median、MAD、EWMA（alpha 默认 0.3）。窗口过滤按解析后的带时区时间戳比较，不做 ISO 字符串比较。
- 偏离检测：对每个 (indicator, bucket) 的最新 eligible 观测计算稳健 z = (x − median) / (1.4826 × MAD)，按 policy 阈值（默认 1.5/2.5/3.5 → 1/2/3 分）映射；`risk_direction` 过滤（如步速只把下降当风险）；稳态（0 分）不落库；重复运行幂等。
- MAD=0 退化规则：值不变视为稳态；任何变化按 policy `zero_mad_score`（默认 1 分）出 candidate 并挂 `zero_mad_degenerate_rule_fixed_score` limitation。

## CLI

```bash
kangshield-info ingest-longitudinal REPORT [REPORT ...] --elder-ref REF
kangshield-info assess-longitudinal --elder-ref REF \
  --policy configs/v1-l1-longitudinal-policy.json
kangshield-info inspect-longitudinal --elder-ref REF
```

`ingest-longitudinal` 按报告 schema 自动识别类型，输出无值的 ingest 回执；`assess-longitudinal` 写 owner/public 两套 JSON + Markdown（public 只含计数，契约 validator 强制）；`inspect-longitudinal` 只打印计数与时间跨度，用于现场核对入库。

## 当前边界

- L0 跌倒 episode 只有 clip 相对时间，绝对时间关联等采集 clip 带墙钟引用后补。
- SDHY1 真实 huayi 响应的 E2 adapter 未实现，真实睡眠数据暂不能 extract。
- 视频像素级指标（步速、STS 等）落地前，视频链路可入库的实际内容是 L0 episodes。
- 语音 candidate、跨老人汇总、云端同步、外部告警、runs/ 自动清理均不在本期范围。
