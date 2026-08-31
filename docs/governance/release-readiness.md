# 发布就绪门

状态：本地展示可用，公开发布未通过
更新时间：2026-08-31

## 当前阻断

- 仓库尚未包含 owner 批准的项目 LICENSE 和第三方 NOTICE。
- CPython 3.13 / Linux x86_64 demo 依赖已用 SHA-256 锁定并通过全新非 editable 离线安装；Torch、Ultralytics、FunASR 等 edge 依赖的完整跨平台锁仍未冻结。
- 姿态与语音模型权重不在 Git 中；YOLO26s 姿态权重已冻结名称、SHA-256、推理尺寸和置信度，但来源携带方式、语音模型摘要与许可证尚未全部关闭。
- Ultralytics 代码/模型适用 AGPL-3.0 或企业许可选择，必须由 owner 根据提交与分发方式决定。
- 萤石当前提供 [`@ezuikit/player-hls`](https://www.npmjs.com/package/%40ezuikit/player-hls) 跨浏览器播放器，但其 npm 元数据未声明许可证，且需要自托管 JS/WASM/Worker；本提交不捆绑该 SDK，只使用浏览器原生 HLS 与新窗口降级。跨浏览器播放器在许可证关闭后再决定是否纳入。
- WHO-5 当前按 CC BY-NC-SA 3.0 IGO、带署名用于本地非商业试点；若提交渠道涉及商业使用或重新许可，需单独复核。
- CAUCAFall 公开模拟数据只覆盖跌倒候选工程链；目标 C6c 的真实 held-out 三域校准、连续长稳和云回看时间一致性仍未完成。
- 冻结版唯一一次 CAUCAFall 留出评估未通过预注册工程门：ADL 片段误报率、运动门保留率和相对完整帧召回损失三项不达标；不得将开发集通过或局部指标包装成发布就绪。
- FBS 中文短信与 CASAS 单人居家数据的一次性留出工程门已通过，但前者不经过摄像头远场音频、VAD/ASR 且负类不是普通对话，后者没有心理健康结局标签且传感器特征只是代理；两者不能关闭真实三域准确率或目标设备门。
- 长程专项测试后修复了“非相邻日期误算连续三天”，因此原 CASAS 留出结果只绑定 predecessor revision `2026-08-31.1`；当前 `2026-08-31.2` 只有合成端到端与 CASAS 开发回归，不得声称拥有新的独立留出结果。
- 本机异常片段包含高度敏感的画面与声音；公开部署前必须由 owner 确认磁盘加密、备份排除、30 天/2 GiB 留存值和操作系统账户边界。

因此页面和报告必须继续显示“本地试点”与非诊断边界，不能宣传为公开发布或临床就绪。

## Runtime 冻结要求

1. 记录 OS、架构、Python、GPU、CUDA/cuDNN 和浏览器范围。
2. 冻结 PyAV、OpenCV、NumPy、Torch、Ultralytics、FunASR 与 Pydantic 的完整依赖闭包。
3. 对每个模型记录任务、来源、版本、权重 SHA-256、许可证、设备和推理配置。
4. 在全新环境安装非 editable 包，离线或受控缓存加载模型，并运行完整测试。
5. 连续运行验证内存上界、模型实时系数、段间隙、失败恢复和背压率。
6. 验证 H.264/AAC 编码速度、磁盘峰值、到期清理、空间上限和断电后的孤儿临时文件恢复。

## 隐私与安全门

- 服务只监听 `127.0.0.1`，不存在公网隧道或反向代理默认配置。
- SQLite、日志、导出和 Git 历史中不存在应用密钥、token、真实设备序列号、直播 URL、临时回放 URL 或连续原始媒体；异常 MP4 只存在 Git ignored 的个人私有目录。
- 候选回放只能通过 owner 点击、精确同源、CSRF 和 JSON POST 触发；本机媒体 URL 使用不可猜随机令牌、10 分钟到期、同源资源策略和 byte range，API 不返回路径。
- public HTML+JSON 自动扫描身份、设备、转写、备注、路径、精确事件时间、问卷答案和播放字段。
- 单老人删除只接受精确重复确认，并同时删除 SQLite 与本机 MP4；云录像删除由云账户另行执行。

## 功能门

- 契约强制恰好三个域、分数仅 `0–3/null`、null 有原因、策略摘要必填且全局分固定 null。
- 三域所有等级、覆盖不足、hard negative、共现窗口、数据过期和问卷合并规则有测试。
- 分段幂等、失败降级、复核持久化、并发复核、schema v1→v5、归档留存和完整个人删除有测试。
- localhost、API schema、CSRF、XSS 安全写入、路径穿越、本机随机令牌/Range 播放、云回退和 public 脱敏有测试。
- owner/public 离线报告在断网浏览器中可打开。

## 发布验收命令

登录节点只下载 [`requirements-demo.lock`](../../requirements-demo.lock) 中带摘要的二进制 wheel 到 `/cache/DeepLearning/$USER/kangshield-validation/wheelhouse`，不运行测试、数据解析或模型；具体命令见根目录 README。随后只负责提交任务：

```bash
sbatch scripts/slurm/validate_submission.sbatch
sbatch scripts/slurm/smoke_installed_demo.sbatch
```

前者在计算节点统一运行全量 pytest、编译、Shell 语法、`git diff --check`、Markdown 链接、前端行为、隐私字符串、跟踪媒体/数据库文件和 public 报告泄露测试；后者在 `/cache` 构建 wheel、全新非 editable 安装并启动完整 demo。工程检查不能替代法律审查或真实目标域验证。
