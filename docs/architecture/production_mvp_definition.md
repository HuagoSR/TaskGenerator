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

R10.0–R10.2 的离线合同、公开 seed 和 teacher-only Bible 已实现；R10 的候选任务、行为验收仍是 `not_implemented`。R10 不能使用 R9 的普通 `candidate_ready` 语义跳过情景真实性验证。未来 Scenario-First task 至少需要：

1. 公开可追溯 Work Seed 与 Professional Rule Set；
2. teacher-only Scenario Bible；
3. factory-side 专业 Skill selection 与带父 Bible 追溯的派生证据包；
4. Task Decision Matrix 与 task-specific rubric；
5. 来源追溯、可解性、答案泄漏、文件可用性和交付合同检查；
6. 四题 pilot 的多模型行为验收。

只有 R10.6 pilot 的全部准入条件通过后，才可定义十题 production cohort。R10 不改变 R9 服务器发布器，也不授权任何 provider、solver、grader、训练、public release 或 promotion 操作。

## Non-Goals

- 不把静态 quality score、LLM proxy 或单个模型结果解释为专家有效性。
- 不因模型低分修改冻结任务或进行低分重抽。
- 不将 GDPval、私有工作材料或历史 R9/R7 包作为新的 Work Seed 输入。
