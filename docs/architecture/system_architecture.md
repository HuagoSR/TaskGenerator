# TaskGenerator 当前系统架构

> 状态：`active`
> 职责：记录当前稳定技术结构与层间边界；宏观路线和阶段状态由根目录《项目概要》管理。

## 总体结构

```text
Source / Skill / Resource Substrate
        ↓
Workflow / Motif / Task-graph Planning
        ↓
Task Package Generation
        ↓
Validity / Evaluation / Feedback / Promotion
```

系统由两条可独立运行但通过明确 contract 连接的流水线组成：Pipeline A 生产可复用语义资产，Pipeline B 将这些资产组装为真实任务包。规划层和评测治理层横跨两条流水线，负责工作流条件化与闭环反馈。

## Pipeline A：Source-to-Skill

输入包括公开材料、专业指南、真实案例和经允许使用的外部来源。主要输出包括：

- `RawSource`、`NormalizedSource`、`SourceBlock`；
- `ExtractedSkillCandidate`、`SkillEvidence`、`SkillRegistryEntry`；
- typed semantic resources、trace edges、motif hints 和 workflow episode proposals。

Pipeline A 的语义抽象可以依赖 LLM，但来源证据、review、registry update 和 promotion 必须显式。Pipeline A 不负责直接生成最终任务，也不应把静态 successor 列表写回技能节点。

## Workflow / Motif / Task-graph Planning

该层从 registry 和 readiness 信号中选择领域、workflow archetype、motif 和 graph roles，形成 `PipelineBSubgraph`、`TaskConstraintGraph` 与 `ExecutionPlanDAG` 等结构。

当前采用可审查、可复现的确定性或 report-first 策略。Transition prior、采样权重和未来 bandit 行为必须由可比较的任务反馈驱动，并经过显式 promotion，不能静默修改。

## Pipeline B：Skill-to-Task

Pipeline B 将任务子图转化为：

```text
TaskBlueprint
→ reference file plan / reference files
→ teacher input / GoldenRun
→ TrainingAnnotation / rubric
→ quality gate / verifier
→ LLM-assisted semantic validation
→ package / rw-task export
```

对启用 `finance_semantic_contract_v2` 的新任务，`task_generation` 内部进一步固定为：

```text
TaskBlueprint
→ generator-owned semantic contract design
→ reference materialization
→ deterministic resolution and recomputation
→ GoldenRun / annotation / contract-bound rubric
→ semantic contract verification
```

合同只有达到 `verified` 才能成为新的 production candidate。历史任务的 inferred contract 只能用于诊断。

F3.1 的 secondary adjudication 使用 claim/finding 定向投影，而不是完整任务包。复审配置必须显式冻结 provider、model、key slot、token 上限和成本预算；当前低成本合同为 `tuzi / gpt-5.6-sol / backup / 1200 tokens / ¥10`，但完整8题校准尚未通过，不能据此推广默认链。

F4 验证了一个更高层的替代方向：LLM以完整任务总编辑身份同时理解 candidate、teacher、rubric和既有执行证据，程序只负责版本化、独立重算、candidate/teacher隔离、成本和发布门禁，再由独立模型进行candidate-blind求解。固定8题全部通过，但该路径仍是bounded reporting cohort，尚未成为默认生成链。

后续从零生产验证在第1题两轮后阻塞：整体编辑能够发现并提出完整修订，但当前系统缺少把 candidate-file revision proposal 安全物化为新 XLSX/DOCX、truth 和 rubric 的通用层。逐题人工放行应继续保留；whole-task materialization 和下游 checksum 重建完成前，整体编辑结果不能直接成为 production evidence。

LLM 可以参与情境变化、教师候选和 prose-heavy 文件生成；确定性代码负责 contract、provenance、manifest、验证、打包和门禁。candidate-visible truth 与 teacher-only supervision 必须保持分离。

## Validity / Evaluation / Feedback / Promotion

该层包括 package-level quality gate、task verifier、real-worldness、difficulty、model-separation diagnostics、production QA、release packaging、rw-task eval 和 promotion / rollback record。

结构验收不能替代真实模型执行证据。单任务或单次执行默认只作为 diagnostic；正式 promotion 需要完整 cohort、固定 grader、明确任务包指纹和可审计的失败处理。

`semantic_validation` 是生成器原生合同之后的独立 LLM 语义审查。它先在 candidate-blind 视图中检查材料是否充分、答案是否唯一，再审计 teacher truth 与 rubric。LLM finding 的 corroboration 字段不被信任；确定性冲突直接进入修订，LLM-only blocker 必须复审，普通建议可形成 `pass_with_advisories`。历史任务没有 V2 证据时标记为 `legacy_semantic_status=not_evaluated`，不能被解释为已经通过新门禁。

## 稳定边界

- Pipeline A registry、readiness、transition prior 和 sampler weight 更新必须 reviewable。
- Pipeline B 在 `candidate_ready` 前保持确定性质量门禁。
- production promotion 不能由生成器静默完成。
- GDPVal 只用于校准和最终测试，不流入训练任务。
- 外部 API 权限按实验授权，secret 只通过环境传递。
- 生成报告和任务产物写入 `artifacts/`；活跃 docs 只保存人工确认的稳定结论。

## 本地统一运行合同

`v3_end_to_end_pipeline` 是本地 source-to-QA 的唯一编排入口。Manifest V2 将五个阶段组织为 scratch-first DAG，记录输入/输出指纹、attempt、checksum、external effects 和 lifecycle index。默认 profile 只进行 rw-task eval preparation，不执行外部评测；中断恢复必须验证 completed stage 的产物 checksum，重跑上游会使下游失效。

接口字段和对象定义见 `global_interface_contracts.md`，finance/audit production contract 见 `production_mvp_definition.md`。
