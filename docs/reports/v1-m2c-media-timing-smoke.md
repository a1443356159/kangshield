# V1-M2c 容器时间戳探针初测报告

状态：Accepted for V1-M2c E1 timing-probe slice；V1-M2c remains In progress

基准日期：2026-07-22

目标设备：CS-C6c-V101-1J4WF（本报告未使用目标设备媒体）

证据提交：`4a65630`

正式运行：`20260722T095247Z-b49f532e`

## 1. 结论

容器轨道与逐包 PTS/DTS 探针已打通，并在确定性同容器音视频夹具上通过 E1 Review。探针能 fail closed 地确认音轨存在、记录逐轨 time base 和时间戳完整性，并输出首尾容器偏移；它不会在没有两个跨模态同步事件时输出 drift。

本报告没有证明 C6c 服务端媒体含音频、设备采集时钟准确、物理声画同步或长期漂移达标。G2 仍等待真实 C6c 原始容器的 E2/E3 证据。

## 2. 输入与可复现性

| 项目 | 结果 |
|---|---|
| Stage | `v1-media-probe` |
| Evidence/source | E1 / `fixture` |
| Manifest | completed |
| Code | `4a65630`，`code_dirty=false` |
| Probe | `media-probe-v0.2.0` |
| Timing contract | `container-timing-v0.1.0` |
| Backend | PyAV 18.0.0 |
| Fixture | deterministic AVI，66,044 bytes |
| Fixture SHA-256 | `0b3bd01c83cc138780b4f3fd809798413ba8885f5ee0770a467a3bac17f24672` |
| Quality | pass，0 error / 0 warning |

夹具分别写入两个新文件时内容完全相同；仓库新增自动化测试持续约束字节级确定性。正式运行目录位于被 Git 忽略的 `runs/20260722T095247Z-b49f532e`。

## 3. 容器与轨道结果

| 项目 | 视频 | 音频 |
|---|---:|---:|
| Stream index | 0 | 1 |
| Codec | FFV1 | PCM S16LE |
| Time base | `1/10` | `1/8000` |
| Declared start | 0 ms | 0 ms |
| Packet count | 30 | 30 |
| Packets with PTS | 30 | 30 |
| Packets with DTS | 30 | 30 |
| Missing PTS / DTS | 0 / 0 | 0 / 0 |
| Negative PTS | 0 | 0 |
| PTS / DTS backward steps | 0 / 0 | 0 / 0 |
| End PTS | 3000 ms | 3000 ms |
| Median / max forward PTS step | 100 / 100 ms | 100 / 100 ms |
| Scan truncated | false | false |

容器识别为 AVI，总时长 3000 ms；`same_container_av=true`。两条轨道均完整覆盖 0～3000 ms。

## 4. 对齐字段解释

| 字段 | 结果 | 可得结论 |
|---|---:|---|
| `audio_minus_video_start_ms` | 0.0 | 合成文件两轨最小 PTS 同起点 |
| `audio_minus_video_end_ms` | 0.0 | 合成文件两轨最大包结束时间相同 |
| `duration_delta_ms` | 0.0 | 合成文件两轨 PTS 覆盖时长相同 |
| `drift_estimate_available` | false | 没有事件检测，不输出漂移 |

这三个 0 ms 只验证夹具与计算契约，不是“C6c 音画同步为 0 ms”。即使真实容器得到相同数值，也仍需开始/结束两次拍手或击板事件检查编码、采集与播放链路中的实际偏移。

## 5. Fail-closed 验证

自动化覆盖：

1. `--require-audio-track` 遇到 video-only 文件时 Observation 为 fail，并记录 `required_audio_track_missing`。
2. packet 上限必须为正；扫描到上限时报告 `scan_truncated=true`、Observation 为 partial。
3. 同容器视频/音频逐包 PTS/DTS、偏移和时长差可重复计算。
4. PyAV 不可用或解析失败时，不把音轨写成 absent；required 模式按 unverified 失败。
5. Matroska 测试输入带敏感标题，报告只保存 metadata key 数量，不保存值或源路径。
6. AVI 正式夹具两次独立生成字节完全一致。

全套验证为 46 passed；`pip check` 无 broken requirements，`compileall` 与 `git diff --check` 通过。

## 6. 隐私与产物校验

| 对象 | SHA-256 |
|---|---|
| Formal manifest | `faf5ed5e2b32ad45cb9252cd78824ccbca9dcf2e2f6db95027246ac4b9bfc8ee` |
| Media probe report | `4aad8b17733cf2f7d34b64f118b3a18eb29718280bc0f9f99066a7b5d17d69ad` |

正式报告记录 `metadata_key_count=2`，同时固定 `metadata_values_persisted=false` 和 `source_path_persisted=false`。对正式运行目录扫描：夹具 title/fixture 元数据值、`/home/yyy`、`data/raw` 和完整源文件名均为 0 命中。SourceAsset URI 只含内容摘要和 `.avi` 后缀。

## 7. Review 决定与下一步

1. 接受 PyAV 18.0.0 + 严格 `ContainerTimingReport` 作为 V1-M2c 原始容器探针。
2. 接受确定性 AVI 作为 E1 回归夹具；不把它升级为目标设备证据。
3. C6c 每个含语音原始 clip 必须使用 `--require-audio-track`，并保留失败 manifest。
4. 当前不实现基于容器首尾差的伪 drift；真实 G2 必须检测两次可见/可听同步事件。
5. V1-M2c 状态转为 In progress，但 C6c 与 CS-EP-SDNL1 的设备能力等级仍为 E0。

下一步取得 C6c 原始媒体后，先运行本探针，再补同步事件检测、真实轨道选择和 E2/E3 报告；若无法取得同容器音频，则按 G2 降级为视频/语言分开展示。
