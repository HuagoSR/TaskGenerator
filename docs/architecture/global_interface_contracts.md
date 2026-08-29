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
| R10 execution | `proposed / not_implemented` | Scenario Bible 编译、证据投影、任务包与行为验收尚未实现。 |

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

teacher-only 单一事实权威。应含组织、角色、时间线、业务对象/交易、政策适用、正常背景、真实异常、未决问题、决策后果和正确处理。每个候选文件及 teacher truth 都必须可追溯到该对象。

### `EvidenceProjectionPlanV1` — implemented / offline only

将 Scenario Bible 投影为候选文件、记录或消息。每份投影记录原始业务目的、产生者、时间、可见字段和与世界状态的映射。不得使用结论性状态字段替代异常事实。

### `TaskDecisionMatrixV1` — implemented / offline only

每个关键判断点绑定候选可见证据、可接受结论、严重错误、允许的不确定结论和后续行动。它是 teacher truth 与 task-specific rubric 的中间权威，不允许直接暴露给 candidate。

### `ScenarioFirstAdmissionReportV1` — implemented / static only

R10 静态 admission 报告。当前覆盖来源追溯、世界一致性、文件投影、直接 teacher-treatment 泄漏、可解性和决策覆盖；完整 package isolation、交付合同、模型交付和模型区分度属于后续阶段。

## Skill and Motif Semantics in R10

- Skill 约束专业判断、验证能力覆盖，并用于模型错误归因。
- Motif 从 Scenario Bible 的关系中标注，用于配额、复杂度分析和覆盖报告。
- 一个情景可有多个 motif；任一 motif 或 skill 都不能独自决定候选文件结构。

## R10.1 Public Seed Admission

- `PublicWorkSourceCatalogV1`：公开来源 URL、检索方式、可用内容 SHA 或浏览器验证说明，以及可引用的段落块。
- `WorkSeedCandidateV1`：一个候选 Work Seed、独立工作模式 ID、接纳/拒绝状态及理由。
- `WorkSeedAdmissionReportV1`：要求每领域四个候选、两个接纳、来源块闭合和匹配的规则集；它不调用 provider、写 registry 或创建 Scenario Bible。
- 当前来源目录和规则集只保存公开来源摘要、段落引用与方法论边界，不保存完整网页副本。

## Compatibility

R10 不修改当前已持久化的 R9 package、manifest、report、rubric 或 archive。现有稳定合同保持读取兼容；R10 的外部执行、生产迁移和 release 方案仍须单独批准。
