# Global Interface Contracts

> 状态：`reference`
> 职责：概述稳定实现合同与 R10 proposed 合同。代码 schema 是字段级唯一事实来源；本文件不记录 campaign 历史。

## Contract Status

| 类别 | 状态 | 含义 |
| --- | --- | --- |
| Stable | `implemented` | 当前 R9 工厂或评测链使用，字段以代码 schema 为准。 |
| Historical | `frozen` | 已关闭实验或 campaign 的读取兼容；不作为新执行入口。 |
| R10 foundation | `implemented / offline only` | 六个 V1 合同和静态 admission validator 已实现；无 provider、文件物化或 campaign 权限。 |
| R10.1 seed admission | `implemented / public-source only` | 来源目录、四候选×两领域的确定性准入、两套专业规则和离线 CLI 已实现。 |
| R10.2 Bible compilation | `implemented / teacher-only` | 四份 Scenario Bible 已通过静态 admission；仍是叙事事实，不可直接物化。 |
| R10.3 readiness diagnostic | `implemented / historical diagnostic` | 证明叙事 Bible 不适合由严格确定性投影器直接物化；不建设 Bible V2。 |
| R10.3 professional Skill foundation | `implemented / offline draft` | 两个 draft factory-side Skill、薄目录与渐进加载器已实现；未调用 provider、未生成任务，旧 Registry 未变。 |
| R10.4 professional Skill curation | `implemented / public-source` | 两个 curated Skill 各绑定规范、工作实践和失败模式来源；DeepSeek 仅起草冻结公开来源批次，原始响应留在 ignored artifacts。 |
| R10.5 derived-evidence public probe | `implemented / public-only pass` | 受限外层 Docker 中的非嵌套 Codex Shell 已创建并验证公开 XLSX、DOCX、PDF；零私有 Bible 上传。 |
| R10 paired derived-evidence experiment | `implemented / twice frozen incomplete` | 四个隔离 session、candidate/teacher admission、condition-blind payload 和一次格式补跑受限的 DeepSeek reviewer 已实现。首个 run 因条件字段误设为必填而冻结；完整重启后，四份自由文本 extension ID 均不被 Bible-only map validator 登记，故无 pair review 或 Skill 效果结论。 |
| R10 task/evaluation | `proposed / not_implemented` | Task/truth compilation、任务包与行为验收尚未实现。 |

## Stable Implemented Contracts

### Source, skill and planning

- `RawSource` / `NormalizedSource` / `SourceBlock`：公开来源及其可审计正规化边界。
- `ExtractedSkillCandidate` / `SkillRegistryEntry`：候选 skill、来源证据和显式 review/registry 流程。
- `CapabilityBrief`：当前 R9 任务设计输入，绑定领域、来源、skills、capabilities 和交付意图。
- `TaskDesignProposal`：LLM 提出的 evidence nodes、records、relations、judgments、skill bindings 和交付意图；LLM 无权定义最终真值、提交路径、registry 或 promotion。

### Package generation

- `EvidenceArtifactSpec`：候选文件的 typed records、事实来源、主键和方法论来源投影。
- `DeliverableContract`：唯一的候选交付路径、格式和存在性合同；prompt、dataset row、expected deliverables 与 delivery inspection 必须由它编译。
- `HybridMaterializationReport` / `EvidenceContentQualityReport` / `TaskVerifierReport`：物化、内容、渲染、来源和导出检查结果。
- `CandidatePackageManifest`：candidate-visible 文件树和 package fingerprint；不得包含 teacher-only artifacts。

### Evaluation and operations

- `ValidityVector`：结构、事实、交付和有效性证据的分轴记录。
- `UtilityProfile`：productive complexity、accidental difficulty 和可用性诊断；不是训练准入。
- `RubricPlanV2`：通用七维成果质量框架；权重在结果产生前冻结。
- `BehavioralExecutionReport`：solver 进程、精确交付、基础设施失败和业务失败的分离记录。
- `ProductionTaskCohortV1` / solver and judge manifests：R9 批处理生产和评测的已实现合同。R9/R7 结果是 frozen evidence，不授予新执行权限。

## Cross-Cutting Authority Rules

```text
LLM: propose semantic design and prose
Program: source boundary, facts, file projection, deliverable path,
         candidate/teacher isolation, package identity and state mutation
```

- GDPval 是 `eval_calibration_only`。
- candidate-visible truth、teacher-only supervision 与运行证据必须隔离。
- `candidate_ready`、openable XLSX、provider pass 或 LLM review 不能自动成为专业有效性、训练、release 或 promotion 证据。
- registry、默认链、release 和训练状态只能由显式 review/apply 路径改变。
- 外部调用必须绑定当前实现、任务包、provider policy、预算和 retry 边界；历史 receipt 不可复用。

## R10 Scenario-First Contracts

以下六个合同已在 `task_generator.core.scenario_first` 实现为严格、可规范化哈希的离线 Pydantic schema。它们不包含 provider、CLI、文件物化或外部执行语义；后续执行层仍须单独设计、测试与授权。

### `WorkSeedV1` — implemented / offline only

公开可追溯的职业工作原型。最少记录：公开来源、角色、触发事件、业务目标、典型输入、自然问题、交付物、受众和来源到抽象的说明。它不包含完整题目、答案或私有工作材料。

### `ProfessionalRuleSetV1` — implemented / offline only

从来源提炼的适用条件、证据要求、例外、禁止假设和可接受处理。它约束 Scenario Bible 与评分，不得冒充具体组织的事实。

### `ScenarioBibleV1` — implemented / offline only

teacher-only 原始事实父权威。应含组织、角色、时间线、业务对象/交易、政策适用、正常背景、真实异常、未决问题、决策后果和正确处理。后续候选文件和 teacher truth 必须可追溯到该 Bible 或其带父链接的派生证据包。

### `EvidenceProjectionPlanV1` — implemented / offline-only historical foundation

旧的严格投影合同。它保留读取与诊断价值，但不再要求 R10 通过补全结构化 Bible 来满足它。

### `TaskDecisionMatrixV1` — implemented / offline only

每个关键判断点绑定候选可见证据、可接受结论、严重错误、允许的不确定结论和后续行动。它是 teacher truth 与 task-specific rubric 的中间权威，不允许直接暴露给 candidate。

### `ScenarioFirstAdmissionReportV1` — implemented / static only

R10 静态 admission 报告。当前覆盖来源追溯、世界一致性、文件投影、直接 teacher-treatment 泄漏、可解性和决策覆盖；完整 package isolation、交付合同、模型交付和模型区分度属于后续阶段。

## Skill and Motif Semantics in R10

- `ProfessionalSkillCatalogEntryV1` — `implemented / curated`：仅包含 contract version、skill ID、名称、触发描述、领域、相对路径、版本和状态；目录中的 `SKILL.md` 是运行时内容权威。loader 先读取目录，按 domain/text 返回至多四项，再安全加载被选中的完整正文与引用。
- `ProfessionalSkillCurationSourcesV1` / `ProfessionalSkillCurationReportV1` — `implemented / public-source`：记录短摘要、章节、URL、访问日期、可获得的内容 SHA 与每条专业 instruction 的 source ID；只允许一次正常 provider 调用及一次格式/传输补跑。
- `ScenarioEvidenceSessionV1` / `ScenarioEvidenceExperimentPlanV1` — `implemented / experimental`：冻结父 Bible、规则、条件、可选 Skill/source map、模型、镜像与一次 session 的输入身份；不是生产任务合同。
- `ScenarioEvidenceCampaignScopeV1` — `implemented / awaiting authorization`：绑定一个完整四-session cohort、源码提交、plan SHA、模型/镜像、两次盲审上限与明确排除动作；只有新的私有上传授权才能消费。
- `ScenarioExtensionRegistryV1` — `implemented / teacher-only`：仅登记唯一、`extension_` 前缀的 `{fact_id, statement}`；不是结构化 Bible，也不声称确定性验证新增事实的专业正确性。
- `ScenarioEvidenceAdmissionReportV1` / `ConditionBlindPairReviewV1` / `ScenarioEvidenceExperimentResultV1` — `implemented / experimental`：仅记录文件隔离、可打开性、evidence-map closure、答案泄漏与盲审状态；两个完整 cohort 均为 `incomplete`，不可作为 Skill 效果结论。新的完整 cohort 才能检验 extension registry 修复。
- `SkillSelectionRecordV1` / `ScenarioEvidenceBundleV1` — `proposed`：若 A/B 实验完整通过，才考虑将其收敛为轻量生产清单；不是新的业务对象本体。
- 专业 Skill 约束出题侧专业判断、能力覆盖和错误归因。通用工具 Skill 不进入项目 Registry。
- Motif 从生成后的情景关系标注，用于分析；任一 motif 或 skill 都不能独自决定候选文件结构。

## R10.1 Public Seed Admission

- `PublicWorkSourceCatalogV1`：公开来源 URL、检索方式、可用内容 SHA 或浏览器验证说明，以及可引用的段落块。
- `WorkSeedCandidateV1`：一个候选 Work Seed、独立工作模式 ID、接纳/拒绝状态及理由。
- `WorkSeedAdmissionReportV1`：要求每领域四个候选、两个接纳、来源块闭合和匹配的规则集；它不调用 provider、写 registry 或创建 Scenario Bible。
- 当前来源目录和规则集只保存公开来源摘要、段落引用与方法论边界，不保存完整网页副本。

## Compatibility

R10 不修改当前已持久化的 R9 package、manifest、report、rubric 或 archive。现有稳定合同保持读取兼容；R10 的外部执行、生产迁移和 release 方案仍须单独批准。
