# 康盾 KangShield

社区独居老人多模态监测与风险预警项目。

当前采用两阶段交付：

- V1：快速探索信息采集、模型可行性和端到端数据形态。
- V2：基于 V1 结论设计并实现最终比赛提交版本。

当前阶段只建设文档和 V1 信息采集探索，不提前固化完整业务系统。

## 文档入口

- [工程架构与模块设计](docs/architecture.md)
- [信息侧详细技术路线](docs/information-side-technical-route.md)
- [设备能力矩阵](docs/device-capability-matrix.md)
- [里程碑与验收门](docs/milestones.md)
- [Review 记录](docs/review-log.md)
- [V1 信息采集与模型探索](docs/v1-information-acquisition.md)

## V1 初步开发

V1 信息侧采用“运行目录 + JSON/JSONL 产物”的离线优先实现。开发入口、命令和产物结构见[信息侧详细技术路线](docs/information-side-technical-route.md)。

## 当前硬件边界

- 萤石摄像头：CS-C6c-V101-1J4WF，带麦克风。
- 萤石睡眠仪：CS-EP-SDNL1。

手环、门锁、红外/人体存在传感器不属于当前已提供设备，相关指标只能保留接口或明确为暂不可得。
