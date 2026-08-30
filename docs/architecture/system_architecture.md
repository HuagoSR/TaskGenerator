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

## R10 Scenario-First 目标架构

```text
公开真实工作种子
        ↓
专业规则与按需加载的专业 Skill
        ↓
teacher-only Scenario Bible
        ↓
Agent 生成的派生证据包
        ↓
candidate-visible 多来源文件
        ↓
自然任务、交付合同与 Task Decision Matrix
        ↓
teacher truth / task-specific rubric
        ↓
静态准入与多模型行为验收
```

### Work Seed 与专业规则

`WorkSeedV1` 是职业工作原型，不是完整题目。它记录角色、触发事件、业务目标、典型输入、自然问题、交付物和受众，并绑定公开可追溯的来源。专业规则说明适用条件、证据要求、例外与可接受处理。

### Scenario Bible

`ScenarioBibleV1` 是单题原始业务事实的 teacher-only 父权威。它包含组织、角色、时间线、交易或业务对象、政策适用、真实异常、未决问题、决策后果和正确处理。它先于候选文件存在，禁止由候选文件反推或与候选输入混存。后续派生证据包只能显式补充不冲突的任务事实，并始终保留父 Bible 链接。

### 专业 Skill 与派生证据包

专业 Skill 是 Agent-native 知识包，而不是任务装配图。其 `SKILL.md` 只说明触发条件、工作目标、专业判断步骤和严重错误；长法规、模板和失败案例按需置于 `references/`、`assets/` 或 `scripts/`。通用表格、文档和 PDF 操作由现成工具 Skill 提供。

原始 `ScenarioBibleV1` 保持冻结。出题 Agent 依据 Bible 与选中的 2–4 个专业 Skill 产生一个带父 Bible ID 的派生证据包，其中记录新增且不冲突的情景事实、candidate 文件和 teacher-only 证据映射。文件必须保留形成目的、时间和口径；冲突只能由日期、金额、审批、版本或缺失等事实体现，不能使用结论性标签。

### Task Compilation

任务从业务事件自然产生，交付物服务于明确受众和决策。`TaskDecisionMatrixV1` 将每个关键判断点映射为可见证据、可接受结论、严重错误和后续行动。七维 rubric 保留为通用质量框架，但不得替代该题的决策矩阵。

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
- 已实现的 R10.0–R10.2 合同继续只读保留；Professional Skill curation、自动 Skill Compiler 与薄型 A/B evidence experiment 均已实现。最新完整 cohort 的四份 bundle 通过静态 admission，两个领域的条件盲审均支持有 Skill 的文件级改进；R10.6 已从两份胜出 bundle 编译并静态接纳审计 XLSX 与采购 DOCX 两题，当前等待用户审题，尚未扩展到 solver。
