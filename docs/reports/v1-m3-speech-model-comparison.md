# V1-M3 语音模型同集对比报告

状态：Accepted for V1-M3 speech slice

日期：2026-07-22

## 1. 结论

FunASR 保留为 V1/V2 普通话 ASR 主链路；OpenAI Whisper small 不晋级为其替代方案，只保留为可复现的实验适配器。相同六条 FLEURS 普通话、相同文本归一化和相同 L40 上，FunASR corpus CER 为 `9/137 = 6.57%`，Whisper small 为 `32/137 = 23.36%`，candidate 劣化 `+16.788` 个百分点，并且六条语音的编辑数都没有优于 baseline。

两个模型都通过 2 秒全零 PCM 静音探针；Whisper 的冷加载更快、Torch peak 更低，但纯推理 RTF 更高。性能优势不足以抵消当前普通话准确率差距。这个 E1 小样本结论不能外推到 C6c 远场、老人语音、方言、噪声或多语种；只有新建 held-out 场景集后才能重开 Whisper 或其他候选，不在当前六条上调参重报。

## 2. 证据定位

| 项目 | 值 |
|---|---|
| 实现提交 | `270fdc1` |
| Slurm job | `1761`，`COMPLETED`，exit `0:0`，elapsed `00:00:55` |
| 节点/GPU | `hepnode1` / NVIDIA L40 46,068 MiB |
| Parent run | `20260722T063528Z-e5fca78b` |
| Parent report | `runs/20260722T063528Z-e5fca78b/reports/speech-model-comparison-report.json` |
| Benchmark | `v1-m2b-public-fixed-6` / `speech-model-comparison-v0.1.0` |
| Evidence | E1 public clean read speech；不是目标设备证据 |
| Source manifest SHA-256 | `11108991e5058c3298970bb47f3a863705e40d8974f81967889df782429e7f04` |
| Benchmark cases SHA-256 | `da41471e2577efe6f8d4f859319c59daddfcd778fdeed6e89cfaeb09b20e9265` |

运行固定 `language=zh`、`task=transcribe`、beam 5、temperature 0、`condition_on_previous_text=false`；Whisper 在 GPU 上使用 FP16。解码参数、模型来源和隐私契约见 [V1-M3 语音模型同集对比设计](../v1-m3-speech-model-comparison.md)。

## 3. 模型绑定

| task | backend/model | version | weight SHA-256 | license | device |
|---|---|---|---|---|---|
| VAD | FunASR FSMN-VAD | `master` | `b3be75be477f0780277f3bae0fe489f48718f585f3a6e45d7dd1fbb1a4255fc5` | Apache-2.0 | `cuda:0` |
| 普通话 ASR | FunASR SeACo Paraformer | `master` | `3d491689244ec5dfbf9170ef3827c358aa10f1f20e42a7c59e15e688647946d1` | Apache-2.0 | `cuda:0` |
| 标点 | FunASR CT-Punc | `master` | `7176cae922a872e130e6b88aef9a1153581711baf79c9124c7c95be383cd6f81` | Apache-2.0 | `cuda:0` |
| 普通话 ASR candidate | OpenAI Whisper small | `20250625` | `9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794` | MIT | `cuda:0` |

ModelScope 的 `master` 名称不是充分版本标识，因此继续以实际 `model.pt` SHA-256 作为工程绑定。Whisper 使用 OpenAI 原始 checkpoint 和 `openai-whisper==20250625`。

## 4. 主结果

| variant | edits / reference chars | corpus CER | exact | blank | silence | inference RTF |
|---|---:|---:|---:|---:|---:|---:|
| FunASR baseline | 9 / 137 | 0.065693（6.57%） | 3/6 | 0/6 | pass，0 chars | 0.037648 |
| Whisper small | 32 / 137 | 0.233577（23.36%） | 0/6 | 0/6 | pass，0 chars | 0.089950 |
| candidate - baseline | +23 edits | +0.167884（+16.788 pp） | -3 | 0 | — | +0.052302 |

Whisper 输出 130 个归一化字符，FunASR 输出 131 个；差异不是由 candidate 空输出造成。两者均对六条语音返回 segment，静音均返回 0 segment、0 字符。

### 4.1 逐 case 错误计数

| case | gender 标签 | reference chars | FunASR edits / CER | Whisper edits / CER |
|---|---|---:|---:|---:|
| `fall-01-fleurs-f01` | female | 18 | 0 / 0.000000 | 6 / 0.333333 |
| `fall-02-fleurs-m01` | male | 26 | 1 / 0.038462 | 9 / 0.346154 |
| `fall-03-fleurs-f02` | female | 20 | 7 / 0.350000 | 10 / 0.500000 |
| `adl-01-fleurs-f03` | female | 17 | 1 / 0.058824 | 5 / 0.294118 |
| `adl-02-fleurs-m02` | male | 28 | 0 / 0.000000 | 1 / 0.035714 |
| `adl-03-fleurs-m03` | male | 28 | 0 / 0.000000 | 1 / 0.035714 |

Whisper 在 6/6 case 的编辑数都高于 FunASR，不存在“总 CER 被单条极端样本拉差、其余样本更好”的反向证据。

### 4.2 gender 诊断切片

| variant | female edits/chars / CER | male edits/chars / CER |
|---|---:|---:|
| FunASR | 8/55 / 0.145455 | 1/82 / 0.012195 |
| Whisper small | 21/55 / 0.381818 | 11/82 / 0.134146 |

每组只有三条且话句不同，不能将差异解释成 gender 公平性结论。这里只记录可复算切片，后续真实样本必须平衡说话人、话句、距离和噪声。

## 5. 性能与资源

| variant | model load | inference total | first / mean / P95 | Torch CUDA peak | process GPU snapshot |
|---|---:|---:|---:|---:|---:|
| FunASR | 35,051 ms | 1,475 ms | 702 / 246 / 702 ms | 2,099 MiB | 2,568 MiB |
| Whisper small | 2,510 ms | 3,524 ms | 753 / 587 / 753 ms | 1,411 MiB | 2,042 MiB |

环境为 Python 3.13.13、Torch 2.13.0+cu130、FunASR 1.3.22、openai-whisper 20250625。Whisper 冷加载约快 14 倍且 Torch peak 少约 688 MiB；FunASR 六条纯推理约快 2.39 倍。两者 warm RTF 都小于 1，满足当前单路离线回放吞吐要求。

`nvidia-smi` 数值是推理后进程快照，不是采样峰值；Torch peak 不覆盖框架外部分配。`/usr/bin/time -v` 记录整个双 variant 进程最大 RSS 5,616,000 KiB，不能拆分归因给单一模型。

## 6. Segment 与静音解释

FunASR 汇总 segment coverage 约为模型 VAD 的语音区间；Whisper 的 segment 是集成解码时间段，甚至有 case 覆盖完整 WAV。二者没有共同人工 VAD 标签，因此不能用更高 coverage 判断 Whisper 的语音检测更好。

两个 2 秒全零探针都返回 0 segment、0 字符。它只排除了当前固定解码对理想全零输入的明显幻觉，不覆盖空调、电视、回声、呼吸、碰撞或远场底噪。

## 7. 证据与隐私审计

- parent + 12 child manifests 共 13 份，全部 `completed`、`code_version=270fdc1`、`code_dirty=false`。
- 逐 case 复算得到 FunASR 9/137、Whisper 32/137，与 variant 和 parent 报告一致。
- 12 个 case report、2 个 variant report、1 个 comparison report 共 15 份 JSON；完整参考文本与完整假设文本的泄漏计数均为 0。
- 对 Slurm stdout/stderr 同样扫描，完整参考与完整假设文本泄漏计数均为 0。
- 完整模型转写只存在于被 Git 忽略的 child `features.jsonl`，case/variant/comparison 和 CLI stdout 只保留计数与聚合。
- 自动化测试 35 passed，`pip check` 无 broken requirements；模型准备脚本在 job 内再次离线校验四个权重摘要。

## 8. 决定与后续门

1. FunASR FSMN-VAD + SeACo Paraformer + CT-Punc 保留为 V2 普通话默认候选；“默认”仍须通过 C6c V1-M2c 真实场景门。
2. Whisper small 在当前 V1-M3 语音切片结论为“不晋级普通话主链路”，不因更快冷加载和较低显存改写准确率结论。
3. 保留 Whisper backend、模型摘要与 runner，便于未来在新的多语种、方言或噪声 held-out 集上复测；禁止继续在这六条上调 beam/prompt/语言后宣称独立提升。
4. C6c 复测至少包含安静/电视背景、1/3/5 米、男女或不同说话人、老人或年龄相近授权说话人、方言/普通话、静音和非语音噪声，并分别报告 CER、VAD 漏检/误激活和 RTF。
5. V1-M3 语言切片通过 Review；完整 V1-M3 仍为 In progress，等待睡眠字段路线形成采用/接口保留/放弃结论。
