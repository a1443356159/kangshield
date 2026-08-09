# V1 正式 Slurm Runtime Preflight 报告

状态：Passed；仅验收 E1 运行基础设施

日期：2026-07-23

正式采用证据：clean commit `b54d8b8`，Slurm job `1780`

## 1. 结论

V1 的八个正式 sbatch 入口已统一到同一套 fail-closed 提交与运行时契约。正式提交必须经过 `scripts/slurm/submit.sh`：提交器要求仓库 clean，冻结完整 40 位 submit commit；计算节点执行 `slurm-runtime-v0.2.0` 时复核 execution commit、checkout-bound import、stdout/runs 权限和所需 CUDA 动态库。排队期间 checkout 变化、绕过提交器、CUDA provider 不可加载或权限不满足都会在读取业务输入前失败。

最终 job `1780` 在 NVIDIA L40 上完成，exit `0:0`。cuDNN 9、ONNX Runtime CUDA provider 和最小 CUDA tensor 均通过；stdout 为 owner-only `0600`，runs 根为 `0700`。该结果只证明正式批处理执行与证据来源可复现，不证明任何模型准确率、公开数据集结果、C6c/SDNL1 接入、风险判断或告警能力。

## 2. 实现切片

| Commit | 内容 |
|---|---|
| `673560d` | 引入共享 `runtime.sh` 和轻量 runtime preflight；将七个业务 sbatch 与一个 preflight 入口迁移到统一 checkout、权限和 CUDA 门 |
| `667ad8d` | 引入统一提交器；冻结完整 submit commit，并在执行时拒绝 commit 漂移；全部 Make target 停止直接调用裸 `sbatch` |
| `b54d8b8` | 在 preflight 中记录 Slurm/CUDA 可见设备上下文，区分节点物理设备清单与作业实际可用设备 |

统一运行层在任何业务输入校验之前完成：

1. 校验 `SLURM_SUBMIT_DIR` 是计算节点可见的 KangShield Git 根目录。
2. 将 Slurm stdout 收紧到 `0600`，将 runs 根创建或校正为 `0700`。
3. 要求完整 submit commit 与 execution `HEAD` 相同，正式证据默认拒绝 dirty checkout。
4. 将 `PYTHONPATH` 绑定到该 checkout 的 `src/`，并反查 `kangshield.__file__`。
5. 清除登录节点本地代理；RTMPose 相关入口额外实际加载 cuDNN 9 和 ONNX Runtime CUDA provider 动态库。

## 3. 自动化验证

- 全量：`129 passed`。
- 新增 Slurm runtime/submit 契约定向：`11 passed`。
- `compileall`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。
- 故障注入覆盖非 Git/KangShield 根、缺失 Slurm 元数据、非法 clean 开关、dirty checkout、缺失/错误 submit commit、submit/execution commit 漂移、不安全 runs 根、错误 import 绑定和业务输入提前失败。
- 静态门确认八个 sbatch 均 source 共享 runtime；九条 Make 提交路径均经过统一提交器，Makefile 不含裸 `sbatch` 或自定义 `--export`。

## 4. L40 运行证据

| 项目 | 第一阶段 | 最终采用 |
|---|---|---|
| Slurm job | `1779` | `1780` |
| Commit | `673560d` | `b54d8b8` |
| Runtime contract | `slurm-runtime-v0.1.0` | `slurm-runtime-v0.2.0` |
| 状态 / exit | `COMPLETED` / `0:0` | `COMPLETED` / `0:0` |
| 节点 / elapsed | `hepnode1` / 3 s | `hepnode1` / 7 s |
| stdout mode | `0600` | `0600` |
| stdout SHA-256 | `74833d2a5cf04ceeb611b15c366993d46798a3b2d26cc7e0a89a9f41a9bd957a` | `e208492910043e9bf383dcb106e70d9b7fc4c3ae8e113140ffb458e818b68cc4` |

job `1779` 验证共享 runtime、权限和 CUDA 基线；随后 Review 识别出“提交后、启动前 checkout 变化”的排队竞态，因此它保留为前置证据，不作为最终契约。job `1780` 额外输出：

- `clean=true`、`submit_commit_bound=true`、`checkout_bound=true`、`owner_only=true`；
- NVIDIA L40，driver `580.105.08`，每张物理卡 `46068 MiB`；
- cuDNN `9` loadable，ONNX Runtime CUDA provider registered/loadable；
- `CUDA_VISIBLE_DEVICES=1`、`SLURM_JOB_GPUS=1`、`torch.cuda.device_count()=1`；
- Torch `2.13.0+cu130`，CUDA tensor sum `1.0`；
- `risk_assessment_emitted=false`、`alert_emitted=false`。

节点级 `nvidia-smi` 列出两张物理 L40，但 job `1780` 的 `TresPerNode=gres/gpu:L40:1`，Slurm/CUDA 环境和 Torch 均只暴露一张分配卡，因此本报告不把节点物理卡数写成作业占用卡数。本集群的 `sacct AllocTRES` 未回填 GPU 项，故 GPU 证据同时保留 sbatch 请求、`scontrol`、Slurm/CUDA 环境和实际 tensor 四个口径。

## 5. 权限与隐私审计

- 两份 stdout 均由提交账户持有且 mode 为 `0600`；runs 根 mode 为 `0700`。
- 两份 stdout 对绝对 home 路径、用户名文本、`RiskAssessment=true` 和 `Alert=true` 的扫描均为 0 命中。
- stdout 与 runs 继续由 `.gitignore` 排除；报告只保存非敏感运行摘要和 SHA-256，不复制本地路径或模型/数据内容。

## 6. Review 决定与边界

1. `slurm-runtime-v0.2.0` + `scripts/slurm/submit.sh` 是 V1 后续正式 Slurm 证据的唯一入口；裸 `sbatch` 只可用于故障诊断，不能升级为正式证据。
2. 业务 `KANG_*` 参数通过提交器进程环境传入；调用方不得覆盖提交器生成的 `--export` 或 submit commit。
3. 新 checkout、Python/CUDA 环境或计算节点先运行 `make submit-runtime-preflight`，通过后再加载模型或数据。
4. 该契约不替代 RunManifest、模型/输入摘要、E2/E3 设备证据和 V2 service ACL；真实设备采集、模型复测和数据治理仍按现有硬门推进。
