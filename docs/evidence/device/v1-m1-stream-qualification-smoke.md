# V1-M1 重复开流资格门 E1 报告

状态：Qualification Passed for E1；不构成 RTSP、C6c、断线恢复或长稳验收

测试日期：2026-07-23（运行 ID 使用 UTC 时间）

实现提交：`fea40f7`；轨道签名加固：`c8bda16`

## 1. 目的与输入

验证三个独立 HTTP 连接能否分别生成有界、owner-only、同容器 A/V artifact，并由父报告严格检查请求 readiness 和完整轨道签名一致性。

- 输入：被 Git 忽略的 +250 ms 音频起点确定性 A/V fixture。
- transport：仅运行期间存在的 loopback HTTP server；endpoint 通过进程环境提供。
- 正式 qualification：clean `c8bda16`。
- 下游复核：Slurm L40 job `1785`，clean `c8bda16`。

## 2. Qualification 结果

Run：`runs/v1-stream-qualification-e1/20260722T234430Z-1f2b14c9`

| 项目 | 结果 |
|---|---:|
| status / issue | completed / 0 |
| evidence / source / scheme | E1 / fixture / http |
| attempts | 3 |
| requested / minimum per attempt | 2000 / 1500 ms |
| captured / ready / not-ready / failed | 3 / 3 / 0 / 0 |
| captured span | 2050 / 2050 / 2050 ms |
| attempt elapsed | 871 / 618 / 601 ms |
| audio start offset | +250 / +250 / +250 ms |
| unique track signature | 1 |
| signatures consistent | true |
| scheduled reopen sequence proven | true |
| repeated capture gate ready | true |

稳定轨道签名：

- video：FFV1、time base `1/1000`、810×1080、`yuv420p`、10 fps；
- audio：PCM S16LE、time base `1/1000`、16 kHz、mono。

三个 raw artifact 的 SHA-256 分别为：

1. `aaaed1fcda80a516fd6a145755240ffeba887903c5eee49610180955af055321`
2. `70b5f3d3408ad3c3b0125c7e1cbb12ed9508fd9f32749fdc04410a0a8d1b0f38`
3. `f999ee41bd360b35b227cfe2408e466de5e5ab0818a7887f66fc8ede2d1872f1`

它们来自相同 fixture，但独立 Matroska mux 的字节摘要不要求相同；资格门比较媒体轨道事实，不把 byte equality 当稳定性。

## 3. 安全与固定 false 边界

- run/子目录和全部文件分别为 `0700/0600`。
- endpoint、端口、环境变量名、源文件名、本地 home、用户名、token/password 和 Risk/Alert true 扫描均为 0 命中。
- `m2c_capture_bundle_ready=false`。
- `involuntary_disconnect_recovery_proven=false`。
- `long_running_stability_proven=false`。
- `network_impairment_tolerance_proven=false`。
- `device_platform_integration_proven=false`。

HTTP server 在客户端达到媒体时长后看到 connection reset，只表示客户端有界停止读取；本报告不把它解释为被测断流或恢复。

## 4. 关键摘要

| 产物 | SHA-256 |
|---|---|
| manifest | `aa6d83c295f3410970767c553ee68856a3a77250ed4d61022a1e7292b48846f3` |
| source assets | `832357d543fb00f600c7b51d1e5d6134cb859b30e536c55122e63fd376a5ae14` |
| observations | `799532ccf31d9d1f54e12db6cd181ea63efe7b14d1e599feb95dde14688a0006` |
| capture report 001 | `4ff4ab3c891132caa0cd675396f302267297c756ab1e8d4c4f34552ce86bac7d` |
| capture report 002 | `dad1e6bc958b14c100668d4ea78e991b32e74d4e2e8dc2616d13e4c18bc36afb` |
| capture report 003 | `5e337c0af30b95db9901f3f8df69004bd54346285f0488dc89bec55e95005c69` |
| qualification report | `e077a2f25e46f19f2c8e66a790d6d3a14034f8ee0e2cd7da02222382f4538e2b` |

## 5. 自动化验证

- 全量：160 passed。
- 新增覆盖：三次真实 PyAV open/remux、父/子 ledger、owner-only 权限、固定失败码、一次失败后继续、轨道签名漂移、父报告计数/gate 篡改、路径 traversal、video-only fail-closed 和 parser 默认值。
- 原单次 capture 的 post-probe 异常现在也只发布固定 `output_verification_failed`，不再回显内部异常 message。
- `compileall`、全部 shell/sbatch `bash -n`、`pip check`、`git diff --check` 通过。

## 6. L40 下游复核

Slurm job `1785` 使用第 3 个 qualification child artifact，验证重复开流产物可以不经转码直接进入现有同容器姿态/语言 Pipeline：

| 项目 | 结果 |
|---|---:|
| state / exit / elapsed | COMPLETED / 0:0 / 45 s |
| node / accelerator | hepnode1 / NVIDIA L40 |
| code / clean | `c8bda16` / true |
| submit commit / checkout bound | true / true |
| runtime owner-only | true |
| input SHA-256 | `f999ee41bd360b35b227cfe2408e466de5e5ab0818a7887f66fc8ede2d1872f1` |
| run | `20260723T000524Z-3b383dbd` |
| status / issue | completed / 0 |
| input layout / A/V / offset | same-container PTS / true / +250 ms |
| duration / sampled frames | 2000 ms / 10 |
| pose detections / speech segments / windows | 40 / 1 / 2 |
| processing / cold-start RTF | 1.018485 / 19.744673 |
| CUDA peak allocated | 2120.295 MB |

输入摘要与 qualification 第 3 个 raw 完全相同，没有生成替代媒体。Pipeline manifest / report SHA-256 分别为 `f4e989ac779ec4614192a0e939aead4180a8ce570fb71a8ac3d535c038fb71a4` / `2918d6713bd847871b1d9a852d3197f5e3f5e49045fc46f868d3d2ebce3a5145`。run 目录/文件保持 `0700/0600`；endpoint、端口、环境变量名、源文件名、本地 home/用户名、secret 和 Risk/Alert true 扫描 0 命中。

processing RTF 略高于 1，只是 2 秒短 clip 上的 E1 观测，不作为实时性能通过门；模型加载仍单列在 cold-start RTF 中。job 只证明一个 qualification child 能被下游模型消费，不把单 child 推理外推成三次推理稳定性、实时流处理或设备接入。

## 7. 结论

E1 重复开流资格门通过：三个独立连接均形成可消费的同容器 artifact，格式签名稳定，失败与隐私边界可审计。

仍未证明 RTSP、C6c/萤石鉴权、非自愿断线恢复、丢包/抖动、长稳、真实设备时钟、M2c 数据包、风险或告警。
