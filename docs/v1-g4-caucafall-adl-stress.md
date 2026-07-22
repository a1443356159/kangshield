# V1-R1 G4 CAUCAFall ADL 负样本压力集

状态：Accepted for E1 public-data stress slice；真实设备 G4 仍 Open

基准日期：2026-07-22

## 1. 目标与非目标

本切片为 G4 增加一条独立的公开 ADL 压力链路，用于回答：在没有跌倒的弯腰、坐下、跪地和行走片段中，姿态覆盖、关键点质量门以及横卧/下降/低运动代理会怎样激活。

它不是跌倒分类 benchmark，不输出 RiskAssessment 或 Alert，也不把代理激活计作误报。数据只有 clip-level 动作标签，没有事件时间、人体框或关键点真值，因此只能形成 E1 工程压力证据。

## 2. 数据源选择

采用 [CAUCAFall V4](https://data.mendeley.com/datasets/7w7fccy7ky/4)，固定 DOI `10.17632/7w7fccy7ky.4` 和 `CC-BY-4.0`。官方版本包含 5 类跌倒和 5 类 ADL，逐动作目录提供 AVI、PNG 与 TXT；本切片只选明确的无跌倒 ADL 视频。

未采用的候选：

- [UP-Fall 官方页](https://sites.google.com/up.edu.mx/challenge-up-2019/data/datasets)明确说明图像文件不再公开，无法形成可重复视频准备链路；
- [NTU RGB+D 官方页](https://rose1.ntu.edu.sg/dataset/actionRecognition/)要求账号审批，并限制为学术非商业使用且禁止再分发/派生，不适合当前快速可重复切片；
- [E-FPDS 官方页](https://gram.web.uah.es/data/datasets/fpds/index.html)有床/沙发类场景价值，但当前页面没有找到足以冻结的明确数据许可证，因此 fail closed，不进入本轮下载清单。

## 3. 固定选择

来源清单位于 `configs/v1-g4-caucafall-negative-videos.json`，SHA-256 为 `3e173cef85b611fb038dc714592ee5350e9048313982b9ae3f17090816904b69`。

| 维度 | 固定值 |
|---|---|
| Subjects | subject-01、subject-06、subject-10 |
| Activities | pick up object、sit down、kneel、walk |
| Illumination | natural 约 210 lux、0 lux IR、artificial 约 130 lux |
| Cases | 3 × 4 = 12 个 AVI |
| Expected person | present |
| Ground truth scope | dataset action-level no-fall |

三个 subject 用于覆盖三种光照，而不是构造人口学比较。准备器要求完整 subject/activity 矩阵、动作名与光照绑定、Mendeley file ID/URL、字节数和 SHA-256 全部一致；任一漂移即失败。

当前集合明确不覆盖空房、纯家具、床上躺卧、宠物和多人，也不是目标老年人或 C6c 机位。这些缺口不能被 12 段 ADL 替代。

## 4. 准备链路

```text
frozen source manifest
        │
        ├── download official XLSX + 12 AVI
        ├── byte-size / SHA-256 fail-closed verification
        ├── unaltered AVI copy
        ├── OpenCV decode + width/height/FPS/frame count validation
        └── fall-adl-cases.json + dataset-lock.json
```

真实准备结果为 12 个 720×480、20 FPS 的 FMP4/AVI，时长 5.85～14.6 秒。准备两次得到相同产物摘要：

| 产物 | SHA-256 |
|---|---|
| `fall-adl-cases.json` | `37cf32e26361f679eb15528856e82e1014bc6e8c1257edcf9dea3079a0cf8277` |
| `dataset-lock.json` | `f8bb837c07bb354beacb3cc51013b42edd10e54432ea25abd1def565e7c2f4b8` |

## 5. 评测链路与隔离

```text
fall-adl-cases.json
        │
        ├── YOLO26n-pose + ByteTrack ─┐
        └── YOLOX-m + RTMPose-m + IoU ├── child video.pose_frame
                                      ├── FallMotionFeatureExtractor
                                      └── child fall case report

12 child reports × variant ──> parent aggregate by activity / illumination
```

参数继续使用 G4 冻结配置 `fall-motion-features-v0.1.0`：5 FPS、bbox 横卧比 `>=1.0`、下降/低运动时间窗、COCO-17 质量门和同 track 历史均不为本数据重新调参。

每个 variant/case 使用独立 child run。原始框与关键点只存在于被 Git 忽略的 child `features.jsonl`；child case report 和 parent report 只包含摘要计数、比例、时序代理和 digest。视频 SourceAsset 使用摘要 URI，显式标记 `contains_raw_media=true`、`source_path_persisted=false`。

## 6. 运行

```bash
make prepare-g4-caucafall

kangshield-info benchmark-fall-adl \
  data/processed/v1-g4-caucafall/fall-adl-cases.json

make submit-g4-adl-benchmark
```

计算节点只做离线模型校验和推理，不下载模型。YOLO 权重摘要必须是冻结值；HumanArt detector/pose 必须同时匹配当前模型 policy，artifact license 继续保持 `model-artifact-license-review-required`。

## 7. E1 验收门

1. 12 个源文件与元数据表逐项通过大小、SHA-256 和解码校验，lock 二次生成不漂移。
2. 两个 variant 在干净提交、L40、完整 12 case 上 completed，所有 child 与 parent 均为 E1。
3. 按 activity、illumination 和 case 报告 pose coverage、fallback、横卧最长持续、下降与低运动代理。
4. 所有 `video.fall_motion_frame` 的风险与告警字段为 false；父报告不含原始框、关键点或本地路径。
5. 横卧、下降或低运动代理出现时只做定位，不写成误报率、precision、recall 或告警性能。

正式结果见 [CAUCAFall ADL 压力报告](reports/v1-g4-caucafall-adl-stress.md)。

## 8. 仍未关闭

1. C6c 白天/夜视、距离、俯仰角、遮挡和安全模拟跌倒正样本。
2. 空房、纯家具、床上躺卧、宠物和真实多人负样本。
3. person-presence、动作区间、跌倒事件起点与 held-out 阈值冻结。
4. 多人身份策略、事件级误触发/检出延迟和人工确认闭环。
5. 非 HumanArt 训练路线候选和最终模型分发许可证。
