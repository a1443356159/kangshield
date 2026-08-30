# 发布与 Runtime 就绪门

状态：Blocked pending D1 decisions
更新时间：2026-08-09

本文合并比赛包 distribution readiness 与 runtime closure。历史审计结果见[分发证据](../evidence/release/v1-r1-distribution-readiness.md)和[runtime 证据](../evidence/release/v1-r1-runtime-closure.md)。

## 当前阻断

- 项目 LICENSE、源码分发方式和 `THIRD_PARTY_NOTICES.md` 未完成；
- 最终姿态、VAD/ASR 模型和 checkpoint 携带/外部缓存方式未决定；
- 最小 `core`、`speech` 和 `core+speech` runtime profile 未冻结；
- competition dependency lock 和全新非 editable 环境未验证。

## 新增待审模型资产（V1-G4 骨架同步）

- PoseC3D SlowOnly-R50 NTU60-XSub checkpoint：实现 Apache-2.0，NTU RGB+D 训练数据仅研究用途，`configs/v1-g4-posec3d-model.json` 记为 `blocked_pending_review`，权重 sha256 待 prepare 时钉入；
- RetinaFace-R50 / ArcFace IR-SE50：facexlib 分发，ArcFace 血缘 InsightFace 非商业限制，`configs/v1-g4-face-models.json` 记为 `blocked_pending_review`，权重 sha256 待钉入；
- 人脸白名单库 `data/face/gallery.npz` 属敏感个人信息，不进 Git，需要最小权限、留存期限和删除机制；
- 同步代码 `src/kangshield/information/prediction_sync/` 以 fall-detection 仓（commit `b263b3f`）为算法权威来源；2026-08-30 核查上游已到 `711e2c0`，共享算法存在漂移且仓库根目录仍无项目 LICENSE。再同步或分发前必须先完成逐文件差异与许可证 owner 决定，不能因公开可读而推定可复制。
- WHO-5 题目与计分说明来源为世界卫生组织 2024 开放版本，许可为 CC BY-NC-SA 3.0 IGO；当前只用于带显式署名的本地非商业试点。若提交渠道允许商业使用或重新许可，必须先单独关闭该内容资产的许可证门。

## Runtime 必须冻结

- OS、架构、Python、GPU、CUDA/cuDNN；
- 姿态 backend、视频/音频解码、数值与睡眠依赖；
- FunASR/SenseVoice 采用决定、模型摘要和来源；
- 每个直接/传递依赖版本、extras、来源和许可证 metadata；
- 模型获取、摘要校验、离线缓存和安装方式。

最终演示使用 `core+speech`。speech 失败时允许 core 明确降级，但不能宣称语音能力已验收。

## Runtime 八门

1. target environment 匹配；
2. repository source 完整；
3. direct requirements 匹配；
4. dependency closure 完整；
5. prohibited closure 为零；
6. installation provenance 可复核；
7. 非 editable、无 `PYTHONPATH` 的隔离运行；
8. license metadata 完整。

共享开发环境或历史候选 profile 不能生成最终 lock 或发布声明。

## 分发五门

1. 所有代码、模型、数据和文档资产标为 include/exclude/undecided；
2. 所有非排除资产都有来源摘要、许可证证据和 owner 决定；
3. LICENSE、NOTICE、competition lock 内容与摘要匹配；
4. `core`、`speech`、`core+speech` runtime closure 和离线回归通过；
5. 最终 RC 在全新环境以 `--require-ready` 通过分发审计。

模型权重不进入 Git，只能随明确许可的比赛包携带，或由摘要校验的受控外部缓存提供。工程审计不替代法律判断。
