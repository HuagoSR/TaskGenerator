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

### R10.4 — Professional Skill curation — `implemented / public-source`

两个 Skill 已由同一冻结公开来源批次完成策展并升为 `curated`。每个 Skill 同时拥有规则、工作实践与失败模式来源；每条专业 instruction 均绑定 source ID。官方 DeepSeek 一次正常调用成功，原始响应和诊断仅留在 ignored artifacts。该阶段未生成任务，也未修改历史 Registry。

### R10.5 — Derived evidence bundle experiment — `implemented / skill effect supported`

无 Skill/有 Skill 成对实验已实现并执行两次。`taskgenerator-eval:milestone-r9-huago-cone-746ff9b55f1b` 的初次 probe 所见 Bubblewrap 嵌套 user namespace 问题，已在不使用特权容器、Stirrup 或临时换 agent 的前提下修复。受限外层 Docker 保留只读根、无额外 capability、`no-new-privileges`、资源上限和单一临时工作区，Codex 在其中运行非嵌套 Shell；公开 probe 已生成并验证 XLSX、DOCX、PDF。首个私有 run 因无 Skill map 缺少空 source-ID 数组而冻结，后验修复已将该字段设为条件化可选。

两个历史 cohort 因过窄的 extension 事实合同冻结，未形成 Skill 效果结论。最小修复只保留 extension 的唯一、安全 ID 与 statement，并允许 Agent 保留不影响闭合判断的 Bible-like 上下文；不建设 Bible V2 或业务对象本体。

自动 Skill Compiler 已完成：Codex/Sol 直接基于 Seed、Rules、公开来源与历史反馈生成完整 Skill 包，DeepSeek独立通过两项来源/内容审查。最新 cohort 的每领域先生成共同基础 bundle，再以无 Skill/有 Skill 的等条件审阅派生两份候选包。四份 bundle 均通过隔离、可打开性、evidence-map 闭合和泄漏检查；DeepSeek 条件盲审在审计与采购都给出至少两项有 Skill 的文件级职业真实性、证据自然度或判断深度改进，聚合为 `skill_effect_supported`。

活跃准入不使用 instruction 配额、来源类型配额或文件级 source ID要求，只保留来源追溯、包安全、隔离、可打开性、evidence-map 闭合和答案泄漏。该结果允许进入两题 task/truth compilation 规划，但仍不是专家有效性、大规模生产或 solver 评测准入。

### R10.6 — Two-task task and truth compilation — `implemented / compiled_for_user_review`

从两份冻结的有 Skill evidence bundle 编译候选题干、交付合同、teacher truth、`TaskDecisionMatrixV1` 和 task-specific rubric。审计题交付 XLSX 工作底稿，采购题交付 DOCX 价格分析备忘录；采购题不要求供应商选择。决策矩阵必须说明每个判断点的可见证据、可接受结论、严重错误、允许的不确定结论和后续行动。通用七维 rubric 只补充成果质量，不覆盖专业决策。两题已在第三个独立 scope 下通过静态 admission；前两次 cohort 的事实投影与路径规范化诊断保留。下一步先由用户检查形态，不运行 solver 或 grader。

### R10.7A — Complete the remaining two user-review tasks — `implementation_ready / not_executed`

现有两题已完成静态 admission 并由用户进行表面审题。下一切片仅补齐另外两题：控制缺陷组合评估交付 DOCX 评估备忘录，商业交付验收处置交付 XLSX 跟进工作簿。新增的两项 factory-side Skill 先以 draft 元数据登记，再由 Skill Compiler 基于官方 PCAOB AS 2201 与 FAR Part 46 材料自动编译并经 DeepSeek 独立来源/内容审查；不人工补写专业结论，不重复 R10.5 A/B 实验。

两份有 Skill evidence bundle 与两道 task/truth package 均须完整静态通过，并生成中文用户检查包。已有两题候选树与 SHA 不得变化。该切片不运行 solver、grader、release 或十题扩展。

### R10.7B — Four-task pilot behavioral admission — `not_implemented`

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
- R10.0–R10.5 已完成；所有历史失败 cohort 保持冻结且不与最终 cohort 混合。R10 尚未生成任务、激活 release、改变历史 registry 或开始训练。
- 每个后续阶段均单独提交、汇报并等待验收。涉及 provider、私有任务、solver 或 grader 的阶段必须先形成独立执行计划与授权。
