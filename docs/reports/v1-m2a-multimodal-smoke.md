# V1-M2a 视频与语言多模态 Pipeline 初测报告

状态：Passed（E1 公开样本）

日期：2026-07-22

本报告验证“视频回放 + 语言回放 -> 结构化多模态数据”的设备无关链路。它不证明萤石实时取流、居家场景精度或最终比赛模型已经通过。

## 1. 可复现证据

| 项目 | 值 |
|---|---|
| run_id | `20260721T182329Z-c026cd02` |
| Slurm job | `1757` |
| 作业结果 | `COMPLETED`，exit `0:0`，节点 `hepnode1`，调度耗时 `00:00:45` |
| 代码 | `fb39903`，`code_dirty=false` |
| Pipeline | `multimodal-replay-v0.2.0` |
| GPU | NVIDIA L40，约 46 GiB |
| Python / Torch | Python 3.13.13 / Torch 2.13.0+cu130 |
| 配置 | 姿态 5 FPS、640 px、conf 0.35、ByteTrack、1 秒融合窗、最多 5 秒、模型离线加载 |
| 证据等级 | E1；公开/构造 smoke，不是目标设备证据 |

运行目录位于本机被 Git 忽略的 `runs/20260721T182329Z-c026cd02/`。仓库只提交本脱敏报告，不提交媒体、完整 FeatureEvent、权重或运行日志。

## 2. 输入与来源

| 输入 | 生成方式 | SHA-256 |
|---|---|---|
| 5 秒 MJPG 视频 | Ultralytics 官方 `bus.jpg` 生成 10 FPS 轻微平移回放 | `9112dbfeb6548d54ee9ac071bd1a7f5d92b54270542de3ee488aca6b04eaeae6` |
| 5 秒中文 PCM WAV | FunASR 官方 ASR 示例 | `a1bd32dc78493c123f9625a66deee562aed2895f53fbc39f2cca3be7e6f4f20f` |

来源：

- `https://ultralytics.com/images/bus.jpg`
- `https://isv-data.oss-cn-hangzhou.aliyuncs.com/ics/MaaS/ASR/test_audio/asr_example_zh.wav`

视频由 `scripts/prepare_public_smoke_inputs.py` 生成，因此视频摘要还取决于当前 OpenCV 编码器；本次输入以表中 SHA-256 为准。

## 3. 模型绑定

| 任务 | 模型/版本 | 权重 SHA-256 | 许可证记录 |
|---|---|---|---|
| 姿态 + 跟踪 | `yolo26n-pose.pt` / Ultralytics 8.4.90 + ByteTrack | `eb3bb8268828aeaf515cec23a4bfafd793944a86fe9af94ba7823609c14522a9` | AGPL-3.0 或 Ultralytics Enterprise |
| VAD | `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | `b3be75be477f0780277f3bae0fe489f48718f585f3a6e45d7dd1fbb1a4255fc5` | Apache-2.0 |
| 中文 ASR | `iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch` | `3d491689244ec5dfbf9170ef3827c358aa10f1f20e42a7c59e15e688647946d1` | Apache-2.0 |
| 标点 | `iic/punc_ct-transformer_cn-en-common-vocab471067-large` | `7176cae922a872e130e6b88aef9a1153581711baf79c9124c7c95be383cd6f81` | Apache-2.0 |

ModelScope snapshot 路径名为 `master`，所以可复现身份以权重 SHA-256 为准。准备脚本发现上游摘要变化时会失败并要求重新 Review。

## 4. 功能结果

| 指标 | 结果 |
|---|---:|
| 媒体时长 | 5,000 ms |
| 抽样视频帧 | 25 |
| 检出人的姿态帧 | 25 / 25 |
| 人体姿态实例总数 | 98 |
| VAD 语音段 | 1 |
| 转写段 | 1 |
| 1 秒多模态窗口 | 5 |
| 词面标签 | 0 |

公开样本转写结果为“欢迎大家来体验达摩院推出的语音识别模型。”，时间范围 920～4,925 ms，与该示例内容一致。该文本只用于确认 ASR 和时间引用链路；单句匹配不能替代 CER、远场噪声或目标人群语音评测。

每个窗口均能反查姿态 FeatureEvent、语音段和转写引用。汇总 `multimodal-pipeline-report.json` 不包含完整文本；完整转写只存在于标记为 `derived_sensitive` 的 `features.jsonl`。

## 5. 性能结果

| 口径 | 耗时/结果 |
|---|---:|
| 模型加载 | 37,072.799 ms |
| 模型已加载后的完整处理 | 2,172.320 ms |
| processing 实时系数 | 0.434464 |
| 冷启动加载 + 处理 | 39,245.120 ms |
| cold-start 实时系数 | 7.849024 |
| 视频 + 姿态分支 | 1,254.990 ms，RTF 0.250998 |
| 语音 + 语言分支 | 513.536 ms，RTF 0.102707 |
| 姿态首帧 | 648.006 ms |
| 姿态稳态均值 | 11.773 ms / 抽样帧 |
| 姿态 p95 | 14.134 ms / 抽样帧 |
| 峰值 CUDA allocated | 2,126.966 MiB |

结论：模型常驻后，这个轻量 smoke 的处理速度快于媒体播放速度；冷启动明显不满足即时拉起要求。V1 demo 应使用常驻推理进程并在演示前预热。以上不是直播端到端时延，未包含摄像头取流、网络、缓冲和告警链路。

## 6. 开发中发现并关闭的问题

| 证据 | 问题 | 修复 |
|---|---|---|
| failed run `20260721T175149Z-e56e7c9a` | FunASR 依赖导入失败；环境中缺少兼容 torchaudio | 为 Slurm 虚拟环境补齐与集群 CUDA Torch 兼容的 torchaudio，并执行 `pip check` 与实际导入验证 |
| Slurm job `1752` / failed run `20260721T175947Z-4e832a28` | 计算节点继承 `127.0.0.1:7890` 代理，模型别名尝试联网后失败 | 登录节点预取权重；别名解析为本地 snapshot；增加 `--offline-models`；batch 脚本清除代理变量 |
| 早期性能报告 | `end_to_end` 未区分模型加载和处理，容易误读 | v0.2 同时报告 processing 与 cold-start 实时系数 |
| 早期模型绑定 | FunASR 权重许可证仅写“待审” | 对本次固定的三个 ModelScope 模型卡建立 Apache-2.0 映射；未知模型仍强制待审 |

失败运行保留 failed manifest，未覆盖或伪装成成功证据。

## 7. 本轮不能得出的结论

- 98 个姿态实例不是准确率；视频本质上是静态公开图片的轻微平移，不能验证跌倒、遮挡、夜视或 track_id 稳定性。
- 一句标准普通话不能验证老人语音、方言、电视串音、远场和噪声条件。
- 独立视频/WAV 共享零时刻，未验证真实 C6c 音视频 PTS 或时钟漂移。
- 这是离线回放，不是萤石直播、回放或服务端音轨能力证据。
- 词面标签只说明某些词出现，不说明真实意图、诈骗事件或健康风险。
- YOLO 基线仍有 AGPL/Enterprise 决策门，尚未自动晋级 V2。

## 8. Review 结论

V1-M2a“设备无关视频 + 语言多模态链路”通过，可以作为后续真实样本和模型对比的共同框架。V1-M1 萤石能力探测、V1-M2b 真实音视频对齐和 V1-M3 模型质量对比仍未完成。

下一批测试应使用已同意、受控的目标场景：正常行走、坐下/起身、模拟跌倒、遮挡/夜视，以及近场/远场/电视背景下的中文口令。每段样本记录期望人次、事件区间和参考转写，再计算漏检、跟踪断裂、关键点覆盖、CER 与处理性能。
