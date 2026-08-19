# 有效决策

状态：Active
更新时间：2026-08-08

本文件只保留当前仍生效的决定；历史讨论不再作为现行入口。

| ID | 决定 | 影响 |
|---|---|---|
| DEC-001 | 当前需求源为 `references/fall-risk-indicators.docx` | 旧七维《监测方案》及其非跌倒主线失效 |
| DEC-002 | 硬件为 1 × C6c + 1 × SDHY1 | 不建设第二机位或跨视角融合；HK-Q1S4M 仅为测试阶段辅助采集设备，其数据不提升目标域证据等级，不进生产基线 |
| DEC-003 | 主线指标为步速、步频、坐站、转身、睡眠时间/时长 | 心率/呼吸仅展示趋势，暂无自动评分阈值 |
| DEC-004 | 评分阈值全部配置化 | 冲突关闭、owner 批准和版本冻结前不输出正式总风险 |
| DEC-005 | 单机位不可见/遮挡/漂移必须 fail closed | 输出 `not_assessable`，不得补猜 |
| DEC-006 | 姿态主候选继续比较 RTMPose 与 fallback | 真机 held-out 和分发门关闭前不做最终选择 |
| DEC-007 | 跌倒 candidate 与风险指标是两类输出 | 共享 provenance，但候选不直接等同风险或告警 |
| DEC-008 | E1/E2/E3/E4 严格分级 | Fixture、公开集、短真机和长稳验收不得混写 |
| DEC-010 | 发布必须通过 runtime 与 distribution 两道门 | LICENSE、NOTICE、lock、模型/数据 disposition 均需关闭 |
| DEC-011 | 最小冻结后立即实现并滚动补证据 | 工程不等待全部真机数据、历史归档或评分冲突关闭 |
| DEC-012 | owner/public 静态报告分离且总分固定 null | public 只含摘要、计数、质量、状态和限制 |
| DEC-013 | 开发集 A 调试，冻结后 held-out B 正式验收 | B 后调参必须新建 policy revision 与 B2，禁止覆盖旧结果 |
| DEC-014 | 指标采集任务固定为 C04 5xSTS、C13 行走中 180°、C14 原地 360° | 阈值只在任务协议匹配且本地测量一致性通过后作为候选 policy 使用 |
| DEC-015 | owner 明确把 C6c 语音辅助链重新纳入 D1，取代原 DEC-009 的语音排除部分 | 包含 VAD、普通话 ASR、help/fall candidate 和 PTS 人工复核；诈骗、情绪、认知、抑郁、表情、社交仍排除 |
| DEC-016 | 语音 candidate 与视频/风险指标分离 | 只提高人工复核优先级，不直接确认跌倒、不评分、不触发临床结论 |
| DEC-017 | 生产环境视频指标为日常被动事件指标：`gait_speed_normalized`（腿长归一、免标定）、`sts_transition_duration`、`turn_duration`；协议版步速/5xSTS/C13/C14 仅用于开发集验证 | 居家免重复标定、免测试动作；`gait_speed`（m/s）完整标定前保持 `not_assessable`；被动指标白名单进 L1 长程基线 |

## 待决定

1. 步速、步频、坐站和转身的完整 0～3 分区间。
2. 睡眠时长冲突分段和跨午夜时间语义。
3. 指标组权重及全局颜色合成方法。
4. 最终姿态模型与模型 artifact 携带方式。
5. 不可评估在 UI 中的展示和人工处置流程。
