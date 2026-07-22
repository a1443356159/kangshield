# V1-M2a 同容器音轨 PTS 对齐初测报告

状态：CPU 真实后端功能证据 Passed；L40 job `1771` Pending

日期：2026-07-23

本报告验证“单音视频容器 → 音轨解码/16 kHz → VAD/ASR → PTS 对齐 FeatureEvent → 多模态窗口”的设备无关链路。输入由既有公开 video/WAV 工程合成，固定为 E1 fixture；它不证明 CS-C6c-V101-1J4WF 能输出带音频的流，也不证明真实 capture clock 或 drift。

## 1. 实现边界

实现提交：

- `8c6df2d`：`AudioBuffer.start_ms`、PyAV 单音轨解码/重采样、PTS gap 静音保留、正负 offset 裁剪、Pipeline/CLI/report 契约与故障门；
- `15406db`：Slurm 强制使用提交 checkout 的 `src/`，并显式传递 `source_type`；
- `eca6231`：bitexact 250 ms 公开 A/V 夹具准备器与可重复性测试。

入口保持两种布局：

- `run-multimodal <video> <pcm-wav>`：仅作 `separate_files_synthetic_common_zero` 工程回归；
- `run-multimodal <av-container> --audio-from-video`：使用 `same_container_pts`，不允许猜测共同零点。

同容器模式在推理前要求：恰好一条视频轨和一条音轨、起点可测、逐包 PTS 完整、扫描未截断、音频 PTS 不逆序。任一条件不满足即失败，不回退到独立文件语义。

## 2. 输入与可重复准备

| 项目 | SHA-256 / 值 |
|---|---|
| 公开视频输入 | `9112dbfeb6548d54ee9ac071bd1a7f5d92b54270542de3ee488aca6b04eaeae6` |
| 公开中文 WAV 输入 | `a1bd32dc78493c123f9625a66deee562aed2895f53fbc39f2cca3be7e6f4f20f` |
| bitexact Matroska 输出 | `c989405d3c4b8cacb3418df919da6530335399b33f3e5e52b9bb307e48dcad80` |
| 输出大小 | 28,741,707 bytes |
| 轨道编码 | FFV1 视频 + PCM S16LE 单声道音频 |
| 工程音轨偏移 | +250 ms |
| 视频 / 音频规模 | 50 帧 / 88,747 samples @ 16 kHz |

准备器对同一输入连续执行两次，输出大小和 SHA-256 完全一致。该稳定性来自 bitexact Matroska mux；250 ms 是测试夹具刻意写入的 PTS，不是从自然同步事件估计的设备偏移。

## 3. Clean CPU 真实后端运行

| 项目 | 值 |
|---|---|
| run_id | `20260722T190551Z-29f7f25c` |
| code | `eca6231`，`code_dirty=false` |
| status / issue | `completed` / 0 |
| evidence / source | E1 / fixture |
| Pipeline | `multimodal-replay-v0.3.0` |
| 配置 | CPU；姿态 5 FPS；1 秒窗口；最多 6 秒；离线模型缓存 |
| input layout | `same_container_pts` |

真实后端为 YOLO26n-pose + ByteTrack、FSMN-VAD、SeACo Paraformer 与 CT-Punc；权重摘要和许可证仍由既有 ModelBinding 记录。本次没有使用 fake backend，也没有联网下载模型。

## 4. PTS 与功能结果

| 检查项 | 结果 |
|---|---:|
| SourceAsset / Observation | 1 / 1 |
| 视频轨 / 音频轨 | 1 / 1 |
| 两轨 packet | 50 / 56 |
| missing PTS / scan truncated | 0 / false |
| `audio_minus_video_start_ms` | 250.0 ms |
| `audio_minus_video_end_ms` | 796.0 ms |
| `duration_delta_ms` | 546.0 ms |
| `drift_estimate_available` | false |
| Pipeline 时间轴 | 5,800 ms |
| 姿态抽帧 / 有人帧 / 实例 | 25 / 25 / 100 |
| VAD 段 / 转写段 | 1 / 1 |
| 融合窗口 | 6 |

视频和音频共用同一个 asset/observation，report 满足 `video_asset_id == audio_asset_id`。音频被解码为 16 kHz 单声道 PCM 后送入 SpeechBackend；VAD 与转写 FeatureEvent 都落在视频时间轴 `1130–5445 ms`。该范围已包含 +250 ms 平移；报告只记录段数，本文只记录时间和转写字符数 20，不复制文本。

末端偏移 796 ms 与 duration delta 546 ms 来自公开 WAV 比视频更长，再加 250 ms 起点偏移；两者不是 drift。单个容器的首尾范围不能替代两个真实同步事件。

## 5. CPU 性能口径

| 口径 | 结果 |
|---|---:|
| 模型加载 | 35,584.214 ms |
| 模型加载后的完整处理 | 3,569.355 ms |
| processing RTF | 0.615406 |
| cold-start RTF | 6.750615 |
| 视频姿态 | 2,090.266 ms；RTF 0.360391 |
| 语言分支 | 657.712 ms；RTF 0.118571 |
| 姿态首帧 / 稳态均值 | 963.081 / 42.111 ms |

CPU processing 小于媒体时长，但冷启动明显不适合演示时即时拉起。该结果只验证功能与粗略容量；L40 job `1771` 将单独提供 GPU 口径。

## 6. 产物摘要与隐私

| 产物 | SHA-256 |
|---|---|
| manifest | `7e82b911b94134a0c5da0e1aecc7fc229b4c108911411df6c1c03d2931d3d32a` |
| container probe | `4e4c7059c274438344975a3ce6e40eb46d840db529e0fb141578479e1f13ce44` |
| pipeline report | `7ebe3d49d5bcfe9be0760f3af0461ddc6e5324a9c849e4f379d6e2b5f9b7a784` |
| source assets | `2ad62d5215a7e6763aefa1bf1b969ef50baf18d9099faa38d6066ba8998e8648` |
| observations | `75cc5921dcdbf24c56a695a667761b9974e4b9cb8f0693724527c468fae01874` |
| sensitive features | `d68398597a348febbd7fa668cc1e146473144e9e5e795e7d338100e82719008f` |
| multimodal windows | `d608515968dfeb25f8f67c6cb730c85d5fd036e5b96b06753606b58348d0bc23` |

manifest、probe、pipeline report、SourceAsset 与 Observation 对本机绝对路径、用户名、原始文件名和完整转写做了 0 命中扫描。完整转写只在被 Git 忽略的 `derived_sensitive` FeatureEvent 中；仓库不提交媒体、run 或模型权重。

## 7. 自动化验证

- 全量：117 passed；
- `compileall`、全部 shell/sbatch `bash -n`、`pip check` 与 `git diff --check` 通过；
- 正偏移：+250 ms 起点、16 kHz、max-duration 截断和 FeatureEvent 平移；
- 负偏移：裁掉视频零点前样本；
- PTS gap：在音频缓冲中保留为静音；
- fail-closed：0/2 音轨、缺 PTS、扫描截断、音频 PTS 逆序、CLI 缺失/冲突选择；
- provenance：同容器只写一份 asset/observation/probe，Slurm 显式绑定 submit checkout。

## 8. 尚未关闭

1. job `1771` 完成前，不发布 L40 processing/cold-start 结果。
2. 本轮是 public/engineered E1，不提升 C6c 能力等级；仍需真实同意的原始容器或可靠同步导出。
3. 容器 PTS 只证明文件内时间语义；真实 G2 必须人工定位至少两个同步事件，计算 offset/drift。
4. 离线文件 replay 不包含萤石鉴权、取流、网络抖动、缓冲、断流恢复或直播延迟。
5. YOLO/RTMPose/Keypoint R-CNN 的最终比赛选择与权重分发门不因本轮改变。
