# V1-M3 语音模型同集对比设计

状态：Implemented，等待干净提交的 L40 正式运行与 Review

基准日期：2026-07-22

## 1. 目标与边界

V1-M2b 已在六条 FLEURS `cmn_hans_cn/dev` 固定语音上得到 FunASR corpus CER `9/137 = 6.57%`。V1-M3 语言切片只回答一个工程问题：在不改变固定语音、参考文本、归一化规则和报告隐私边界的前提下，OpenAI Whisper small 是否值得作为 V2 的普通话/多语种候选。

本轮不是公开 ASR 榜单，也不声称覆盖 C6c 远场麦克风、老人语音、方言、电视背景、多人重叠或噪声。六条语音只有 E1 工程证据；模型决定仍需 V1-M2c 真实设备复测。

## 2. 固定 variant

| variant_id | 链路 | 固定版本/权重 | 许可证 | 定位 |
|---|---|---|---|---|
| `funasr-paraformer` | FSMN-VAD + SeACo Paraformer-zh + CT-Punc | 既有 ModelScope `master` snapshot，三个 `model.pt` 分别以 SHA-256 绑定 | Apache-2.0 | V1 中文 baseline |
| `whisper-small` | OpenAI Whisper 多语种 small | `openai-whisper==20250625`，官方 `small.pt`，244M，SHA-256 `9ecf7799…e794` | MIT | V1-M3 对照候选 |

完整模型 ID、上游提交、URL、字节数和摘要冻结在 `configs/v1-m3-speech-models.json`。Whisper 使用 OpenAI 原始实现与原始 checkpoint，不经过 Transformers 二次封装。模型和代码依据 [OpenAI Whisper 官方仓库](https://github.com/openai/whisper)；`v20250625` 已将 Python 3.13 纳入项目支持与持续集成记录，当前 Slurm Python 3.13 不再需要单独 Python 3.11 环境。

## 3. 固定输入与解码

- 只读取 `data/processed/v1-m2b/benchmark-cases.json` 中六条 FLEURS 音频；不重跑 URFD 视频或姿态模型。
- 输入统一为 16 kHz、单声道、float32 PCM；运行时音频时长必须与冻结 manifest 相差不超过 2 ms。
- 参考与假设均执行 `NFKC + casefold + Unicode alphanumeric only`，不额外做简繁转换、同义词替换或英文词转写修正。
- Whisper 显式固定 `language=zh`、`task=transcribe`、`beam_size=5`、`temperature=0`、`condition_on_previous_text=false`。
- Whisper 固定 `no_speech_threshold=0.6`、`logprob_threshold=-1.0`、`compression_ratio_threshold=2.4`；GPU 默认 FP16，CPU 预检使用 FP32。
- 以上参数在查看 candidate 结果前冻结；本固定集不得用于继续调参后再报告同集提升。

## 4. Pipeline 与模块设计

```text
frozen benchmark-cases.json
        │
        ├── read_pcm_wav ──> FunASRSpeechBackend ──┐
        │                                           ├── SpeechSegment
        └── read_pcm_wav ──> WhisperSpeechBackend ─┘        │
                                                            ├── child features.jsonl（受控转写）
                                                            └── privacy-safe case metrics
                                                                     │
                                                        variant / comparison report
```

| 模块 | 职责 |
|---|---|
| `speech_backend.py` | 维持共同 `SpeechBackend → SpeechSegment` 契约；Whisper 秒级 segment 统一换算为毫秒，不伪造跨模型可比的 confidence |
| `speech_benchmark.py` | 对每个 variant 只加载一次模型，逐 case 建独立 run，计算 CER、覆盖、耗时和静音探针，再形成父报告 |
| `contracts.py` | 定义不含参考/假设原文的 case、variant、comparison 严格契约 |
| `prepare_v1_m3_speech_models.py` | 登录节点下载或计算节点离线校验 Whisper 与三个 FunASR 权重摘要 |
| `v1_m3_speech_comparison.sbatch` | 在 L40 上以同一 Python/CUDA 环境顺序运行两个 variant，计算节点禁止下载 |

## 5. 指标与静音探针

主指标为 corpus CER：先汇总六条样本的编辑数和参考字符数，再相除，不能平均六个 case CER。辅指标包括：

- 每 case CER、完全匹配、空输出和字符数；
- 按标注 gender 分组的 corpus CER，仅作切片诊断，不作公平性结论；
- segment union duration / WAV duration，明确它不是带人工 VAD 标签的共同检测指标；
- 模型加载耗时、首条/均值/P95/最大推理耗时、纯推理 RTF；
- Torch CUDA peak 与 `nvidia-smi` 进程显存快照，分别注明口径。

两个 variant 在六条真实语音之后各运行一次 2 秒、16 kHz、单声道全零 PCM 静音探针。验收条件是归一化后字符数为 0；报告只保存 segment 数、字符数和 pass/fail，绝不保存可能的幻觉文本。该探针只检查明显静音误转写，不代表真实房间噪声误报率。

## 6. 隐私与产物

逐句参考文本只来自被 Git 忽略的数据 manifest；模型转写只进入 child run 的 `features.jsonl`，privacy level 为 `derived_sensitive`。以下产物都不含逐句原文：

- `speech-case-evaluation.json`：case ID、字符数、编辑数、CER、覆盖和耗时；
- `speech-variant-<id>.json`：聚合、分组、运行环境和静音探针；
- `speech-model-comparison-report.json`：两个 variant 的差值与共同限制；
- CLI stdout：仅打印聚合 CER、exact/blank、RTF 和静音 pass/fail。

## 7. 运行与验收

登录节点准备并校验权重：

```bash
python -m pip install -e ".[dev,multimodal,speech-compare]"
python scripts/prepare_v1_m3_speech_models.py
python scripts/prepare_v1_m3_speech_models.py --offline
```

本地 CPU 预检或提交 L40：

```bash
kangshield-info benchmark-speech-models \
  data/processed/v1-m2b/benchmark-cases.json \
  --offline-models \
  --funasr-device cpu \
  --whisper-device cpu \
  --whisper-fp32

make submit-m3-speech-comparison
```

正式 Review 前必须同时满足：

1. 权重离线校验全部通过，parent + 12 child manifests 为 `completed`、干净提交且 commit 一致。
2. Slurm job 为 L40、exit `0:0`，两个 binding 均记录实际 CUDA device、版本和摘要。
3. FunASR baseline 在同一规则下复现 `9/137` corpus CER；不一致先定位回归，不能直接比较 candidate。
4. 两个静音探针均明确记录；非空输出必须列为失败案例。
5. 报告中没有参考或假设全文，且 CER、总字符数、总编辑数可由 case 汇总复算。
6. 根据 CER、静音、性能、C6c 待验证边界形成“采用 / 条件候选 / 放弃”结论，不把六条 clean speech 当最终选型。

## 8. 已完成的开发预检

- 自动化测试：35 passed。
- Whisper `small.pt`：483,617,219 bytes，SHA-256 `9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794`，离线校验通过。
- 三个 FunASR 权重摘要与 V1-M2a/M2b 记录一致，离线校验通过。
- 两次独立的 Python 3.13 CPU 六 case 全链路预检均为 7/7 manifests completed；它们是 dirty 开发运行，不作为正式里程碑证据。
- FunASR 开发预检原样复现 `9/137 = 0.065693`、3/6 exact；Whisper 固定参数预检为 `32/137 = 0.233577`、0/6 exact。该早期信号显示 Whisper small 在 clean Mandarin 切片上明显较差，因此不做同集调参，只等待 L40 复现和错误类别 Review。
- 两个 2 秒全零 PCM 探针均为 0 字符；14 份开发态 manifests 对应的 16 份 report 中，完整参考与完整假设文本泄漏计数均为 0。

正式 L40 结果、失败样本和晋级决定将在干净提交运行后写入 `docs/reports/v1-m3-speech-model-comparison.md` 和 Review log。
