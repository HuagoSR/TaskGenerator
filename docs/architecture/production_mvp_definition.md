# Production MVP Definition

> 状态：`reference`
> 职责：说明当前可运行的 R9 production contract 与 R10 的准入边界；不记录历史 campaign 细节。

## Current Production Contract

R9 是当前已实现的内部批处理生产能力。它从受控 Git release 构建 factory/eval Linux/amd64 镜像，在 huago-cone 上以单并发运行，并将运行数据、secrets 与 release metadata 分离。

当前 release 语义：

- `current` 与 `previous` 保持可查询、可回滚；R9/R7 历史结果均只读。
- release context 不得包含 `.env`、provider key、Codex authentication、artifacts、缓存或原始模型输出。
- factory/eval 应通过网络关闭、只读根、无凭据的 Linux/amd64 parity 与对应 smoke。
- 发布和激活前可用磁盘不得低于 **95 GiB**；清理只能按独立授权作用于 TaskGenerator 资源或未使用 BuildKit cache，不能触及其他项目。
- provider、solver 和 grader 运行必须保留首错、使用隔离 workspace，并区分基础设施失败与任务业务失败。

## Current Readiness Semantics

| 状态 | 含义 | 不代表 |
| --- | --- | --- |
| `generated` | proposal 或 package 已产生 | 结构或职业有效性。 |
| `structurally_valid` | schema、关系和合同通过 | 真实工作情景。 |
| `candidate_ready` | candidate package 可执行且通过 package 门禁 | solver 成功、专业有效性或训练准入。 |
| `production_ready_for_evaluation` | cohort 满足本轮固定生产数量和完整性规则 | 默认 solver、训练或 release promotion。 |
| `behaviorally_validated` | 仅在未来定义完整模型行为证据后使用 | 人工专家结论。 |

R7 的 5/10 冻结结果没有达到 `production_ready_for_evaluation`，不得用于 partial evaluation 或与旧 cohort 混合。

## R10 Admission Boundary

R10.0–R10.8 已产生四道用户验收任务、两道 compiler-revision 任务及完整行为证据。R10.8 最终结论是 `evaluator_revision_required`，不是基础设施 incomplete，也不是扩题准入。R10.9 改用 World-First / Task-Mining 小实验；R10 不能使用 R9 的普通 `candidate_ready` 语义跳过情景真实性验证。未来 Scenario-First task 至少需要：

1. 公开可追溯 Work Seed 与 Professional Rule Set；
2. 在任务出现前冻结的 teacher-only 工作世界及 candidate 业务材料；
3. 来源约束的 Professional Skill 与自然难度计划；
4. 与 world ledger 隔离的 Task Mining 和 Teacher Truth 重建；
5. Task Decision Matrix、task-specific rubric 与三档 Judge 校准；
6. 来源追溯、可解性、答案泄漏、文件可用性、交付合同和 matched 行为验收。

R10.9 已证明 World-First 链可以产出四个静态通过且被两种 Solver 完成的任务，但正式 paired review 的 Judge 边界不稳定，未满足扩展条件。十题 production cohort 继续关闭；R10.9 不改变 R9 服务器发布器，也不授权训练、public release 或 promotion。

R10.10 当前是生成侧 rubric 编译验证，不是生产扩展。它读取两个冻结 R10.9 开发任务的要求、候选材料与监督，生成独立 V2 rubric 并审查；不读取 Solver 答案或 GDPval 内容。审查通过仅表示 LLM proxy 的初步支持，不授予评分稳定性、十题 cohort、Skill promotion 或生产 release 准入。新增任务和行为验证须另行规划。

## Non-Goals

- 不把静态 quality score、LLM proxy 或单个模型结果解释为专家有效性。
- 不因模型低分修改冻结任务或进行低分重抽。
- 不将 GDPval、私有工作材料或历史 R9/R7 包作为新的 Work Seed 输入。
