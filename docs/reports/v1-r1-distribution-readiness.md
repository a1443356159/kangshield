# V1-R1 比赛提交分发就绪门 E1 报告

日期：2026-07-23

状态：Engineering gate Passed；submission bundle Blocked as designed

范围：`distribution-readiness-v0.1.0` 的配置校验、来源绑定、资产处置、人工决定、必需文件、五级 gate、CLI 退出语义、provenance、权限与隐私

## 1. 结论

V1-R1 G5 已从文字检查项落成可执行门禁。实现能在资产来源漂移、项目文件缺失/未绑定、人工决定未确认或任一非排除资产未清门时稳定 fail closed；正向测试也证明所有证据满足时能够打开，而不是把结果硬编码为 blocked。

本轮工程工具验收通过，但比赛提交包明确未就绪：

- 7/7 个冻结来源文件与 policy 摘要一致。
- 13 个资产中 include 2、exclude 7、undecided 4；6 个非排除资产仍阻断。
- 5 个 required decision 全部 Open。
- `LICENSE`、`THIRD_PARTY_NOTICES.md`、`requirements/competition.lock` 全部缺失。
- 5 个 readiness gate 全部为 false。
- 最终 decision 为 `blocked_pending_distribution_review`，`submission_bundle_ready=false`。
- `legal_advice_provided=false`，RiskAssessment/Alert 均为 false。

因此，“门禁实现完成”和“比赛包可以分发”是两个相互独立的结论；本报告只验收前者。

## 2. 正式运行

| 项目 | 结果 |
|---|---|
| 实现提交 | `6c32364` |
| run | `20260722T214700Z-958cd4fb` |
| stage / evidence | `v1-r1-distribution-readiness` / E1 |
| status / issues | completed / 0 |
| code provenance | `6c32364`，`code_dirty=false` |
| policy SHA-256 | `456b18d3b571682b36bfe2681c5559e0232c933ef471df1869c451dc50a7d7eb` |
| manifest SHA-256 | `6a789be873900e2d1f074ddd89a221dfe4b87e56a5f851793e42dcc6b4889771` |
| source-assets SHA-256 | `a3d82e1567dcdc355248ab0cd8ca1041c0e9f209730822fdadb08585748d698e` |
| report SHA-256 | `6dbb82849a28a73f08f059cc564a00f47549c678bba5a9b02fdf6daa4ecaab8b` |
| 权限 | runs 根/run/目录 `0700`；manifest/source-assets/report `0600` |

manifest 不保存 policy 或 repository root 的本地路径；输入通过 policy SHA-256 派生的 opaque SourceAsset 引用。聚合产物中 `/home/`、用户名、风险 true 和告警 true 均为 0 命中。

## 3. 资产结果

| 分类 | bundle action | clearance | 当前处理 |
|---|---|---|---|
| 项目代码 | include | blocked pending owner decision | 等待许可证与源码分发方式 |
| Python 依赖闭包 | include | blocked pending review | 等待 competition lock、传递依赖盘点与 NOTICE |
| HumanArt detector/pose | undecided | blocked pending review | 分开审查实现、权重和训练数据血缘 |
| Keypoint R-CNN 权重 | undecided | blocked pending review | 分开审查 TorchVision 实现与预训练权重/关联数据条款 |
| FunASR 模型栈 | undecided | blocked pending review | 等待最终打包方式和模型卡/许可材料随包策略 |
| Ultralytics runtime/YOLO 权重 | exclude | excluded from bundle | 仅保留 V1 实验历史，不进入当前提交 profile |
| Whisper small | exclude | excluded from bundle | 因普通话主链路决定排除，不是因其 MIT 许可 |
| URFD/FLEURS/CAUCAFall/Open Images | exclude | excluded from bundle | 仅作 E1 本地评测，不随比赛包分发 |

当前 6 个阻断资产正是项目代码、依赖闭包、三项姿态 artifact 和 FunASR 栈。excluded 资产不阻断的前提是打包清单确实不携带它们；本门禁不把 excluded 等同于 cleared。

## 4. Gate 结果

| Gate | 结果 | 主要阻断输入 |
|---|---|---|
| `project-license-ready` | false | 项目资产、2 个 owner decision、`LICENSE` |
| `dependency-notice-ready` | false | 依赖资产、NOTICE owner、lock、NOTICE 文件 |
| `pose-distribution-ready` | false | 3 个姿态 artifact、最终 variant/打包决定、NOTICE |
| `speech-distribution-ready` | false | FunASR、打包决定、NOTICE |
| `submission-bundle-ready` | false | 以上所有非排除资产、5 个决定和 3 个文件 |

`--require-ready` 定向测试验证 blocked 报告仍先完整落盘，然后进程返回 `2`。普通审计返回 `0`，避免把“识别出未就绪”错误记成 assessor 运行失败。

## 5. 自动化与故障注入

- 全量测试：137 passed。
- 新门禁定向覆盖：policy schema、重复/未知引用、source coverage、来源缺失/摘要漂移、repository path/symlink 越界、必需文件缺失/过小/未绑定/摘要漂移、决策证据路径泄露、资产动作与 clearance 不一致。
- 正向打开测试：全部 required file/decision/asset 满足时，五个 gate 与 `submission_bundle_ready` 均为 true。
- CLI 覆盖：默认参数、owner-only 产物、opaque policy 引用、blocked 普通审计和 `--require-ready` 退出码。
- 静态验证：`compileall`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。

## 6. Review 边界

本轮接受以下工程结论：

1. `configs/v1-r1-distribution-readiness.json` 是当前比赛提交 draft profile 的机器可读来源；仓库内其他模型/数据配置仍是事实来源，并由摘要绑定。
2. 公开评测数据、Ultralytics/YOLO 和 Whisper 均不进入当前提交包；若重新引入，必须修改 disposition 并重新 Review。
3. 项目许可证、源码分发方式、最终姿态方案和模型打包方式属于人工 owner decision，不能由工具自动选择。
4. `LICENSE`、NOTICE 和 competition lock 必须人工审查后以 SHA-256 绑定；仅出现文件名不能开门。
5. 门禁不是法律意见；比赛规则和上游条款必须在最终 Release Candidate 前重新检查。

未关闭事项：

- 项目负责人确认项目许可证、源码分发方式和 NOTICE owner。
- 模型负责人确认最终姿态 variant；项目负责人确认所有模型 artifact 的取得/携带方式。
- 根据最终环境生成依赖 lock，完成直接/传递依赖和 native runtime 清单。
- 生成最终 `THIRD_PARTY_NOTICES.md` 并把三个文件摘要写回 policy。
- 以 `--require-ready` 在干净 Release Candidate 上重跑。

设计与使用方法见 [V1-R1 比赛提交分发就绪门](../v1-r1-distribution-readiness.md)，Review 决议见 [REV-023](../review-log.md#rev-023-v1-r1-比赛提交分发就绪-review)。
