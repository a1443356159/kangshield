# V1-M2c 采集包就绪门初测报告

状态：Accepted for E1 tooling slice；V1-M2c remains In progress

日期：2026-07-22

正式运行：`20260722T131022Z-9e3b47dc`

代码：`6f1c02a`，`code_dirty=false`

## 1. 结论

采集包 strict schema、C01～C10 场景/标注、媒体摘要/轨道、双同步事件、三模型 held-out 策略和 SDNL1 文件引用已经在一条 CLI 中打通。10 个合成 clip 均为“结构可用”，策略和文件检查 0 error / 0 warning。

最终决定正确保持为 `tooling_only` / `partial`：

| 门 | 结果 |
|---|---:|
| `structurally_usable_clip_count` | 10 / 10 |
| `synchronized_usable_clip_count` | 1 |
| 核心覆盖缺口 | 0 |
| C01～C10 矩阵缺口 | 0 |
| 三模型策略验证 | 3 / 3，variant/digest 匹配 |
| 睡眠文件摘要验证 | 1 / 1 |
| `camera_ready_for_model_retest` | false |
| `camera_matrix_complete` | false |
| `sleep_sample_ready_for_profiling` | false |
| `capture_bundle_ready_for_review` | false |

这些 false 不是失败遗漏，而是 E1 synthetic 输入必须保持的证据边界。本报告没有使用 C6c、SDNL1、真实参与者或真实同意文件。

## 2. 输入与 provenance

| 项 | 值 |
|---|---|
| E1 capture manifest | `d70a26f98a64f567c89ebb55dd19f46a4c40c49630a1b66c3df0a26a22608d6b` |
| Capture policy | `6c4fa5f4aa87fe2cb250c9645afff16f983271f4907fc293175fb0b224043384` |
| 共享 AVI bytes / SHA-256 | 66,044 / `0b3bd01c83cc138780b4f3fd809798413ba8885f5ee0770a467a3bac17f24672` |
| 正式 manifest SHA-256 | `a8f8145036984f269f469a186ec45c200fd281c757223a99030c4701a159c246` |
| Readiness report SHA-256 | `2bd9595a4bad8b23331f1cc7ed2955fec0d5d254530e9c0548cdf274a9d5958d` |
| Run status | completed，E1，fixture，444 ms |

合成包故意把同一个确定性 AVI 复制到十个场景路径，所以 `duplicate_media_content_count=9`。`synthetic=true` 时仅用于覆盖代码分支；真实 manifest 中任何跨 clip 重复摘要都会阻断真机门。

## 3. 覆盖结果

结构门观察到：

- C01～C10 全部存在，媒体 SHA-256/字节数与 manifest 一致。
- 每个容器均有 FFV1 视频与 PCM S16LE 音频轨，媒体探针为 pass。
- 白天/夜视、空场/人物、远距、弯腰、床上横卧、夜视横卧、家具遮挡核心 tag 均覆盖。
- person-present 场景具备 `person_present` 和 policy 要求的动作标签；两个空场场景无人物窗口。
- C02 包含开始/结束两个 fixture 同步事件，人工计算接缝输出 start offset 0 ms、end offset 0 ms、drift 0 ms/min。
- held-out 分区早于采集，标签晚于采集，首次推理仍为空；YOLO、RTMPose、Keypoint R-CNN 三个 variant 与冻结策略摘要一致。

上述动作标签只验证 manifest 结构。十段媒体实际是同一段无人合成图像，不能据此声称动作内容、标注准确率、姿态覆盖或音视频真机同步通过。

## 4. Fail-closed 回归

自动化覆盖四类关键边界：

1. E1 全结构通过仍只能得到 `tooling_only`，四个真机布尔量保持 false。
2. `../` 路径越出采集包时对应 clip 结构不可用，报告不回显私有文件名。
3. 媒体摘要被篡改时该 clip 不计入结构可用数。
4. 只有移除 fixture marker、使用 E2 非 fixture、唯一媒体摘要、真实采集方法和人工同步方法后，完整测试包才能打开 `capture_bundle_ready_for_review` 逻辑分支。

全仓回归为 70 passed，`pip check` 无 broken requirements，`git diff --check` 通过。

## 5. 隐私检查

正式 run 不持久化输入路径；source URI 使用摘要化 asset 名。对 run 目录扫描以下 fixture 私有/敏感标记均为 0 命中：operator/participant ref、原始 clip 文件名、`data/raw`、本地绝对路径、睡眠 fixture 中的姓名和设备序列号。

Readiness report 明示：

```text
raw_paths_persisted=false
identity_refs_persisted=false
annotation_windows_persisted=false
health_values_persisted=false
```

每个 clip 只发布 scenario ID、opaque ref、摘要匹配、轨道状态、标签集合/数量和同步派生值。原始标注起止时刻、同意内容、设备 ref、operator/participant ref 和睡眠值均不复制。

## 6. Review 决定

1. 接受 `M2cCaptureReadinessReport`、manifest 1.1、场景 policy 和 `assess-m2c-capture` 作为真实数据到达前的 V1-M2c 执行入口。
2. 接受“摄像头核心复测门”和“完整采集包 Review 门”分离；至少 8 个核心 clip 可以先开始模型复测，但不能替代 C01～C10 与 SDNL1 完整采集门。采集包门也不替代三模型/语言/睡眠字段报告或整个 M2c 里程碑。
3. 接受三姿态 variant ID + policy digest 的 held-out 绑定；目标集上禁止重新选择阈值后回写首次结果。
4. 接受双事件人工 offset/drift 作为容器 PTS 探针之后的下一层证据；不把 fixture 的 0 ms 外推到 C6c。
5. V1-M2c 与 V1-R1 保持 In progress；两台设备能力等级不因本 E1 结果提升。

## 7. 下一步

1. 复制 manifest 模板和三模型策略到受控目录，在任何 C6c 推理前冻结分区。
2. 按 C01～C10 采集，先达到 8 个核心可用 clip，即可在不等待睡眠字段语义的情况下启动三模型/FunASR 复测。
3. 对至少一段原始同容器媒体人工定位两次拍手/击板，保存真实 offset/drift。
4. 获取 SDNL1 真实导出并依次运行采集包 gate、`profile-sleep` 与 `assess-sleep-route`。
