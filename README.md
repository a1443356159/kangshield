# KangShield 康盾

面向独居老人的单机位三域风险本地守护产品。

KangShield 把定时采集、姿态分析、VAD/普通话 ASR、跌倒候选和 SDHY1 长程指标串成一条可运行产品链：

```text
目标 C6c 定时采集 → 增量分析 → 三域规则等级 → 每老人 SQLite
                                      ↓
                         本地看板 → 人工复核 → 双版本离线导出
```

产品始终分别展示跌倒、心理健康、诈骗三个风险域的 `0–3/null` 等级，不合成总分。证据不足、数据过期或模型失败时返回 `null`，不会补猜。所有等级固定标记为 `pilot_unvalidated`：不是概率、临床诊断、诈骗确认或已验证预测结论。

## 一分钟演示

安装开发环境后，用合成数据启动完整交互演示：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,media]"

kangshield-info serve-product \
  --elder-ref demo-elder \
  --device-ref demo-c6c \
  --host 127.0.0.1 \
  --port 8765 \
  --store-root /tmp/kangshield-submission-demo \
  --runs-dir /tmp/kangshield-submission-runs \
  --demo
```

浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。演示数据会随启动时间生成，包含三域等级、28 天趋势、候选时间线和可持久化人工复核，不读取真实老人数据，也不生成原始媒体或逐字稿。

## 产品能力

- **三域风险卡片**：显示等级、文字解释、数据覆盖、更新时间和规则状态。
- **28 天个人趋势**：页面明确展示“与过去的自己相比”，并把日间活动规律、活动量、语言互动和已确认睡眠规律分别标为平稳、轻度变化或明显变化；不做表情或声学情绪识别。
- **每月幸福感自评**：首页按自然月提醒完成 5 项 WHO-5；填写、修改或删除后立即重算心理健康风险，答案和历史仅保存在该老人的本机长程库中。
- **内置产品文档**：首页底部可进入本机文档页，集中查看服务条款、隐私范围、风险规则、技术路线、安全设计和数据删除说明。
- **语音证据与事件复核**：由语音触发的提醒显示最多 120 字转写片段；照护者可确认或忽略，并添加不进入分享报告的私有备注，操作后立即重新评分。
- **增量分析**：启动时回溯最近 14 天，之后默认每 300 秒扫描新采集；摘要幂等，失败写入 ledger 并重试。
- **双版本导出**：owner 版保留原因、趋势和审计；public 版移除身份、原始指标、备注、路径、逐字稿和精确事件时间。
- **隐私最小化**：HTTP 只绑定 `127.0.0.1`，不提供原始画面、媒体文件或任意文件读取路由，不自动向外部告警。

## 正式运行

```bash
kangshield-info serve-product \
  --elder-ref <pseudonymous-ref> \
  --device-ref <target-camera-ref> \
  --host 127.0.0.1 \
  --port 8765

kangshield-info export-product-report \
  --elder-ref <pseudonymous-ref> \
  --visibility owner_only \
  --output reports/owner

kangshield-info export-product-report \
  --elder-ref <pseudonymous-ref> \
  --visibility public_evidence \
  --output reports/public
```

目标设备固定为一台 `CS-C6c-V101-1J4WF`；`CS-EP-SDHY1` 只提供已确认可用的睡眠趋势。辅助摄像头不进入评分。

## 技术实现

- Python 3.11+、Pydantic 契约、标准库 HTTP 服务和内嵌 HTML/CSS/JS，无前端构建链。用户页面只显示“康盾”品牌和盾牌叶片图标，不暴露策略、模型、接口或发布门术语。
- 看板通过单个聚合接口完成一次数据库连接和一次风险快照构建；旧分项 API 保持兼容。候选事件与复核审计批量读取，写操作在服务内串行化。
- 每老人 SQLite schema v3：采集分析 ledger、日级特征、三域候选、assessment 历史、复核审计和月度幸福感自评。
- 长程库不保存完整逐字稿；只有命中风险规则的事件可保存一个规范化、最长 120 字的转写片段，用于本机照护者解释。public/分享报告继续完全移除该文字。
- 姿态链支持 YOLO、RTMPose 与 Keypoint R-CNN 候选；语音链支持同容器 PTS 对齐、VAD、普通话 ASR 和规则候选。
- 风险策略由 [`configs/v2-multidomain-risk-policy.json`](configs/v2-multidomain-risk-policy.json) 版本化，并在每个结果中绑定 revision 和 SHA-256。
- 月度自评采用[世界卫生组织 WHO-5（2024）](https://www.who.int/publications/m/item/WHO-UCN-MSD-MHE-2024.01)，按 CC BY-NC-SA 3.0 IGO 用于本地非商业试点；它是心理健康规则的一项本人自评证据，不是诊断。

实时检测工程 [`leoCHENG100/fall-detection`](https://github.com/leoCHENG100/fall-detection) 提供了实时姿态、PoseC3D 与人脸白名单算法的早期参考；已有同步边界记录在 `prediction_sync/SYNC_MANIFEST.json`。其当前仓库未提供项目 LICENSE，因此新版界面为独立实现，未直接复制对方前端；同步算法在许可证关闭前也不进入可分发发布包。

## 验证与提交边界

```bash
make test
git diff --check
```

Git 只跟踪代码、策略、测试、文档和脱敏证据。以下本机资产均被忽略，不进入提交：

- `data/`：公开数据、受控输入和每老人长程库；
- `models/`：外置模型权重；
- `runs/`、`logs/`：可再生运行产物与日志；
- `secrets/`、`.env*`：凭据和设备配置。

当前作品已满足本地演示形态，但仍是未验证试点。项目 LICENSE、第三方 NOTICE、最终依赖锁、模型许可证与真实 held-out 校准没有全部关闭前，不应宣传为已通过公开发布或临床门槛。

## 文档入口

- [三域产品设计](docs/design/multidomain-risk-mvp.md)
- [系统架构](docs/design/system-architecture.md)
- [当前状态](docs/governance/current-status.md)
- [发布门](docs/governance/release-readiness.md)
- [完整文档中心](docs/README.md)
