# V1-M2c 容器音视频时间戳探针

状态：Accepted for V1-M2c E1 timing-probe slice；真实设备 G2 仍 Open

基准日期：2026-07-22

目标设备：CS-C6c-V101-1J4WF

## 1. 目标与边界

本切片先补齐“原始媒体里到底有什么轨道和时间戳”的设备无关工具，再把同一套工具用于 C6c 原始容器。它负责回答：

1. 容器中是否同时存在 video/audio track。
2. 每条轨道的 codec、time base、声明时长和逐包 PTS/DTS 完整性。
3. 两轨首尾时间戳的容器内相对偏移。
4. 扫描是否截断、时间戳是否缺失或在 demux 顺序中后退。

本切片不负责证明 C6c 已接入，也不把容器 PTS 当作采集时钟准确率、声画物理同步或漂移结论。V1-M2c 的 G2 只有在真实原始容器和两次可见/可听同步事件完成复核后才能关闭。

## 2. 实现选择

本机没有系统 `ffprobe`/`ffmpeg`，因此使用固定版本 `av==18.0.0` 直接读取容器、stream 和 packet。PyAV 官方 [Packet API](https://pyav.org/docs/stable/api/packet.html)定义了 packet 的 PTS、DTS、duration 和 time base；[Time API](https://pyav.org/docs/stable/api/time.html)说明时间戳按对应 time base 解释；[Stream API](https://pyav.org/docs/stable/api/stream.html)提供轨道级 start、duration、frames 和 rate 信息。

实现链路：

```text
原始媒体文件
  ├── SourceAsset：摘要、大小、来源与证据等级
  ├── OpenCV：视频可解码性、宽高/FPS、抽样图像质量
  └── PyAV：container → video/audio streams → demux packets
                  │
                  └── ContainerTimingReport + MediaStreamTiming[]
```

`container_timing.py` 只读取本地普通文件；路径不存在时立即失败，不把输入交给网络协议解析。

## 3. 契约与时间语义

### 3.1 容器级字段

| 字段 | 含义 |
|---|---|
| `format_names` | PyAV 识别的容器格式名 |
| `container_start_ms` / `container_duration_ms` | 容器声明的起点和时长，不替代逐轨扫描 |
| `video_stream_count` / `audio_stream_count` | 实际选中的视频/音频轨道数 |
| `same_container_av` | 同一个被探测文件同时含至少一条视频轨和音频轨 |
| `audio_minus_video_start_ms` | 首条音频轨最小 PTS 时间减首条视频轨最小 PTS 时间 |
| `audio_minus_video_end_ms` | 首条音频轨最大包结束时间减首条视频轨最大包结束时间 |
| `duration_delta_ms` | 音频 PTS 覆盖时长减视频 PTS 覆盖时长 |
| `drift_estimate_available` | 当前固定为 `false`；没有跨模态事件检测就不输出漂移 |

首条轨道按 stream index 选择。多视频或多音频文件仍记录所有轨道，但首尾偏移只比较各模态 index 最小的第一条轨道；真实样本出现多轨时必须人工确认目标轨道，不能只读聚合偏移。

### 3.2 轨道级字段

每条 `MediaStreamTiming` 保存：

- codec、time base、声明 start/duration/frame count；
- packet 总数以及包含 PTS/DTS 的包数；
- PTS/DTS 缺失、负 PTS、demux 顺序后退次数；
- first/last demux PTS、min/max PTS、包结束时间和 PTS span；
- packet duration 总和、相邻非负 PTS 步长的 median/max；
- 视频宽高、像素格式和 rate，或音频采样率、声道、layout 和 sample format。

`pts_backward_step_count` 不自动判错：带 B-frame 的视频可能合法重排。报告保留计数供编码/容器 Review，不把“PTS 后退”直接解释为断流。

## 4. Fail-closed 与资源上限

- `--require-audio-track` 下，PyAV 不可用/探测失败为 `required_audio_track_unverified`，没有音轨为 `required_audio_track_missing`，Observation 必须 `fail`。
- `--max-packets-per-stream` 必须为正数，默认 `200000`。任一选中轨达到上限后停止整次 demux，并把所有轨标为 `scan_truncated=true`；Observation 为 `partial`，不能用不完整扫描关闭 G2。
- PyAV 未安装时返回结构化 warning；不把异常正文、路径或底层库信息直接持久化，只保留异常类型。
- 容器元数据只保存 key 数量，不保存 key/value；报告明确记录 `metadata_values_persisted=false`、`source_path_persisted=false`。

## 5. 确定性 E1 夹具

```bash
make prepare-m2c-timing-fixture
kangshield-info probe-media \
  data/raw/public-smoke/v1-m2c-timing.synthetic.avi \
  --evidence-level E1 \
  --source-type fixture \
  --require-audio-track
```

夹具固定为 3 秒 AVI：96×64、10 fps、FFV1 视频；8 kHz、mono、PCM S16LE 音频；0.5 秒和 2.5 秒各含一次同步白帧/脉冲。选择 AVI 是为了避开 Matroska 自动生成的随机 SegmentUID。两次独立生成必须字节完全一致；当前文件为 66,044 bytes，SHA-256：

```text
0b3bd01c83cc138780b4f3fd809798413ba8885f5ee0770a467a3bac17f24672
```

当前探针只读取轨道/包时间戳，并不检测这两个白帧/脉冲。它们是后续真实同步事件检测与 drift 估计的测试接缝。

## 6. E1 验收结果

干净提交 `4a65630` 的正式运行 `20260722T095247Z-b49f532e` 为 completed、`code_dirty=false`：

- AVI 中 1 条 FFV1 视频轨、1 条 PCM S16LE 音频轨；
- 两轨各扫描 30 个包，PTS/DTS 均 30/30，无缺失、负值、后退或截断；
- 视频 time base `1/10`，音频 time base `1/8000`；
- start offset、end offset 和 duration delta 均为 0 ms；
- `drift_estimate_available=false`；
- synthetic 元数据值、完整文件名、`data/raw` 和本地绝对路径泄漏计数均为 0。

完整证据见 [V1-M2c 容器时间戳探针初测报告](reports/v1-m2c-media-timing-smoke.md)。本验收只关闭 E1 工具切片，不提升 C6c 的 E0 设备能力等级。

## 7. 真实样本使用规则

1. 必须探测 C6c 原始导出/录制容器，不先抽轨或重编码。
2. 输入按真实来源标为 E2 `local_file` 或 E2 `sdk_export`；直播 API 成功与媒体导出是不同证据。
3. 每段含语音 clip 使用 `--require-audio-track`；失败结果也保留 manifest。
4. 开始和结束附近各录一次可见/可听拍手或击板，另行检测两个事件的音频峰值与视频变化时刻。
5. 只有两次事件都可定位，才估计起始 offset 与随时间变化；容器 start/end/duration 差只能作为诊断，不得冒充 drift。
6. 多轨、缺 PTS、扫描截断、断流或重连均进入 Review，不手工修改时间轴后宣称同步。
