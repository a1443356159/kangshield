# 当前工程状态

状态：Active
更新时间：2026-08-30

## 范围

当前主线是在目标 C6c 单机位上交付本地三域风险产品 MVP：跌倒、心理健康、诈骗分别输出 `pilot_unvalidated` 的 0–3/null 规则等级，进入长程 SQLite、localhost 看板、人工复核和 owner/public 导出。辅助机位不进入评分；不做全局总分、临床诊断、诈骗确认、外部自动告警、表情或声学情绪识别。

## 已有基础

- C6c 已取得短 E2 主码流：HEVC 2560×1440@15fps + AAC 16 kHz mono。
- FunASR VAD/Paraformer/标点、Whisper 对照和同容器 multimodal replay 旧实现可复用；它们尚未形成现行语音契约或目标 C6c A/B 结论。
- 三次独立开流 3/3 ready，轨道签名一致。
- 单段取流、重复开流、受控故障和 session ledger 工具可用。
- SDHY1 的 huayi/whst 真实接口已返回心率、呼吸率、状态和睡眠相关数据。
- YOLO、RTMPose、Keypoint R-CNN 姿态候选与公开回归证据可复用。
- 跌倒帧特征、candidate episode、export、bundle、标注/裁决 scorer 已形成工程链。
- 三个指标 CLI 已用 E1 fixture 打通：五项视频观测、心率/呼吸趋势、睡眠语义阻断，以及 owner/public 双版本静态报告。
- 公共契约强制不可评估值为 null；评分 policy 未冻结时不允许分项分数，`global_score` 固定为 null。
- C01～C12 保留既有语义，采集矩阵已增加 C13 180°、C14 360°、C15 跪地和 C16 多人交叉。
- fall-detection 仓（commit `b263b3f`）的预测指标、PoseC3D 侧车和人脸白名单模块已整体同步到 `prediction_sync/`（`SYNC_MANIFEST.json` 记录来源与逐文件摘要，本地禁止改算法）；`capture-fall-features` 新增 `--prediction-policy`、`--posec3d`、`--face` 骨架开关，缺省行为不变。
- `SpeechSegment`/`VoiceCandidate` 已成为正式契约，确定性 matcher 候选 policy 已建立；PoseC3D 与人脸模型策略、prepare 脚本和独立环境依赖已就位，权重 digest 待 prepare 时钉入。
- 以人为中心的长程记忆库骨架已落地（`longitudinal/` 包 + `ingest/assess/inspect-longitudinal` 三命令 + `configs/v1-l1-longitudinal-policy.json`）：三链路报告幂等入库、L0 跌倒 episode 持久化、L1 个人基线偏离（median/MAD/EWMA，owner-only 0–3 分，`global_score=null`）；真实 SDHY1 响应的 E2 adapter 与语音 candidate ingest 仍是缺口。
- 三域产品 MVP 已增加 schema v3 增量迁移、采集分析 ledger、日级行为特征、三域 candidate/assessment、复核审计、月度 WHO-5 自评、14 天初次回溯与 300 秒扫描；模型不可用时写失败 ledger 并降级为 `model_unavailable/null`。
- `serve-product` 固定 localhost，现已提供面向评审的响应式三域首页、可视化 28 天趋势、candidate 时间线、质量状态、筛选与复核弹窗；同源/CSRF/JSON 门保持不变。`--demo` 仅允许 `demo-*` 假名并按当前时间生成合成数据，不读取真实老人资产。
- 用户界面已收敛为“康盾”单一品牌与盾牌叶片图标，移除英文品牌和策略、模型、接口、发布门等工程字段；新增个人基线摘要，明确所有生活规律变化只与本人过去 28 天比较。
- 心理健康区已增加按自然月提醒的 WHO-5 幸福感自评；本月填写、修改和删除均本机持久化并立即重算心理风险。原始分低于 13 时本域至少为 2，较高问卷分不抵消行为侧证据；未填写不补猜，public 导出不含答案、分数或时间。
- 看板读取已从五个分项请求收敛为单个 `/api/dashboard` 聚合请求：一次 SQLite 连接、一次 snapshot，事件复核审计批量读取；分项接口继续兼容，复核与问卷写操作串行化。
- 首页底部新增本机 `/docs` 文档入口，集中说明服务条款、隐私与删除、三域规则、技术路线、安全设计、局限和 WHO-5 许可；文档为内嵌静态页面，不开放 Markdown 或任意文件读取。
- 语音触发的 candidate 现在可保存并通过本地 API 显示最长 120 字的规范化转写片段；完整逐字稿仍不进入长程库，owner 离线报告只提取受限片段，public 不含字段名或任何转写文字。
- `export-product-report` 使用同一套独立实现的视觉语言生成离线 owner/public HTML+JSON，public 不含标识、原始指标、逐字稿、备注、路径、candidate 或精确事件时间。
- 已对照 `fall-detection@711e2c0`：借鉴其评审导览、实时状态和分区表达，不复制其前端；本地同步仍固定在 `b263b3f`，上游算法已有漂移且源仓缺少项目 LICENSE，许可证关闭前不再同步进可分发提交面。
- 2026-08-30 本机验收：`256 passed`；三段内嵌 JavaScript 均通过 `node --check`，owner/public 实际导出成功，public 隐私字段扫描、Markdown 本地链接、shell syntax 和 `git diff --check` 通过。

## 尚未关闭

- C02～C10、夜视、床边横卧、遮挡、多人和真实跌倒正负样本。
- 30 分钟真实 wall/media 长稳。
- 单机位步速标定误差、步频事件，以及 5xSTS/协议化转身动作边界的本地测量一致性。
- SDHY1 缺失值、完整夜、就寝/起床边界与长期覆盖。
- 三域规则仍是未验证 pilot，需要真实 held-out 数据与 owner 发布门；全局总分明确不建设。
- 最终姿态模型、项目许可证、模型携带方式、NOTICE 和 runtime lock。
- PoseC3D（NTU60 研究用途）与 RetinaFace/ArcFace（InsightFace 非商业）的许可证审查和权重 digest 钉入。
- `fall-detection` 源仓项目许可证、当前 `711e2c0` 与已同步 `b263b3f` 的算法差异审计。
- 同步预测指标在真实采集数据上的验证：5 fps 与 15 fps 的步事件可比性、步速标定、5xSTS 协议化边界。
- C6c 远场/噪声/多人语音 A/B、SenseVoice challenger 接入、语音 public report 和 speech runtime/distribution 门。

## 当前资产

| 资产 | 用途 | Git 策略 |
|---|---|---|
| `data/` | 公开集、fixture、受控输入和长程库 | 忽略；本机保留，不进入提交 |
| `models/` | 模型候选权重 | 忽略；本机外置，许可证关闭前不进入提交 |
| `runs/` | 本地与 L40 运行产物 | 忽略；可再生，正式结论只提炼到 evidence |
| `logs/` | 采集与 Slurm 日志 | 忽略；不作为提交或文档入口 |
| `configs/` | 模型、采集、事件和发布策略 | 跟踪；D1 新增指标 policy |

下一步是关闭全量测试与页面验收、完成真实目标设备回溯、核对 public 脱敏包，并由 owner 决定 LICENSE/NOTICE/依赖锁和模型携带方式。真实校准关闭前，提交口径仍为“本地工程演示作品”，不是已验证健康产品。详见[里程碑](milestones.md)、[指标、模型与语音实现方案](../design/indicator-implementation.md)和[测试矩阵](test-matrix.md)。
