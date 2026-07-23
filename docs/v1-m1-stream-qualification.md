# V1-M1 重复开流资格门

状态：Implemented E1 v0.1.0；C6c / RTSP E2 与故障网络矩阵仍 Open

基准日期：2026-07-23

## 1. 目的与设计决定

单次 `capture-stream` 只能证明一次有界媒体接收。真实 C6c 采集前还需确认：同一 endpoint 能否重复建立连接、每次是否都得到可用于同容器 Pipeline 的媒体、轨道格式是否漂移。

V1 不在一个媒体文件中静默重连或拼接断点。`qualify-stream` 将每次连接保存成独立 raw artifact、独立 `StreamCaptureReport`，再生成只含安全摘要的父级 `StreamQualificationReport`：

```text
endpoint（仅进程环境）
  ├─ independent open 001 -> bounded A/V artifact 001 -> capture report 001
  ├─ independent open 002 -> bounded A/V artifact 002 -> capture report 002
  └─ independent open 003 -> bounded A/V artifact 003 -> capture report 003
                                      |
                                      v
           count + requested readiness + track signature consistency
                                      |
                                      v
                    StreamQualificationReport
```

这样可以保留每个连接的来源、摘要和失败边界，避免把跨连接时间轴伪装成连续设备时钟。

## 2. 命令

```text
kangshield-info qualify-stream
  [--endpoint-env KANG_STREAM_ENDPOINT]
  [--attempt-count 3]
  [capture-stream 的 evidence/source/device/duration/timeout/packet/transport 参数]
  [--allow-video-only]
  [--require-ready]
```

真实网络流示例：

```bash
read -rsp 'Stream endpoint: ' KANG_STREAM_ENDPOINT
printf '\n'
export KANG_STREAM_ENDPOINT

kangshield-info qualify-stream \
  --source-type network_stream \
  --evidence-level E2 \
  --device-ref c6c_demo_01 \
  --attempt-count 3 \
  --duration-s 10 \
  --minimum-duration-s 8 \
  --transport tcp \
  --require-ready

unset KANG_STREAM_ENDPOINT
```

端点值、摘要、变量名和 PyAV/FFmpeg 原生日志都不进入产物。含凭据 URL 不得写入 shell 历史、Slurm 脚本、配置或聊天记录。

## 3. 运行边界

- `attempt_count` 允许 2～20，默认 3；每次完整复用单次采集的 open/read timeout、媒体时长、wall-time 和 packet 上限。
- 每次尝试都会关闭旧 container，再独立打开 endpoint；尝试之间不复用 decoder、packet 或时间轴。
- 成功但不满足请求 readiness 的尝试保存为 `captured_not_ready`；预期流错误保存为 `failed` 并继续下一次。
- 非预期内部错误仍使整个 run failed，不被资格报告吞掉。
- 资格 run 完成但 gate=false 是合法审计结果；只有 `--require-ready` 才在报告落盘后返回 2。

## 4. 失败码与隐私

父报告只允许固定、无路径的失败码：

- `open_failed`、`remux_failed`、`output_verification_failed`；
- 视频/音频轨道布局错误；
- required audio 缺失；
- packet 时间戳、视频关键帧、视频/音频 packet 或媒体 artifact 缺失；
- 未在 allowlist 的内部错误统一降级为 `stream_capture_failed`。

异常 message、endpoint 和底层日志不进入父报告。失败尝试不能引用 artifact；路径契约只接受 `artifacts/*.mkv` 和 `reports/*.json`，拒绝绝对路径、反斜杠与父目录跳转。

## 5. 轨道签名

每次成功采集发布 path-free 轨道签名：

| 轨道 | 一致性字段 |
|---|---|
| 视频 | stream type、codec、time base、宽、高、pixel format、average rate |
| 音频 | stream type、codec、time base、sample rate、channels、channel layout |

只比较 codec/time base 会漏掉清晰度、帧率或音频格式漂移，因此不能作为资格门。坐标、完整 metadata、源路径和身份信息不进入签名。

## 6. Gate 语义

`repeated_capture_gate_ready=true` 必须同时满足：

1. 所有请求尝试都完成，没有 failed 或 captured-not-ready；
2. 默认音频模式下，每次 `same_container_multimodal_ready=true`；video-only 模式则检查 `capture_artifact_ready`；
3. 每次都有轨道签名，且全部签名完全一致；
4. unique track signature 数恰好为 1。

`scheduled_reopen_sequence_proven=true` 只要求至少两次尝试 ready，用于表达“计划性关闭后可以再次打开”。以下字段固定为 false：

- `involuntary_disconnect_recovery_proven`；
- `long_running_stability_proven`；
- `network_impairment_tolerance_proven`；
- `device_platform_integration_proven`；
- `m2c_capture_bundle_ready`、RiskAssessment 和 Alert。

因此 gate 通过不会关闭断流恢复、鉴权刷新、丢包/抖动、长稳、萤石平台或 M2c 数据治理门。

## 7. 产物

```text
runs/<qualification-run>/
├── manifest.json
├── source_assets.jsonl
├── observations.jsonl
├── artifacts/
│   ├── stream-capture-001.mkv
│   ├── stream-capture-002.mkv
│   └── stream-capture-003.mkv
└── reports/
    ├── stream-capture-001.json
    ├── stream-capture-002.json
    ├── stream-capture-003.json
    └── stream-qualification.json
```

每个 raw artifact 都是独立 SourceAsset；即使媒体内容相同，Matroska 容器字节摘要也不要求相同。run/子目录固定 `0700`，媒体、JSON 和 JSONL 固定 `0600`。

## 8. E1 结论与下一门

clean `c8bda16` 的三次 loopback HTTP 资格运行全部 ready，完整结果见[正式 E1 报告](reports/v1-m1-stream-qualification-smoke.md)。它关闭的是工具、重复开流和格式漂移检测接缝；下一步仍是：

1. 用 C6c 的真实 endpoint 执行短 E2 TCP 资格门；
2. 分别记录有效鉴权、无权限、过期凭据和无音轨结果；
3. 用受控代理或网络仿真执行 stall、断流、丢包、抖动与恢复矩阵；
4. 执行至少 30～60 分钟长稳，不用三段短 clip 外推；
5. 通过后再按 C01～C12、双同步事件和同意/留存规程采集 M2c 包。
