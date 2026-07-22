# V1-R1 G4 Open Images 静态居家人物检测压力集

状态：Implemented revision r2；等待修正提交上的 L40 三模型正式运行

基准日期：2026-07-22

## 1. 目标与边界

本切片补一条严格独立的静态人物检测压力链路，用来回答两个有限问题：

1. 在人工复核且带 Open Images 人工验证负标签的室内家具、宠物图片上，姿态后端是否错误激活人物框；
2. 在有穷举 Person 框的室内多人图片上，各后端能否以固定 IoU 门匹配全部人物。

它不是视频回放，不把单张图片复制成伪视频，也不运行 tracking、运动特征或跌倒规则。结果不能解释为跌倒误报率、事件召回率、床上躺卧识别、宠物运动鲁棒性或 C6c 域内表现，并固定不生成 `RiskAssessment` 或 `Alert`。

## 2. 数据源决定

采用 [Open Images V7 数据说明](https://storage.googleapis.com/openimages/web/factsfigures_v7.html)与[官方下载页](https://storage.googleapis.com/openimages/web/download_v7.html)的 validation split。选择理由是：validation/test 提供人工验证的图像级正负标签；可用正类在 validation/test 上提供穷举框标注；因此 Person 负标签可用于静态 false activation 计数，Person 正标签与框可用于多人匹配。

本轮同时审阅但未采用：

| 候选 | 有用信息 | 本轮决定 |
|---|---|---|
| [UP-Fall 官方数据页](https://sites.google.com/up.edu.mx/har-up/)与[论文](https://www.mdpi.com/1424-8220/19/9/1988) | 17 名健康青年、11 类活动、双摄像头，含躺卧与 5 类跌倒 | Defer；受控实验室人群/背景与目标老人居家域仍有明显差异，完整数据量很大，且本轮检查未找到足以冻结到逐文件清单的数据像素许可证 |
| [EDF/OCCU Zenodo 记录](https://zenodo.org/records/15494102) | 躺卧、家具遮挡方向与目标缺口接近 | Defer；记录规模约 26.9 GB，本轮检查未看到明确可冻结的 license 字段，不在许可证不清时下载或转入仓库资产 |
| [CAUCAFall V5](https://data.mendeley.com/datasets/7w7fccy7ky/5) | 延续现有 ADL/跌倒视频来源 | 不静默升级；仓库现有回归绑定 V4，且 V5 仍不能直接补齐带可靠人物负标签的家具/宠物和静态多人框门 |

后续若重开以上来源，必须新建 source manifest revision，不能把新版本混入本套 12 case 或改写既有 CAUCAFall V4 证据。

## 3. 许可证与逐图审计

Open Images 页面列出的标注由 Google LLC 以 CC BY 4.0 提供，下载页列出的图片为 CC BY 2.0；同时官方明确不保证每张图片的许可证状态，要求使用者自行核验。为此准备链路采用双层 fail-closed：

1. 标注归因固定为 `Open Images annotations by Google LLC`、`CC-BY-4.0` 和许可证 URL；
2. 每张图固定原始 Flickr landing page、作者、标题、作者页、`CC-BY-2.0` URL，并记录 2026-07-22 对原页面精确许可证链接的检查；
3. `attribution.json` 明确声明图片从 CVDF validation 下载源逐字节复制、未做改动；
4. 任一 landing page、作者、标题、license link、源字节数或 SHA-256 漂移即拒绝准备或评测；
5. 比赛提交、演示媒体展示或再分发前必须逐图重新审计，当前检查不能永久替代交付时审计。

源清单位于 `configs/v1-g4-openimages-static-home-negative.json`，suite ID 为 `v1-g4-openimages-static-home-negative-12-r2`，SHA-256 为 `434126ff0919dabed9ee40d702d71993fd8b5866d6c46162fa1441c8c2acfcd0`。

## 4. 固定选择

| 场景 | Case 数 | 真值 |
|---|---:|---|
| `person_absent_furniture` | 4 | Person 人工验证负标签；床、椅、沙发等上下文正标签；人工确认画面无人 |
| `person_absent_pet` | 4 | Person 人工验证负标签；Cat/Dog 正标签；人工确认画面无人 |
| `multi_person_indoor` | 4 | Person 人工验证正标签；2～4 个 validation Person 框；人工确认可见多人 |

12 张图均为 Open Images validation、零旋转、唯一 image ID、唯一像素摘要。多人子集的总 Person 真值框数为 11。选择过程是一次人工视觉筛选，不是双人一致性标注；它只减少明显的场景错配，不能消除 Open Images 标注遗漏、训练集重叠或选择偏差。

首轮 r1 在 job `1765` 后进行困难 case 视觉复核，发现 `oi-multi-wheelchair-occlusion` 有一个明显可见人物未被 Person 框覆盖，会把模型的正确检出误计为 FP。该 run 被拒绝作为正式指标，图片也未通过修正版的“可见人数等于框数 + 框逐一视觉对齐”门。r2 用两名远距离人物与两个框一致的室内会议室图片替换它；两版以不同 suite ID 和 source digest 隔离，不能合并统计。

## 5. 准备链路与确定性产物

```text
frozen source manifest
        │
        ├── 4 个官方 provenance CSV
        ├── 12 张官方 validation JPEG
        ├── size / SHA-256 / dimensions / rotation 校验
        ├── Person 人工验证标签与 validation boxes 交叉核对
        ├── 上下文标签、逐图归因与人工 review 交叉核对
        └── static-home-cases.json + attribution.json + dataset-lock.json
```

准备命令：

```bash
make PYTHON=.venv/bin/python prepare-g4-static-home
```

连续两次准备得到完全相同的产物摘要：

| 产物 | SHA-256 |
|---|---|
| `static-home-cases.json` | `e62b34dbf093253e240bf780a85105caaf0ade09e722415a85136ba330340470` |
| `attribution.json` | `fbcbec44f0276e09f6567d2c00d5c4cae0a9529de59ebf8e6e10c4f072e55efd` |
| `dataset-lock.json` | `7568e4b8c49f4e8629a151c9dd05d2ff67ff08a030b1e84ec16bfa8c647b3f94` |

`data/raw` 与 `data/processed` 均不入 Git；Git 只保存冻结清单、准备器、契约、测试和说明。

## 6. 评测链路与指标

```text
static-home-cases.json
        │
        ├── YOLO26n-pose ──────────────────┐
        ├── YOLOX-m + RTMPose-m ───────────┤  tracking=false；每图只推理一次
        └── Keypoint R-CNN ─────────────────┘
                           │
                           ├── person-absent：所有预测框计 FP
                           ├── multi-person：IoU >= 0.5 贪心一对一匹配
                           └── child case counts → parent variant/scenario 汇总
```

三条路线沿用现有冻结权重、输入尺寸和检测阈值，不为本 12 图调参。固定指标包括：

- box-level matched / FP / FN、precision、recall；
- 8 个 person-absent case 的 false-activation case 数与比例；
- 4 个多人 case 中至少检出一人、全部真值人物均被匹配的 case 数；
- 单图推理耗时与 variant 聚合耗时。

`StaticHomeImageCase` 冻结图片摘要、场景和真值框；`StaticHomeCaseEvaluation` 只保存计数、平均置信度、平均 matched IoU 和耗时；`StaticHomeGroupMetrics`、`StaticHomeVariantReport`、`StaticHomeBenchmarkReport` 负责场景与父级汇总。parent/child report 均不持久化预测框或绝对路径，原始图片只作为被 Git 忽略的 child SourceAsset。

## 7. 运行与验收门

```bash
kangshield-info benchmark-static-home \
  data/processed/v1-g4-openimages-static-home/static-home-cases.json

make submit-g4-static-home-benchmark
```

正式 E1 子门要求：

1. 12 张图片、4 个 provenance CSV、suite、attribution 和 lock 全部通过摘要及契约检查，二次准备不漂移；
2. 三个 variant 在同一干净提交、NVIDIA L40、完整 12 case 上完成，parent + 36 child 都为 clean / E1 / completed；
3. `tracking_enabled=false`，没有把静态图片重复成时间序列；
4. parent/case report 不含预测坐标、本地绝对路径或逐图许可证个人信息；
5. parent、variant 和 36 个 child 的 `risk_assessment_emitted`、`alert_emitted` 均为 false；
6. 报告只写“静态人物检测压力”，不写跌倒、时序事件或 C6c 能力已验收。

正式结果完成后记录到 `docs/reports/v1-g4-openimages-static-home-stress.md` 和 REV-015。

## 8. 仍未关闭

1. C6c 白天/夜视、距离、俯仰角、遮挡和室内域偏移；
2. 视频中的真实空场持续误触发、宠物移动、人物进出、多人 tracking 与身份切换；
3. 床上躺卧、坐地/弯腰、跌倒正样本及事件起点；
4. 事件级 false activation、recall、检测延迟、持续时间和人工确认闭环；
5. Open Images 与姿态模型训练数据的样本重叠审计；
6. 最终模型权重、数据和比赛提交物的许可证/NOTICE Review。
