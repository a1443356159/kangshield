# Review 记录

状态：Active
更新时间：2026-08-09

## REV-036：文档合并与旧设计清理

- 删除 8 份旧跌倒事件设计和 4 份旧模型设计；对应历史运行事实继续保留在 `docs/evidence/`。
- 三份指标/模型/语音调研合并为 `design/indicator-implementation.md`。
- 五份取流、时间基、故障和 session 文档合并为 `device-data/streaming-and-media.md`。
- runtime closure 与 distribution readiness 合并为 `governance/release-readiness.md`；萤石平台事实并入设备能力矩阵。
- Markdown 文档由 62 份降至 42 份；全仓本地链接检查无断链。

## REV-034：加速施工快速启动

- 范围：SDHY1 命名、C13～C16、指标公共契约、三个 CLI、fixture 主链和双版本静态报告。
- 结论：工程入口已建立；评分 policy 继续保持未冻结，不阻塞原始指标实现。
- 证据边界：视频 fixture 输入是已测量重复值，不证明像素到姿态或真机准确率；睡眠 fixture 不证明完整夜语义。
- 隐私：owner-only 报告可含真实分项值；public evidence 不含 observation 或原始健康值。
- 未关闭：真机开发集 A、三晚 SDHY1、31 × 60 秒长稳、姿态状态机、A/B 模型结果、LICENSE/NOTICE/lock。
- 测试：指标、CLI、M2c、事件与 feature targeted tests 47 项通过；全量 pytest 184 项通过。

## REV-035：语音辅助链重新纳入 D1

- 范围：C6c 音频时间基、VAD、普通话 ASR、标点、`help_request` / `fall_related` candidate、音视频 PTS 对齐、隐私和 runtime/distribution 门。
- owner 决定：语音正式进入 D1；诈骗、声纹、情绪、认知、抑郁、表情和社交评分继续排除。
- 模型基线：FunASR FSMN-VAD + SeACo Paraformer-zh + CT-Punc；SenseVoiceSmall 进入 A 集 challenger；Whisper 仅保留历史回归。
- 输出边界：完整转写 owner-only；public 只含计数和质量。VoiceCandidate 不评分、不直接确认跌倒、不发出临床结论。
- 证据边界：已有 AAC 16 kHz mono 短 E2 和历史 E1 工具，但现行语音契约、目标 C6c A/B、流式延迟、许可证和发布门仍未关闭。
