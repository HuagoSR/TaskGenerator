# TaskGenerator 文档索引

> 状态：`active`
> 职责：定义文档入口、生命周期和归档规则，不承担项目状态记录。

## 阅读顺序

1. [`../项目概要.md`](../项目概要.md)：唯一项目级状态源。
2. [`../AGENTS.md`](../AGENTS.md)：工程执行、安全和仓库边界。
3. [`architecture/system_architecture.md`](architecture/system_architecture.md)：当前稳定技术架构。
4. [`architecture/global_interface_contracts.md`](architecture/global_interface_contracts.md)：全局接口契约。
5. [`architecture/production_mvp_definition.md`](architecture/production_mvp_definition.md)：当前 production contract。
6. [`architecture/pipeline_reconstruction_problem_statement.md`](architecture/pipeline_reconstruction_problem_statement.md)：下一轮流水线重构的问题定义与证据边界。
7. [`architecture/pipeline_reconstruction_optimization_plan.md`](architecture/pipeline_reconstruction_optimization_plan.md)：当前活跃重构 workstream 的阶段、合同、指标、门禁和 promotion 计划。
8. [`operations/pipeline_reconstruction_runbook.md`](operations/pipeline_reconstruction_runbook.md)：重构实验的授权、执行、盲化、评测、服务器与 rollback 治理手册；当前是否存在可执行 campaign 以该文档和《项目概要》的最新状态为准。
9. [`archive/README.md`](archive/README.md)：历史计划、handoff 和报告索引。

## 生命周期

| 状态 | 含义 | 维护规则 |
| --- | --- | --- |
| `active` | 当前入口或当前技术合同 | 对应事实变化时必须更新 |
| `reference` | 仍有复用价值，但不管理项目状态 | 接口或约束变化时更新 |
| `historical` | 已完成阶段的原始记录 | 原则上只读 |
| `superseded` | 已被后续证据替代 | 保留用于追溯，不作为决策依据 |

## 放置规则

- 宏观目标、阶段台账、当前瓶颈和 A–F 路线只写入根目录《项目概要》。
- 当前稳定架构与接口放在 `docs/architecture/`。
- 小型静态示例放在 `docs/examples/`。
- 已完成阶段材料统一放在 `docs/archive/phases/phaseXX/`。
- 旧基础路线、schema 历史和 Pipeline A/B 早期 handoff 放在 `docs/archive/foundations/`。
- 阶段性报告及图片放在 `docs/archive/reports/`。
- 运行生成物、日志、任务包、grader 输出和临时报告只写入 `artifacts/`。

当前活跃 workstream 为流水线重构，执行计划由《项目概要》链接并保存在 `architecture/pipeline_reconstruction_optimization_plan.md`。workstream 完成后必须迁入 archive，不能继续占用活跃架构目录或继续承担当前状态管理职责。

Milestone E 和 Milestone F 财务任务生产均已完成并归档；F4.3 真实执行随后重新打开了任务质量与交付合同问题。当前不再沿旧生产扩题，而是按活跃重构计划推进。宏观状态仍只由根目录《项目概要》管理。
