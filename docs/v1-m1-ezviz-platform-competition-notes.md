# 萤石赛事平台使用与资源边界（官方材料归档）

状态：Active v1.4

更新时间：2026-08-02

本文件归档萤石赛事支持方公开发布的官方材料关键事实，并标注对项目决策的影响。原文为网页且 FAQ 会持续更新，以原链接为准。

## 1. 来源

| 材料 | 链接 | 归档日期 |
|---|---|---|
| 赛事技术对接常见问题汇总（aid=718） | <https://ezsuperfans.com/portal.php?mod=view&aid=718> | 2026-08-02 |
| 设备资源支持范围的特别说明（aid=712，2026-07-03） | <https://ezsuperfans.com/portal.php?mod=view&aid=712> | 2026-08-02 |
| 2026 揭榜挂帅-海康威视 FAQ（aid=706） | <https://ezsuperfans.com/portal.php?mod=view&aid=706> | 2026-08-02 |
| 设备套餐激活接口说明（aid=716） | <https://ezsuperfans.com/portal.php?mod=view&aid=716> | 2026-08-02 |
| 无感睡眠伴侣产品功能点概览（help/1849） | <https://open.ys7.com/help/1849> | 2026-08-02 |
| 睡眠体征监测组件（help/1850） | <https://open.ys7.com/help/1850> | 2026-08-02 |
| EP 设备属性查询机制示例（help/2053） | <https://open.ys7.com/help/2053> | 2026-08-02 |

## 2. 赛事流程与资源申请（aid=706）

1. 官方赛事系统报名并通过组委会审核后，企业开通萤石开放平台使用权限并组织线上命题答疑。
2. 硬件支持不强制限定具体型号，企业专家按方案评估匹配（含型号替换或数量调整）；非萤石硬件只要符合平台接入协议可用，但硬件支持只针对萤石品牌。
3. 平台使用原则：**必须以萤石开放平台为前提，核心音视频能力调用平台 API/SDK**；开发环境、语言和第三方库（PyTorch/sklearn 等）不限；可结合第三方大模型；自有模型可封装 API 自行调用。
4. 方案设计五板块：市场调研；技术架构与实现路径；硬件设备需求清单（型号+应用场景+部署方式）；软件平台权限与预算申请；预期成果与落地可行性。
5. **企业不提供数据集，参赛团队须利用硬件自行采集。**
6. 评审侧重：多模态不考量参数多少，侧重"老人好用、愿意持续使用、最终买单"的效果认证；隐私参考工信部合规要求，与用户接受度相关，不是技术评分主指标。
7. 赠送设备以萤石 C6C 400 万摄像机为主（<https://www.ys7.com/item/651492.html>）。
8. 新手入门文档：<https://ezsuperfans.com/portal.php?mod=view&aid=90>。

## 3. 平台使用要点（aid=718）

1. 设备报错 9048 = 设备套餐未激活；一个激活码仅激活一个设备通道。
2. 激活套餐报错 500 多为参数位置/参数错误；按"软件服务开通指南"的 curl 在 Postman 中验证。
3. 使用增值服务前必须先领代金券，否则账号欠费导致设备套餐失效。
4. 设备必须先成功接入萤石开放平台，才可调用平台语音、图像、视频能力。
5. 自研本地模型合规口径：模型基于萤石云获取的视频流训练、识别结果依赖萤石云数据，即算使用平台。
6. 视频流本地拉取可用**录像下载**：<https://open.ys7.com/help/4162>。
7. 参赛设备不支持对接算法训练平台；训练需求须自行拉流后本地完成。
8. 代金券可用于 AI 大模型服务平台（<https://token.ezviz.com/>）及开放平台各类付费产品。
9. 接入设备时报"设备不存在"= 设备未配网。
10. 平台全部开放设备接口清单：<https://open.ys7.com/help/737>。

## 4. 设备套餐激活接口（aid=716）

- 接口：`POST https://open.ys7.com/api/v3/mall/device/package/code/active`。
- Header：`accessToken`；Body 为对象数组（最大 100）：`packageDeviceId`（激活码 id）、`deviceSerial`（设备序列号）、`channelNo`（通常 1）。
- 返回 `activeCode`：0=激活成功；10005=激活码信息不存在或用户不匹配；40001=次数超限/套餐过期/激活码过期；50000=激活失败/服务异常。

## 5. 赛事资源边界（aid=712）

1. 赛事聚焦三大方向：**跌倒风险、心理健康、诈骗识别**。
2. 暂不提供居家环境类传感设备（水浸、烟雾等）。
3. 暂不提供跌倒检测雷达：仅开放"人员跌倒结果通知"告警，不提供底层信号点；鼓励从事前预判与预警角度攻关。
4. 毫米波雷达：**不开放原始数据**；允许团队自行采购第三方雷达。
5. 萤石手环：无开放接口，不支持使用。
6. 经边缘 AI 处理的摄像头无法接入萤石开放平台。
7. 第三方雷达数据无法直接上传萤石云平台；须自建本地平台做数据中转与融合。
8. 赛事统一主推设备：萤石 C6C 摄像机，支持萤石协议或国标协议即可。

## 6. 睡眠雷达开放能力（aid=706 + 组件仓文档）

aid=706 明确："萤石不提供雷达的信号点，目前跌倒雷达只提供是否跌倒结果，**睡眠雷达提供心率和呼吸率**"，并指向开放平台文档：

- 跌倒雷达文档：<https://open.ys7.com/help/3891>。
- 睡眠雷达文档入口：<https://open.ys7.com/help/2053>（设备云组件仓属性查询机制）。

设备云组件仓存在"萤石智家无感睡眠伴侣"产品线的完整功能点文档（help/1849、help/1850，2023-09-07 起）：

| 功能点 | 接口 |
|---|---|
| 呼吸率统计 | 每日呼吸率统计；每周/月呼吸率统计；每年呼吸率统计 |
| 心率统计 | 每日心率统计；每周/月/年心率统计；异常心率统计 |
| 睡眠统计 | 每日睡眠统计；每周/月/年睡眠统计 |
| 属性查询 | 分页查询单个属性历史记录；查询设备属性最新数据 |
| 设备管理 | 序列号获取 deviceId；手动刷新在线状态；平台用户设备绑定 |

已确认的接口形态（2026-08-02 按官方文档归档；均为 GET + accessToken）：

| 接口 | 路径 | 关键返回 |
|---|---|---|
| 每日心率统计（help/1839） | `/api/service/sleepDetector/v3/third/forward/huayi/analysis/v1/devices/{deviceId}/daily/average/hearts` | 日聚合 avg/max/min/count + 极高（≥160）/极低（<45）/不规则计数 + **minutesList 每 10 分钟 avg/max/min/ts 序列** |
| 每日呼吸率统计（help/1836） | `/api/service/sleepDetector/v3/third/forward/huayi/analysis/v1/devices/{deviceId}/daily/...` | 每 10 分钟呼吸率序列 + riskRank 睡眠呼吸风险等级（FREE/LOW/MIDDLE…） |
| 异常心率统计（help/1841） | 同上 huayi 转发族 | 时间范围内每 10 分钟异常心率区间 |
| 每日睡眠统计（help/1842） | `/api/service/sleepDetector/v3/third/forward/huayi/analysis/v1/devices/{deviceId}/daily/sleep` | score + list（stage/ts 分期时间线）+ items（name/value/referenceMin/Max/unit：睡眠时长、浅睡/深睡比例、深睡连续性、清醒次数） |
| 属性历史（help/1844） | `/api/service/sleepDetector/v3/third/forward/huayi/open/v3/devices/{deviceId}/properties/history` | 分页 data（heartRate/breathRate/state/createTime/ts），属性级序列 |
| EP 睡眠报告（help/2097，睡眠伴侣EP/森思泰克 whst） | `/api/service/sleepDetector/v3/third/whst/sleepReport/list`（deviceSerial + startDate/endDate） | 上床/入睡/醒来/起床时刻，在床/清醒/浅睡/深睡/睡眠总时长，离床次数与各次离床时间，体动次数，深/浅/清醒百分比与睡眠打分，平均心率/呼吸率，**freqRecordOutput 每 5 分钟心率/呼吸频率记录**，分期曲线（zipResponse 可裁剪），resultCode 可信度 |

注意存在两个文档族：huayi 转发族（deviceId 寻址）与 whst/EP 族（deviceSerial 寻址，"睡眠伴侣EP"与 CS-EP-SDNL1 的 EP 段一致）；哪一族适用于 SDNL1 须账号实测。相关接口还有心率异常监测使能设置（help/2082）、正常心率范围查询（help/2061）等，属性读写统一走 `/api/v3/device/otap/prop`（GET 查询 / PUT 设置）。

**边界**：上述为统计与属性级接口，不是 50 ms 级原始数据；文档示例存在字段语义矛盾（每日睡眠统计"睡眠时长"单位标"小时"而示例值 31380 更接近秒），单位/时间/缺失语义必须在真实响应上复核；CS-EP-SDNL1 与组件文档的型号兼容性、调用频率与费用须账号实测。组件仓功能点可能需要报备后才能调用。

E1 预开发已落地（REV-032）：四个 synthetic fixture（`tests/fixtures/sleep/huayi-*.synthetic.json`、`whst-sleep-report.synthetic.json`）、候选 mapping 示例（`configs/sleep/sdnl1-field-map.component-warehouse.example.json`）与回归测试（`tests/test_sleep_component_schema.py`）；fixture 只能产出 candidate，不能解锁 adapter。

## 7. 对项目决策的影响

| 事实 | 影响 |
|---|---|
| C6C 400 万为赛事赠送/主推设备 | REV-031 设备边界（2 × C6c）与赛事推荐一致，选型风险消除 |
| 睡眠雷达 HR/RR/睡眠统计 API 有官方文档 | SDNL1 数据接入从"完全未知"降级为"型号兼容性与粒度待账号验证"；睡眠侧首要动作变为账号内组件仓实测，书面确认问题同步收窄为粒度/字段/费用三项 |
| 雷达信号点/原始数据不开放 | SDNL1 的 50 ms 级原始数据确认不可得，矩阵对应行已按 Not assumed 归档 |
| 录像下载（help/4162） | 直播取流之外的第二条离线拉流路径，与现有离线管线形态匹配；开放范围/码流/费用待验证 |
| 核心音视频必须调用平台 API/SDK，自研本地模型合规 | 现有"拉流 → 本地 RTMPose/FunASR"架构满足赛事口径，无需改用平台 AI 服务 |
| 企业不提供数据集 | M2c 双机位采集规程（REV-031 行动项）成为唯一数据来源，优先级最高 |
| 手环无开放接口 | REV-001 起的手环 Exclude 获官方确认 |
| 评审侧重"老人好用、持续使用、买单" | V2 演示设计需突出无感、低打扰和家属端价值，而非指标数量 |
| 赛事三大方向（跌倒风险、心理健康、诈骗识别） | 与 REV-030 命名规范（风险提示/疑似高风险交互事件）一致；心理健康涵盖认知/抑郁筛查方向 |

## 8. 待办

- [ ] 比赛方案 PDF 原文仍需入库（REV-030 行动项，截止 2026-08-09）；一票否决条款按原文复核。
- [ ] 确认赛事代金券/激活码领取责任人与设备套餐激活流程（每台 C6c 一个激活码）。
- [ ] 验证录像下载能力对赛事 C6c 套餐的开放范围、码流规格与费用。
- [ ] 赛事账号内实测睡眠组件仓：SDNL1 适用文档族（huayi 转发族 vs whst/EP 族）与型号兼容性、每日统计字段清单与单位语义（含"睡眠时长"单位矛盾）、属性历史/freqRecordOutput 实际粒度、调用频率限制与费用。

## 9. 设备到位后的数据拉取链路（2026-08-02 按官方文档调研）

### 视频流

1. `POST https://open.ys7.com/api/lapp/token/get`（body：appKey/appSecret）→ accessToken，有效期 7 天，调用方负责缓存与刷新。
2. 确认设备已接入账号且套餐已激活（未激活报 9048；激活接口见第 4 节）。
3. `POST https://open.ys7.com/api/lapp/v2/live/address/get`（form 编码），关键参数：
   - `deviceSerial` + `channelNo`（默认 1）；
   - `protocol`：1-ezopen / 2-hls / 3-rtmp / 4-flv（默认 1）；
   - `quality`：1=高清（主码流）/ 2=流畅（子码流）；
   - `expireTime`：30 秒～720 天（仅 hls/rtmp/flv）；
   - `type`：1=预览 / 2=本地录像回放 / 3=云存储录像回放（回放仅 rtmp/ezopen/flv）；
   - `startTime`/`stopTime`：回放区间（云存储限同一天）；`supportH265`、`playbackSpeed`（仅 flv 回放）。
   - 返回 `data.url` 与 `data.expireTime`。
4. 服务端拉流建议 protocol=2（hls）或 4（flv）：均为 HTTP 系，PyAV/FFmpeg 可直接消费，与现有 `capture-stream`/`qualify-stream`/`run-stream-session` 工具链兼容；`quality=1` 用于验证是否真给 2K 主码流。
5. 控制台-设备管理-直播地址可复制地址手动验证。
6. 回放与批量获取：type=2/3 回放地址；SDK 侧 SD 卡/云录像下载 MP4（help/4162）；服务端批量另有视频采集服务（回放/即时/预约录制接口），需单独开通。
7. 额度与费用：免费试用 3 路并发、1M 码率、120 天；标准流带宽计费，代金券可抵扣。

### 睡眠仪

1. 文档族判定：`GET https://open.ys7.com/api/service/sleepDetector/v3/third/huayi/deviceId?deviceCode=<deviceSerial>`（help/1846）能返回 deviceId → 走 huayi 族统计接口；否则试 whst 族 `sleepReport/list`（直接用 deviceSerial）。
2. huayi 族：每日心率（help/1839）/每日呼吸率（help/1836）/每日睡眠统计（help/1842）/异常心率（help/1841）＋属性历史（help/1844）＋最新属性（help/1845）。
3. whst/EP 族：`GET /api/service/sleepDetector/v3/third/whst/sleepReport/list?deviceSerial&startDate&endDate`（help/2097）。
4. 原始响应按 E2 原始健康数据处理：owner-only 保存原始 JSON，脱敏副本进 `profile-sleep`/`assess-sleep-route`；真实响应到达前不改 policy。

## 10. 首次真机连通记录（2026-08-04，交互式 API 验证，非正式 run）

凭据与序列号不落档，以下只记录事实与接口行为。

账号设备清单：

- C6c 一台在线：型号确认 CS-C6c-V101-1J4WF，固件 V5.3.8 build 260513，WiFi 在线。
- 睡眠仪一台在线：型号 **CS-EP-SDHY1（小贝壳）**，非本文档与能力矩阵冻结的 CS-EP-SDNL1；设备边界差异待 REV 确认。

摄像头实测：

- `POST /api/lapp/device/encrypt/off` 可远程关闭视频加密（解除直播地址 60019 阻断）。
- `POST /api/lapp/camera/video/sound/set`（enable=1）麦克风开关可用。
- `POST /api/lapp/v2/live/address/get`（protocol=2、quality=1）返回 m3u8，但因**设备套餐未激活**，播放列表只含 `ErrCode/9048_0.ts` 占位错误段（表现为约 512px、无音轨的占位画面）；protocol=4（flv）地址 404。真实主码流分辨率/帧率/音轨须在套餐激活后复测。

睡眠仪实测（huayi 族，deviceId 为绑定序列号的数字后缀）：

- 每日心率统计 200：日聚合 + minutesList 每 10 分钟序列，当日已有实测数据。
- 属性历史 200：总记录逾千条，**记录间隔约 1 秒**（远优于分钟级预期），heartRate/breathRate 实测返回；`state` 为字符串枚举（实测 "STATIC"），与文档示例的整型不一致——真实语义须按响应修正。
- 每日睡眠统计 200 但仅返回 deviceId：设备新装，尚无完整夜间数据。

结论：睡眠数据通路已通（E2 级真实接口）；摄像头取流仅剩设备套餐激活（代金券 + 每通道一个激活码）一个前置；账号内暂无第二台 C6c，双机位基线缺一台设备。

## 11. 9048 排查与设备能力集（2026-08-04 补充）

9048 现象：激活设备套餐后 HLS 播放列表仍只返回 `ErrCode/9048_0.ts` 占位段；同一时刻 ezopen 地址（protocol=1）可正常生成（`ezopen://...hd.live`，仅格式化不校验套餐）。

可能原因（按概率）：

1. 激活未真正成功——FAQ 记录激活时报 500 多为参数位置/参数错误，须以 `activeCode=0` 为准；
2. 激活的是 APP 侧会员/云存储，而非开放平台设备套餐（云直播）；
3. 未先领代金券就使用增值服务，账号欠费导致套餐失效（FAQ 第 3 条）；
4. 激活错设备序列号或通道号；
5. 套餐类型不含云直播标准流。

排查动作：控制台-设备管理查看设备套餐状态/类型/有效期与账户代金券余额；或以激活码重调 `POST /api/v3/mall/device/package/code/active` 看 activeCode（0=成功；40001=次数超限/套餐过期/激活码过期；10005=激活码不存在或用户不匹配）；控制台云直播画面是否可播放可区分设备侧与 API 侧问题。

设备能力集实测（`POST /api/lapp/device/capacity`，2026-08-04）：

- 音频：`support_audio_onoff=1`、`support_device_sound=1`、`support_talk=1`；
- 视频：`video_quality_capacity` 四档（videoLevel 1～4，streamType 1），`support_resolution=16-9`；
- 录像：`support_disk=1`（SD 卡）、`support_replay_download=1`（SD 卡录像下载）、`support_fullday_record=1`、`support_cloud=1`；
- 云台/智能：`support_ptz=1`、`ptz_preset=1`、人形/手势检测若干；
- 网络：`support_wifi_5G=1`、`support_channel_number=1`（单通道）；
- 其他：`support_encrypt=1`、`support_device_Distortion_Correction=1`（畸变校正）。

## 12. 套餐激活与 9053（2026-08-04 补充）

- 用赛事激活码调 `POST /api/v3/mall/device/package/code/active`（packageDeviceId + deviceSerial + channelNo=1）返回 `activeCode=0 成功`——证明此前用户侧的"已激活"并未真正生效。
- 激活后 HLS 占位段由 `ErrCode/9048` 变为 **`ErrCode/9053`**（quality=1/2 均同）；ezopen 地址（protocol=1）始终可正常生成。
- 9053 无公开文档定义。按 90xx 族（9048/9049=并发/套餐类）推断，候选原因：① 标准流（HLS/RTMP/FLV）为计费服务，账号无代金券/余额覆盖带宽费；② 服务传播延迟（部分服务首开最长约 2 小时生效）；③ 套餐类型不含标准流协议。
- 待办：控制台领取代金券并查余额；控制台云直播画面可否播放（区分设备侧/标准流服务侧）；必要时按 9053 向赛事支持或工单求证。
- 激活码用量：已用 1 个（本机通道 1），余 4 个；第二台 C6c 到位后需再用 1 个。

## 13. 睡眠真实 E2 首跑（2026-08-04）

真实账号数据首次进入 profile/route 链路（原始导出存 `data/raw/sdhy1-e2/`，0600，不落档细节）：

- 属性历史 50 条 profile（run `20260804T075034Z-ff7d8cbf`）：container `$.data`，5 字段，3 个映射候选。
- Route 评估（run `20260804T075035Z-f2965eab`，policy v1-sleep-route-2026-08-04 + `configs/sleep/sdhy1-field-map.e2.json`）：`heart_rate_bpm`、`respiratory_rate_bpm`、`measurement_at` 三者 **blocked_semantics，仅缺 missing_semantics**；其余 16 个 direct 未观测；derived 全关；`values_persisted=false`。三个 P0 字段距 ready_for_adapter 只差缺失值语义一项确认。
- 属性历史全量约 5,000 条（当日新装），state 实测取值 STATIC/MOTION（字符串枚举），记录间隔约 1 秒；500 条样本中未见零值记录，"无人/离床"的缺失表达需待空房时段窗口再观测。
- 每日心率统计正常返回；每日呼吸率统计确切路径为 `.../devices/{deviceId}/average/breaths`（无 `/daily/` 段，响应字段为 `minuteList` 非 `minutesList`，含 riskRank/sleepDatetime/wakeupDatetime），当日两次 500 未取到，待重试；每日睡眠统计待完整夜间数据。
- 激活后 HLS 仍 9053（激活起约 1 小时），继续等待传播或代金券/余额核查。

## 14. 摄像头取流打通与首个 E2 采集（2026-08-04）

9053 在激活码激活并完成传播后解除（激活起约 1 小时后恢复）。实测：

- FLV 地址（protocol=4、quality=1、supportH265=1）返回**主码流 HEVC 2560×1440@15fps + AAC 16 kHz 单声道音轨**；此前"512px 无音轨"均为 9048 占位段假象。
- `capture-stream` E2 首采成功（run `20260804T075947Z-76c9a6dc`）：20 秒、300 视频包（15 fps）、310 音频包、duration_limit 正常终止，`capture_artifact_ready=true`、`same_container_multimodal_ready=true`。
- `probe-media` 复核（run `20260804T080037Z-47f4fd18`）：视频 PASS、音轨 present、单视频单音频。
- 直播地址有效期最长可设 720 天；本次测试地址 7 天有效。
- 未关闭项：实际帧率 15（非 25），"网传帧率自适应"实锤；H.265 为主码流默认（可支持 H264 待测）；长稳/双机位/夜视未测；RTSP/ONVIF 仍不可用（萤石云私有协议）。

## 15. SDHY1 数据面完整调研（2026-08-04）

实测与文档交叉确认，SDHY1 可用数据面（whst 族接口文档标称 SDNL1 专用，但 sleepReport/bodyDetect 对 SDHY1 实测可用）：

已实测 API 通（E2）：

| 数据 | 接口 | 状态 |
|---|---|---|
| 心率（约 1 秒属性序列 + 每 10 分钟统计 + 日聚合 + 极高/极低/不规则计数） | huayi 属性历史（help/1844）、每日心率（help/1839）、异常心率（help/1841） | 已返回真实数据 |
| 呼吸率（约 1 秒属性序列 + 每 10 分钟统计 + riskRank 呼吸风险等级） | huayi 属性历史、每日呼吸率（help/1836，`average/breaths`，字段 `minuteList`） | 属性历史已有数据；每日接口当日 500 待重试 |
| 在床/离床事件流（messageType 1=在床 2=离床） | whst bodyDetect（help/2098，offset/limit 分页） | API 通，暂无事件（白日新装） |
| EP 睡眠报告（上床/入睡/醒来/起床、在床/清醒/浅睡/深睡/总时长、离床次数与各次时间、体动、深浅醒百分比+打分、平均心率/呼吸率、5 分钟频率记录、分期曲线、睡眠问题、resultCode 可信度 + 周期对比 aggregation） | whst sleepReport/list（help/2097） | API 通，待首个完整夜 |
| 每日睡眠统计（score + 分期时间线 + 指标集） | huayi daily/sleep（help/1842） | 待首个完整夜 |
| 周/月/年统计（心率/呼吸率/睡眠） | huayi help/1840/1843 等 | 文档确认，待数据积累 |
| 最新属性 | huayi help/1845 | 文档确认 |

文档有但 SDHY1 待验证：otap prop 配置/状态类（睡眠监测时间段、人体存在/体动灵敏度、离床未归时长与使能、长时间未体动、心率异常使能、实时有无人、提醒方式与计划）——文档标称仅 SDNL1 适用，实测 `GET /api/v3/device/otap/prop` 返回 200 但 data 为 null，SDHY1 大概率未实现该属性层。

官方明确不可得：原始雷达信号点。

与 REV-031 可保留指标对照：在床/离床、上床与离床时间、夜间离床次数与时长、睡眠报告/指数、分钟级心率/呼吸率（实际优于分钟级）、心率/体动异常、数据完整率——全部有对应接口；入睡潜伏期、PSG 分期、AHI、HRV、血氧维持不可承诺。

## 16. 资格门与真机多模态首跑（2026-08-04）

- `qualify-stream` 三次独立开流（run `20260804T081325Z-d2c3e261`）：3/3 ready、0 失败，轨道签名一致（HEVC 2560×1440@15 + AAC 16 kHz mono），`repeated_capture_gate_ready=true`。真实码流格式稳定性首次验证；断线恢复/长稳仍 false。
- 25 秒基线采集（run `20260804T081528Z-b0c890ac`）：375 视频包/388 音频包，双 ready。
- 真机多模态首跑（run `20260804T081613Z-4e328905`，CPU）：`same_container_pts` 链路消费真实 C6c 容器，124 采样帧 `pose_detection_count=0`、VAD 0 语音段、13 个融合窗口，RTF 0.30。**该 clip 即为 M2c C01（白天/近/空房静态）首个真机样本：全链 124 帧零人物误激活**。远场语音、夜视与有目标场景未测。
- 结论：C6c 视频+音频 → 采集 → 同容器 PTS → 姿态/VAD/ASR → 融合窗口的完整链路在真实设备媒体上跑通；Yolo26n 基线用于本次，RTMPose 对照待跑。
