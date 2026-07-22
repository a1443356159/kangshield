# V1-R1 候选比赛 Runtime Closure E1 报告

日期：2026-07-23

状态：Engineering gate Passed；current candidate environment Blocked as designed

范围：候选 RTMPose + FunASR L40 profile、live `pip inspect` 脱敏、extras/marker 闭包、版本/来源/纯净度/许可证 metadata gate、RunArtifact provenance 与隐私

## 1. 结论

`runtime-closure-v0.1.0` 已关闭从宽范围项目依赖到可审计候选闭包之间的工程断点。正向 fixture 能在隔离、版本、extras、来源和 metadata 全部满足时打开八门；缺依赖、版本漂移、marker/extras、禁入包、editable/PYTHONPATH、direct URL、环境污染、许可证 metadata 和来源摘要漂移均 fail closed。

当前共享 `.venv` 仍不能生成最终比赛 lock：八门只通过 3 门，结论为 `blocked_runtime_closure_review`。这是预期评估结果，不是工具运行失败，也不否定已经完成的 L40 模型功能 smoke。

## 2. 正式运行

| 项目 | 结果 |
|---|---|
| 实现提交 | `876ce07` |
| run | `20260722T222305Z-2b36b79b` |
| stage / evidence | `v1-r1-runtime-closure` / E1 |
| status / issues | completed / 0 |
| code provenance | `876ce07`，`code_dirty=false` |
| profile | `v1-r1-l40-rtmpose-funasr-candidate` / `candidate_not_release` |
| profile SHA-256 | `a1ef8ef46caf5002cd9e5fdaf461c7aeb09e0ac4b55cb0fc36f5ec7f69d10823` |
| inventory SHA-256 | `95feddb3e64c35da30578c616c78745676203d462849fda26af3aefb63119322` |
| closure report SHA-256 | `e683bb64e33cac573bed040065585ed1c732bfc77e9e7116845151a8da5f2f34` |
| manifest SHA-256 | `61313b04afd2e85387e81e1608f1bdbecc966f95054b620645fe87202b13637c` |
| source-assets SHA-256 | `f40be1bbaa20ef5114fd322b98e5ad6767d3e2d6552446f57bc465a50191f75d` |
| 权限 | runs 根/run/报告目录 `0700`；manifest/source-assets/JSON reports `0600` |

run 使用已安装 `kangshield-info` 入口，没有用 `PYTHONPATH=src`。manifest 不保存 profile、snapshot 或 repository root 路径；inventory/report 对 `/home/`、用户名和 Risk/Alert true 扫描均为 0 命中。

## 3. Gate 结果

| Gate | 结果 | 阻断数/说明 |
|---|---|---|
| target environment | true | CPython 3.13.13、Linux x86_64 匹配 |
| repository source | true | `pyproject.toml` 摘要匹配 |
| direct requirements | false | 1；缺 headless OpenCV |
| dependency closure | false | 4；ONNX Runtime CUDA extras distributions |
| prohibited closure absent | true | 5 个禁入包均未进入计算闭包 |
| installation provenance | false | 26；1 个 editable + 25 个未批准 direct URL |
| isolated environment | false | 76 个闭包外 distribution |
| license metadata | false | 3；KangShield、CUDA toolkit、KaldiIO |

汇总：installed 189、direct 7/8 matched、closure 111、dependency issue 4、prohibited-in-closure 0、extraneous 76、license-metadata-missing 3、gate 3/8 ready。

## 4. 关键发现

1. 项目 editable metadata 已从 0.2.0 修正至 0.3.0，KangShield 根版本现在匹配；但 editable 安装本身仍不构成 RC 安装来源。
2. 当前只有 GUI `opencv-python`，候选 profile 要求 `opencv-python-headless`。GUI 包属于闭包外/禁入项，不能把相同 `cv2` import 误写成 profile 已满足。
3. `onnxruntime-gpu[cuda,cudnn]==1.27.0` 的根 extras 激活后，缺少 `nvidia-cuda-nvrtc-cu13`、`nvidia-cuda-runtime-cu13`、`nvidia-cufft-cu13`、`nvidia-curand-cu13` 四项 metadata dependency。此前 CUDA loadability smoke 证明动态库可用，但不等于 Python distribution 闭包完整。
4. Ultralytics、Whisper、TorchVision、pytest 和 GUI OpenCV 都未进入 RTMPose + FunASR 计算闭包，说明候选 profile 能排除 V1 对照/fallback；它们仍安装在共享开发环境，因此 isolation gate 不通过。
5. 25 个闭包包来自未批准 direct URL metadata，KangShield 为 editable。报告只保存包名和状态，不保存 URL 或本地源码路径。
6. 许可证 metadata 缺失不直接证明包不可用，但没有足够输入生成可审计 NOTICE，因此必须保持 fail closed。metadata present 也只代表有待复核线索，不代表法律 clearance。

## 5. 自动化验证

- 全量测试：147 passed；runtime closure 新增 10 项测试。
- 正向门：隔离 fixture、根 extra 传播、Linux marker 与完整 license metadata 可打开 8/8。
- 故障门：target/source/direct/dependency/prohibited/install/isolation/license 八类分别可被关闭。
- 隐私：pip `metadata_location`、direct URL value、editable path、`PYTHONPATH` 内容和 legacy license 正文均不落盘；只保存布尔、包名或 SHA-256。
- CLI：live/replay、owner-only 产物、两类 SourceAsset、路径不持久化和 `--require-ready` 退出码均已覆盖。
- 静态检查：`compileall`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。

## 6. 对 G5 的影响

runtime profile 已作为第八个 source binding 接入 distribution readiness policy。clean follow-up run `20260722T222307Z-254cb0ca` 得到 8/8 source matched，但原有 5 个 owner decision、3 个发布文件和 6 个资产 clearance 仍未关闭，因此 distribution gate 继续保持 0/5 ready。其 policy/report SHA-256 分别为：

- policy：`e5916a8c6f55209c40bb97f0872c5dddd2db33f0ec8a903e7d29990f3c723b32`
- distribution report：`3a22916af9b981cd2acf99b1e907a647c4237471253506bfd6d8d4e62a836651`

本切片没有生成 `requirements/competition.lock` 或 NOTICE，也没有改变 HumanArt/FunASR、项目许可证或提交包的 clearance 状态。

设计和操作见[候选 Runtime 依赖闭包门](../v1-r1-runtime-closure.md)。
