# V1 视频与语言多模态采集 Pipeline

状态：Implemented Baseline v0.2

更新时间：2026-07-22

适用范围：V1 设备无关链路探索；不代表萤石实时流或最终比赛模型已经验收

## 1. 本阶段结论

V1 先采用可回放的两路输入打通主链路：

```text
视频文件 ──> 时间戳抽帧 ──> 人体姿态 + 跟踪 ─┐
                                                ├─> 固定时间窗 ─> 多模态窗口与报告
PCM WAV ──> 单声道 16 kHz ─> VAD + ASR + 标点 ─┘
```

这一阶段解决的是工程接口和数据形态，不依赖 CS-C6c-V101-1J4WF 的具体取流方式。后续接入萤石时，只替换输入适配器，保留 FeatureEvent、ModelBinding、MultimodalWindow 和运行报告。

当前输入约束：

- 视频由 OpenCV 解码，按媒体相对时间抽帧。
- 语言流首版接收独立的无压缩 PCM WAV，自动下混并重采样为单声道 16 kHz。
- 视频和音频被假设拥有共同的零时刻；当前没有估计两路时钟偏差。
- 当前是离线回放，不把结果写成直播时延。

## 2. V1 基线模型

| 子任务 | 选定基线 | 结构化输出 | 选择理由 | 许可证与 V2 门 |
|---|---|---|---|---|
| 人体姿态与跟踪 | YOLO26n-pose + ByteTrack | 人框、COCO-17 关键点、置信度、track_id | 单个轻量模型即可同时给出人实例和姿态；接口支持连续帧 tracker state | Ultralytics AGPL-3.0 或 Enterprise；V2 冻结前必须确认项目开源策略或替换模型 |
| 语音活动检测 | FunASR FSMN-VAD | 语音段起止毫秒 | 与中文 ASR 同一框架，少一套音频预处理和时间语义 | 当前固定 ModelScope 权重模型卡为 Apache-2.0 |
| 中文 ASR | FunASR SeACo Paraformer（`paraformer-zh` 别名） | 中文文本与段级时间范围 | 中文离线识别、时间戳和热词路线更贴合当前场景 | 当前固定 ModelScope 权重模型卡为 Apache-2.0 |
| 标点恢复 | FunASR CT-Punc | 带标点文本 | 与 Paraformer 官方组合一致，便于后续文本规则和人工 review | 当前固定 ModelScope 权重模型卡为 Apache-2.0 |
| 词面标签 | 项目内确定性关键词规则 | help_request、fall_related、fraud_related | 只验证 FeatureEvent 到融合窗的数据流，不引入不可解释风险分类器 | 只能称词面观测，不能称意图、诈骗或健康诊断 |

官方文档显示，YOLO26n-pose 默认输出 COCO 的 17 个人体关键点；连续帧使用 `persist=True` 保留跟踪状态。FunASR 官方示例直接组合 `paraformer-zh`、`fsmn-vad` 和 `ct-punc`。本项目同时记录模型仓库名、框架版本、权重 SHA-256、运行设备、配置和许可证。

V1 没有直接采用通用视觉语言大模型。当前需要的是逐帧坐标、时间戳、语音段和可回放的结构化事件；通用 VLM 可以在后续作为低频语义增强候选，但不能替代姿态、VAD/ASR 和确定性对齐。

## 3. 备选模型与暂不采用原因

| 候选 | 当前结论 | 后续触发条件 |
|---|---|---|
| RTMPose / MMPose | V2 重点备选，许可证路线更宽松，但本轮尚未建立相同输入和相同指标的实测 | Ultralytics 许可证与提交策略冲突，或目标摄像头样本上精度明显更优 |
| MediaPipe Pose | 适合快速单人端侧原型；本轮选择了同时提供人框和 track_id 的统一后端 | 需要 CPU/移动端部署对比时加入 |
| Whisper | 多语言能力强，但本轮中文、离线、时间戳链路优先采用 Paraformer | 出现方言、多语言或远场中文识别短板时加入固定样本对比 |
| Silero VAD | 轻量 VAD 候选；当前为了减少框架和时间语义分叉采用 FSMN-VAD | FunASR VAD 在噪声和远场样本上覆盖率不合格时加入 |
| 端到端音视频大模型 | 暂不进入 P0 主链路 | 有独立 GPU 预算、任务标注和可解释评测集后再评估 |

“选定基线”只表示它用于 V1 打通链路，不等于已经晋级 V2。

## 4. 模块设计

```text
src/kangshield/information/
├── streaming.py             # 视频回放迭代器、PCM WAV 读取/重采样
├── pose_backend.py          # 姿态后端协议、YOLO26n-pose + ByteTrack 适配器
├── speech_backend.py        # 语音后端协议、FunASR、结果归一化、词面标签
├── multimodal_pipeline.py   # 探测、特征提取、时间窗融合和性能报告
├── contracts.py             # ModelBinding、FeatureEvent、MultimodalWindow、Report
├── artifacts.py             # 统一落盘，不让模型后端直接写运行目录
└── cli.py                   # run-multimodal 命令
```

边界：

- `streaming` 只负责解码和时间戳，不知道模型。
- `pose_backend` 和 `speech_backend` 只返回结构化 Python 对象，不写文件、不输出风险。
- `multimodal_pipeline` 负责把后端输出转换成公共契约并对齐。
- `artifacts` 是运行目录的唯一写入口。
- CLI 负责模型构造和运行参数，不承载推理逻辑。

## 5. 数据契约

### 5.1 ModelBinding

每个实际加载的模型记录：

- task、backend、model_name、model_version。
- 权重 `model_digest`。
- license 和 device。
- 输入尺寸、阈值、tracker、采样率、语言、离线模式等 configuration。

别名只用于 CLI；报告写入完整模型仓库名。未知自定义 FunASR 模型自动写为 `model-license-review-required`。

### 5.2 FeatureEvent

当前生成四类主要事件：

- `video.pose_frame`：帧时间、人数、人框、COCO-17 关键点、track_id。
- `audio.speech_segment`：VAD 语音段起止时间。
- `language.transcript_segment`：文本、语言和来源语音段引用。
- `language.lexical_tags`：从文本派生的词面类别，不是风险结论。

完整转写标记为 `derived_sensitive`，只进入受控的 `features.jsonl`，汇总报告不复制文本。

### 5.3 MultimodalWindow

按 `fusion_window_ms` 生成窗口，包含：

- 视频与音频 observation 引用。
- 窗口内所有 source_feature_refs。
- pose_frame_count、max_person_count、track_ids。
- speech_segment_count、transcript_feature_refs、semantic_tags。
- 每个模态是否可用和窗口质量状态。

区间使用左闭右开重叠语义；跨窗口语音段会被两个相邻窗口引用，而不会复制文本。

## 6. 运行产物

```text
runs/<run_id>/
├── manifest.json
├── source_assets.jsonl
├── observations.jsonl
├── features.jsonl
├── multimodal_windows.jsonl
└── reports/
    ├── multimodal-video-probe.json
    ├── multimodal-audio-probe.json
    └── multimodal-pipeline-report.json
```

性能报告区分：

- `processing_end_to_end`：模型加载完成后的整条处理链实时系数。
- `cold_start_end_to_end`：模型加载加处理的冷启动实时系数。
- 视频、语言分支实时系数和姿态首帧/稳态延迟。
- Python、Torch、GPU、Slurm job 和峰值 CUDA 显存。

实时系数小于 1 表示处理耗时小于媒体时长。冷启动只影响新进程首轮；常驻 worker 的容量判断应使用 processing 口径，但启动策略仍要处理冷启动。

## 7. 本地与 Slurm 运行

核心测试：

```bash
.venv/bin/python -m pytest -q
```

准备公开 smoke 输入：

```bash
.venv/bin/python scripts/prepare_multimodal_models.py
.venv/bin/python scripts/prepare_public_smoke_inputs.py
```

本地或已分配 GPU shell：

```bash
.venv/bin/kangshield-info run-multimodal \
  data/raw/public-smoke/ultralytics-bus-replay.avi \
  data/raw/public-smoke/funasr-asr-example-zh.wav \
  --pose-model models/yolo26n-pose.pt \
  --offline-models \
  --pose-sample-fps 5 \
  --fusion-window-ms 1000 \
  --max-duration-s 5
```

提交 Slurm：

```bash
export KANG_VIDEO_INPUT="$PWD/data/raw/public-smoke/ultralytics-bus-replay.avi"
export KANG_AUDIO_INPUT="$PWD/data/raw/public-smoke/funasr-asr-example-zh.wav"
export KANG_MAX_DURATION_S=5
sbatch scripts/slurm/v1_multimodal_smoke.sbatch
```

两个准备脚本应在可联网登录节点执行。模型脚本把 YOLO 权重写入被 Git 忽略的 `models/`，把三个 FunASR snapshot 写入 ModelScope 缓存，并校验 V1 冻结的权重 SHA-256。上游 `master` 发生变化时脚本会失败，必须经过模型 Review 后才能更新基线摘要。

Slurm 脚本请求 1 张 L40、8 CPU、20 分钟，并强制从本地缓存加载模型。计算节点不依赖公网，也不会继承指向登录节点 localhost 的代理。

## 8. V1-M2a 验收门

- [x] 视频和语言输入能进入同一次 RunManifest。
- [x] 姿态、VAD、ASR、标点和融合窗口均产生版本化产物。
- [x] 权重摘要、许可证、环境、warm processing 与 cold-start 性能可追溯。
- [x] 报告不复制完整转写；完整文本只进入敏感 FeatureEvent。
- [x] 自动化测试覆盖回放采样、WAV 重采样、FunASR 归一化、模型缓存和跨模态窗口。
- [x] Slurm L40 公开样本 smoke 完成。
- [ ] 真实 C6c 同容器音视频或可靠同步样本完成。
- [ ] 固定居家场景集上的姿态漏检、跟踪稳定性、ASR 字错率和噪声测试完成。
- [ ] V2 姿态许可证/替代模型决策完成。

前六项关闭的是“设备无关链路”，后三项属于 V1 真实数据和模型对比，不得由公开 smoke 替代。

## 9. 官方依据

- [Ultralytics YOLO26](https://docs.ultralytics.com/models/yolo26)
- [Ultralytics Pose 任务](https://docs.ultralytics.com/tasks/pose)
- [Ultralytics Track 模式](https://docs.ultralytics.com/modes/track)
- [FunASR 官方仓库](https://github.com/modelscope/FunASR)
- [SeACo Paraformer 模型卡](https://modelscope.cn/models/iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch)
- [FSMN-VAD 模型卡](https://modelscope.cn/models/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch)
- [CT-Punc 模型卡](https://modelscope.cn/models/iic/punc_ct-transformer_cn-en-common-vocab471067-large)
- [Ultralytics 许可证说明](https://docs.ultralytics.com/help/contributing)
