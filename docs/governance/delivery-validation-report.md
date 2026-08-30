# KangShield 公开数据集交付验证报告

更新日期：2026-08-31

当前状态：三域公开工程验证已完成；跌倒留出门未通过，诈骗与个人基线留出门通过
产品口径：`pilot_unvalidated`

## 1. 这份报告回答什么

本页是公开数据集测试的唯一人工报告，记录可复现输入、固定划分、策略绑定、调参过程、最终盲测与交付边界。机器可审计结果最终写入 `artifacts/validation/`，不提交视频、逐帧姿态、本地缓存路径或下载临时链接。

公开数据集只能证明工程链路在特定模拟样本上的表现，不能证明真实老人、目标 C6c、临床结局或商业发布性能。标签只在候选生成完成后用于计算指标，不进入规则判断。

## 2. 数据与隔离契约

| 数据 | 用途 | 固定划分 | 许可证与来源 |
|---|---|---|---|
| CAUCAFall v5 | 跌倒视频开发与一次性留出评估 | Subject 1–5 开发；Subject 6–10 留出 | [DOI 10.17632/7w7fccy7ky.5](https://doi.org/10.17632/7w7fccy7ky.5)，CC BY 4.0 |
| FBS Spam SMS Dataset | 中文诈骗语境规则的词法工程评估 | 样本引用 SHA-256 对 5 取模；bucket 0 留出，其余开发 | [官方仓库](https://github.com/Cypher-Z/FBS_SMS_Dataset)，固定提交 `49173b1`；上游要求引用来源与 CCS 2020 论文，未声明 SPDX 许可证 |
| CASAS Smart Home in a Box longitudinal data | 个人 28 天行为基线、缺数保护和规则响应评估 | hh101–hh103 开发；hh104–hh106 留出 | [DOI 10.5281/zenodo.15708568](https://doi.org/10.5281/zenodo.15708568)，CC BY 4.0 |

CAUCAFall 每位受试者包含 5 类模拟跌倒与 5 类日常活动，因此开发集和留出集各为 25 条跌倒、25 条日常活动。媒体仅缓存到 `/cache` 文件系统；下载后必须同时通过官方字节数和 SHA-256 校验。留出集在策略冻结前不得下载、查看、试跑或参与阈值选择。

三个来源各自只回答一个有限问题，不能互相替代。FBS 是短信而不是摄像头听到的语音或 ASR 输出；CASAS 是环境传感器而不是摄像头派生指标，也没有心理健康结局标签；月度 WHO-5 仍只由合成夹具和规则测试覆盖。

## 3. 指标定义

- 跌倒事件召回：产生至少一个待人工复核候选的跌倒视频数 / 跌倒视频总数。
- 日常活动片段误报率：产生至少一个跌倒候选的日常活动视频数 / 日常活动视频总数。
- 轻量门保留率：至少保留一个非基线运动窗口的跌倒视频数 / 跌倒视频总数。
- 送模比例：送入姿态模型的帧数 / 5 fps 筛查帧数；上限由策略固定。
- 首次检出时间：从活动视频起点到首个候选的时间，不是从真实跌倒起点计算的延迟。

候选级指标不是概率，也不等同于三域看板的 0–3 风险等级；正式等级仍由版本化三域规则、数据覆盖和人工复核共同决定。

冻结前预先声明 `caucafall-engineering-demo-gate-v1`：最终轻量路径跌倒召回至少 0.50、日常片段误报率不高于 0.10、跌倒运动门保留率至少 0.90、平均送模比例不高于 0.50、Slurm CPU 平均处理实时系数不高于 1.00，且相对完整帧参考的召回损失不高于 0.12。所有条件同时满足才记为公开数据集工程演示门通过；它不构成临床、目标设备或发布门。

## 4. 调参前开发集基线

运行日期：2026-08-31

样本：Subject 1–5，共 50 条
姿态模型：`yolo26n-pose.pt`，模型 SHA-256 `eb3bb8268828aeaf515cec23a4bfafd793944a86fe9af94ba7823609c14522a9`

| 路径 | 跌倒检出 | 跌倒事件召回 | 日常误报 | 日常片段误报率 | 平均送模比例 |
|---|---:|---:|---:|---:|---:|
| 原轻量门 | 0 / 25 | 0.00 | 0 / 25 | 0.00 | 0.048374 |
| 完整帧参考 | 6 / 25 | 0.24 | 0 / 25 | 0.00 | 1.000000 |

基线结论：原全局灰度均值阈值无法保留开发集中的跌倒运动；即使跳过轻量门，原 bbox-only 横向持续规则也遗漏多数样本。因此优化必须分别解决轻量选择和候选状态机，不能把完整帧结果当作轻量路径结果。

## 5. 开发集优化记录

| 轮次 | 主要变更 | 轻量路径跌倒 / ADL | 完整帧跌倒 / ADL | 决定 |
|---|---|---:|---:|---|
| D0 | 全局平均灰度帧差；bbox-only 横向代理；YOLO26n | 0/25；0/25 | 6/25；0/25 | 否决：运动门未保留跌倒 |
| D1 | 局部最高 10% 变化像素；bbox + COCO-17 躯干代理 | 7/25；1/25 | 8/25；1/25 | 保留局部运动门 |
| D2 | 姿态置信度 0.35 → 0.20 | 7/25；2/25 | 9/25；2/25 | 否决：无召回收益且误报增加 |
| D3 | YOLO26n → YOLO26s | 11/25；3/25 | 13/25；3/25 | 保留模型，继续收紧候选 |
| D4 | 增加 bbox/近地/恢复抑制与事件合并 | 12/25；0/25 | 15/25；1/25 | 保留候选状态机 |
| D5 | 运动峰值中心化选帧 | 10/25；1/25 | 15/25；1/25 | 否决：轻量召回下降 |
| D6 | 姿态输入 640 → 960 | 12/25；0/25 | 未运行 | 否决：无召回收益且计算增加 |
| D7 | 修正近地恢复语义并缩短近地确认时长 | 12/25；1/25 | 17/25；2/25 | 保留完整帧规则，轻量损失仍过大 |
| D8 | 严格 50% 向下取整；仅放宽候选帧间隔 | 12/25；1/25 | 未运行 | 否决参数；保留硬上限修复 |
| D9 | 特征历史与候选状态均容忍 650 ms 选帧间隔 | 13/25；1/25 | 未运行 | 保留：恢复 1 个跌倒，无新增误报 |
| D10 | 快速下降阈值 0.15 → 0.10，仍要求组合证据 | 14/25；1/25 | 待冻结重放 | 选中并停止调参 |

D0–D6 是操作方提出“不得在登录节点计算”之前的探索结果，不作为最终计算面证据；D7–D10 均由 Slurm 计算节点完成。每轮只使用 Subject 1–5，未按单个样本标签写特殊规则。

冻结时间为 `2026-08-30T18:12:50Z`，冻结提交为 `8ce592f`，冻结清单见 [`artifacts/validation/caucafall-policy-freeze.json`](../../artifacts/validation/caucafall-policy-freeze.json)。此时 Subject 6–10 媒体缓存为空。最终绑定为：

- edge `ef0568e5b27169a8b7ecd40e9662a054cf6ab222a43504d2eecd6a8725e54569`
- feature `e72052cec6107191899c43652a9dee14b8463f0f32b2ef4052b9202b00c400ae`
- candidate `d70c29687a84931d392fb1fe89f6333604f4d95caef586fd58409ea5d618670f`
- pose model `a083adb42303728ae14c4bd6bd56d80da46f82fb2564dbd6f31dcc92ea321646`

## 6. 冻结后的留出结果

冻结后先在 Subject 1–5 对冻结代码执行一次双路径重放，再只执行一次 Subject 6–10 基准。两次任务都由 Slurm 调度到 `hepnode3` 的 CPU 执行；登录节点未加载模型或运行批量推理。

| 划分与路径 | 跌倒检出 | 跌倒召回 | ADL 误报 | 运动门保留率 | 平均送模比例 | 平均实时系数 |
|---|---:|---:|---:|---:|---:|---:|
| 开发重放，轻量 | 14 / 25 | 0.56 | 1 / 25（0.04） | 1.00 | 0.495133 | 0.393402 |
| 开发重放，完整帧 | 17 / 25 | 0.68 | 2 / 25（0.08） | 不适用 | 1.000000 | 0.789060 |
| 留出盲测，轻量 | 17 / 25 | 0.68 | 4 / 25（0.16） | 0.88 | 0.457926 | 0.355654 |
| 留出盲测，完整帧 | 21 / 25 | 0.84 | 4 / 25（0.16） | 不适用 | 1.000000 | 0.770801 |

| 预注册条件 | 阈值 | 开发重放 | 留出盲测 |
|---|---:|---:|---:|
| 轻量跌倒召回 | ≥ 0.50 | 0.56，通过 | 0.68，通过 |
| ADL 片段误报率 | ≤ 0.10 | 0.04，通过 | 0.16，**未通过** |
| 跌倒运动门保留率 | ≥ 0.90 | 1.00，通过 | 0.88，**未通过** |
| 平均送模比例 | ≤ 0.50 | 0.495133，通过 | 0.457926，通过 |
| 平均处理实时系数 | ≤ 1.00 | 0.393402，通过 | 0.355654，通过 |
| 相对完整帧召回损失 | ≤ 0.12 | 0.12，通过 | 0.16，**未通过** |
| 总门结果 | 全部条件同时满足 | 通过 | **未通过** |

执行证据：开发重放为 Slurm job `2887`，状态 `COMPLETED/0:0`，用时 `00:09:21`；留出盲测为 job `2888`，状态 `COMPLETED/0:0`，用时 `00:10:37`。机器报告分别为 [`caucafall-dev.json`](../../artifacts/validation/caucafall-dev.json)（SHA-256 `5c5edaaffcb332696f9fb521c8ae0f6dfc1cd09c8a0e701573715138935c70a0`）与 [`caucafall-holdout.json`](../../artifacts/validation/caucafall-holdout.json)（SHA-256 `1a565ed74e41f116e63bd8ddb0689d09269f2a20c2c2314f189a6adb7529bcea`）。报告包含逐片段结果，但不包含本地缓存路径。

留出集未通过工程门后没有回看样本继续调参，也不会重复运行来挑选有利结果。当前冻结版保留为可审计基线；下一版若继续优化，必须先登记新策略和独立外部测试集，不能把这 50 条留出片段再次称为盲测集。

## 7. 可复现命令

登录节点只允许执行下载与哈希核验：

```bash
.venv/bin/python scripts/benchmark_caucafall.py \
  --split dev \
  --cache-root "/cache/DeepLearning/$USER/kangshield-public-data" \
  --accept-license CC-BY-4.0 \
  --prepare-only
```

姿态推理和批量基准只通过 Slurm 计算节点提交，日志和完整结果先写 `/cache`：

```bash
sbatch \
  --chdir="$PWD" \
  --output="/cache/DeepLearning/$USER/kangshield-validation/logs/caucafall-%j.out" \
  --error="/cache/DeepLearning/$USER/kangshield-validation/logs/caucafall-%j.err" \
  scripts/slurm/benchmark_caucafall.sbatch \
  --split dev \
  --mode both \
  --cache-root "/cache/DeepLearning/$USER/kangshield-public-data" \
  --output "/cache/DeepLearning/$USER/kangshield-validation/results/caucafall-dev.json" \
  --accept-license CC-BY-4.0 \
  --model "/cache/DeepLearning/$USER/kangshield-models/yolo26s-pose.pt" \
  --device cpu
```

冻结策略后将 `--split dev` 改为 `--split holdout`。脚本固定记录数据集 DOI/版本/许可证、受试者、官方媒体哈希、三份策略哈希、姿态模型绑定、逐片段结果、工程门和限制，不记录缓存路径。仓库只同步最终小型 JSON 报告，不同步媒体、权重或 Slurm 日志。

## 8. 诈骗语境与个人基线验证契约

FBS 验证器先对消息做 Unicode NFKC、大小写、空白和标点规范化，再调用产品正式规则；源标签只在规则输出完成后用于汇总。固定哈希划分不依赖文件顺序，开发集 10,424 条，留出集 2,604 条。指标是“源诈骗类别被规则标记率”和“源非诈骗类别被规则标记率”，不是摄像头对话中的召回率或误报率。后者仍由广告、博彩等垃圾或非法消息组成，并非普通居家对话。

CASAS 每个家庭独立构建自己的日级序列，提取日间 15 分钟活动 bin、运动事件量和源数据已有的睡眠起点代理；不跨家庭建立人群基线，也不使用住户身份。验证器检查三件事：少于 7 个合格日期时必须 `null`；达到 28 天窗口后能够持续给出规则评估；对预先构造的一个轻度、一个严重、两个严重和等级 2 连续三天变化，必须分别响应 1、2、3、3。构造变化只验证规则灵敏度，不代表住户存在心理问题。

冻结前声明两组工程门：

- `fbs-fraud-context-engineering-gate-v1`：至少 1,000 条消息，源诈骗类别标记率 ≥ 0.50，源非诈骗类别标记率 ≤ 0.15。
- `casas-personal-baseline-engineering-gate-v1`：每户至少 28 个合格日期，基线后可评估率 ≥ 0.90，无效行率 ≤ 0.001，基线不足全部 fail closed，四种受控变化全部符合预期等级。

## 9. 开发、冻结与一次性留出

诈骗开发初始基线对 10,424 条消息的源诈骗类别标记率为 0.327844，源非诈骗类别标记率为 0.103919。开发轮 D1 仅依据开发分区补充通用中文上下文并强化标点/空白混淆规范化，得到 0.599800 与 0.107720。CASAS 开发阶段修复公开 CSV 格式解析和受控响应的日历窗口后，hh101–hh103 最少有 54 个合格日期，基线后可评估率均为 1.0，基线前全部为 `null`，四种响应全部正确。

策略于 `2026-08-30T19:08:39Z` 冻结，提交为 `a30fd59`，冻结清单见 [`public-domains-policy-freeze.json`](../../artifacts/validation/public-domains-policy-freeze.json)。清单绑定正式三域策略、评分实现、验证器和 Slurm runner 的 SHA-256，并预先固定两个数据集的开发/留出分区和门槛。源压缩包物理上包含全部分区，因此隔离是程序化的；冻结前没有请求 holdout 分区结果，冻结后只允许运行一次。

| 域与划分 | 样本/家庭 | 主要指标 | 工程门 |
|---|---:|---|---|
| 诈骗开发 D1 | 10,424 条 | 源诈骗类别标记率 0.599800；源非诈骗类别标记率 0.107720 | 通过 |
| 诈骗留出 | 2,604 条 | 源诈骗类别标记率 0.536437；源非诈骗类别标记率 0.113744 | 通过 |
| 个人基线开发 | hh101–hh103 | 最少 54 个合格日期；基线后可评估率 1.0；无效行率 0.000002 | 通过 |
| 个人基线留出 | hh104–hh106 | 最少 36 个合格日期；基线后可评估率 1.0；无效行率 0 | 通过 |

唯一留出任务为 Slurm job `2909`，在 `hepnode3` 完成，状态 `COMPLETED/0:0`。结果生成后未修改正式策略、评分器或验证器。机器报告为 [`public-domains-dev.json`](../../artifacts/validation/public-domains-dev.json)（SHA-256 `265728ef2cea1c4bc8718a5c61fbd633526c0b9206b742fa0bb56599790faf12`）和 [`public-domains-holdout.json`](../../artifacts/validation/public-domains-holdout.json)（SHA-256 `997e29cff69ae2817647a8fad27b4675e49490c20dcf5cb866a8ffb13ce97b72`）；两份报告只保存聚合值与不可逆摘要，不含消息正文、时间戳、本地路径、老人或设备标识。

## 10. 诈骗与个人基线复现命令

公开源准备可在登录节点执行；解析、评分和基准只能提交给 Slurm 计算节点。缓存、日志与中间报告均写入 `/cache`：

```bash
sbatch \
  --chdir="$PWD" \
  --output="/cache/DeepLearning/$USER/kangshield-validation/logs/public-domains-%j.out" \
  --error="/cache/DeepLearning/$USER/kangshield-validation/logs/public-domains-%j.err" \
  scripts/slurm/benchmark_public_domains.sbatch \
  --split dev \
  --cache-root "/cache/DeepLearning/$USER/kangshield-public-data" \
  --output "/cache/DeepLearning/$USER/kangshield-validation/results/public-domains-dev.json" \
  --accept-fbs-source-terms \
  --accept-casas-license CC-BY-4.0 \
  --no-download
```

冻结后才可把 `--split dev` 改为 `--split holdout`；本次 holdout 已消耗，不能重复运行并继续称其为盲测。公开压缩包只保存在 `/cache`，不进入 Git 或 `/home` 提交面。

## 11. 交付结论与未关闭项

KangShield 已具备可运行、可复核、可离线导出的本地三域工程演示链路。诈骗语境与个人基线的一次性留出工程门通过，CAUCAFall 的唯一一次留出工程门**未通过**。因此本轮可以提交为透明标注限制的课程/工程展示作品，不能宣称三个域的真实准确率、公开数据全面泛化、目标设备部署门或发布门已经关闭。

失败具有明确方向：留出集轻量路径仍能在不高于 0.50 的送模比例和实时系数低于 1.00 的条件下取得 0.68 跌倒召回，但 ADL 误报、运动门保留和相对完整帧召回损失未达到预注册阈值。后续工作应使用新的开发数据改进时序状态与负样本约束，再用新的独立测试集验证，而不是针对本次留出样本补规则。

以下边界保持不变：

- 模拟跌倒不能代替真实居家老人或目标 C6c 的前瞻验证。
- CAUCAFall 不覆盖遮挡、夜视、多人、远场音频、中文诈骗或长期心理变化。
- FBS 不经过摄像头远场音频、VAD 或 ASR，且其非诈骗类别不是普通居家对话；门通过只证明中文词法规则按预期工作。
- CASAS 环境传感器只是日间出现、活动量和睡眠代理，没有心理健康结局；门通过只证明个人基线、缺数保护和等级响应工作。
- Ultralytics 权重当前绑定 `AGPL-3.0-or-Ultralytics-Enterprise`；公开或商业交付前必须关闭许可证门。
- 产品继续 fail closed：证据不足、过期或模型失败返回 `null`，不补猜、不合成总分、不自动外部告警。

## 12. 最终仓库验收

本轮最终验收日期为 2026-08-31：

- Slurm seal job `2919` 在 `hepnode3` 先执行 `compileall`，再运行全量 `pytest -q`，状态 `COMPLETED/0:0`，结果为 `85 passed in 4.22s`；同时通过全部 Slurm/启动脚本语法、`git diff --check`、隐私字符串和跟踪大资产扫描。登录节点未运行 Python 测试、数据解析或模型推理。
- 测试覆盖本地 Markdown 链接，并封印四份最终公开报告的 SHA-256、固定划分、工程门结果、策略/模型摘要、无原始记录约束和计算节点执行标记。
- Slurm installed-demo job `2918` 在 CPython 3.13 / Linux x86_64 上构建 wheel，在 `/cache` 全新虚拟环境以非 editable、`--no-index`、`--require-hashes` 方式安装 [`requirements-demo.lock`](../../requirements-demo.lock)，从源码目录外启动 localhost demo，并验证 health、三域 snapshot、文档页、owner/public 导出和 public 脱敏；状态 `COMPLETED/0:0`。四份运行策略随 wheel 安装，模型权重仍不进入 wheel。
- 提交面扫描未发现 `/home` 用户路径、具体 `/cache` 用户路径、设备/老人标识、转写、本地媒体路径、下载临时链接，也没有跟踪视频、音频、模型权重、SQLite、`data/`、`models/`、`runs/`、`logs/` 或 `secrets/` 资产。
- 旧 `models/`、`runs/`、`data/raw/` 与 `logs/` 分别由 Slurm job `2889`–`2892` 迁移到 `/cache/.../kangshield-legacy-archive/20260831/`，表观规模约为 982 MiB、1.1 GiB、720 MiB 与 258 KiB；job `2893`、`2894` 完成迁移审计。迁移可恢复且未执行删除，当前产品的 `data/processed/` 保留原位。
