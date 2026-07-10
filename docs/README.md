# TaskGenerator 文档索引

> 状态：`active`
> 职责：定义文档入口、生命周期和归档规则，不承担项目状态记录。

## 阅读顺序

1. [`../项目概要.md`](../项目概要.md)：唯一项目级状态源。
2. [`../AGENTS.md`](../AGENTS.md)：工程执行、安全和仓库边界。
3. [`architecture/system_architecture.md`](architecture/system_architecture.md)：当前稳定技术架构。
4. [`architecture/global_interface_contracts.md`](architecture/global_interface_contracts.md)：全局接口契约。
5. [`architecture/production_mvp_definition.md`](architecture/production_mvp_definition.md)：当前 production contract。
6. [`archive/README.md`](archive/README.md)：历史计划、handoff 和报告索引。

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

未来如需详细 workstream 计划，可在执行期创建局部文档并由《项目概要》链接；workstream 完成后必须迁入 archive，不能继续占用活跃架构目录。

当前 workstream：[`handoffs/MILESTONE_E_WORKSTREAM_2026-07-10.md`](handoffs/MILESTONE_E_WORKSTREAM_2026-07-10.md)，状态为 `awaiting_external_authorization`。
