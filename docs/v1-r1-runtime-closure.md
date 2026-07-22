# V1-R1 候选比赛 Runtime 依赖闭包门

状态：Implemented Baseline v0.1；E1 工具完成，候选环境仍为 Blocked

更新时间：2026-07-23

适用范围：V1-R1 G5、候选比赛运行环境收敛、最终 `requirements/competition.lock` 与第三方 NOTICE 的前置证据

## 1. 目标与边界

本门禁把“代码在当前环境里能运行”与“该环境可以冻结为比赛依赖闭包”分开。它从当前解释器的 `pip inspect` 或已脱敏快照出发，沿 profile 中的直接依赖、extras 和 PEP 508 markers 计算实际传递闭包，再检查版本、安装来源、禁入包、环境纯净度和许可证元数据。

门禁负责：

- 固定一个候选 runtime profile 的 Python/平台、仓库来源摘要和直接依赖版本。
- 把 `onnxruntime-gpu[cuda,cudnn]` 等根 extras 继续传播到传递依赖，而不是只做普通 `pip check`。
- 识别缺失/版本不符依赖、URL dependency、editable/PYTHONPATH、闭包外包和缺失许可证元数据。
- 生成可回放、无本地路径的 `runtime-inventory.json` 与 `runtime-closure.json`。
- 为最终 clean environment、competition lock 和 NOTICE 提供包名/版本/证据缺口清单。

门禁不负责：

- 自动安装、卸载或替换当前环境中的包。
- 自动生成最终 `requirements/competition.lock` 或 `THIRD_PARTY_NOTICES.md`。
- 把包 metadata 中存在许可证字段解释为已经完成法律或分发 clearance。
- 决定 HumanArt/FunASR 权重是否随比赛包携带。
- 把候选 L40 profile 写成最终比赛平台承诺。

报告固定 `candidate_only=true`，并把 `competition_lock_emitted`、`third_party_notice_emitted`、`legal_advice_provided`、RiskAssessment 与 Alert 全部固定为 false。

## 2. 当前候选 Profile

配置：`configs/v1-r1-runtime-profile-rtmpose-funasr.json`

profile 名称承接已完成的 L40 探索路线，但当前 target gate 只冻结 Linux x86_64 与 CPython 3.13.13；GPU/CUDA native runtime 仍由 Slurm preflight 验证，最终比赛镜像还需独立 receipt。profile 状态始终为 `candidate_not_release`。直接依赖为：

| 直接依赖 | 固定版本 | 目的 |
|---|---|---|
| KangShield | 0.3.0 | 当前工程与公共契约 |
| NumPy | 2.4.4 | 媒体、ONNX Runtime 与语音数组 ABI |
| opencv-python-headless | 4.13.0.92 | 无 GUI 视频解码与预处理 |
| PyAV | 18.0.0 | 同容器音视频 PTS |
| onnxruntime-gpu | 1.27.0，激活 `cuda,cudnn` extras | HumanArt YOLOX + RTMPose ONNX |
| Torch | 2.13.0 | FunASR L40 推理 |
| FunASR | 1.3.22 | 普通话 VAD/ASR/标点 |
| SoundFile | 0.14.0 | FunASR 音频依赖 |

当前 profile 禁止 Ultralytics、OpenAI Whisper、TorchVision、GUI OpenCV 与 pytest 进入闭包；`pip/setuptools/wheel` 只作为 bootstrap 例外。KangShield 可以由本地构建产物安装，但 editable install、`PYTHONPATH` 注入和未明确批准的其他 direct URL 均不能通过正式安装 provenance 门。

这份 profile 只表达“若采用 RTMPose + FunASR 主路径，需要审计什么”，不替代最终模型选择。选择 Keypoint R-CNN、CPU fallback、容器预置 CUDA 或不同 Python 后，必须新增 profile，不能在本文件中静默换依赖。

## 3. 数据流与隐私

```text
current interpreter or sanitized replay
                │
                ▼
           pip inspect
                │  raw metadata only in memory
                ▼
sanitize names / versions / requirements / license evidence
strip metadata_location, URL value, local path and license body
                │
                ├── runtime-inventory.json
                ▼
direct roots + extras + markers → transitive closure
                │
                └── runtime-closure.json
```

脱敏快照只保存：规范化包名、版本、installer 标识、requested/direct-URL/editable 布尔值、结构化 dependency name/specifier/marker/extras，以及许可证 metadata 的状态、SPDX expression、legacy value SHA-256 和许可证 classifier。以下内容不落盘：

- `metadata_location` 和 site-packages 路径。
- editable/source/direct URL 的实际值。
- `PYTHONPATH` 内容；只保留是否配置的布尔值。
- legacy license 正文；只保留 SHA-256。
- 原始包 description、作者邮箱和其他无关 metadata。

marker 中出现路径型内容、无法解析的 requirement 或 URL dependency 时 fail closed。快照与 profile 作为两个 aggregate SourceAsset 绑定，runs 根/run/报告目录继续遵守 `0700/0600`。

## 4. 闭包算法

1. 对 profile 直接 requirement 做规范化、唯一性和版本约束检查；URL、marker 或无版本约束的根依赖被拒绝。
2. 按 profile 目标 Python/平台评估每个 `Requires-Dist` marker，而不是使用调用机器的隐含默认值。
3. 从根 requirement 携带的 extras 开始广度遍历；某个依赖新增 extras 时重新评估其可选边。
4. 每条生效边检查目标包是否存在、实际版本是否满足 specifier、是否为 URL dependency。
5. 闭包完成后，独立检查禁入包、安装 provenance、闭包外包和许可证 metadata。

这种做法可以发现普通 `pip check` 看不到的根 extras 缺口。例如当前 profile 显式请求 `onnxruntime-gpu[cuda,cudnn]`，因此 CUDA/CUDNN 可选依赖必须进入候选闭包，即使已安装包的普通 base requirements 看起来没有破损。

## 5. 八个 Gate

| Gate | Ready 条件 |
|---|---|
| `target-environment-ready` | Python、实现、OS、架构与 profile 完全一致 |
| `repository-source-ready` | `pyproject.toml` 等来源存在且 SHA-256 匹配 |
| `direct-requirements-ready` | 所有直接依赖存在且版本满足约束 |
| `dependency-closure-ready` | 生效的 extras/marker 传递边全部可解析且满足版本 |
| `prohibited-closure-absent` | 禁入包没有进入计算闭包 |
| `installation-provenance-ready` | 无 editable/PYTHONPATH，未批准 direct URL 为零 |
| `isolated-environment-ready` | 除闭包和 bootstrap 外没有其他可见 distribution |
| `license-metadata-ready` | 每个已安装闭包包至少有一项可审计许可证 metadata |

只有八个 gate 全部通过，`closure_snapshot_ready=true`。这仍只表示“快照可以进入人工 lock/NOTICE Review”，不表示提交包可发布；最终 G5 仍由 distribution readiness gate 管理。

## 6. 命令

开发环境盘点：

```bash
make PYTHON=.venv/bin/python assess-runtime-closure
```

该 Make 入口使用 `PYTHONPATH=src`，所以会如实关闭 installation-provenance gate；它用于开发盘点，不用于 RC 证明。

干净已安装环境盘点：

```bash
kangshield-info assess-runtime-closure \
  --profile configs/v1-r1-runtime-profile-rtmpose-funasr.json \
  --repository-root . \
  --runs-dir runs
```

重放某次已脱敏快照：

```bash
kangshield-info assess-runtime-closure \
  --snapshot <prior-run>/reports/runtime-inventory.json
```

候选环境硬门：

```bash
kangshield-info assess-runtime-closure --require-ready
```

普通审计在正确产出 blocked 报告时返回 `0`；`--require-ready` 在报告完整落盘后返回 `2`。

## 7. 当前 E1 结果

clean run `20260722T222305Z-2b36b79b` 对现有共享开发环境得到：

- 189 个可见 installed distribution，候选闭包 111 个。
- 8 个直接依赖中 7 个匹配；缺 `opencv-python-headless==4.13.0.92`。
- extras/marker 闭包有 4 个缺失项：ONNX Runtime 请求的 CUDA NVRTC、runtime、CUFFT、CURAND `*-cu13` distributions。
- 5 个禁入包都在闭包外，因此 `prohibited-closure-absent=true`；但它们仍存在于共享开发环境，随 71 个其他包一起形成 76 个 extraneous distribution。
- 26 个 installation provenance 阻断：KangShield editable install，以及 25 个未批准 direct-URL 安装记录。
- 3 个闭包包缺许可证 metadata：KangShield、`cuda-toolkit`、`kaldiio`。
- 八个 gate 中只有 target、repository source 和 prohibited closure 三个通过；最终 `blocked_runtime_closure_review`。

这不否定 jobs `1776`～`1780` 的 L40 功能证据。它只证明共享探索环境混合了 Conda、开发工具、多个模型候选和本地安装来源，不能直接复制成比赛 lock/NOTICE。

## 8. 打开流程

1. 在独立环境或容器层安装 KangShield 非 editable 构建产物，不设置 `PYTHONPATH`。
2. 只安装 profile 的八个根依赖；用 headless OpenCV 替换 GUI OpenCV。
3. 对 ONNX Runtime 1.27 CUDA extras 选择完整满足 metadata 的安装方式；若比赛镜像预置动态库而不以 Python distribution 提供，必须新 profile 明确表达并增加 native-runtime receipt，不能口头忽略四项缺口。
4. 重跑 closure gate，删除 76 个闭包外包并消除未批准 direct URL。
5. 为 KangShield、CUDA toolkit、KaldiIO 和其他 legacy/classifier-only 项完成人工许可证证据复核。
6. 只有 clean snapshot 八门通过后，才生成候选 `requirements/competition.lock` 和 NOTICE 草案。
7. 最终模型/打包/项目许可证 owner 决策完成后，把 lock/NOTICE 摘要绑定进 distribution profile，再运行其 `--require-ready`。

正式证据见[候选 Runtime Closure E1 报告](reports/v1-r1-runtime-closure.md)。
