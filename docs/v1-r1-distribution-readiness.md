# V1-R1 比赛提交分发就绪门

状态：Implemented Baseline v0.1；工程工具已完成，提交包仍为 Blocked

更新时间：2026-07-23

适用范围：V1-R1 G5、V2 比赛提交包设计与 Release Candidate 检查

## 1. 目标与非目标

本门禁把散落在模型、数据集和工程配置中的许可证与分发边界变成可重复执行的工程检查。它回答的是“当前冻结的比赛包是否具备进入人工发布 Review 的证据”，而不是自动给出法律结论。

门禁负责：

- 固定项目代码、依赖闭包、模型权重和评测数据的 bundle disposition。
- 绑定资产判断所依据的仓库文件及 SHA-256，来源漂移时 fail closed。
- 要求项目许可证、第三方 NOTICE 和比赛依赖 lock 实际存在、非空且摘要已冻结。
- 要求项目许可证、源码分发方式、最终姿态方案、模型打包方式和 NOTICE 负责人均由具名角色确认。
- 输出 owner-only、可审计的 RunManifest 与 `distribution-readiness.json`。

门禁不负责：

- 替项目负责人选择开源或闭源许可证。
- 将框架许可证自动外推为预训练权重、训练数据或比赛提交物的授权。
- 下载、复制或重新分发任何权重、数据集、许可证文本或原始媒体。
- 替代比赛规则、上游条款和最终法律 Review。
- 产生 RiskAssessment 或 Alert。

## 2. 模块与输入

实现入口：

```text
configs/v1-r1-distribution-readiness.json
        │
        ├── 8 个 source binding + SHA-256
        ├── 13 个 distribution asset
        ├── 5 个人工 decision
        ├── 3 个 required release file
        └── 5 个 readiness gate
                │
                ▼
src/kangshield/information/distribution_readiness.py
                │
                ▼
runs/<run_id>/
├── manifest.json
├── source_assets.jsonl
└── reports/distribution-readiness.json
```

八个 source binding 覆盖 `pyproject.toml`、候选 runtime profile、姿态/语言模型配置和三个公开数据集配置。每个资产必须至少由一个来源覆盖；资产、文件、决策和 gate ID 必须唯一，未知引用、绝对路径、`..`、反斜杠或越过仓库根的 symlink 均被拒绝。

## 3. 资产处置语义

| `bundle_action` | 含义 | 是否阻断 |
|---|---|---|
| `include` | 计划进入提交包，必须完成 clearance | 未清门或来源漂移时阻断 |
| `exclude` | 明确不进入提交包，可继续用于 V1 本地评测 | 不阻断，但重新引入必须重新 Review |
| `undecided` | 尚未决定是否进入提交包 | 始终阻断 |

`exclude` 不是“许可证已清门”，而是“当前包不携带该资产”。它不能被用来暗示允许重新分发，也不能在打包阶段被静默加入。

当前 `v2-competition-submission-draft` profile 固定 13 项资产：

| 处置 | 数量 | 当前资产 |
|---|---:|---|
| include | 2 | KangShield 项目代码、比赛 Python 依赖闭包 |
| undecided | 4 | HumanArt YOLOX detector、HumanArt RTMPose、TorchVision Keypoint R-CNN、FunASR 模型栈 |
| exclude | 7 | Ultralytics runtime、YOLO26n 权重、Whisper small、URFD、FLEURS、CAUCAFall、Open Images |

这里把“实现代码”“预训练权重”“训练/评测数据”和“最终提交包”分开判断。MMPose 的实现许可证不自动清除 HumanArt 权重；TorchVision 的实现许可证也不自动清除与训练数据关联的预训练权重。公开数据集只保留为 V1 E1 评测输入，不进入比赛提交包。

## 4. Fail-closed 条件

### 4.1 来源配置

source binding 只有 `matched`、`missing`、`digest_mismatch` 三种结果。任一资产所覆盖的来源没有全部匹配时，`source_evidence_ready=false`；该资产只要不是 `exclude` 就阻断 gate。

因此，修改 `pyproject.toml`、模型配置或数据集配置后，必须先重新审查资产 disposition，再更新 policy 中的来源摘要。不能只更新 SHA-256 来绕过 Review。

### 4.2 必需文件

三个发布文件必须同时满足：

1. 路径位于仓库内且不是越界 symlink。
2. 文件存在并达到最小字节数。
3. policy 已写入 `expected_sha256`。
4. 实际摘要与期望摘要一致。

对应状态为 `matched`、`missing`、`too_small`、`digest_unbound` 或 `digest_mismatch`。仅创建文件不会打开 gate；未绑定摘要仍然 fail closed。

### 4.3 人工决定

`confirmed` decision 必须同时有非空 `value` 和可审计的 `evidence_ref`。引用不得是本机绝对路径。当前五个决定为：

- 项目许可证选择。
- 比赛包的源码分发方式。
- 最终姿态 variant。
- 模型 artifact 打包方式。
- 第三方 NOTICE 负责人。

这些决定只能由 policy 中列出的 `project-owner` 或 `model-owner` 确认；工具不会推断默认答案。

## 5. 五个 Readiness Gate

| Gate | 必须关闭的范围 |
|---|---|
| `project-license-ready` | 项目代码、许可证选择、源码分发方式、`LICENSE` |
| `dependency-notice-ready` | 依赖闭包、NOTICE 负责人、competition lock、`THIRD_PARTY_NOTICES.md` |
| `pose-distribution-ready` | 最终姿态选择、模型打包方式、所有未排除姿态权重、NOTICE |
| `speech-distribution-ready` | FunASR 模型栈、模型打包方式、NOTICE |
| `submission-bundle-ready` | 所有 required file/decision 和所有非排除资产 |

最终报告只有在五个 gate 全部 ready 时才允许 `submission_bundle_ready=true`。实现不把某个子 gate 的通过外推为整个提交包可发布。

## 6. 运行方式

日常审计：

```bash
make PYTHON=.venv/bin/python assess-distribution-readiness
```

指定输入：

```bash
kangshield-info assess-distribution-readiness \
  --policy configs/v1-r1-distribution-readiness.json \
  --repository-root . \
  --runs-dir runs
```

Release Candidate 门：

```bash
kangshield-info assess-distribution-readiness --require-ready
```

普通审计即使结论为 blocked 也会以成功进程完成并留下报告，因为“正确识别未就绪”是有效评估结果。`--require-ready` 在报告落盘后对未就绪返回退出码 `2`，用于 CI/提交脚本 fail closed。

policy 作为 opaque `SourceAsset` 登记，manifest 只保存摘要和 profile；CLI 不持久化 policy、repository root 的本地路径。runs 根、run/报告目录及 JSON/JSONL 继续遵守 `0700/0600` owner-only 契约。

## 7. 当前基线与打开流程

初始基线运行 `20260722T214700Z-958cd4fb` 得到 7/7 来源匹配。接入候选 runtime profile 作为第八个来源后，clean follow-up run `20260722T222307Z-254cb0ca` 得到：8/8 来源匹配、0/3 必需文件匹配、0/5 决定确认、6 个阻断资产、0/5 gate ready，结论仍为 `blocked_pending_distribution_review`。这是预期的 fail-closed 状态，不是工具失败。

按以下顺序打开门禁：

1. 项目负责人确认项目许可证和源码分发方式，生成并人工审查 `LICENSE`。
2. 模型负责人从当前姿态候选中做最终选择；项目负责人确认权重是随包携带、安装时取得还是完全排除。
3. 在独立候选环境运行 runtime closure gate，关闭直接/传递依赖、extras/marker、安装 provenance、环境纯净度和许可证 metadata 缺口；根据最终平台另行盘点 native runtime。
4. 八个 closure gate 全部通过并完成人工复核后，才由该最终环境生成 `requirements/competition.lock`。
5. 生成并人工复核 `THIRD_PARTY_NOTICES.md`，明确包含资产、许可文本/署名和不随包携带的评测资产。
6. 将三个文件的最终 SHA-256、五项 confirmed decision 与证据引用写回 policy。
7. 重跑普通审计检查明细，再以 `--require-ready` 作为 Release Candidate 硬门。
8. 发布前重新检查上游官方条款和比赛规则；条款或打包方式变化必须新开 Review。

## 8. 版本变更规则

以下变化必须升级 policy/assessor 版本或新增 profile，不能静默覆盖：

- 增删提交包中的依赖、模型、权重、数据或 native runtime。
- 改变权重取得/携带方式、源码分发方式或项目许可证。
- 改变 required file、decision 或 gate 语义。
- 接受当前 excluded 资产重新进入比赛包。
- 改变 V2 比赛平台、容器镜像或部署环境，导致依赖闭包不同。

正式 E1 证据见 [V1-R1 分发就绪门报告](reports/v1-r1-distribution-readiness.md)，依赖前置门见[候选 Runtime 依赖闭包门](v1-r1-runtime-closure.md)，决策状态见 [V1-R1 探索收敛与 V2 输入清单](v1-r1-exploration-review.md)。
