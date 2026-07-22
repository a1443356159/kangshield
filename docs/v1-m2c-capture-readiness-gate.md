# V1-M2c 采集包、标注与 Held-out 就绪门

状态：Accepted for E1 tooling slice；真实 C6c/SDNL1 证据仍 Open

基准日期：2026-07-22

目标设备：CS-C6c-V101-1J4WF、CS-EP-SDNL1

## 1. 目标与边界

本模块把[目标设备采集规程](v1-m2c-device-sample-protocol.md)从人工清单变成可执行契约。真实文件到达后，同一条命令完成：

1. 检查采集包内引用是否越界、缺失或被替换。
2. 调用既有媒体探针检查视频/音频轨道、解码、PTS/DTS 和时长。
3. 检查 C01～C12 场景元数据、person-presence、动作区间和安全条件。
4. 用开始/结束两个同步事件计算人工复核的音视频 offset 与每分钟 drift。
5. 确认 held-out 分区、标签和三姿态 variant 的策略在首次推理前冻结。
6. 只输出脱敏就绪报告，不复制身份、原始路径、标注时间窗或睡眠值。

本模块不检查视频画面是否真的发生了 manifest 声称的动作，也不运行姿态、ASR、跌倒判断或告警。动作标签仍须双人或抽样人工 Review。E1 合成采集包可证明工具链完整，但不能证明目标设备或场景数据有效。

## 2. 两级门控

为兼顾快速推进和证据边界，报告分成两个层级：

| 层级 | 必须满足 | 允许的下一步 |
|---|---|---|
| `camera_ready_for_model_retest` | 非 fixture 的 E2+；真实同意与 C6c 能力快照；至少 8 个结构可用 clip；核心白天/夜视、空场/人物、远距、弯腰、床上横卧、夜视横卧和家具遮挡覆盖；至少 1 个双同步事件 clip；媒体不重复；三模型策略摘要匹配 | 按冻结参数运行三姿态 variant 和 FunASR，不在该集调阈值 |
| `capture_bundle_ready_for_review` | 上述门通过；C01～C10 全矩阵结构可用；至少 1 份真实 SDNL1 导出及能力快照通过摘要检查 | 采集包可以申请数据 Review 并交给完整下游评测；不代表 V1-M2c 里程碑完成 |

`camera_matrix_complete` 与 `sleep_sample_ready_for_profiling` 单独发布，避免把“摄像头可以复测”“睡眠文件可以做字段 profile”和“M2c 完整验收”合成一个状态。

决策枚举：

- `tooling_only`：E1、fixture、template 或 synthetic，只证明结构工具。
- `not_ready`：核心采集、文件、轨道、标注或 held-out 门未通过。
- `camera_retest_ready_sleep_pending`：真实摄像头核心集可复测，睡眠样本或全矩阵未完成。
- `camera_retest_ready_matrix_incomplete`：摄像头可复测且睡眠样本可 profile，但 C01～C10 尚不完整。
- `capture_bundle_ready_for_review`：完整真实采集包门通过；下游模型、语言和睡眠字段报告仍是独立门。

## 3. 可执行架构

```text
受控采集目录
  ├── capture-manifest.json (schema 1.1)
  ├── consent/                只验证存在、大小和摘要
  ├── capabilities/           脱敏 C6c / SDNL1 快照
  ├── camera/                 原始容器，不先转码
  ├── sleep/                  API / SDK / App 原始导出
  └── policies/               推理前冻结的模型策略副本
          │
          ▼
M2cCapture assessor
  ├── Pydantic strict schema + scenario policy
  ├── relative-path containment + SHA-256 + byte size
  ├── MediaProbe / ContainerTimingReport
  ├── annotation / synchronization / safety checks
  └── evidence + held-out + coverage gates
          │
          ▼
runs/<run_id>/
  ├── manifest.json
  ├── source_assets.jsonl / observations.jsonl
  └── reports/
      ├── m2c-media-probe-*.json
      └── m2c-capture-readiness.json
```

输入路径必须是规范化的 POSIX 相对路径；绝对路径、`..`、反斜杠和解析后越出采集根目录的符号链接均拒绝。报告只保存 opaque asset/capture/clip ref 和内容摘要，不回显被拒绝的路径。

## 4. Manifest 1.1

模板为 `configs/v1-m2c-capture-manifest.example.json`，实际文件保留在 Git 忽略目录。主要字段如下：

| 分组 | 必填事实 |
|---|---|
| 根信息 | `template_only`、`synthetic`、带时区采集区间、伪名化 operator/participant ref |
| 同意 | 相对引用、SHA-256、字节数；内容不进入报告 |
| 设备 | 伪名 device ref、精确型号、固件版本、采集方式、脱敏能力快照摘要 |
| 机位 | 高度、俯仰角、泛化房间区域、实际距离标记 |
| Held-out | 全 manifest 分区、分区冻结时间、标签冻结时间、首次推理时间和模型策略摘要 |
| Clip | 场景、光照/夜视、距离、遮挡、person-presence、原始文件摘要、媒体时间、轨道事实、标注窗口、同步事件和安全控制 |
| 睡眠导出 | 来源类型、文件摘要、请求/覆盖时间、时区、文档版本、已知单位和问题 |

时间顺序强制为：

```text
partition_frozen_at
    <= captured_start_at < captured_end_at
    <= labels_frozen_at <= first_inference_at（若已有首次推理）
```

这只能防止 manifest 明示的事后划分，不能替代采集团队的过程审计。真实采集前应先复制模板与策略，填入分区冻结时间；采集结束并完成人工标签后再写 `labels_frozen_at`，之后才能第一次运行模型。

## 5. 场景与标注契约

冻结策略为 `configs/v1-m2c-capture-policy.json`。C01～C10 是完整 Review 矩阵，C11/C12 为条件允许时的安全模拟跌倒。每个 ID 固定 scenario、光照、夜视、距离、遮挡、person-presence 与必需标签；不能把另一个动作改名冒充该 ID。

动作窗口只允许以下离散标签：

```text
person_present, walking, turning, sit_down, stand_up,
bend_pick, bed_lie, bed_rise, furniture_occlusion,
simulated_fall, speech
```

- person-absent clip 必须为 0 人且没有人物/动作窗口。
- person-present clip 至少有 `person_present`，并包含该 scenario 的必需动作。
- 所有窗口必须落在媒体时长内；报告只保留标签集合与窗口数，不保留起止时刻。
- 模拟跌倒必须同时声明安全垫、保护人员和清场；条件不足就不采 C11/C12。
- operator 记录的断流、重试等问题保留为 warning，不静默删除该 clip；轨道、摘要或标注硬错误仍阻断结构可用状态。

## 6. 音视频同步

至少一个原始同容器 clip 必须有 `start` 与 `end` 两个可见/可听事件，并由真实采集人工定位：

```text
offset = audio_ms - video_ms
drift_ms_per_minute =
  (end_offset - start_offset) * 60000 / (end_video_ms - start_video_ms)
```

E1 fixture 可使用 `automatic_fixture`；非 synthetic manifest 使用该方法会失败。真实数据必须写 `manual_frame_and_waveform`。结果只表示该容器内两个物理事件的相对对齐，不证明设备 wall-clock 准确率。

## 7. 三模型 Held-out 冻结

当前策略逐项绑定：

| Variant | 策略 SHA-256 |
|---|---|
| `yolo26n-pose` | `b5b4bcbf908221c7057794962c2cfd37a2d728c6f6b98695efbe2be73d1deeed` |
| `rtmpose-m-humanart` | `b5b4bcbf908221c7057794962c2cfd37a2d728c6f6b98695efbe2be73d1deeed` |
| `torchvision-keypointrcnn` | `921883358f6f2b23f0760d9f9612213adb044f54c9ac3e6ae24c8225e186f8db` |

采集包必须包含策略副本，并同时满足相对路径、文件摘要和 variant-to-digest 绑定。只凑三个任意文件不能开启门。该 gate 只冻结复测输入，不改变 REV-013 的候选结论或权重分发状态。

## 8. 证据与隐私

- `fixture` 最高 E1；即使 10/10 clip 和所有摘要通过，父级真机就绪仍为 false。
- 非 fixture E2 才能打开文件采集门；API 能力是否达到 E3 仍由真实可复查调用另行判断。
- `template_only=true`、`synthetic=true`、synthetic acquisition 或 JSON 顶层 `fixture/synthetic=true` 均不能冒充真实采集。
- 真实 manifest 中跨 clip 重复媒体 SHA-256 会阻断，合成回归包才允许重复。
- 汇总契约固定 `raw_paths_persisted=false`、`identity_refs_persisted=false`、`annotation_windows_persisted=false`、`health_values_persisted=false`。
- schema 错误、路径越界和缺文件的 failed run 使用脱敏错误，不把 Pydantic 输入或本地路径写入 step error。

## 9. 使用方法

生成并评估 E1 回归包：

```bash
make PYTHON=.venv/bin/python prepare-m2c-capture-fixture
make PYTHON=.venv/bin/python assess-m2c-capture-fixture
```

评估真实受控包：

```bash
kangshield-info assess-m2c-capture \
  data/raw/v1-m2c/<capture_id>/capture-manifest.json \
  --policy configs/v1-m2c-capture-policy.json \
  --evidence-level E2 \
  --source-type local_file
```

自动化流程需要完整采集包 Review 门时增加 `--require-ready`；未通过时命令返回 2，但评估 run 仍是 completed，因为“完成评估且结论未就绪”不同于工具执行失败。该选项不检查下游模型报告，不能用作 V1-M2c 里程碑 Done gate。

## 10. 验收与剩余工作

确定性 E1 结果见[采集包就绪门初测报告](reports/v1-m2c-capture-readiness-smoke.md)。当前已关闭：strict schema、文件完整性、媒体探针编排、场景/标注、安全、双事件计算、三模型策略绑定、两级决策、隐私报告与回归测试。

仍未关闭：

1. C6c 原始媒体、真实能力快照和 E2 采集包。
2. 真实双事件人工定位及 offset/drift Review。
3. SDNL1 真实导出、字段 profile 与 confirmed mapping。
4. 三姿态 variant 和 FunASR 在 C6c held-out 集上的正式复测。
5. 双人一致性、裁决和事件级误触发/检出延迟的 E1 工具口径已由 [G4 事件评估就绪门](v1-g4-event-evaluation-readiness.md)关闭；真实标注内容抽查、真实候选策略/指标和多人策略仍 Open。
