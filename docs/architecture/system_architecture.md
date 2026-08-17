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

F4 验证了一个更高层的替代方向：LLM以完整任务总编辑身份同时理解 candidate、teacher、rubric和既有执行证据，程序负责版本化、独立重算、candidate/teacher隔离、成本和发布门禁，再由独立模型进行candidate-blind求解。F4.2 已补齐受限 whole-task materialization，并从全新公开 source 与 scratch registry 生产8题；内部 truth、视觉、盲解、verifier/export 和人工式检查均通过。但当前 LLM 仍位于固定 blueprint/adapter 生成之后，主要承担成品修订，没有在 adapter 之前掌握 evidence topology、workflow judgment 和 deliverable intent 的整体设计权。

F4.3 的真实 rw-task 执行进一步证明，内部语义有效性和 export compatibility 仍不能替代行为级验收：8题32个组合只有15个实际生成交付文件，Slots 2/5/8 暴露 prompt、模板名与 deliverable path 不一致或提交位置不清。其余5题的三个有效模型评分又高度饱和。当前不推广该路径为默认链；问题定义见 [`pipeline_reconstruction_problem_statement.md`](pipeline_reconstruction_problem_statement.md)，活跃实施计划见 [`pipeline_reconstruction_optimization_plan.md`](pipeline_reconstruction_optimization_plan.md)。

当前稳定链中，LLM 可以参与情境变化、教师候选、prose-heavy 文件生成和后置整体编辑；确定性代码负责 contract、provenance、manifest、验证、打包和门禁。重构 experimental profile 已加入 materialization 之前的 design frontend：程序先从 source/skill/workflow/domain 信号生成 `CapabilityBrief`，再由 proposal-only executor 请求并验证 `TaskDesignProposal`。v7 provider screening 暴露旧二次调用只是同提示重发，并且模型经常用裸章节名或自造 alias 填写 `bound_element_ids`。当前 executor 已把 canonical ID namespace 编入 schema/prompt；唯一 repair 会读取首轮 execution report，把原 proposal、blocking findings、authority reasons 和有效 IDs 编入完整 replacement-proposal prompt。无 proposal 时状态仍为 `awaiting_provider`，legacy blueprint 只作为兼容路线继续，不能标记为 LLM-led。truth、deliverable path、rubric authority、promotion 和 registry mutation 始终由程序治理。candidate-visible truth 与 teacher-only supervision 必须保持分离。

## Validity / Evaluation / Feedback / Promotion

该层包括 package-level quality gate、task verifier、real-worldness、difficulty、model-separation diagnostics、production QA、release packaging、rw-task eval 和 promotion / rollback record。

结构验收不能替代真实模型执行证据。单任务或单次执行默认只作为 diagnostic；正式 promotion 需要完整 cohort、固定 grader、明确任务包指纹和可审计的失败处理。

`semantic_validation` 是生成器原生合同之后的独立 LLM 语义审查。它先在 candidate-blind 视图中检查材料是否充分、答案是否唯一，再审计 teacher truth 与 rubric。LLM finding 的 corroboration 字段不被信任；确定性冲突直接进入修订，LLM-only blocker 必须复审，普通建议可形成 `pass_with_advisories`。历史任务没有 V2 证据时标记为 `legacy_semantic_status=not_evaluated`，不能被解释为已经通过新门禁。

## 当前重构边界

现有架构继续作为 legacy compatibility route，但以下语义必须在重构中修正：

- `candidate_ready` 当前只证明结构、verifier 和 export compatibility，不证明真实交付、专业合理性或训练价值；
- opt-in `reconstruction_experimental` profile 已由 `DeliverableContract` 统一编译 prompt、`dataset_row.deliverable_files`、expected-deliverables 和 grader 前置 delivery inspection；legacy profile 与历史任务仍保留兼容语义，不能倒推为已通过新合同；
- candidate-blind 文本求解能证明关键结果可计算，但不能证明 solver 会在真实工具环境中创建并提交精确文件；
- whole-task editor 位于固定 adapter 之后，容易在修复可回答性时继续保留模板形态或删除 productive complexity；
- rubric 与 model panel 尚未稳定区分事实有效性、工具失败和专业质量。

重构首先在 opt-in `reconstruction_experimental` profile 中引入新合同。目前 `DeliverableContract`、`CapabilityBrief`、semantic proposal normalizer、`TaskDesignProposal`、causal-binding validator、feedback-conditioned proposal repair、persisted-proposal offline replay、offline hybrid materializer、solver tool preflight、`BehavioralExecutionReport`、`ValidityVector`、`UtilityProfile`、七维 `RubricPlanV2` 和 matched-route comparison scaffold 的本地核心已经实现。proposal executor 默认使用 `gpt-5.6-sol`，需要显式 external-provider gate，并默认拒绝 `claude-sonnet-4-6`。R6 authorization request 与 receipt 写入 hash-addressed immutable governance archive；active receipt 是受管副本，执行前同时复核其自身 SHA 和 active request SHA，每个 authorization 独立核算成本且受 campaign 总上限约束。receipt compiler 支持初始与 sequential slice，但 previous-slice receipt 不能激活新 request。本地完整测试与最终固定 Linux/amd64 parity 均为 254 项（指纹 `b31a79b3eea9aeddc6d45c097e717f07f1e589f1f401326d3521d83467b9505d`）；容器断网、只读、无凭据并清理成功。该证据证明合同代码路径的一致性，不证明真实 solver 行为。在新的 provider/solver campaign、受控路线比较和显式 promotion 前，不修改 legacy 默认链。

R6 campaign 进一步把三路线从标签变为可执行的设计权限差异。strict-template 由 `StrictTemplateProposalCompiler` 从同一 `CapabilityBrief` 程序编译；skill-guided LLM 固定 actor、trigger、workflow graph shape 和证据节点/关系数量，只委托业务叙事、判断点、skill binding 与 deliverable sections；LLM-led hybrid 可以设计完整 evidence topology。三路线随后进入同一个 `HybridTaskMaterializer`，因此真值、文件生成、交付合同、Validity/Utility 和 rubric 治理保持一致。`RouteComparisonCampaign` 冻结 12 个 assignment、代码与来源指纹、`gpt-5.6-sol` 模型、成本上界和 authorization receipt，硬阻断 `claude-sonnet-4-6`，并提供首错保留、一次重试、resume 与 route-blind staging。持久化 strict V2 proposal 可经 `replay_persisted_proposal` 在零外呼条件下重算当前 validation/binding/authority 报告，用于构造可重放 repair-readiness；它不能伪装成真实 provider attempt。离线 campaign 只物化 strict controls；没有有效 receipt 时必须停在 `authorization_required`。

R6 的 v7、v15、v16、v21、v22 已形成逐层诊断链并全部冻结。v23 在 policy-application brief 上首次真实验证 semantic provider interface：skill-guided 与 LLM-led 均首轮通过，程序在不增删事实、不改变 productive complexity 的情况下归一化为 strict V2。历史 repair 只接受 `proposal_blocked` 且具有持久化 strict proposal 的首错。V28 closeout 后，接口增加 `semantic_proposal_blocked`：只有完整对象可由兼容 draft schema 解析、normalization evidence 和实际初始 prompt 均落盘时，才允许唯一一次 feedback repair；广泛 schema/provider/materialization failure 继续停止。V29 又验证了 strict `proposal_blocked` repair：duplicate skill binding 首错被保留，反馈修复通过。prompt 现明确每个 selected skill 恰好一个 binding，screening 从 finding details 区分 namespace、cardinality 与 missing/decorative failure；该变更不改写 V29 历史 screening。没有完整 matched packages 前不得进入 solver/grader，canonical registry、readiness 和 server release 均未改变。

候选文件层随后被重新审计。v15/v16 两个 briefs 的三路线共 58 个 XLSX 虽然全部 openable、可渲染并与 export 副本 SHA 一致，但均由旧 `HybridTaskMaterializer` 写成统一五列占位表；`Observed_Value` 只由 row/node index 产生，方法论 `Source_Ref` 与场景数值来源混在一起。原 visual gate 只验证 freeze pane、filter 与 print fit，不验证实际可读性；原 factual pass 只验证同源程序可以重算自身占位值。新增 `EvidenceContentQualityReport` 后六个历史 package 全部 blocked。

Proposal 与 Materializer 之间的 V2 semantic-artifact 层现已完成本地核心。LLM 通过 `v3.task_design_semantic_proposal.1` 提出 typed artifact spec、flat scenario records、relation join/comparison contract、判断、skill bindings 和 productive complexity；其中每条 relation 的两个 join fields 已升级为 provider-schema 非空必填。normalizer 只写入执行版本、record wrapper、候选可见标志、LLM origin 与全 false authority，绝不代填 join key，再严格验证为 `v3.task_design_proposal.2`。V2 materializer 写入业务字段、类型格式和 Provenance，并从实际文件重算 anchors；content report 仍是 blocking gate。V28 已冻结为 7/8 和 `redesign_again`，不得被新代码重算成 pass。post-V28 schema/draft-repair 改造通过 tracked missing-join negative control、42 项 normalizer/executor/campaign 测试和完整 local/fixed-container 252/252；container parity 指纹 `2178bd38...c23b`，campaign code fingerprint `4ec4dadb...b36b`。该证据只证明 V29 离线合同路径，不能建立真实 provider 稳定性、行为 Utility 或路线优胜。V2 provider completion 下限保持 16,000 tokens，费用权限不随 token 上限自动扩大。

评测结果通过独立证据编译层进入比较器。`RouteComparisonEvidenceCompiler` 为每个 blind task 读取冻结 package 的 Validity/Utility/rubric、精确三个 solver 的 `BehavioralExecutionReport`、valid-delivery-only grader repeats 和专业复核。它验证 package root、brief、blind task、panel model 与 environment identity，并将 process、delivery、business、professional 和 grader stability 分开聚合。strong solver 加至少另一名 solver 的有效交付才构成 task-level delivery pass；相同失败覆盖两个 solver 或少于两个有效交付视为 systemic task failure。十二题必须同时编译成功，之后 `RouteComparisonAnalyzer` 才能执行绝对门槛和相对排序。

R7 使用独立 report-only promotion compiler。screening 只能选择两个 confirmation candidates；没有 confirmation、服务器候选复现、matched environment、rollback 或 major-validity closure 时只能 hold/redesign。完整 confirmation 最多生成 opt-in candidate profile 的 promote proposal，默认链、release、registry 和 training authority 仍为 false，后续 review/apply 与 activation 必须再次授权。

## 稳定边界

- Pipeline A registry、readiness、transition prior 和 sampler weight 更新必须 reviewable。
- Pipeline B 在 `candidate_ready` 前保持确定性质量门禁；`candidate_ready` 不得被解释为 behaviorally validated 或 training-ready。
- production promotion 不能由生成器静默完成。
- GDPVal 只用于校准和最终测试，不流入训练任务。
- 外部 API 权限按实验授权，secret 只通过环境传递。
- 生成报告和任务产物写入 `artifacts/`；活跃 docs 只保存人工确认的稳定结论。

## 本地统一运行合同

`v3_end_to_end_pipeline` 是本地 source-to-QA 的统一编排入口。Manifest V2 将 `source_to_skills`、`registry_prepare`、`task_generation`、`semantic_validation`、`production_review` 和 `rw_task_eval` 六个阶段组织为 scratch-first DAG，记录输入/输出指纹、attempt、checksum、external effects 和 lifecycle index。默认 profile 只进行 rw-task eval preparation，不执行外部评测；中断恢复必须验证 completed stage 的产物 checksum，重跑上游会使下游失效。

接口字段和对象定义见 `global_interface_contracts.md`，finance/audit production contract 见 `production_mvp_definition.md`，重构期间的目标合同和迁移顺序见 `pipeline_reconstruction_optimization_plan.md`。
