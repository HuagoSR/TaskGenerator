# R10 Scenario-First 流水线优化计划

> 状态：`active`
> 职责：定义下一轮实现与验证顺序。R9/R7 是冻结历史证据，不是当前执行计划。

## 目标

将 TaskGenerator 从“Skill + Motif 驱动的任务包生成器”重构为“公开工作种子驱动、由 Agent-native 专业 Skill 辅助的职业情景编译器”。目标不是增加文件数量，而是稳定生成具有业务因果、自然信息不完整性、职业交付物和模型区分度的多文件任务。

首轮范围固定为四题：审计两题、采购两题。所有 Work Seed 仅使用公开、可追溯材料。R10 在完成离线实现和新授权前不得执行外部调用。

## Design Principles

- 先有业务事件和完整世界，再有候选文件与任务；不从 motif 直接拼接故事。
- 专业规范约束判断，不冒充组织事实；Scenario Bible 是唯一业务事实权威。
- 候选材料展示事实、记录和不确定性，不能直接展示答案标签。
- 专业 Skill 只为出题 Agent 提供专业深度、能力覆盖和错误归因；Motif 用于生成后的关系标签与分析。
- 程序只负责来源追溯、candidate/teacher 隔离、答案泄漏、文件可打开性、交付路径和状态；LLM 可提出情景扩展、证据文件和表达。
- 任务只能在静态准入和多模型行为准入都通过后进入候选题库。

## Workstreams

### R10.0 — Offline contracts and regression corpus — `implemented`

已实现六个严格 V1 合同、规范化 SHA、report-only 静态 admission validator 与不含私有任务内容的 R7 诊断 fixture。当前验证来源追溯、世界引用/时间线、投影规模与事实映射、正常背景比例、答案标签与直接 teacher-treatment 泄漏、决策证据覆盖和不确定性处理。该层不读取密钥、不调用 provider、不抓取来源、不物化文件，也不改变 R9/R7。

### R10.1 — Public Work Seed admission — `implemented / public-source only`

已建立公开来源目录、候选 seed、规则集和离线 admission CLI。每个领域审查四个候选、接纳两个：审计为公司自产信息可靠性与控制缺陷组合评估；采购为简易采购价格合理性与商业交付验收处置。所有种子描述角色、触发、目标、输入、自然问题、交付物和受众，并明确“规则/方法论”与“未来组织事实”的边界。该轮通过直接公开来源调研完成，未调用 Tuzi 或 DeepSeek；若未来语义批次使用 provider，仍按整批冻结和整批重启规则执行。

### R10.2 — Scenario Bible compiler — `implemented / teacher-only`

已实现 teacher-only Bible compiler、静态 validator 和单批官方 DeepSeek JSON 调用合同。四份正式 Bible 已通过 admission：每份含 3 个角色、14 条事实（6 条正常背景、1 条异常、1 条未决问题及政策、后果、处理事实），并验证事实唯一性、时间可行性、角色权限和政策边界。原始 SDK/schema 与输出截断 run 保留为冻结诊断，不混入正式 evidence；后续任何新 Bible batch 仍须保持单 provider、单次调用、零 SDK retry。

### R10.3 — Agent-native professional Skill foundation — `implemented / offline draft`

冻结四份现有 Bible，不建设结构化 Bible V2。已建立两个 draft 专业 Skill 包：审计证据可靠性与采购价格合理性；各含简洁 `SKILL.md` 与现有 R10 规则锚点 source map。薄目录和按需 loader 已验证：先按元数据发现，至多返回四项，再读取选中正文。通用表格、文档和 PDF 能力不重复实现；旧 Registry 只读保留且哈希不变。

### R10.4 — Professional Skill curation — `next / not_implemented`

为两个 draft Skill 统一策展公开规范、工作实践和失败模式来源。只有每条非显然专业指令都可定位到公开来源，且每个 Skill 同时具备规则、实践或失败模式支持时，才可升为 `curated`。该阶段不生成任务；若使用 provider，必须冻结输入、整批执行并单独获得执行授权。

### R10.5 — Derived evidence bundle experiment — `not_implemented`

在 Scenario Bible 后选择至多 2–4 个 factory-side 专业 Skill，由 Agent 产生独立 `ScenarioEvidenceBundleV1`。该包绑定父 Bible 和 Skill 选择，记录非冲突场景扩展、candidate 文件和 teacher-only 映射。先对一个审计和一个采购 Bible 比较无 Skill/有 Skill 生成，不因单例失败手改任务；Skill 未产生可见专业增益时先修订 Skill。

### R10.6 — Two-task task and truth compilation — `not_implemented`

从触发事件编译候选题干、交付合同、teacher truth、`TaskDecisionMatrixV1` 和 task-specific rubric。决策矩阵必须说明每个判断点的可见证据、可接受结论、严重错误、允许的不确定结论和后续行动。通用七维 rubric 只补充成果质量，不覆盖专业决策。

### R10.7 — Four-task pilot admission — `not_implemented`

对四题运行离线一致性、candidate/teacher isolation、可解性、答案泄漏、文件渲染和交付合同测试。通过后，以同一冻结任务包运行多模型 solver 与独立 grader，测量交付有效率、关键判断准确性、major defect、评分分歧和模型分离度。

每题都必须同时满足：来源完整、世界因果一致、无答案泄漏、信息足以支持结论、存在正常背景与真实不确定性、有效交付可评分。低分或失败不得触发单题重写；应归因并修复 compiler、seed admission 或 projection 规则。

### R10.8 — Scale decision — `not_implemented`

仅当四题均通过静态准入，且至少两个模型在共同任务上表现出可解释的差异，才编写十题 production plan。若失败，冻结 pilot，保留证据并优先修复共性合同；不扩建 agent 框架、不更换默认 solver、不启动训练或 promotion。

## Acceptance Metrics

| 维度 | Pilot 要求 |
| --- | --- |
| 来源 | 4/4 Work Seed 公开可追溯，方法论与业务事实边界明确。 |
| 世界一致性 | 每个候选事实都可追溯到 Scenario Bible；无冲突的时间、角色或政策状态。 |
| 真实性 | 文件与记录规模服务于业务情景，含自然正常背景，交付物有明确业务受众。该项由审阅与行为证据判断，不设新的机械配额。 |
| 可解性 | 每个关键判断都具有候选可见证据；允许“证据不足”而非要求臆测。 |
| 抗泄漏 | 不以 `Questionable`、`Exception`、`Requires Follow-Up` 等结论标签代替底层事实。 |
| 评分 | 每题有 task-specific decision matrix；关键错误不能被通用表达质量抵消。 |
| 行为 | 至少两个模型完成有效交付；结果不应全部饱和或全部不可完成。 |

## Boundaries

- 不修改或重解释历史 R9/R7、R6 或 archive 证据。
- 不复用 GDPval 内容、hidden rubric 或历史私有任务作为生成输入。
- R10.0–R10.3 已完成；Skill foundation 未调用 provider、上传任务、激活 release、改变历史 registry 或开始训练。
- 每个后续阶段均单独提交、汇报并等待验收。涉及 provider、私有任务、solver 或 grader 的阶段必须先形成独立执行计划与授权。
