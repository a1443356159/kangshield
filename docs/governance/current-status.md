# 当前工程状态

状态：Active
更新时间：2026-08-19

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
- 全量自动化测试最近验证为 `246 passed`（2026-08-19）。
- 三个指标 CLI 已用 E1 fixture 打通：五项视频观测、心率/呼吸趋势、睡眠语义阻断，以及 owner/public 双版本静态报告。
- 公共契约强制不可评估值为 null；评分 policy 未冻结时不允许分项分数，`global_score` 固定为 null。
- C01～C12 保留既有语义，采集矩阵已增加 C13 180°、C14 360°、C15 跪地和 C16 多人交叉。
- fall-detection 仓（commit `b263b3f`）的预测指标、PoseC3D 侧车和人脸白名单模块已整体同步到 `prediction_sync/`（`SYNC_MANIFEST.json` 记录来源与逐文件摘要，本地禁止改算法）；`capture-fall-features` 新增 `--prediction-policy`、`--posec3d`、`--face` 骨架开关，缺省行为不变。
- `SpeechSegment`/`VoiceCandidate` 已成为正式契约，确定性 matcher 候选 policy 已建立；PoseC3D 与人脸模型策略、prepare 脚本和独立环境依赖已就位，权重 digest 待 prepare 时钉入。
- 以人为中心的长程记忆库骨架已落地（`longitudinal/` 包 + `ingest/assess/inspect-longitudinal` 三命令 + `configs/v1-l1-longitudinal-policy.json`）：三链路报告幂等入库、L0 跌倒 episode 持久化、L1 个人基线偏离（median/MAD/EWMA，owner-only 0–3 分，`global_score=null`）；真实 SDHY1 响应的 E2 adapter 与语音 candidate ingest 仍是缺口。
- 三域产品 MVP 已增加 schema v2 增量迁移、采集分析 ledger、日级行为特征、三域 candidate/assessment、复核审计、14 天初次回溯与 300 秒扫描；模型不可用时写失败 ledger 并降级为 `model_unavailable/null`。
- `serve-product` 固定 localhost，提供三域卡片、28 天趋势、candidate 时间线、质量状态和带同源/CSRF 门的复核 API；`export-product-report` 生成离线 owner/public HTML+JSON，public 不含标识、原始指标、逐字稿、备注、路径或精确事件时间。

## 尚未关闭

- C02～C10、夜视、床边横卧、遮挡、多人和真实跌倒正负样本。
- 30 分钟真实 wall/media 长稳。
- 单机位步速标定误差、步频事件，以及 5xSTS/协议化转身动作边界的本地测量一致性。
- SDHY1 缺失值、完整夜、就寝/起床边界与长期覆盖。
- 三域规则仍是未验证 pilot，需要真实 held-out 数据与 owner 发布门；全局总分明确不建设。
- 最终姿态模型、项目许可证、模型携带方式、NOTICE 和 runtime lock。
- PoseC3D（NTU60 研究用途）与 RetinaFace/ArcFace（InsightFace 非商业）的许可证审查和权重 digest 钉入。
- 同步预测指标在真实采集数据上的验证：5 fps 与 15 fps 的步事件可比性、步速标定、5xSTS 协议化边界。
- C6c 远场/噪声/多人语音 A/B、SenseVoice challenger 接入、语音 public report 和 speech runtime/distribution 门。

## 当前资产

| 资产 | 用途 | Git 策略 |
|---|---|---|
| `data/` | 公开集、fixture、受控输入 | 忽略；按来源和摘要管理 |
| `models/` | 模型候选权重 | 忽略；D1 重新决定携带范围 |
| `runs/` | 本地与 L40 运行产物 | 忽略；正式结论提炼到 evidence |
| `logs/` | Slurm stdout | 忽略；不作为文档入口 |
| `configs/` | 模型、采集、事件和发布策略 | 跟踪；D1 新增指标 policy |

下一步在不等待评分 policy 的情况下采集视频/语音开发集 A、三晚 SDHY1 与 31 × 60 秒 wall/media 长稳，同时实现姿态状态机、现行语音契约、VoiceCandidate 和脱敏报告。详见[里程碑](milestones.md)、[指标、模型与语音实现方案](../design/indicator-implementation.md)和[测试矩阵](test-matrix.md)。
