# V1-M1 有界音视频流采集适配器

状态：Implemented E1 v0.1.0；真实 C6c / RTSP E2 门仍 Open

基准日期：2026-07-23

## 1. 目标与边界

本切片把“网络音视频流”接到已经验证的同容器多模态入口，形成以下设备无关链路：

```text
endpoint（仅进程环境）
  -> PyAV 有界打开/读取
  -> 等待首个视频关键帧
  -> codec-copy Matroska 原子落盘
  -> MediaProbe + ContainerTimingReport
  -> owner-only 同容器 artifact
  -> run-multimodal --audio-from-video
```

它解决的是采集 adapter seam，不解决以下问题：

- 不证明 CS-C6c-V101-1J4WF 的萤石平台权限、直播 URL 或麦克风音轨可得。
- 不证明 RTSP 长稳、鉴权刷新、断线重连、丢包、抖动或端到端延迟。
- 不把接收时刻解释成设备事件时刻，不由单段容器 PTS 推断真实 capture clock 或 drift。
- 不生成 RiskAssessment 或 Alert，也不改变 M2c 真机采集包与 held-out 门。

## 2. 命令接口

入口为：

```text
kangshield-info capture-stream
  [--endpoint-env KANG_STREAM_ENDPOINT]
  [--runs-dir runs]
  [--evidence-level E1|E2]
  [--source-type fixture|network_stream]
  [--device-ref <opaque-ref>]
  [--duration-s 10]
  [--minimum-duration-s 1]
  [--open-timeout-s 10]
  [--read-timeout-s 5]
  [--max-packets 200000]
  [--max-packets-per-stream 200000]
  [--transport auto|tcp|udp]
  [--allow-video-only]
  [--require-ready]
```

端点值只从 `--endpoint-env` 指定的环境变量读取；命令行参数、manifest、report 和应用日志均不保存端点值、端点摘要或环境变量名。默认要求单音轨；只有显式 `--allow-video-only` 才允许无音频输出，此时 `same_container_multimodal_ready` 必为 false。`tcp` / `udp` 只允许用于 RTSP(S)。

真实网络流的安全调用方式：

```bash
read -rsp 'Stream endpoint: ' KANG_STREAM_ENDPOINT
printf '\n'
export KANG_STREAM_ENDPOINT

kangshield-info capture-stream \
  --evidence-level E2 \
  --source-type network_stream \
  --device-ref c6c_demo_01 \
  --duration-s 30 \
  --minimum-duration-s 20 \
  --transport tcp \
  --require-ready

unset KANG_STREAM_ENDPOINT
```

不要把带用户名、密码、token 或签名的完整 URL 写进 shell 历史、配置文件、作业脚本或聊天记录。进程环境本身仍是敏感运行边界，操作者必须限制同机进程查看权限并在运行后立即 `unset`。

## 3. 证据等级

| 输入 | 允许的最高等级 | 额外要求 | 能证明什么 |
|---|---:|---|---|
| `fixture` + HTTP(S)/RTSP(S)/本地文件 | E1 | 不能提供真机声明 | 采集、落盘、探针和下游接口可执行 |
| `network_stream` + HTTP(S)/RTSP(S) | E2 | E2 必须提供 opaque `device_ref` | 一次真实来源的有界媒体被接收并保存 |
| 平台 SDK/API 能力调用 | 本命令不覆盖 | 另走能力快照与 E3 Review | 平台能力、权限与调用可重复性 |

`network_stream` 被公共契约限制为最高 E2。即使一次真实 RTSP 采集成功，`device_platform_integration_proven` 仍固定为 false；平台级 E3 必须另有脱敏能力调用、接口版本和重复运行证据。

## 4. 采集算法与失败语义

1. 校验协议、source/evidence 组合和参数；拒绝换行、NUL、未知协议与 HTTP 上的 RTSP transport 选项。
2. 使用 PyAV 的独立 open/read timeout 打开输入，只接受恰好一条视频轨和最多一条音轨；默认要求音轨存在。
3. 等待首个视频关键帧，关键帧前的音频与非关键视频包不写入输出，避免产出不可独立解码的开头。
4. 复制 packet 到 Matroska，不进行转码；清空容器与轨道 metadata。采集同时受媒体时长、wall time 和 packet 数三重上限约束。
5. 先写同目录随机 `.partial`，成功后以 `0600` 原子替换为 `artifacts/stream-capture.mkv`。
6. 对输出重新运行媒体与逐包时间戳探针。探针、报告或登记任一步失败，都删除未登记的原始媒体和 partial 文件。
7. 捕获并丢弃 PyAV/FFmpeg 原生日志；对外错误只保留阶段和异常类型，避免底层错误回显带凭据 URL。

`packet_limit` 与 `wall_time_limit` 属于非 clean termination，不能打开 readiness。流在达到目标时长前自然结束可以形成报告，但只有满足最短媒体跨度才可 ready。

实现中不得在输入容器关闭后访问 PyAV `Stream.codec_context` 等 FFmpeg-backed 对象；轨道类型与 codec 名必须在容器打开期间复制为纯 Python 值。该边界已由实际 native segfault 暴露并纳入回归测试。

## 5. 产物与契约

每次运行生成：

```text
runs/<run_id>/
├── manifest.json
├── source_assets.jsonl
├── observations.jsonl
├── artifacts/stream-capture.mkv
└── reports/stream-capture.json
```

run 根与子目录固定 `0700`，媒体、JSON 和 JSONL 固定 `0600`。`StreamCaptureReport` 记录：

- evidence/source、端点协议和 transport；
- 请求时长、最短时长、timeout、packet 上限与 termination reason；
- 检查/复制包数、首包关键帧状态和逐轨 codec/包数；
- 嵌套的 `MediaProbeReport` 与 `ContainerTimingReport`；
- `capture_artifact_ready`、`same_container_multimodal_ready`；
- 固定 false 的设备平台证明、风险和告警声明。

报告不记录端点、端点摘要、FFmpeg 原生日志、源文件路径或容器 metadata value。

## 6. Readiness 与退出码

`capture_artifact_ready=true` 必须同时满足：

- 媒体探针质量为 pass、恰好一条视频轨；
- 输出从视频关键帧开始；
- 媒体跨度达到 `minimum_duration_s`；
- termination 为 `duration_limit` 或 `end_of_stream`；
- 所有输出轨均有 packet、PTS 完整且 timing scan 未截断。

`same_container_multimodal_ready=true` 还要求：

- 恰好一条音轨，且音视频位于同一容器；
- audio-minus-video 起点 offset 可测且有限；
- 音频 PTS 没有逆序。

普通命令在成功写出完整但 not-ready 报告时返回 0；`--require-ready` 在报告落盘后返回 2。运行时异常返回非零，并执行失败清理。

## 7. 下游调用

ready artifact 可直接进入现有同容器路径：

```bash
kangshield-info run-multimodal \
  runs/<capture-run>/artifacts/stream-capture.mkv \
  --audio-from-video \
  --pose-model models/yolo26n-pose.pt \
  --offline-models
```

下游仍会独立复核唯一音视频轨、PTS 完整性和 timing scan。采集报告的 ready 不能绕过 Pipeline 自己的 fail-closed gate。

## 8. 隐私、同意与留存

该命令会真实持久化原始音视频，必须在运行前明确：采集同意、访问人、受控存储位置、留存期限和删除责任人。raw artifact 与敏感 FeatureEvent 均被 Git 忽略；禁止把它们复制进文档、issue、模型报告或比赛包。失败清理只处理本次尚未登记的 partial/raw 文件，不代替项目的数据到期删除流程。

## 9. 当前验收与下一门

E1 已完成 HTTP loopback、真实 PyAV remux、同容器探针和 L40 多模态消费，证据见[正式初测报告](reports/v1-m1-bounded-stream-capture-smoke.md)。下一门按顺序为：

1. 取得 C6c 的脱敏 RTSP/平台取流方式和麦克风音轨结论。
2. 运行一次短 E2 采集并核对原始 artifact、轨道与凭据扫描。
3. E1 先复用已通过的[受控故障矩阵](v1-m1-stream-fault-matrix.md)；真机再补鉴权失败、RTSP TCP/UDP、packet loss/jitter、timeout 与断线恢复 E2。
4. 按 M2c C01～C12 规程采集，保留开始/结束两次可见可听同步事件，计算真实 offset/drift。
5. 只有平台调用可重复且能力快照通过后，才单独申请 C6c E3。
