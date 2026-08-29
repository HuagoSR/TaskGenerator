# R10 Scenario-First 流水线优化计划

> 状态：`active`
> 职责：定义下一轮实现与验证顺序。R9/R7 是冻结历史证据，不是当前执行计划。

## 目标

将 TaskGenerator 从“Skill + Motif 驱动的任务包生成器”重构为“公开工作种子驱动的职业情景编译器”。目标不是增加文件数量，而是稳定生成具有业务因果、自然信息不完整性、职业交付物和模型区分度的多文件任务。

首轮范围固定为四题：审计两题、采购两题。所有 Work Seed 仅使用公开、可追溯材料。R10 在完成离线实现和新授权前不得执行外部调用。

## Design Principles

- 先有业务事件和完整世界，再有候选文件与任务；不从 motif 直接拼接故事。
- 专业规范约束判断，不冒充组织事实；Scenario Bible 是唯一业务事实权威。
- 候选材料展示事实、记录和不确定性，不能直接展示答案标签。
- Skill 约束专业深度、能力覆盖和错误归因；Motif 用于关系标签、配额与分析。
- 程序负责事实边界、投影、一致性、隔离、路径和状态；LLM 只可提出种子抽象、情景和表达。
- 任务只能在静态准入和多模型行为准入都通过后进入候选题库。

## Workstreams

### R10.0 — Offline contracts and regression corpus — `implemented`

已实现六个严格 V1 合同、规范化 SHA、report-only 静态 admission validator 与不含私有任务内容的 R7 诊断 fixture。当前验证来源追溯、世界引用/时间线、投影规模与事实映射、正常背景比例、答案标签与直接 teacher-treatment 泄漏、决策证据覆盖和不确定性处理。该层不读取密钥、不调用 provider、不抓取来源、不物化文件，也不改变 R9/R7。

### R10.1 — Public Work Seed admission — `implemented / public-source only`

已建立公开来源目录、候选 seed、规则集和离线 admission CLI。每个领域审查四个候选、接纳两个：审计为公司自产信息可靠性与控制缺陷组合评估；采购为简易采购价格合理性与商业交付验收处置。所有种子描述角色、触发、目标、输入、自然问题、交付物和受众，并明确“规则/方法论”与“未来组织事实”的边界。该轮通过直接公开来源调研完成，未调用 Tuzi 或 DeepSeek；若未来语义批次使用 provider，仍按整批冻结和整批重启规则执行。

### R10.2 — Scenario Bible compiler — `implemented / teacher-only`

已实现 teacher-only Bible compiler、静态 validator 和单批官方 DeepSeek JSON 调用合同。四份正式 Bible 已通过 admission：每份含 3 个角色、14 条事实（6 条正常背景、1 条异常、1 条未决问题及政策、后果、处理事实），并验证事实唯一性、时间可行性、角色权限和政策边界。原始 SDK/schema 与输出截断 run 保留为冻结诊断，不混入正式 evidence；后续任何新 Bible batch 仍须保持单 provider、单次调用、零 SDK retry。

### R10.3 — Evidence projection — `blocked / structured-fact gap`

已实现 report-only projection-readiness gate。四份正式 Bible 均缺少业务对象 ID、candidate visibility、artifact hints 和 field values；因此它们不能在不新增/臆造组织事实的前提下确定性生成 4–7 份候选文件和 20–60 条记录。下一步不是手工补题，而是设计新的 teacher-only 结构化事实扩展，随后从新的、完整 Bible batch 重启投影。文件应模拟不同业务来源与形成时间；正常记录占多数，3–5 个关键判断点跨文件出现。异常只能由底层事实、缺失、版本、金额、日期或权限关系表达。

### R10.4 — Task and truth compilation — `not_implemented`

从触发事件编译候选题干、交付合同、teacher truth、`TaskDecisionMatrixV1` 和 task-specific rubric。决策矩阵必须说明每个判断点的可见证据、可接受结论、严重错误、允许的不确定结论和后续行动。通用七维 rubric 只补充成果质量，不覆盖专业决策。

### R10.5 — Four-task pilot admission — `not_implemented`

对四题运行离线一致性、candidate/teacher isolation、可解性、答案泄漏、文件渲染和交付合同测试。通过后，以同一冻结任务包运行多模型 solver 与独立 grader，测量交付有效率、关键判断准确性、major defect、评分分歧和模型分离度。

每题都必须同时满足：来源完整、世界因果一致、无答案泄漏、信息足以支持结论、存在正常背景与真实不确定性、有效交付可评分。低分或失败不得触发单题重写；应归因并修复 compiler、seed admission 或 projection 规则。

### R10.6 — Scale decision — `not_implemented`

仅当四题均通过静态准入，且至少两个模型在共同任务上表现出可解释的差异，才编写十题 production plan。若失败，冻结 pilot，保留证据并优先修复共性合同；不扩建 agent 框架、不更换默认 solver、不启动训练或 promotion。

## Acceptance Metrics

| 维度 | Pilot 要求 |
| --- | --- |
| 来源 | 4/4 Work Seed 公开可追溯，方法论与业务事实边界明确。 |
| 世界一致性 | 每个候选事实都可追溯到 Scenario Bible；无冲突的时间、角色或政策状态。 |
| 真实性 | 每题 4–7 文件、20–60 记录、正常记录占多数，交付物有明确业务受众。 |
| 可解性 | 每个关键判断都具有候选可见证据；允许“证据不足”而非要求臆测。 |
| 抗泄漏 | 不以 `Questionable`、`Exception`、`Requires Follow-Up` 等结论标签代替底层事实。 |
| 评分 | 每题有 task-specific decision matrix；关键错误不能被通用表达质量抵消。 |
| 行为 | 至少两个模型完成有效交付；结果不应全部饱和或全部不可完成。 |

## Boundaries

- 不修改或重解释历史 R9/R7、R6 或 archive 证据。
- 不复用 GDPval 内容、hidden rubric 或历史私有任务作为生成输入。
- 不在本计划阶段调用 provider、上传任务、激活 release、改变 registry 或开始训练。
- R10.0 的离线 contracts 已实现；R10.1 及之后的来源、provider、文件、parity 和外部执行各需要新的独立计划与授权。
