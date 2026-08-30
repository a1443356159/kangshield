# KangShield 康盾

面向独居老人的单机位、以个人为中心的三域风险守护 MVP。

```text
C6c 连续直播流（内存）
  → 60 秒审计段
  → 运动与音频活动轻量筛选
  → 关键窗口姿态 / VAD / 普通话 ASR
  → 跌倒、心理健康、诈骗三域规则等级
  → 每人 SQLite → 本地看板 → 人工复核 → owner/public 导出

原始录像：摄像头云服务            本机原始音视频：不落盘
```

三个风险域始终分别输出 `0–3` 或 `null`，不合成总分。证据不足、数据过期或模型失败时明确返回 `null`，不会补猜。等级统一标记为 `pilot_unvalidated`：不是概率、临床诊断、诈骗确认或已验证预测结论，也不会自动向外告警。

## 一分钟演示

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

kangshield-info serve-product \
  --elder-ref demo-elder \
  --device-ref demo-c6c \
  --host 127.0.0.1 \
  --port 8765 \
  --store-root /tmp/kangshield-demo \
  --demo
```

浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。演示数据随启动时间生成，走真实 SQLite、评分器、复核 API、问卷和导出链，不读取真实老人或设备资产。

## 面向用户的能力

- 三张风险卡分别说明等级、原因、数据覆盖和更新时间。
- 28 天趋势始终表述为“与过去的自己相比”，不做同龄人排名。
- 每自然月提醒填写一次 WHO-5 幸福感自评，保存后即时重算心理健康域。
- 语音触发事件显示最多 120 字的风险相关转写片段；完整逐字稿不入库。
- 照护者可确认或忽略候选，并记录 owner-only 备注；操作后即时重算且保留审计。
- 连接萤石云录像后，异常事件可在前端按需回看含声音的短片段。播放地址只在点击时临时获取，关闭弹窗即从页面移除，不写入 SQLite 或报告。
- owner 离线报告保留事件与审计；public 报告移除身份、设备、原始指标、转写、备注、路径和精确事件时间。
- 页面底部提供服务条款、技术路线、风险规则、隐私和删除说明。

## 正式运行

连续分析需要边缘依赖和外置模型：

```bash
python -m pip install -e ".[edge]"
```

在 Git ignored、权限为 `0600` 的 `secrets/ys7.env` 中配置：

```bash
YS7_APP_KEY=...
YS7_APP_SECRET=...
KANG_DEVICE_SERIAL=...
KANG_ELDER_REF=elder_pseudonym
KANG_DEVICE_REF=c6c_target
```

加载环境后，一条命令启动连续分析、看板、问卷、复核和云端异常片段回看：

```bash
set -a
. secrets/ys7.env
set +a

kangshield-info serve-product \
  --elder-ref "$KANG_ELDER_REF" \
  --device-ref "$KANG_DEVICE_REF" \
  --host 127.0.0.1 \
  --port 8765 \
  --continuous \
  --edge-provider ezviz
```

无看板的常驻分析入口是：

```bash
kangshield-info run-edge-monitor \
  --provider ezviz \
  --elder-ref "$KANG_ELDER_REF" \
  --device-ref "$KANG_DEVICE_REF"
```

不要对同一设备同时运行这两个连续入口。systemd 示例见 [`deploy/kangshield-product.service`](deploy/kangshield-product.service)，启动脚本见 [`scripts/run_product.sh`](scripts/run_product.sh)。

## 导出与删除

```bash
kangshield-info export-product-report \
  --elder-ref "$KANG_ELDER_REF" \
  --device-ref "$KANG_DEVICE_REF" \
  --visibility owner_only \
  --output reports/owner

kangshield-info export-product-report \
  --elder-ref "$KANG_ELDER_REF" \
  --device-ref "$KANG_DEVICE_REF" \
  --visibility public_evidence \
  --output reports/public

kangshield-info delete-product-data \
  --elder-ref "$KANG_ELDER_REF" \
  --confirm-ref "$KANG_ELDER_REF"
```

删除命令只删除指定假名对应的本机派生数据库；云录像需在云服务账户中另行管理。

## 实现与安全边界

- Python 3.11+、Pydantic、SQLite、标准库 HTTP 和内嵌 HTML/CSS/JS；无前端构建链或 CDN。
- HTTP 服务只接受 `127.0.0.1`，写操作要求精确同源、随机 CSRF token 和 JSON content type。
- 不提供本地媒体、任意文件或完整逐字稿读取路由。
- 直播流按 60 秒在内存中分段；5 fps 灰度帧差和 500 ms 音频 RMS 先筛选，重模型只处理关键窗口。
- 只有重模型成功处理的覆盖可支持“0 分”；背压、断流和模型失败均写固定失败码并 fail closed。
- 每人 SQLite schema v4 保存无媒体分段审计、分析 ledger、日级个人特征、三域候选/assessment、复核历史和月度问卷。
- 风险策略和轻量选择策略分别由 [`configs/v2-multidomain-risk-policy.json`](configs/v2-multidomain-risk-policy.json) 与 [`configs/v2-edge-segment-policy.json`](configs/v2-edge-segment-policy.json) 版本化并绑定 SHA-256。

界面信息组织借鉴了实时守护产品的首屏导览、状态分区和事件队列思路，并参考了 [`leoCHENG100/fall-detection`](https://github.com/leoCHENG100/fall-detection) 的实时检测方向；最终提交未复制其前端或同步算法代码。

## 验证与发布边界

```bash
make test PYTHON=.venv/bin/python
git diff --check
```

`data/`、`models/`、`runs/`、`logs/`、`secrets/` 和 `.env*` 均被 Git 忽略。历史本机资产不会因仓库裁剪而自动删除。

当前作品可直接本地演示，但仍是未验证试点。项目 LICENSE、第三方 NOTICE、依赖锁、模型许可证和真实目标域 held-out 校准关闭前，不应宣传为公开发布或临床级产品。月度自评采用[世界卫生组织 WHO-5（2024）](https://www.who.int/publications/m/item/WHO-UCN-MSD-MHE-2024.01)，当前按 CC BY-NC-SA 3.0 IGO 用于带署名的本地非商业试点。

## 文档

- [三域产品设计](docs/design/multidomain-risk-mvp.md)
- [系统架构](docs/design/system-architecture.md)
- [连续取流与云端回看](docs/device-data/streaming-and-media.md)
- [当前状态](docs/governance/current-status.md)
- [发布门](docs/governance/release-readiness.md)
