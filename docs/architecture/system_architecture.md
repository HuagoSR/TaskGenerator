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
→ package / rw-task export
```

LLM 可以参与情境变化、教师候选和 prose-heavy 文件生成；确定性代码负责 contract、provenance、manifest、验证、打包和门禁。candidate-visible truth 与 teacher-only supervision 必须保持分离。

## Validity / Evaluation / Feedback / Promotion

该层包括 package-level quality gate、task verifier、real-worldness、difficulty、model-separation diagnostics、production QA、release packaging、rw-task eval 和 promotion / rollback record。

结构验收不能替代真实模型执行证据。单任务或单次执行默认只作为 diagnostic；正式 promotion 需要完整 cohort、固定 grader、明确任务包指纹和可审计的失败处理。

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
