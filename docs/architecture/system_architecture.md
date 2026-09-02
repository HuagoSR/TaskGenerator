# TaskGenerator 系统架构

> 状态：`active`
> 职责：区分当前已实现能力与 R10 目标架构；项目状态以《项目概要》为准。

## 当前已实现的 R9 工厂

```text
公开来源
→ skill extraction / scratch registry
→ CapabilityBrief + motif planning
→ LLM task-design proposal
→ deterministic materialization
→ candidate/teacher package
→ integrity / render / export validation
→ solver / grader execution
```

这条链已经能生成候选文件、交付合同、teacher artifacts 和 rw-task export，并支持受治理的服务器生产与模型执行。确定性代码负责 provenance、事实边界、candidate/teacher isolation、文件路径、package fingerprint、导出和状态变更；LLM 只提出语义设计与表达。

R9/R7 证明了工程闭环可运行，但不能证明自动任务具备职业真实性。R7 从零复验的 5/10 provider freeze 是历史诊断，不得继续或拼接。

## R10.9 World-First / Task-Mining 目标架构

```text
公开 Work Seed、Rules 与专业来源
        ↓
Professional Skill 与自然难度辩论
        ↓
无题干、无 rubric 的完整工作世界
        ↓
冻结 candidate-visible 多来源业务文件
        ↓
独立 Task Miner 发现自然工作任务
        ↓
独立 Agent 重建 Teacher Truth / Decision Matrix
        ↓
三档完整交付校准 Judge
        ↓
静态准入与多模型行为验收
```

### Work Seed 与专业规则

`WorkSeedV1` 是职业工作原型，不是完整题目。它记录角色、触发事件、业务目标、典型输入、自然问题、交付物和受众，并绑定公开可追溯的来源。专业规则说明适用条件、证据要求、例外与可接受处理。

### 历史 Scenario Bible 与新工作世界

`ScenarioBibleV1` 继续作为 R10.2–R10.8 的冻结事实权威。R10.9 不修改或复用这些 Bible，也不建设结构化 Bible V2。新实验由 Agent 先产生 campaign-scoped `world_ledger.md` 和自然业务材料；此时不存在题干、交付合同、rubric 或预设答案。工作世界冻结后，Task Miner 才从 candidate-visible 材料中发现任务。

### 专业 Skill 与派生证据包

专业 Skill 是 Agent-native 知识包，而不是任务装配图。其 `SKILL.md` 只说明触发条件、工作目标、专业判断步骤和严重错误；长法规、模板和失败案例按需置于 `references/`、`assets/` 或 `scripts/`。通用表格、文档和 PDF 操作由现成工具 Skill 提供。

原始 `ScenarioBibleV1` 保持冻结。出题 Agent 依据 Bible 与选中的 2–4 个专业 Skill 产生一个带父 Bible ID 的派生证据包，其中记录新增且不冲突的情景事实、candidate 文件和 teacher-only 证据映射。文件必须保留形成目的、时间和口径；冲突只能由日期、金额、审批、版本或缺失等事实体现，不能使用结论性标签。

### Task Mining 与 Truth Reconstruction

Task Miner 只读取候选材料和公开角色/触发背景，不读取 world ledger、难度计划或预期答案。它必须发现真实从业者会自然收到的任务、业务受众和领域原生交付物。另一 Agent 再从冻结题干、候选材料、Rules 与 Skill 中重建 Teacher Truth。`TaskDecisionMatrixV1` 继续把判断点映射到可见证据、可接受结论、严重错误和后续行动。

### 职业对抗难度与 Judge 校准

难度只能由职业流程中的正常业务量、跨系统口径、证据可靠性、权限边界或支持有条件结论的信息缺口产生。基础世界与强化世界保持角色、目标和交付类型可比，强化版最多应用两个来源可解释的变化。正式 Solver 之前，每题以优质、合理但不完整、重大捷径错误三档完整交付校准两位 Judge；校准失败不得用 Solver 结果掩盖。

### Admission 与反馈

静态门禁只检查来源追溯、candidate/teacher isolation、可解性、答案泄漏、文件可用性和交付合同。文件与记录规模、正常背景比例和多 motif 覆盖作为质量指导，由用户审阅和行为实验检验，而不再驱动新的复杂本体。多模型行为验收检查任务是否既非饱和也非不可完成，并将失败归因到 Skill、证据、场景或执行层。

## Skill 与 Motif 的新职责

| 对象 | R10 职责 | 不再承担的职责 |
| --- | --- | --- |
| 专业 Skill | 为出题 Agent 提供专业判断、工作步骤和错误归因 | 直接决定题目模板、表格外形或 candidate 的默认能力。 |
| Motif | 描述生成后出现的信息关系与分析维度 | 作为先验的业务故事生成器。 |
| Scenario Bible | 提供业务因果和事实权威 | 向 candidate 直接暴露答案。 |

一个情景可以包含多个 motif；motif 应从情景关系中识别，而不是先选 motif 再拼接业务故事。

## 稳定边界

- GDPval 仅作形态和评测校准，不进入生成或训练输入。
- candidate-visible 事实、teacher-only 真值与治理证据必须隔离。
- 结构、导出和模型交付通过都不自动授予训练、promotion、release 或 registry mutation 权限。
- 已实现的 R10.0–R10.8 合同与证据继续只读保留。R10.8B-2 的新私有行为结果完整，但结论为 `evaluator_revision_required`：一题接近平局，一题存在 Judge 边界歧义。R10.9 的 World-First manifest、职业难度计划、paired Judge review 和薄型 campaign runner 已实现但尚未执行；不得提前扩大到十题。
