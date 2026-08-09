# 证据索引

状态：Historical evidence index
更新时间：2026-08-08

本目录中的报告记录特定提交、输入和运行时刻，不表达当前工程状态。当前结论以 [current-status](../governance/current-status.md) 为准。

## 设备与采集

- [有界取流](device/v1-m1-bounded-stream-capture-smoke.md)
- [重复开流](device/v1-m1-stream-qualification-smoke.md)
- [受控故障](device/v1-m1-stream-fault-matrix-smoke.md)
- [Session Supervisor](device/v1-m1-stream-session-supervisor-smoke.md)
- [Session 媒体时长门](device/v1-m1-stream-session-media-duration-gate-smoke.md)
- [媒体时间基](device/v1-m2c-media-timing-smoke.md)
- [采集就绪门](device/v1-m2c-capture-readiness-smoke.md)

## 模型

- [公开集基线](models/v1-m2b-public-dataset-benchmark.md)
- [姿态对比](models/v1-m3-pose-model-comparison.md)
- [Keypoint R-CNN](models/v1-m3-torchvision-keypointrcnn-candidate.md)
- [睡眠字段路线](models/v1-m3-sleep-field-route.md)

## 跌倒事件链

- [运动特征](fall/v1-g4-fall-motion-features.md)
- [ADL 压力](fall/v1-g4-caucafall-adl-stress.md)
- [静态居家压力](fall/v1-g4-openimages-static-home-stress.md)
- [候选压力](fall/v1-g4-fall-candidate-public-stress.md)
- [Feature Capture](fall/v1-g4-fall-feature-capture.md)
- [Candidate Export](fall/v1-g4-candidate-export-bridge.md)
- [Event Bundle](fall/v1-g4-event-bundle-assembly.md)
- [事件评估](fall/v1-g4-event-evaluation-smoke.md)

## 发布与运行

- [Slurm Runtime](release/v1-slurm-runtime-preflight.md)
- [Runtime Closure](release/v1-r1-runtime-closure.md)
- [Distribution Readiness](release/v1-r1-distribution-readiness.md)
