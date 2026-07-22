# V1-M3 睡眠字段路线与 Fail-Closed Gate

状态：Implemented，等待干净提交的 E1 路线报告与 Review

基准日期：2026-07-22

目标设备：CS-EP-SDNL1

## 1. 路线决定

V1 不训练睡眠分期、生命体征或风险模型，也不根据商品参数猜测 API 字段。当前采用“字段发现 → 语义确认门 → adapter → 多夜覆盖审计 → 派生指标”的路线：

1. `profile-sleep` 只发现字段路径、类型、非空计数和名称候选，不保存值。
2. `assess-sleep-route` 对照《监测方案》的 machine-readable policy 和人工 mapping config，判断每个字段是未观察、候选未确认、证据不足、语义不足还是可开始 adapter 实现。
3. 只有 E2/E3 真实导出/API、非 fixture mapping，以及单位、时间、值域和缺失语义全部确认，单个字段才可变为 `ready_for_adapter`。
4. 路线评估器本身永远不输出标准化睡眠或生命体征值；adapter 只能在真实 schema Review 后另行实现。
5. IV、IS、RA、M10/L5 等多夜指标即使字段就绪也保持禁用，直到连续时间覆盖、时区、采样规律和个人基线通过独立审计。

这会关闭 V1-M3 的“选什么睡眠模型”问题：当前答案是“不选模型，只保留严格的字段接口与派生前置条件”。它不会关闭 V1-M1/M2c 的“真实 SDNL1 数据能否取得”问题。

## 2. 《监测方案》指标分层

policy 固定在 `configs/sleep/v1-sleep-route-policy.json`，并绑定原始《监测方案》SHA-256 `1f094fe453ce32de7dc3dcb0935b7dd3036e36495140639ec36a6279361fccb0`。

### 2.1 仅在设备直接开放时接入

| 分组 | Canonical fields | 当前状态 |
|---|---|---|
| 时间与质量 P0 | `measurement_at`、`report_generated_at`、`device_status` | 必须先区分离线、缺失、离床与报告延迟 |
| 基础生命体征 P0 | `heart_rate_bpm`、`respiratory_rate_bpm` | 商品量程不等于 API 字段；不验证医学精度 |
| 在离床与睡眠摘要 P0 | `bed_presence`、`sleep_start_at`、`sleep_end_at`、`total_sleep_duration` | 必须确认时区、区间边界和单位 |
| 睡眠连续性 P1 | `awakening_count`、`waso_duration`、`long_wake_episode_count`、`sleep_efficiency_ratio` | 必须确认 awake、episode 和分母定义 |
| 分期/体动 P1 | `sleep_stage`、`movement_duration_ratio`、`body_movement_index`、`turnover_count`、`rem_duration`、`nap_duration` | 必须确认类别、epoch、日夜边界和设备算法版本 |

共 19 个 direct-if-exposed 字段。名称相似最多产生 candidate，绝不自动确认。

### 2.2 只有满足连续数据条件才派生

| 指标组 | 必需字段 | V1 工程门 |
|---|---|---|
| 睡眠时长趋势 | total sleep + report time | 至少 7 夜、时区和缺失审计 |
| 早醒偏移 | sleep end + report time | 至少 7 夜和个人基线 |
| 觉醒/WASO 趋势 | awakening + WASO + report time | 至少 7 夜且设备 awake 语义确认 |
| IV/IS | regular measurement time + body movement | 至少 7 个完整 24h 周期；睡眠日级报告不够 |
| RA/M10/L5/M10 中点 | regular measurement time + body movement | 至少 7 个完整 24h 周期、时区和活动代理确认 |

“7 夜”是当前工程 readiness 下限，不是临床有效性结论；正式趋势窗口必须在 V2 评测方案中另行冻结。

### 2.3 不得默认存在

以下 11 类保持 `not_assumed`：RR intervals、SDNN/SDRR、RMSSD、pNN50、HF、LF/HF、SpO2、AHI、体温、血压、原始雷达信号。聚合心率不能反推 HRV；呼吸率或“呼吸暂停提醒”也不能直接视为 AHI。

## 3. 官方公开资料边界

- [CS-EP-SDNL1 官方商品页](https://www.ys7.com/item/994492.html?position=search_pc)确认 59–64 GHz FMCW、50 ms 硬件数据周期、两组 bpm 量程、0.5–1.5 m 距离和萤石云视频 APP 联网，但页面当前显示商品已下架，也没有开发字段。
- [萤石居家养老雷达开发套件](https://open.ys7.com/cn/s/157)宣传健康档案可含睡眠时长、心率、呼吸和睡眠深度，但页面列出的推荐雷达是 `DS-TDSB00-EKT/EKH`，不是 `CS-EP-SDNL1`。
- [萤石“睡觉检测”服务](https://open.ys7.com/cn/s/623)宣传呼吸、体动、深浅睡周期和翻身次数；其[产品文档](https://open.ys7.com/help/4223)需要 JavaScript/账号环境，公开抓取未取得请求字段、单位、时间粒度或目标型号兼容清单。

因此这些内容只提升“值得向萤石账号/商务确认的候选能力”，不提升 CS-EP-SDNL1 的 E0 能力状态，更不能当作 E2/E3 字段证据。

## 4. 模块与契约

```text
raw JSON/CSV export
        │
        ├── SleepProfileReport（字段路径/类型/计数，无值）
        │            │
        │            ├── monitoring policy（绑定监测方案 digest）
        │            └── manual mapping（candidate/confirmed/rejected）
        │                         │
        └────────────────> SleepRouteAssessmentReport
                                  │
                   ready_for_adapter? ── no ──> interface only / blocked reason
                                  │ yes
                                  └──> 后续单字段 adapter 实现与真实样本 Review
```

| 文件 | 职责 |
|---|---|
| `sleep_profile.py` | v0.2 字段发现；扩展到时间、状态、睡眠连续性、分期、体动和摘要别名 |
| `sleep_route.py` | 校验 policy、原始方案 digest、mapping evidence 和所有确认项；输出 fail-closed 路线报告 |
| `contracts.py` | 严格定义 direct field、derived indicator 和 route report，不含值字段 |
| `v1-sleep-route-policy.json` | 19 direct、5 derived、11 not-assumed 的 machine-readable 需求边界 |
| `sdnl1-field-map.example.json` | synthetic candidate 示例；所有单位/时间/值域/缺失语义故意为 null |

## 5. 状态机

Direct field 只允许以下状态：

- `not_observed`：导出中没有名称候选或 mapping。
- `candidate_unconfirmed`：找到名称候选，但没有人工确认。
- `source_path_missing`：confirmed mapping 指向本次 profile 不存在的路径。
- `blocked_evidence`：mapping 标为 confirmed，但输入仍是 fixture/E1 或 mapping 证据高于输入。
- `blocked_semantics`：单位、时间、值域、缺失语义不完整，或单位不在 policy 允许列表。
- `mapping_rejected`：人工明确拒绝该路径。
- `ready_for_adapter`：仅表示可以开始实现单字段 adapter，不表示已经输出值或验证医学准确性。

所有 derived indicator 当前只有 `blocked_source_fields` 或 `blocked_time_coverage`，`calculation_enabled=false`。

## 6. E1 预期与隐私

运行 synthetic fixture：

```bash
kangshield-info assess-sleep-route \
  tests/fixtures/sleep/sdnl1-export.synthetic.json \
  --evidence-level E1 \
  --source-type fixture
```

预期：19 个 direct fields 中只有 timestamp、heart rate、respiratory rate、in-bed 形成 4 个 `candidate_unconfirmed`，ready 为 0；11 个 not-assumed 保持关闭，5 个 derived 全部禁用，decision 为 `interface_only_waiting_for_e2_e3_schema`。

输入中的姓名、设备序列号和四个合成数值均不得进入 profile/route report。允许报告字段路径、类型、记录数、候选路径、policy/mapping SHA-256 和阻塞理由。

## 7. 真实样本解锁流程

```bash
kangshield-info assess-sleep-route sanitized-sdnl1-export.json \
  --evidence-level E2 \
  --source-type sdk_export \
  --mapping-config local-confirmed-sdnl1-map.json
```

真实 mapping 不得提交设备序列号、token 或样本值。每个 confirmed field 必须给出：

1. 实际 source path 与本次 profile 一致。
2. 单位来自接口文档或可保存的厂商确认，不从量程猜测。
3. observation/report 时间、时区、区间边界和生成延迟语义。
4. categorical 值域，例如在床、离床、无人、离线分别如何表达。
5. null、字段缺失、0、空数组和接口失败的区别。
6. 固件、服务产品、API/SDK 版本和证据 run。

取得 ready field 后仍只授权实现 adapter；至少连续三晚完成完整率、重复、断点和延迟报告后，才讨论日级派生。生命体征/分期准确率还需要独立参考设备，不能由本 gate 验收。
