# V1 测试矩阵

状态：Active v0.1
更新时间：2026-08-08

| 层级 | 必测项 | 当前自动化状态 |
|---|---|---|
| 契约 | 可评估值约束、未冻结 policy 禁止分数、public 无真实分项、总分 null | 已覆盖 |
| 视频指标 | 标定缺失、关键点/脚点低质量、track/时间戳中断、动作不完整；步态/转身有效 trial 不足；5xSTS 非完整五次 | 标定缺失已覆盖；当前通用三样本 gate 待 v1.1 拆分 |
| 睡眠指标 | 心率/呼吸趋势、跨午夜、完整夜、时区、缺失/离线/null | 趋势与 `blocked_semantics` 已覆盖；真实完整夜待 E2 |
| 语音 | 音轨/PTS、VAD、普通话 ASR、最终 segment、help/fall candidate、静音/噪声/电视/转述/多人、public 脱敏 | 旧 FunASR/Whisper 与 multimodal 工具可复用；现行契约、SenseVoice 和目标 A/B 待补 |
| 场景 | C01～C10、C13～C16；C11/C12 安全门；夜视、远距、床边、多人、hard negative | fixture 结构覆盖；真机待采集 |
| held-out | 指标级可评估率/MAE、步事件 F1、5xSTS 完成率、转身边界误差、时序抖动；TP/FP/FN、FP/hour、延迟、分层失败 | 旧三模型工具可复用；whole-body A 对照和 B 集未建立 |
| 性能 | L40 视频 5/10 fps、语音离线/流式 RTF、P95 端到端延迟、CPU/GPU 内存 | 待 A/B job |
| 发布 | Markdown 链接、活动 SDNL1 引用、隐私字符串、shell syntax、全量 pytest、diff check | 本轮持续执行；RC 门未关闭 |

测试证据只提升对应门：fixture 不证明真机准确率，短 E2 不证明长稳，受控恢复不证明 RTSP 同连接恢复。
