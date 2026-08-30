# 连续取流、异常归档与事件回看

状态：产品运行说明 v0.6
更新时间：2026-08-30

## 1. 媒体原则

- 正式产品连续处理直播流，不再按两小时落盘采集。
- 连续原始录像由摄像头云服务管理；本机不保存完整 60 秒段，只归档实际风险候选窗口。
- 每 60 秒形成一个逻辑审计段，视频帧、PCM 和关键窗口只存在于进程内存。
- 候选出现后，从仍在内存的 5 fps JPEG 与 16 kHz PCM 截取事件前 10 秒至后 20 秒，编码为带声音 H.264/AAC MP4。
- MP4 位于每人私有 `anomaly_clips/`，目录 `0700`、文件 `0600`，默认保留 30 天且每人最多 2 GiB；SQLite 只保存规范化相对路径、摘要、大小和到期时间。
- 临时直播地址、回放地址、token、应用密钥和设备序列号不得进入日志、SQLite 或报告。

## 2. 轻量关键窗口

`configs/v2-edge-segment-policy.json` 固定首版选择策略：

- 视频以 5 fps、最大宽度 640 px 的内存 JPEG 缓冲，使用缩略灰度帧差、median/MAD 和最小运动阈值选取窗口；每 10 秒保留一个个人基线帧。
- 音频在内存中转换为 16 kHz mono PCM，以 500 ms RMS、噪声底和活动阈值选择可能有人声的窗口。
- 视频和音频各最多选择原段的 50%，单个 ASR 窗口最长 15 秒。
- 轻量门只节省计算，不输出风险；未进入姿态或 ASR 的时间不能支持“无异常”的 0 分。

采集线程持续产生内存段，单工作线程复用模型。队列背压、断流、轨道错误、时间戳错误和模型失败都会写固定状态，不会被静默跳过。

## 3. 本机归档优先、云端回退

事件候选保存所属审计段和精确事件时间，不保存播放 URL。照护者点击“播放异常片段”时：

1. POST 请求通过 localhost、同源、CSRF 和 JSON 校验；
2. 后端确认候选属于当前目标设备，并检查其本机归档索引与文件大小；
3. 本机文件存在时，签发仅驻留内存 10 分钟的随机 URL；媒体路由只接受该令牌，支持 MP4 byte range，并设置同源资源策略；
4. 本机文件缺失时，才把事件前 10 秒至后 20 秒限制在审计段内，向萤石开放平台换取 HTTPS HLS 地址；
5. 浏览器在同一弹窗播放画面和声音，关闭后立即移除页面 URL。

本机 MP4 使用浏览器普遍支持的 H.264/AAC；若回退的 HLS 无法原生播放，页面提供新窗口降级入口。萤石跨浏览器 SDK 的许可证和自托管资源尚未通过发布门，因此当前不捆绑。云录像套餐、设备在线状态、账户权限和云端周期只影响回退能力。

public 导出不包含播放能力、归档索引、路径、candidate 或精确事件时间。删除本机个人数据会删除 SQLite 与 `anomaly_clips/`；不会删除云录像，两处仍需分别管理。由于异常 MP4 含敏感画面与声音，正式使用应启用磁盘加密并排除非受控备份。

## 4. 启动

`secrets/ys7.env` 必须为 Git ignored 的私密文件，建议权限 `0600`：

```bash
YS7_APP_KEY=...
YS7_APP_SECRET=...
KANG_DEVICE_SERIAL=...
KANG_ELDER_REF=elder_pseudonym
KANG_DEVICE_REF=c6c_target
KANGSHIELD_POSE_MODEL=/cache/DeepLearning/your-user/kangshield-models/yolo26s-pose.pt
```

完整产品：

```bash
scripts/run_product.sh
```

或直接运行：

```bash
kangshield-info serve-product \
  --elder-ref "$KANG_ELDER_REF" \
  --device-ref "$KANG_DEVICE_REF" \
  --host 127.0.0.1 \
  --port 8765 \
  --continuous \
  --pose-model "$KANGSHIELD_POSE_MODEL" \
  --edge-provider ezviz
```

仅分析、不启动看板时使用 `run-edge-monitor`。两种连续入口不能对同一设备同时运行。

本机异常归档默认启用。临时关闭时增加：

```bash
--no-local-anomaly-archive
```

## 5. 验收重点

- 真实目标设备的分段间隙、时间引用和云回放范围一致；
- 轻量门对跌倒、低运动异常和远场语音的召回不因节省计算而不可接受；
- 模型处理速度长期跟得上采集速度，背压率在 owner 批准范围内；
- 只有有 candidate 的窗口生成 MP4；不存在完整段、endpoint、token 或临时云回放 URL 落库；
- 到期和容量清理有效，归档索引与文件一致，删除个人数据后无残留；
- 模型不可用时三域降级明确，Web 服务仍可访问。
