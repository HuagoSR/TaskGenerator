# TaskGenerator 文档索引

> 状态：`active`；核对日期：2026-09-10。
> 职责：定义文档入口、职责和生命周期；不记录运行状态。

## 阅读顺序

1. [`../项目概要.md`](../项目概要.md)：唯一项目级状态源与 R10 研究边界。
2. [`../AGENTS.md`](../AGENTS.md)：工程、安全与操作边界。
3. [`architecture/system_architecture.md`](architecture/system_architecture.md)：当前实现与目标架构。
4. [`architecture/global_interface_contracts.md`](architecture/global_interface_contracts.md)：当前接口索引、代码入口与历史兼容。
5. [`architecture/production_mvp_definition.md`](architecture/production_mvp_definition.md)：生产边界与证据语义。
6. [`architecture/pipeline_reconstruction_problem_statement.md`](architecture/pipeline_reconstruction_problem_statement.md)：真实性问题定义。
7. [`architecture/pipeline_reconstruction_optimization_plan.md`](architecture/pipeline_reconstruction_optimization_plan.md)：造题研究主线与有限评分支持；后续实验须另定范围。
8. [`operations/pipeline_reconstruction_runbook.md`](operations/pipeline_reconstruction_runbook.md)：评分暂停边界、只读查看与后续实验授权要求。
9. [`research/agent_task_production_harness_20260907.md`](research/agent_task_production_harness_20260907.md)：造题 harness 调研、来源限制与设计依据；实现及最新单题闭环结果见概要。
10. [`archive/README.md`](archive/README.md)：历史阶段材料索引。

## 生命周期

| 状态 | 用途 | 维护规则 |
| --- | --- | --- |
| `active` | 当前入口、架构、合同或计划 | 事实变化时同步更新。 |
| `reference` | 稳定约束或示例 | 仅在接口变化时更新。 |
| `historical` | 已关闭阶段的原始记录 | 原则上只读，不覆盖当前状态。 |
| `proposed` | 已批准但尚未实现的设计 | 必须明确标记为不可执行。 |

## 放置规则

- 《项目概要》只管理目标、当前证据、瓶颈和路线。
- `docs/architecture/` 只管理当前或 proposed 的技术结构与合同。
- `docs/operations/` 只管理可执行边界、停止条件和恢复规则。
- `docs/research/` 保存来源明确的调研与研究判断，不重复记录 campaign 状态，不作为生产案例输入或运行授权。
- `docs/archive/` 保留历史计划、报告与 handoff；Git 历史承担旧活跃文档的精确追溯。
- 任务包、provider 输出、执行日志、截图和临时诊断只写入 `artifacts/`。

只想了解项目进展时，先读项目概要；开发时再查架构与代码合同；执行前查 runbook。忽略目录中的私有产物链接只在本机可用，不视为共享仓库缺失文件。旧活跃文档通过 Git 历史追溯，不另复制归档快照。
