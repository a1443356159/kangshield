# V1-M1 信息侧初步开发报告

日期：2026-07-22

结论：离线采集骨架通过；真实设备能力尚未验证。

## 1. 实现范围

- Pydantic 公共契约：SourceAsset、Observation、FeatureEvent、RunManifest。
- RunArtifacts：原子 JSON、JSONL、步骤状态、代码版本、失败留痕。
- probe-media：文件事实、WAV、OpenCV 视频元数据与抽样图像质量。
- profile-sleep：JSON/CSV 字段发现、敏感字段标记、标准字段候选。
- inspect-ezviz：SDK/API JSON 快照脱敏、设备型号和 capability 字段发现。
- Evidence guard：阻止 Fixture 或普通导出夸大证据等级。
- CLI、Synthetic Fixture、示例睡眠字段映射。

## 2. 自动化验证

```text
PYTHONPATH=src python3 -m pytest -q
...........                                                              [100%]
11 passed
```

覆盖：

- 完成与失败 RunManifest。
- WAV 技术元数据。
- OpenCV 合成视频技术元数据与抽样帧。
- 未知文件显式降级。
- 睡眠 JSON/CSV 字段发现。
- Fixture 证据等级上限。
- 萤石快照型号发现与敏感信息脱敏。
- CLI 完整运行目录。

## 3. 手工命令验证

使用临时目录执行：

1. 一秒 16 kHz 单声道 WAV。
2. 64×48、10 FPS、MJPG 合成 AVI。
3. CS-EP-SDNL1 Synthetic Fixture。
4. C6c/睡眠仪 Synthetic 萤石设备快照。

结果：

- 四次运行 manifest 均为 completed。
- WAV：audio、16 kHz、1 channel、1.0 s、quality=pass。
- AVI：64×48、10 FPS、10 frames、5 个抽样帧。
- AVI 音轨状态：not_inspected_by_opencv。
- 睡眠：2 records、4 fields、3 个映射候选。
- 萤石：发现两个目标型号，但所有功能项仍要求 functional test。

## 4. 隐私检查

对临时运行目录的 JSON/JSONL 进行字符串扫描，以下内容均未出现：

- Synthetic accessToken。
- Synthetic 摄像头序列号。
- Synthetic 设备名称。
- Synthetic 人员姓名。

SourceAsset URI 使用内容摘要，不保留原始文件名。

## 5. 当前不能证明的能力

本报告没有证明：

- C6c 真实设备列表、直播、回放、抓图或告警已接通。
- C6c 媒体包含可取得的音轨。
- CS-EP-SDNL1 向开发者开放任何睡眠或生命体征字段。
- MediaPipe、YOLO、FunASR 等模型已在目标设备数据上运行。
- 任何跌倒、认知、抑郁或诈骗风险精度。

这些项目必须使用 E2/E3 真实证据继续推进。
