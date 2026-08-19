# C6c 取流、媒体时间基与长稳

状态：Active consolidated guide v1.0
更新时间：2026-08-09

本文合并有界取流、重复开流、故障矩阵、流会话和媒体时间基文档。特定历史运行结果仍保留在[证据索引](../evidence/README.md)。

## 1. 能回答什么

- `capture-stream`：一次真实来源能否生成独立、可解码、owner-only 的同容器音视频 artifact；
- `qualify-stream`：多个独立连接是否全部 ready，轨道签名是否一致；
- `probe-media`：video/audio track、codec、time base、PTS/DTS、包覆盖和扫描截断；
- `run-stream-session`：多个独立 segment 的 gap、失败 streak、外部重开和 wall/media 双门；
- `exercise-stream-faults/recovery`：E1 环境中的 stall、截断、503、reset 和 supervisor 状态机。

这些工具不证明平台级接入、同连接自动重连、packet-loss 容忍、物理声画同步、漂移或长期稳定；每项声明必须由对应真机证据单独打开。

## 2. 隐私和共同规则

- endpoint 只经环境变量读取；不得写入命令行、配置、日志、文档或聊天。
- 原始媒体与 runs 目录 owner-only，raw/目录权限分别保持 `0600/0700`。
- 每次连接生成独立 artifact，不在一个文件中静默拼接断点或修改时间轴。
- 默认要求一条视频轨和一条音频轨；只有纯视频指标才可显式 `--allow-video-only`。
- 失败只持久化固定错误码，不保存底层异常正文、URL、token、序列号或容器 metadata 值。

安全输入 endpoint：

```bash
read -rsp 'Stream endpoint: ' KANG_STREAM_ENDPOINT
printf '\n'
export KANG_STREAM_ENDPOINT
```

结束后立即执行：

```bash
unset KANG_STREAM_ENDPOINT
```

## 2.1 开放平台取地址与已知设备差异

直播地址每次会话现取（有过期时间）。`scripts/ezviz_live_endpoint.py` 从 `YS7_APP_KEY`/`YS7_APP_SECRET` 环境变量换 token 并打印 `protocol=4, quality=1, supportH265=1` 的 FLV 地址到 stdout，密钥与地址均不落盘：

```bash
export KANG_STREAM_ENDPOINT="$(
  .venv/bin/python scripts/ezviz_live_endpoint.py <deviceSerial>
)"
```

- 云端流未建立时拉流返回 404：先 `curl -r 0-1023` 预热一次（或在平台 App 看一眼画面）再 `capture-stream`。
- 揭榜挂帅/资源包设备需先按设备绑定激活码（`mall/device/package/code/active`，每设备一个码），否则地址可生成但拉流 404。
- 音频 codec 随设备而异：C6c 为 AAC 16 kHz；HK-Q1S4M 为 pcm_alaw 8 kHz，Matroska 无法直拷，取流时透明转码为 pcm_s16le 并在报告挂 `audio_track_transcoded_to_pcm_s16le`（契约字段 `output_codec_name` 记录落盘 codec）。

## 2.2 定时自动采集

`scripts/scheduled_capture.sh` 由系统 crontab 驱动（当前 `23 */2 * * *`）：每台设备取新地址、curl 预热、`capture-stream` 60 秒（内置 probe 质检），每台设备写一行无值状态到 `logs/scheduled_capture/status.jsonl`（ready、包数、音频 RMS——RMS 用于当场发现无声/异常录制）；凭证和设备列表均从 `secrets/ys7.env`（0600，gitignored）读取，设备列表格式为 `KANG_CAPTURE_DEVICES='serial:pseudonymous_ref ...'`，真实序列号不得写入脚本或文档；14 天前的 `stream-capture.mkv` 自动清理。冒烟用 `DURATION_S=10 bash scripts/scheduled_capture.sh`。调整节奏或停用用 `crontab -e`。

## 3. 短取流与资格门

```bash
kangshield-info capture-stream \
  --evidence-level E2 \
  --source-type network_stream \
  --device-ref c6c_demo_01 \
  --duration-s 30 \
  --minimum-duration-s 20 \
  --transport tcp \
  --require-ready

kangshield-info qualify-stream \
  --evidence-level E2 \
  --source-type network_stream \
  --device-ref c6c_demo_01 \
  --attempt-count 3 \
  --duration-s 10 \
  --minimum-duration-s 8 \
  --transport tcp \
  --require-ready
```

资格门要求所有尝试 ready，视频/音频 packet 与 PTS 可审计，输出 artifact 可解码，轨道类型、codec、宽高/fps、采样率/声道/time base 签名一致。一次或三次成功仍只属于短 E2，不等于长稳。

## 4. 媒体时间基

`probe-media --require-audio-track` 检查：

- container start/duration 与 video/audio stream 数；
- 每轨 codec、time base、声明 start/duration、packet 和 PTS/DTS 完整性；
- 首尾 PTS、负值、后退、跨度、相邻步长和扫描截断；
- `audio_minus_video_start_ms`、`audio_minus_video_end_ms` 与 duration delta。

容器首尾偏移不能替代物理同步或 drift。真实语音 clip 应在开始和结束附近各录一次可见/可听拍手或击板；只有两个事件的音频峰值与画面变化都可定位时，才可计算起始 offset 和随时间变化。

多轨、缺 PTS、扫描截断、断流或重连进入 Review。B-frame 可能导致合法的 demux PTS/DTS 重排，不能只凭一次后退计数判错。

## 5. 长稳会话

```bash
kangshield-info run-stream-session \
  --evidence-level E2 \
  --source-type network_stream \
  --device-ref c6c_demo_01 \
  --segment-count 31 \
  --duration-s 60 \
  --minimum-duration-s 50 \
  --minimum-session-wall-s 1800 \
  --minimum-ready-media-s 1800 \
  --failure-backoff-s 2 \
  --transport tcp \
  --require-ready
```

`minimum-session-wall-s` 和 `minimum-ready-media-s` 是独立验收条件，不是自动延长器。只有全部 segment ready、轨道签名一致，且 wall 与 ready media 均达到声明门，才能声明 segmented long-running stability。stall、gap、backoff 和 failed segment 不贡献有效媒体时长。

## 6. 受控故障

E1 固定覆盖完整响应、分块延迟、HTTP 503、首包/部分 body stall、截断和 TCP reset。工具门要求实际注入场景与预期状态/时限一致、partial 清理完成、报告无敏感信息。

受控恢复只证明 supervisor 能记录 `ready -> failed -> ready` 的三个独立 segment；不证明 RTSP 同连接 reconnect、packet loss/jitter 或目标设备容忍。真实升级顺序为短取流、三次资格、场景采集、双同步事件、31 × 60 秒长稳，最后才是非自愿网络故障试验。

## 7. 失败与退出语义

- `--require-ready` 在报告完整但 gate 未通过时返回 2；非预期内部错误才是 run failed。
- 常见固定原因包括 open/remux/output verification 失败、required audio missing、轨道布局错误、packet/PTS/关键帧缺失、时长不足和扫描截断。
- `captured_not_ready` 可以保留完整 artifact 供诊断，但不得贡献 readiness；failed segment 不得引用 raw artifact。
- 任何失败都不得通过手工改时间轴、覆盖原文件或删除失败记录变成成功证据。

## 8. 当前事实

C6c 已有 HEVC 2560×1440@15fps + AAC 16 kHz mono 短 E2，以及 3/3 独立开流一致性。真实夜视/远距/遮挡/多人、物理同步/漂移、31 × 60 秒长稳、非自愿断流和 packet loss 仍需补证据。
