# 里程碑与验收门

状态：Active v2.0
基准日期：2026-08-08
提交目标：2026-09-05

## 总体计划

| 里程碑 | 时间 | 状态 | 验收门 |
|---|---|---|---|
| 快速启动 | 08-08～08-09 | In progress | SDHY1、C01～C16、指标契约和三个 CLI 的 fixture 主链可运行 |
| M1-A 数据通路 | 08-09～08-12 | Planned | 原始视频/语音/睡眠输出端到端生成，开发集 A、三晚睡眠与长稳有来源记录 |
| M1-B 指标实现 | 08-11～08-16 | Planned | 四类视频指标、语音 candidate、质量门、静态报告与 A 集复测完成，参数 v0.1 冻结 |
| M2 held-out | 08-17～08-23 | Planned | B 集视频指标/事件与语音 CER、VAD、candidate、误报、延迟、性能和最终模型决定完整 |
| RC | 08-24～08-29 | Planned | 新环境可复现，LICENSE/NOTICE/lock、最小 runtime 和离线演示齐全 |
| 演示缓冲 | 08-30～09-01 | Planned | 全流程彩排、失败降级和一条命令生成报告 |
| Final Freeze | 09-02～09-04 | Planned | 只修阻断问题 |
| 提交 | 09-05 | Planned | 完成比赛提交 |

## V1 收口门

- [x] 需求源替换为 `fall-risk-indicators.docx`。
- [x] 硬件冻结为 1 × C6c + 1 × SDHY1。
- [x] 双机位和旧七维风险主线移出范围；2026-08-08 owner 决定后，语音以辅助 candidate 形式重新纳入。
- [x] C6c 主码流 HEVC 2560×1440@15 + AAC 16 kHz mono 短 E2 已取得。
- [x] C6c 三次独立开流 3/3 ready。
- [x] SDHY1 huayi/whst 真实接口 E2 已取得。
- [ ] C02～C10、夜视、床边横卧、遮挡和多人样本完成。
- [ ] 30 分钟 wall/media 双门长稳完成。
- [ ] 新指标阈值冲突与总分合成策略由 owner 决定。
- [ ] 最终姿态模型、许可证和携带方式决定。
- [ ] 最终 ASR/VAD 模型、语音 public 输出、许可证和 speech runtime 决定。

## 快速启动门

- [x] 活动代码、配置、fixture 和 CLI 从 SDNL1 对齐到 SDHY1；历史证据保留原始设备口径。
- [x] 保留 C01～C12 原语义，并新增 C13 180°、C14 360°、C15 跪地、C16 多人交叉。
- [x] 冻结 `IndicatorObservation`、`IndicatorAssessment`、`IndicatorSummaryReport`。
- [x] `extract-video-indicators`、`extract-sleep-indicators`、`build-indicator-report` 已用 fixture 打通。
- [x] owner/public JSON 与 Markdown 分离，`global_score=null`，未冻结分项为 `policy_not_frozen`。

## M1-A/M1-B 门

- [ ] 冻结步速/步频/坐站/转身的动作边界和单机位质量门。
- [ ] 冻结 SDHY1 心率、呼吸、就寝时间和睡眠时长 mapping。
- [ ] 消除睡眠分段、转身分段、步速分段和总分算法冲突。
- [ ] 冻结版本化评分 policy 与摘要绑定。
- [ ] 冻结人工复核、不可评估和失败降级 UI 状态。
- [ ] 冻结 SpeechSegment、VoiceCandidate、语义 matcher、PTS 融合窗口和语音质量门。
- [ ] 冻结单元、契约、场景、真机和发布测试矩阵。

工程实现不等待评分冲突关闭；原始指标继续推进。开发集 A 用于调试和冻结 v0.1，held-out B 必须在标签与参数冻结后运行。B 后任何参数变化必须产生新 policy revision 与 B2。

## RC 发布门

- [ ] 最小非 editable 环境通过 runtime closure。
- [ ] 项目 LICENSE、第三方 NOTICE 和 competition lock 齐全。
- [ ] 所有携带模型和数据都有明确 disposition。
- [ ] 新环境离线安装和回归通过。
- [ ] 阻断问题清零，非阻断限制进入交付说明。
