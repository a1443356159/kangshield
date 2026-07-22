# V1-M3 睡眠字段路线评审报告

状态：Accepted for V1-M3 sleep field slice

基准日期：2026-07-22

目标设备：CS-EP-SDNL1

证据提交：`5635e95`

正式运行：`20260722T072520Z-77a0f3b6`

## 1. 结论

V1 不选择或训练睡眠/生命体征模型。当前采用无值字段 profiler 与 fail-closed route gate：先发现真实 schema，再由人工证据确认单位、时间、值域和缺失语义，最后才允许实现单字段 adapter。

本次 E1 synthetic fixture 只发现 4 个名称候选，19 个 direct-if-exposed 字段中 0 个达到 `ready_for_adapter`；5 组多夜派生全部关闭，11 个 not-assumed 字段继续禁止假设。该结果关闭 V1-M3 的“睡眠信息采用什么模型/路线”问题，但不证明 CS-EP-SDNL1 的真实 API/SDK/导出能力，也不关闭 V1-M1 或 V1-M2c。

## 2. 输入、运行与可复现性

| 项目 | 结果 |
|---|---|
| Stage | `v1-m3-sleep-field-route` |
| Evidence | E1、synthetic fixture |
| Manifest | completed |
| Code | `5635e95`，`code_dirty=false` |
| Profile | `sleep-profile-v0.2.0` |
| Route | `sleep-route-assessment-v0.1.0` |
| 输入 | 2 records、4 non-sensitive fields |
| 持久化数值 | false |
| Route decision | `interface_only_waiting_for_e2_e3_schema` |

正式运行目录为 `runs/20260722T072520Z-77a0f3b6`。运行产物不提交 Git；本报告记录足以复核的代码版本、策略摘要、输入摘要与决策统计。

## 3. 字段路线结果

### 3.1 Direct fields

| 状态 | 数量 | 说明 |
|---|---:|---|
| `candidate_unconfirmed` | 4 | 只由名称匹配产生，不确认单位或医学语义 |
| `not_observed` | 15 | fixture 中没有候选路径 |
| `ready_for_adapter` | 0 | E1/fixture 不得解锁 adapter |
| 合计 | 19 | 来自《监测方案》的 direct-if-exposed 路线 |

发现的 4 个候选为：

| Canonical field | Candidate source path | 结果 |
|---|---|---|
| `measurement_at` | `$.records[].timestamp` | `candidate_unconfirmed` |
| `heart_rate_bpm` | `$.records[].heart_rate` | `candidate_unconfirmed` |
| `respiratory_rate_bpm` | `$.records[].respiratory_rate` | `candidate_unconfirmed` |
| `bed_presence` | `$.records[].in_bed` | `candidate_unconfirmed` |

四项均为 `can_standardize=false`。名称相似不会授权输出标准化数值。

### 3.2 Derived 与 not-assumed

| 路线 | 数量 | 结果 |
|---|---:|---|
| Multi-night derived | 5 | 全部 `blocked_source_fields`，`calculation_enabled=false` |
| Not assumed | 11 | 全部保持关闭 |

派生项包括睡眠时长趋势、早醒偏移、觉醒/WASO 趋势、IV/IS 和 RA/M10/L5；即使未来源字段 ready，也必须另过连续覆盖、时区、采样规律与个人基线门。

## 4. 摘要与来源绑定

| 对象 | SHA-256 |
|---|---|
| 《监测方案.docx》 | `1f094fe453ce32de7dc3dcb0935b7dd3036e36495140639ec36a6279361fccb0` |
| Sleep route policy | `a696329e2e66efbc9091ee305aae38410c5bccfcd2def39cb6f577357a06aece` |
| Mapping config | `f6571be0a9069acdb7e1a8b9a8c9b04c962a2441acb7847c9e993583951c408c` |
| Synthetic fixture | `9e43065c24f020ccdb56e12f38a4c1571eefe8d9d7d6c0d0b9989a927b0e7b2a` |

fixture 为 390 bytes。策略加载时会校验原始《监测方案》摘要；源文件漂移会 fail closed，而不是静默沿用旧指标表。

## 5. 官方资料边界

[CS-EP-SDNL1 官方商品页](https://www.ys7.com/item/994492.html?position=search_pc)可以证明设备公开参数与当前下架状态，但没有给出开发字段。[居家养老雷达开发套件](https://open.ys7.com/cn/s/157)和[睡觉检测服务](https://open.ys7.com/cn/s/623)说明萤石生态中存在睡眠、心率、呼吸、体动等通用能力；它们没有证明目标型号 CS-EP-SDNL1 返回这些字段。对应[产品文档](https://open.ys7.com/help/4223)还需要账号/JavaScript 环境才能继续核对请求、响应、单位、时间粒度与兼容型号。

因此公开资料只形成待确认候选，不提升目标设备的证据等级。

## 6. Fail-closed 验证

自动化测试覆盖以下关键行为：

1. E1 fixture 即使伪造 `confirmed` mapping，也不能解锁字段。
2. 只有 E2/E3 非 fixture 输入，且 source path、单位、时间、值域和缺失语义完整时，单字段才可变为 `ready_for_adapter`。
3. `ready_for_adapter` 只授权后续 adapter 实现，不输出值、不证明设备准确率。
4. 派生指标不会因名称候选自动启用。
5. 《监测方案》摘要漂移、非法单位和缺失语义均阻断路线。

全套验证为 40 passed，`pip check` 无 broken requirements。

## 7. 隐私审计

profile 和 route report 均明确记录 `values_persisted=false`。对两份 JSON 报告扫描：

- synthetic 姓名和设备序列号完整泄漏：0；
- fixture 中 8 个完整原始字段值片段泄漏：0；
- 报告仅保留字段路径、类型、记录数、候选关系、摘要和阻塞理由。

这项审计只覆盖当前报告契约；真实 E2/E3 样本仍须先脱敏，并保存在 Git 忽略的受控位置。

## 8. Review 决定

1. 采用 SleepProfile v0.2 + SleepRouteAssessment 作为 V2 睡眠 adapter 的前置门。
2. 不选择睡眠模型，不从商品量程、通用服务或相似字段名猜测目标设备 schema。
3. 只有 E2/E3 真实 schema 与完整语义确认才授权实现单字段 adapter。
4. 多夜派生和生命体征/睡眠分期准确率验收继续关闭，分别等待连续覆盖和独立参考设备。
5. V1-M3 睡眠字段切片通过 Review；姿态、语音和睡眠三条 E1 路线均已决策，因此 V1-M3 在 E1 探索范围标记 Done。
6. V1-M1 与 V1-M2c 仍为 In progress/Planned；不得用本 E1 结果替代 C6c 或 CS-EP-SDNL1 真机证据。

## 9. 下一步解锁条件

1. 使用有权限的萤石账号读取目标产品接口文档并保存版本化证据。
2. 确认 CS-EP-SDNL1 是否兼容相应开放服务，以及设备、固件、服务产品和账号权限组合。
3. 取得至少一晚脱敏 E2 API/SDK/导出样例，确认字段、单位、时区、区间、缺失、离线和报告延迟语义。
4. 完成至少连续三晚 E3 完整率、重复、断点和延迟审计后，再讨论日级 adapter 与派生路线。
