# TaskGenerator 文档索引

> 状态：`active`
> 职责：定义文档入口、职责和生命周期；不记录运行状态。

## 阅读顺序

1. [`../项目概要.md`](../项目概要.md)：唯一项目级状态源与 R10 研究边界。
2. [`../AGENTS.md`](../AGENTS.md)：工程、安全与操作边界。
3. [`architecture/system_architecture.md`](architecture/system_architecture.md)：当前实现与目标架构。
4. [`architecture/global_interface_contracts.md`](architecture/global_interface_contracts.md)：稳定合同摘要与 R10 草案。
5. [`architecture/production_mvp_definition.md`](architecture/production_mvp_definition.md)：现行生产状态与准入语义。
6. [`architecture/pipeline_reconstruction_problem_statement.md`](architecture/pipeline_reconstruction_problem_statement.md)：真实性问题定义。
7. [`architecture/pipeline_reconstruction_optimization_plan.md`](architecture/pipeline_reconstruction_optimization_plan.md)：R10 活跃计划。
8. [`operations/pipeline_reconstruction_runbook.md`](operations/pipeline_reconstruction_runbook.md)：当前停止点与未来执行前置条件。
9. [`archive/README.md`](archive/README.md)：历史阶段材料索引。

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
- `docs/archive/` 保留历史计划、报告与 handoff；Git 历史承担旧活跃文档的精确追溯。
- 任务包、provider 输出、执行日志、截图和临时诊断只写入 `artifacts/`。

R10 是当前活跃研究主线；R9/R7 是冻结的历史生产证据。当前 R10 文档采用“Scenario Bible → factory-side 专业 Skill → 派生证据包”的路线：已有 Bible 保持冻结，后续 Skill 与任务实现必须逐阶段验收。不得把 archive 或 artifacts 的内容解释为当前授权或当前生产状态。
