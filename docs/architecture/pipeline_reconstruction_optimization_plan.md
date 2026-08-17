# TaskGenerator 流水线重构优化计划

> 状态：`active / workstream`
> 制定日期：2026-07-16
> 职责：把 [`pipeline_reconstruction_problem_statement.md`](pipeline_reconstruction_problem_statement.md) 中的问题定义转化为可执行的重构、验证、比较和 promotion 计划。
> 关闭规则：完成路线比较和 promotion 决策后迁入 `docs/archive/`，宏观结论只同步到根目录《项目概要》。

## 一、计划结论

本轮不以“增加 LLM 调用次数”为目标，而是重新分配任务设计权和验证责任：

```text
Source / Skill / Capability Brief
        ↓
LLM whole-task design proposal
        ↓
deterministic materialization / truth / deliverable contract
        ↓
whole-task editorial review on the actual candidate package
        ↓
offline validity gates
        ↓
independent black-box solver execution
        ↓
Validity + Utility comparison
        ↓
explicit promotion or rollback
```

核心假设是：

- LLM 更适合在完整上下文中设计职业场景、证据关系、工作步骤、必要判断和交付目标；
- 程序更适合保证 provenance、事实重算、candidate/teacher 隔离、文件合同、可复现性和发布治理；
- 真实 solver 行为和独立评价必须作为第三类证据，不能由生成器或其内部 reviewer 自证；
- 纯模板、skill-guided LLM 和 LLM 主导混合路线都必须通过同源、同任务目标、同环境的受控比较，不能预先宣告某条路线胜出。

在重构完成前，当前默认生成链、canonical registry、服务器 `current` release 和 `evidence_to_deliverable` promotion 状态全部冻结。

### 1.1 2026-07-19 宏观重排：停止以治理层数量代表进展

后续不再沿着“panel blocked → 立即换模型 → 再加一版授权/证据合同”的路径机械推进。V3 strong 失败的逐轮证据为：provider 请求正常返回并产生 token usage，但连续七个 assistant turns 的 `content`、`tool_calls` 和可见 reasoning 均为空，工具调用为 0；它没有进入 E2B 或 Excel 操作阶段。因此该结果不能证明 `gpt-5.6-sol` 的任务能力不足，原 `agent_nonconvergence` 只保留为历史粗分类，当前解释提升为 `model_gateway_agent_protocol_indeterminate`。未授权 request `8b6c6aad...e65ab` 冻结为 superseded pre-execution artifact，不得创建 receipt 或执行。

工作重排为两条并行轨道，随后才汇合到路线比较：

1. **轨道 A：限额式 agent 兼容性闭环。** 只修复响应可观测性、空响应 fail-fast、context/completion 预算混用和 client protocol 选择；最多一次离线改造、一次 1–2 call 公共工具探针。探针仍异常则停止适配，选择已知兼容模型，不继续调 agent。
2. **轨道 B：任务真实性金样本。** 不等待完整 solver panel，先从四个 motif 选择约 6 个实际任务，检查岗位真实性、信息充分性、自然难度、专业判断空间、真实交付形态和 rubric 关注点；LLM proxy 只能初筛，至少抽样引入独立专业判断。
3. **汇合点：最小行为 screening。** 只有轨道 A 提供可用 solver，且轨道 B 的任务达到绝对真实性门槛，才运行 12-task matched screening；否则输出 `redesign_again`，不扩充 schema、模型矩阵或任务数量。
4. **训练与 promotion 继续后置。** 路线比较只回答任务生成路线是否有效；不自动导出训练集，不启动 SFT/RL，不切换默认链。

去工程化约束：除非真实任务或真实执行暴露 blocking defect，R0–R5 接口冻结；新模块必须替代旧步骤或消除人工操作，不能只增加包装层；测试数量仅作回归证据，不再作为主要进度指标；兼容性工作不得超过上述一次改造和一次探针预算。

## 二、证据基线与当前边界

| 项目 | 当前事实 | 对本计划的约束 |
| --- | --- | --- |
| Phase 16 | 24/24 完成，结论为 `redesign_again` | 不继续局部调优或推广 Contract V2 / E2D |
| Milestone C/D/E | 本地自动化、服务器复现、warehouse slice 已完成 | 保留 Manifest V2、scratch-first、checksum、resume 和 Docker 底座 |
| Finance production | 60/60 candidate-ready | 不把数量或内部 pass 解释为训练价值 |
| F4.2 | 新 source→skill→task 八题内部检查 8/8 通过 | 证明混合闭环可运行，不证明行为有效或有区分度 |
| F4.3 | 32 个 solver 组合仅 15 个实际交付；Slots 2/5/8 系统性无交付 | 输出合同必须先成为 blocking gate |
| F4.3 有效任务 | 其余五题的三个有效模型平均分为 0.98/0.96/1.00 | 需要重新设计 productive complexity、rubric 和 solver panel |
| 当前 release | `milestone-f-data-production-6304e84` | 重构路线不得静默切换 production current |

本计划当前不授权：

- 新的私有任务包外部上传或模型评测；
- RL、SFT、reward training 或训练数据正式导出；
- canonical registry、sampler weight、transition prior 或默认生成器 mutation；
- 继续批量扩题；
- 激活 F4.2/F4.3 candidate release。

## 三、重构原则

### 当前实施进度（2026-07-18）

| 阶段 | 状态 | 已完成证据 | 剩余边界 |
| --- | --- | --- | --- |
| R0 | `completed` | Slots 2/5/8 已转为 tracked、去敏的 regression fixtures；三类已知失败可由离线 negative tests 稳定阻断；未复制 private package、provider output 或 secret | 保留为后续所有路线的不可删除回归基线 |
| R1 | `container_core_implemented` | versioned `DeliverableContract` 与全部门禁保持通过；当前本地完整测试与固定 Linux/amd64 容器均为 254 项；容器指纹 `b31a79b3eea9aeddc6d45c097e717f07f1e589f1f401326d3521d83467b9505d`，断网、只读、无凭据且清理成功 | Slots 2/5/8 的真实 solver 复验属于后续 R4 campaign，不能从容器 contract parity 推导 behaviorally validated |
| R2 | `post_v29_binding_cardinality_redesign_offline_ready` | relation join fields 为 provider-schema 必填；V29 又真实验证 strict proposal feedback repair。prompt 现要求每个 selected skill 恰好一个 binding，screening 区分 namespace/cardinality/missing-decorative。local/container 253/253；code fingerprint `c0860676...4990` | V29 不能证明跨 brief 稳定性。广泛 schema/provider/materialization failure 仍不可重试；cardinality 修复尚需 fresh provider observation |
| R3 | `typed_record_semantics_false_positive_fixed` | V27 fan-in 两路线 13 workbooks/26 sheets 实审全部通过；skill block 唯一原因是 role/header gate 忽略 `record_type=evidence_assessment_criterion`。门禁现使用 typed record semantics、排除 field labels，正负回归和 8/8 零外呼 replay 已通过，完整 local/container 为 249/249 | V27 原 block 保留且不得改写；replay 不是 provider attempt 或新物化。仍无真实 solver/professional evidence |
| R4 | `agent_protocol_diagnosis_required` | 三模型环境、fixture、工具和预算相同；weak 实际调用工具但生成伪 XLSX，medium 正常调用工具并通过。strong 的 provider transport/usage 正常，但连续空 assistant response、0 tool calls，未进入 sandbox；原 `agent_nonconvergence` 不足以支持模型能力判断 | 先完成脱敏响应元数据、空响应 fail-fast、context/completion 预算拆分和 client 兼容性判断；最多一次 1–2 call 公共探针。`8b6c...e65ab` 不得执行 |
| R5 | `recomputability_separated_locally` | factual validity 不再因 candidate-visible deterministic anchors 自动 pass，而是 provisional；内容 gate blocked 会阻断 factual validity，`missing_candidate_field` 只由实际 content report 清除。generator-owned evidence 不能自行建立 business grounding | 增加独立 business-grounding evidence contract；Utility productive-complexity 仍需真实行为/专业证据，结构 proxy 不得升级最终状态 |
| R6 | `behavioral_comparison_held_for_protocol_and_reality` | replacement contract 可复用，但候选 request 已冻结；V31 的 12 个 blind packages 仍保持未执行。路线比较框架完整，不代表现在就应运行 | 并行完成 agent 兼容性闭环与约 6-task 真实性金样本；两者均过绝对门槛后才恢复 12-task screening |
| R7 | `artifact_bound_report_core_implemented` | screening 必须从冻结 manifest 与完整 12-record compile report 重算；`RouteConfirmationReportV2` 只能由 absolute gates、matched environment、server reproduction、rollback、major-validity closure 五类独立 gate evidence 编译，gate/support 均校验 SHA；tamper、缺证或重算不一致只能 hold/redesign。即使输出 promote，也固定为 opt-in profile，default-chain/release/registry/training authority 全部为 false | 尚无真实 screening/confirmation/server evidence；不得从离线 scaffold 推导 production-ready、training-ready 或默认链 promotion |

阶段判断：V31 provider screening 与 blind staging 已通过，但 V1–V3 tool panels 均 blocked。weak 是真实文件工具行为失败，medium 通过，strong 则是模型—Tuzi gateway—Chat Completions—Stirrup 协议链的待判定故障，不能解释为模型能力排名。当前不执行 replacement request，不增加 turns/calls，也不立即换 strong 模型。下一步同时推进一个限额式兼容性诊断和一个约 6-task 的真实性金样本；完整 panel 与 12-task screening 只在两条轨道都达到绝对门槛后恢复。

当前已生成的离线证据位于 ignored artifacts：

- `artifacts/pipeline_reconstruction/deliverable_contract_smoke/deliverable_contract_smoke_report.json`；
- `artifacts/pipeline_reconstruction/end_to_end_runs/reconstruction_r1_legacy_compat/acceptance_report.json`；
- `artifacts/pipeline_reconstruction/end_to_end_runs/reconstruction_r1_blocking_profile/acceptance_report.json`；
- `artifacts/pipeline_reconstruction/task_design_frontend_smoke/task_design_frontend_smoke_report.json`；
- `artifacts/pipeline_reconstruction/end_to_end_runs/reconstruction_r2_design_frontend_v2/acceptance_report.json`；
- `artifacts/pipeline_reconstruction/hybrid_materializer_smoke/r3_offline_four_motif_v3_20260716/hybrid_materializer_smoke_report.json`；
- `artifacts/pipeline_reconstruction/solver_preflight_smoke/local_reference_20260716/solver_tool_preflight_report.json`；
- `artifacts/pipeline_reconstruction/hybrid_materializer_smoke/r5_offline_four_motif_v1_20260716/hybrid_materializer_smoke_report.json`；
- `artifacts/pipeline_reconstruction/route_comparison/r6_offline_manifest_v1_20260716/route_comparison_manifest.json`；
- `artifacts/pipeline_reconstruction/route_comparison/r6_campaign_dry_run_v4_20260716/campaign_manifest.json`；
- `artifacts/pipeline_reconstruction/route_comparison/r6_campaign_dry_run_v4_20260716/governance/campaign_preflight_report.json`；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-122633-daa6d94f/parity_report.json`（保留的首次导入路径失败）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-122735-04a91c44/parity_report.json`（断网、只读、无凭据，161 项测试通过）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-124745-e6fb9ea0/parity_report.json`（最新快照，断网、只读、无凭据，171 项测试通过）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-125223-32471cee/parity_report.json`（加入 provider 分片 resume 后的最终快照，171 项测试通过）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-130544-fd3fe077/parity_report.json`（加入 formal evidence compiler 后的最新快照，176 项测试通过）；
- `artifacts/pipeline_reconstruction/formal_brief_cohort/r6_admission_all_web_offset_0_20260716/formal_brief_cohort_admission_report.json`（四组 occurrence 审计之一；正式 cohort 被来源准入阻断）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-132219-7c8208f7/parity_report.json`（加入 source provenance/admission gate 后的最新快照，181 项测试通过）；
- `artifacts/pipeline_reconstruction/formal_public_substrate/r6_graph_calibration_registry_v1_20260716/seed_report.json`（隔离 public-source scratch registry 的 15-skill seed）；
- `artifacts/pipeline_reconstruction/formal_brief_cohort/r6_workflow_cohesion_audit_v2_20260716/formal_brief_cohort_admission_report.json`（旧结构 cohort 在 workflow-group coherence 下 4/4 blocked）；
- `artifacts/pipeline_reconstruction/formal_brief_cohort/r6_cohesive_admission_v4_20260716/formal_brief_cohort_admission_report.json`（单一 workflow-group 四 motif cohort，4/4 pass）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v6_20260716/governance/campaign_preflight_report.json`（历史冻结 formal campaign，12 assignments structural pass；原授权状态不得复用）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v6_20260716/governance/provider_smoke_authorization_request.json`（不可执行的精确双 assignment、gpt-5.6-sol、8 美元授权申请单）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v6_20260716/governance/provider_smoke_authorization_receipt.json`（用户授权的精确双 assignment receipt，绑定冻结 request/source/admission/policy 指纹）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v6_20260716/first_failures/cmp_b042a088da019f76_provider_proposal.json`（LLM-led 首次 causal-binding/authority failure，重试成功后仍保留）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v6_20260716/route_packages/brief_31f83336b665/skill_guided_llm/hybrid_materialization_report.json`（真实 provider proposal 的 skill-guided materialization pass）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v6_20260716/route_packages/brief_31f83336b665/llm_led_hybrid/hybrid_materialization_report.json`（真实 provider proposal 的 LLM-led materialization pass）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-134214-dc9d5bde/parity_report.json`（最新快照，182 项测试通过）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-140452-37e10a3e/parity_report.json`（workflow-group coherence 后最新快照，186 项测试通过）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-142024-5ea375b4/parity_report.json`（assignment-scoped authorization 与 R7 promotion 后最新快照，191 项测试通过）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-143014-83a40038/parity_report.json`（不可篡改授权链后最新快照，193 项测试通过）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-143652-2505937b/parity_report.json`（authorization-request 完整指纹公开后的最新快照，193 项测试通过）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v7_20260716/governance/campaign_preflight_report.json`（历史冻结 formal campaign，12 assignments structural pass；后续 provider screening 已作出 `redesign_again`）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v7_20260716/governance/authorization_requests/`（四份不可覆盖、hash-addressed 的双 assignment 授权申请）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-151356-52a4a244/parity_report.json`（追加式授权历史与独立预算核算后的最新快照，194 项测试通过）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v7_20260716/governance/provider_screening_outcome.json`（4/8 provider packages materialized，13 attempts，5 次无反馈重发，结论 `redesign_again`）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-185351-8ab3ada0/parity_report.json`（feedback-conditioned repair 合同后的最新快照，断网、只读、无凭据，197 项测试通过）；
- `artifacts/pipeline_reconstruction/task_design_repair_readiness/v8_preflight_from_v7_failures_20260717/repair_readiness_report.json`（v7 五个首错离线复演 5/5 pass，0 external calls）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v8_20260717/`（缺 readiness replay 的 superseded 离线候选，不得授权执行）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v9_20260717/governance/repair_readiness_verification_report.json`（五个首错当前代码重放 pass）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v9_20260717/governance/campaign_preflight_report.json`（v9 12 assignments structural pass，4 strict controls，0 external calls）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v9_20260717/`（仍依赖外部绝对路径的 superseded 离线候选，不得授权执行）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-192407-779034f8/parity_report.json`（readiness replay 与 v9 合同后的最新快照，断网、只读、无凭据，199 项测试通过）；
- `artifacts/pipeline_reconstruction/task_design_repair_readiness/v10_portable_from_v7_failures_20260717/`（自包含五首错 evidence bundle 与 5/5 readiness report）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v10_20260717/governance/campaign_preflight_report.json`（v10 12 assignments structural pass，4 strict controls，0 external calls）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v10_20260717/governance/authorization_requests/f1f2a947a297746e094ea7e2688116f097619fea7504d7df09005805ea5fab40.json`（superseded，不得批准或创建 receipt）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-193610-1d15cc10/parity_report.json`（portable bundle 与 v10 合同后的最新快照，断网、只读、无凭据，200 项测试通过）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v10_20260717/`（只在 prepare 重放 bundle 的 superseded 离线候选，不得授权执行）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v11_20260717/governance/campaign_preflight_report.json`（曾通过 continuous replay，后因代码指纹变化 fail closed，superseded）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v11_20260717/governance/authorization_requests/a7bb911ef9f711877f74117d788dd8123d31c1e4ff4b5fb6957df8b3f00a45c5.json`（superseded，不得批准或创建 receipt）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v12_20260717/`（因完整 evidence-freeze/R7 重算加固改变代码指纹而 fail closed，superseded）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v13_20260717/`（因 legacy semantic-review 高价模型默认阻断改变代码指纹而 fail closed，superseded）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v14_20260717/`（因 receipt compiler 改变代码指纹而 fail closed，superseded）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v15_20260717/governance/provider_screening_outcome.json`（用户授权 cross-check slice：两条路线首轮 pass，2/2 materialized，19,851 tokens，173.937 秒，4/8 美元；partial decision=`awaiting_provider_completion`）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v15_20260717/`（执行后 report-semantics 修复改变代码指纹，保存为 evidence，不得追加执行）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v16_20260717/governance/campaign_preflight_report.json`（preflight V2，12 assignments structural pass，external calls=true）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v16_20260717/governance/authorization_requests/3e3bd45281008c0883ce2362cee839f2552019524301fb0a83cd544f89db7e94.json`（已批准并完成的 policy-application 最小双路线申请）；
- `artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v16_20260717/governance/provider_screening_outcome.json`（2/8 provider assignments materialized，1 次 feedback-conditioned retry，31,026 tokens，226.827 秒，6/8 美元，decision=`awaiting_provider_completion`）；
- `artifacts/pipeline_reconstruction/content_audit/v15_v16_three_route_20260717/content_audit.md`（58 个 candidate XLSX 的只读内容/视觉审计；六个 route packages 全部被 report-first content gate 阻断）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260717-040628-14eb014b/parity_report.json`（preflight/screening V2 当前快照，断网、只读、无凭据，源码指纹 `14eb014b...ccb3`，219 项测试通过）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-212550-7cf7bc2b/parity_report.json`（当前代码最终快照，断网、只读、无凭据，源码指纹 `7cf7bc2b...9cdb`，219 项测试通过）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-211149-8c0ae98b/parity_report.json`（当前代码最终快照，断网、只读、无凭据，源码指纹 `8c0ae98b...f331`，217 项测试通过）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-205617-44e8026f/parity_report.json`（当前代码最终快照，断网、只读、无凭据，源码指纹 `44e8026f...cee4`，216 项测试通过）；
- `artifacts/pipeline_reconstruction/docker_parity/r6-docker-20260716-191044-0417de2a/parity_report.json`（formal repair-readiness admission 后最新快照，198 项测试通过）；
- `artifacts/pipeline_reconstruction/end_to_end_runs/reconstruction_r3_design_gate/acceptance_report.json`。

当前操作手册为 `docs/operations/pipeline_reconstruction_runbook.md`，覆盖 v7/v15 历史证据、v16 structural preflight、immutable request/receipt compiler、provider resume、停止条件、盲化 staging、显式 evidence freeze、solver/grader evidence、artifact-bound R7 confirmation、服务器空间清理和 rollback。

这些报告证明的是 R0/R1 本地合同链、R2/R3 设计与物化合同、R4 行为门禁代码、R5 质量分轴合同、R6 比较框架和正式来源 fail-closed 准入。v7 证明旧重试并非真正 repair；v16 则提供了一条真实 feedback-conditioned repair 成功观测。单点成功仍不证明跨 brief package completion、真实 solver 能力、专业 Utility、路线优越性或训练价值。

### 3.1 LLM 拥有设计权，程序拥有真值权和发布权

LLM 可以决定场景、角色、触发事件、材料关系、专业判断、工作流和交付意图；任何数值、匹配、分类、路径和 promotion 状态必须由确定性代码验证或生成。

### 3.2 一个事实只能有一个权威合同来源

prompt、模板、`deliverable_files`、expected-deliverables manifest 和 grader staging 不得分别维护文件名或路径。它们必须由同一个 versioned contract 编译生成。

### 3.3 内部一致性与独立有效性分开

生成器、resolver 和 rubric builder 共享前提时，只能证明内部一致性。整体语义审查、真实工具执行和专业质量评价必须尽量与生成前提解耦。

### 3.4 Validity 与 Utility 分轴

`Validity` 回答“任务是否正确、充分、合同一致并可执行”；`Utility` 回答“任务是否真实、有价值、有区分度并服务目标能力”。通过 Validity 不自动意味着高质量训练任务。

### 3.5 最少但关键的门禁

不再默认“发现一个问题就增加一个 stage”。新门禁必须说明它阻止的真实失败、输入输出、独立性和 promotion 影响；不能证明收益的旧检查应合并、降级为 diagnostic 或移除。

### 3.6 先小规模配对比较，再决定默认链

所有路线使用相同 source、skill/capability brief、任务数量、solver 环境、grader 合同和失败归因。先筛选，再确认，不进行无界扩题或模型 sweep。

### 3.7 保留治理底座和失败证据

保留 scratch registry、candidate/teacher 隔离、manifest、checksum、resume、外部效果台账、provider 预算、历史失败和 rollback。重构不覆盖已有 artifacts。

## 四、目标架构与职责分配

### 4.1 设计输入层

新增 `CapabilityBrief`，把 task generation 的输入从“motif + adapter 参数”提升为受来源约束的能力目标，至少包含：

- `source_refs`：支撑任务的公开来源和 evidence spans；
- `selected_skill_ids`：进入设计的 semantic skills；
- `business_role`、`trigger_event`、`business_goal`；
- `required_capabilities`：证据筛选、关系推断、规划、判断、复核、表达等；
- `productive_complexity_floor`：必须保留的有价值复杂性；
- `forbidden_shortcuts`：不得直接告诉候选人的 join、步骤或结论；
- `domain_and_safety_constraints`。

### 4.2 LLM 整体设计层

新增 versioned `TaskDesignProposal`。LLM 接收完整 `CapabilityBrief`、source/skill 摘要和可用文件类型，在单次整体设计中提出：

- 场景、角色、触发事件和真实使用者；
- evidence ecosystem 及文件间关系；
- 候选人必须自行完成的工作规划和判断；
- deliverable intent、受众和实际使用方式；
- productive complexity 与 accidental difficulty 的显式区分；
- 每个 skill 对工作流、证据关系或交付要求的 observable binding；
- 可回答性风险、待程序物化的事实约束和不应假设的内容。

LLM proposal 不得直接成为 truth、rubric、release 或 registry mutation 的权威来源。

### 4.3 确定性物化与合同层

程序根据 proposal 生成或物化 candidate-visible 文件，并建立：

- `TaskConstraintGraph` / `EvidenceDossierPlan`；
- deterministic seed、resolver 和 expected facts；
- `DeliverableContract`；
- candidate/teacher visibility manifest；
- prompt 的确定性提交段落；
- GoldenRun、TrainingAnnotation 和 fact validity records。

固定 adapter 从“控制整道题形态”降级为以下角色之一：

- 安全且可复现的 materializer；
- deterministic fact anchor；
- legacy compatibility route；
- LLM proposal 无法物化时的显式 fallback。

### 4.4 Whole-task 编辑层

编辑模型必须看到实际物化后的 candidate package、teacher contract、deliverable contract 和当前 findings，再提出版本化修订。它可以请求修改场景、文件内容或任务要求，但：

- 不能静默改 truth；
- 不能自由改写由 `DeliverableContract` 编译的提交段落；
- 不能把 productive complexity 简化为逐步说明；
- 每次修订必须重新物化并重跑下游验证；
- repair iteration 和 provider cost 必须有上限。

### 4.5 独立验证层

验证分为五类，分别记录状态，不再被一个 `candidate_ready` 掩盖：

1. `factual_validity`：candidate-visible 文件可以独立重算 truth；
2. `semantic_validity`：材料充分、要求明确、判断依据成立；
3. `contract_validity`：prompt、模板、文件名、格式和路径一致；
4. `behavioral_validity`：陌生 solver 在真实工具环境中生成精确预期交付物；
5. `professional_validity`：任务和交付物符合目标职业的合理工作方式。

每个维度必须同时记录 `evidence_tier` 和 `decision_authority`。确定性代码、独立 solver、LLM proxy 与人类领域专家属于不同证据等级；仅由 LLM 整体审查支持的专业合理性只能记为 `provisional`，不能伪装成人类专家结论。

### 4.6 Utility 与 promotion 层

新增 `UtilityProfile`，独立记录：

- real-worldness；
- productive complexity；
- source/skill causal contribution；
- rubric effective dimensions；
- model separation 和 score saturation；
- grader stability；
- 任务的训练能力目标；
- 人工式审查、调用成本和运行成本。

promotion 只读取冻结 cohort 的 `ValidityVector + UtilityProfile + BehavioralExecutionReport`，不得从单个内部 pass 或单次高分直接推导。

## 五、核心接口合同

### 5.1 `CapabilityBrief`

建议输出：`capability_brief.json`

最低要求：每个 selected skill 至少绑定一个实际 workflow step、evidence relation、required judgment 或 deliverable requirement。仅出现在标签或 prompt prose 中的 skill 计为 decorative binding。

### 5.2 `TaskDesignProposal`

建议输出：`task_design_proposal.json`

最低要求：

- source/skill refs 可追溯；
- required judgments 与材料关系明确；
- productive complexity 和 forbidden shortcuts 明确；
- deliverable 只表达意图，不自行指定不受治理的提交路径；
- unresolved design questions 非空时不得物化为 production candidate。

### 5.3 `DeliverableContract`

建议输出：`deliverable_contract.json`

最低字段：

```json
{
  "contract_version": "v1",
  "deliverables": [
    {
      "file_name": "review_output.xlsx",
      "relative_path": "deliverable_files/review_output.xlsx",
      "format": "xlsx",
      "creation_mode": "create|copy_then_edit|edit_provided_copy",
      "source_template": null,
      "must_exist": true,
      "must_be_nonempty": true,
      "openability_check": true
    }
  ],
  "prompt_submission_clause": "compiled_by_program",
  "allow_unlisted_deliverables": false
}
```

必须由该合同统一编译：

- prompt 的提交说明；
- `dataset_row.json.deliverable_files`；
- `expected_deliverables.json`；
- rw-task input staging；
- solver output inspection；
- grader staging。

### 5.4 `ValidityVector`

建议输出：`validity_vector.json`

每个维度使用 `not_evaluated|provisional|pass|revise|blocked`，并记录 evidence paths、evidence tier、finding owner、decision authority 和是否独立于生成器。不得把 `not_evaluated` 或 LLM-only `provisional` 解释为专家级 `pass`。

### 5.5 `BehavioralExecutionReport`

建议输出：`behavioral_execution_report.json`

至少区分：

- `solver_attempted`；
- `solver_process_completed`；
- `expected_deliverable_present`；
- `expected_deliverable_valid`；
- `wrong_name_or_path`；
- `empty_or_unopenable`；
- `tool_or_provider_failure`；
- `business_result_incorrect`；
- `professional_quality_insufficient`。

没有有效交付文件时不得调用 grader，也不得生成业务能力分数。

### 5.6 `UtilityProfile` 与 `RouteComparisonRecord`

建议输出：

- `utility_profile.json`；
- `route_comparison_manifest.json`；
- `route_comparison_report.json`；
- `reconstruction_promotion_record.json`。

比较记录必须冻结 route、source、brief、代码提交、模型、grader、环境、预算、重试和任务包 fingerprint。

## 六、分阶段实施计划

### R0：证据冻结与回归基线

目标：在不调用外部模型的前提下，把 F4.3 的失败变成可重复的系统回归测试。

工作项：

1. 冻结 Slots 2/5/8 的 prompt、reference/template、dataset row、expected deliverables 和失败原因；
2. 建立 tracked public/synthetic regression fixtures，不复制 secret 或原始 provider 输出；
3. 固定失败 taxonomy：文件名冲突、原地编辑歧义、提交目录不清；
4. 记录当前通用 exporter、validator 和 eval runner 的行为差距；
5. 冻结当前 public-smoke 和 legacy production compatibility baseline。

退出门禁：

- 三类已知失败都能由离线测试稳定重现；
- fixture 不包含 private package、teacher leak 或 secret；
- canonical registry 和现有 artifacts 不变。

外部权限：不需要。

### R1：统一输出合同与 blocking gate

目标：让 prompt、模板、目标文件名和提交路径只有一个权威来源。

工作项：

1. 实现 versioned `DeliverableContract` schema、compiler 和 validator；
2. 把 whole-task materializer、Pipeline B exporter、export validator、eval prep、runner inspection 和 grader staging 接入同一合同；
3. 对 basename、extension、relative path、template collision、create/copy/edit mode 做确定性检查；
4. 新增无需外部模型的 submission-path smoke，在与 rw-task 相同的目录映射中创建占位交付并验证发现逻辑；
5. runner 统一使用“精确预期文件存在、非空、可打开”作为 valid delivery；
6. 缺交付时阻止 grading，并保留过程结束与真实交付的独立计数；
7. 将该 gate 接入 `candidate_ready` 之前，但先仅在 reconstruction experimental profile 中 blocking。

退出门禁：

- Slots 2/5/8 回归 fixture 被新 gate 阻断；
- 正常 fixture 通过 exact-path、format 和 openability 检查；
- legacy profile 行为和 Milestone C public smoke 保持兼容；
- 通用 runner 与 F4.3 专用 runner 的 delivery 语义一致。

外部权限：不需要。

### R2：LLM 整体任务设计前端

目标：让 LLM 在 adapter 之前参与完整任务设计，而不是只在成品之后修补。

工作项：

1. 实现 `CapabilityBrief` 和 `TaskDesignProposal` schema；
2. 从 source evidence、semantic skills、workflow episode、motif grammar 和 domain profile 生成设计上下文；
3. 设计 whole-context prompt，要求 scenario、evidence topology、judgments、deliverable intent 和 productive complexity；
4. 明确 LLM 无 truth、path、promotion 和 registry mutation 权限；
5. 增加 deterministic proposal validation、source/skill binding report 和 prompt-injection boundary；
6. 先用 mock/tracked fixture 完成离线 contract tests，再申请 bounded public-source provider smoke。

退出门禁：

- proposal contract 可离线复现并拒绝缺 provenance、装饰性 skill 或未解决核心问题的设计；
- 每个 required capability 都映射到可观察的任务行为；
- 未经 materialization 的 proposal 不会进入 package 或 production state。

外部权限：离线开发不需要；真实 provider smoke 需要新的明确授权。

### R3：混合 materialization 与 whole-task repair loop

目标：将 LLM 设计转化为可复现文件任务，同时避免 adapter 再次接管全部任务形态。

工作项：

1. 把 adapter 分拆为 materializer、fact anchor 和 legacy template route；
2. 从 proposal 生成 evidence dossier、candidate-visible files 和 deterministic truth anchors；
3. 由 `DeliverableContract` 编译最终提交段落，禁止 editor 自由漂移文件名；
4. 让 whole-task editor 读取实际 candidate package 和 governed contracts；
5. 增加 complexity-preservation check，防止修订把判断题变成逐步填表；
6. 修订后重跑 materialization、truth、isolation、contract、visual 和 package gates；
7. repair loop 默认一次修订、最多一次受治理重试，超限即停止。

退出门禁：

- 至少覆盖当前四个 motif 的离线 experimental packages；
- truth 全部来自 candidate-visible deterministic recomputation；
- proposal 中的 skill/capability bindings 在最终文件和 rubric 中仍可追踪；
- 无跨模板 residue、路径冲突或 teacher leak。

外部权限：真实 editor 调用需要单独授权；离线 fixture/materializer 不需要。

### R4：独立行为验证与失败归因

目标：证明陌生 solver 能在真实工具环境中提交正确文件，而不是只返回文本答案或正常结束进程。

工作项：

1. 增加 solver tool preflight，先用极小公共任务验证文件创建、复制、保存和提交能力；
2. 在判断模型能力前，先证明 provider transport、响应字段映射、tool-call parsing、sandbox execution 四层分别可观测；“有 token 但 content/tool calls 均为空”分类为 protocol indeterminate，不得归为弱能力；
3. response audit 只保存 finish reason、字段存在性、content 长度、tool-call 数、reasoning 字段状态和 token usage 等脱敏元数据，不保存 secret；连续一至两次空 assistant response 立即停止；
4. 将模型真实 context window、agent summarization threshold 和每次 completion reservation 分开配置，不再用一个 `max_tokens` 同时承担三种语义；
5. 只允许一次 1–2 call 的公共工具兼容性探针。若正确 client/protocol 下仍不能形成 tool call，记录 adapter incompatibility 并更换候选，不继续增加预算；
6. 只让通过 preflight 的模型进入业务难度比较；未通过者按 tool-capability、protocol compatibility 或 provider failure 分别保留；
7. solver 只能读取 candidate-visible package 和 `DeliverableContract` 编译后的 prompt；
8. 精确区分 provider、gateway/protocol、tool、non-delivery、wrong path、invalid file、business error 和 professional quality；
9. 在本地与固定 Docker 环境复现相同 delivery inspection；只有 valid delivery 才进入 grader。

退出门禁：

- Slots 2/5/8 不再出现由任务合同导致的系统性无交付；
- 过程完成、真实交付、文件有效和业务评分四组指标完全分离；
- 空 assistant response 不再消耗完整 turn/call budget，gateway/protocol 故障不会进入模型能力排名；
- 首次失败、重试理由和所有 output fingerprints 被保留。

外部权限：真实 solver/grader 执行需要新的 campaign-scoped 明确授权。

### R5：Utility、productive complexity 与 rubric 重构

目标：把“事实正确”从二元高权重评分中分离出来，建立可区分的专业质量评价。

工作项：

1. deterministic facts 作为 validity anchors，避免重复 criterion 只检查同一结果；
2. rubric 至少区分事实准确、证据追踪、方法/过程、异常处置、可复核性、结构可用性和专业表达；
3. 每个 criterion 具有独立 failure signal、证据要求和部分得分语义；
4. 建立 productive-complexity profile，评估 evidence integration、planning、judgment、audit trail 和 deliverable design；
5. 建立 accidental-difficulty blocker，覆盖缺字段、错误路径、工具不兼容、隐含 primary truth 和 grader 不稳定；
6. 对 selected skills 做 causal binding/ablation：移除 skill 后若工作流、证据关系和交付要求均不变，则标记为 decorative；
7. 校准 solver panel，确保工具能力合格且存在可比较的弱—中—强梯度；
8. 在看到正式结果前冻结 score saturation、grader disagreement 和 informative-case 口径。
9. 专业合理性若只能由 LLM proxy 检查，必须保留 `provisional` 与专家证据缺口；它可以支持路线筛选，但不能单独授权训练池 admission。

退出门禁：

- rubric 不再由同义 fact checks 主导；
- Validity failure 不被包装成低业务分数；
- 每个任务的 productive complexity 和 skill causal contribution 可审计；
- solver panel preflight 与 grader stability 合同冻结。

外部权限：rubric 离线开发不需要；模型校准需要单独授权。

### R6：三路线同源受控比较

目标：用最小但可解释的实验决定下一代默认任务生成路线。

比较路线：

- Route A：当前严格模板/adapter 路线；
- Route B：skill-guided LLM 设计，但主要沿用现有 materializer；
- Route C：LLM whole-task design + deterministic governance 的混合路线。

实验分三级：

1. reality cohort：从四个 motif 中取约 6 题，以实际 candidate package 审查岗位真实性、信息充分性、自然难度、专业判断空间、真实交付形态和 rubric 关注点；存在系统性问题时回到设计层，不运行完整 panel；
2. screening：仅在 reality cohort 与 agent compatibility 都通过后，每条路线各生成一题，共 12 个 packages，运行全部离线 gates 和单个合格 solver；
3. confirmation：只保留 screening 最优的两条路线，使用冻结 brief 和小型合格 solver panel 做配对确认。

控制变量：

- 相同 public source 范围和 source snapshot；
- 相同 selected skills、capability goals、motif 配额和文件类型预算；
- 相同代码提交、容器、solver/grader 合同、timeout、重试和成本上限；
- route-blind task IDs 和 reviewer context；
- 不使用 GDPVal 任务内容。

比较指标：

- offline validity rate；
- exact valid delivery rate；
- systemic task failure / major defect rate；
- professional plausibility；
- productive complexity coverage；
- skill causal coverage；
- rubric effective dimension count 和 score saturation；
- comparable model pairs、grader disagreement 和 failure attribution；
- LLM 调用成本、运行时间、人工式复核成本和实现复杂度。

退出门禁：

- promotion thresholds 在执行前冻结，结果后不得调参追线；
- 至少一条路线同时满足 Validity 与 Utility，而不是只在单轴获胜；
- 若所有路线均失败，输出 `redesign_again`，不以相对最佳替代绝对门槛；
- 完整比较 report、fingerprints、成本和失败证据可复核。

外部权限：需要新的、明确命名的 comparison campaign 授权。

### R7：Production 集成、服务器候选与 closeout

目标：只在比较证据支持时，把胜出路线以可回滚方式接入生产。

工作项：

1. 写入 `reconstruction_promotion_record.json`，明确 promote、hold 或 redesign；
2. 新路线先作为 opt-in versioned profile，不覆盖 legacy 默认链；
3. 运行本地离线、Docker 离线、服务器候选复现和 bounded public smoke；
4. 验证 canonical registry、GDPVal 污染隔离、secret、manifest 和 rollback；
5. 仅在显式 review/apply 后创建 candidate release；
6. 激活 release 前再次获得用户授权；
7. 更新《项目概要》，将本计划和详细报告归档。

退出门禁：

- 候选 release 可在本地和服务器复现；
- legacy route 和 current release 可回滚；
- production contract、接口、runbook 和文档同步；
- 没有未决 major validity finding；
- 用户显式批准激活。

外部权限：服务器 public smoke 和 release 激活分别需要明确授权。

当前离线进度：report-only promotion compiler 已实现。它不会创建 candidate release 或 apply mutation；缺正式 screening/confirmation/server/rollback 证据时只能输出 hold/redesign。

## 七、状态模型与 promotion 语义

现有生命周期暂不破坏性改名。重构期间使用 additive axes：

```text
legacy structural state:
generated -> structurally_valid -> verifier_passed -> candidate_ready

reconstruction validity axes:
factual_validity
semantic_validity
contract_validity
behavioral_validity
professional_validity

utility axes:
real_worldness
productive_complexity
skill_causal_contribution
rubric_resolution
model_separation
```

过渡规则：

- `candidate_ready` 只表示 legacy structural/export contract 成立；
- `candidate_ready` 不再被文字解释为训练准备完成；
- 新路线只有完成 offline validity 才能成为 `reconstruction_validity_ready`；
- 只有受治理真实执行完成后才能成为 `behaviorally_validated`；
- `training_pool_candidate` 必须同时满足冻结的 Validity 和 Utility 门槛，并经过显式 promotion；
- 历史任务未运行新合同则标记 `not_evaluated`，不得自动补写 `pass`。

## 八、指标定义

### 8.1 Validity

- `offline_valid_task_rate`：五类 validity 中不需要外部执行的维度全部通过的任务比例；
- `exact_valid_delivery_rate`：合格 solver-task 组合中，精确预期路径文件存在、非空、可打开的比例；
- `systemic_task_failure_rate`：多个合格 solver 因同一任务合同问题失败的任务比例；
- `major_task_defect_rate`：存在错误 truth、材料不足、合同冲突或不可执行要求的任务比例；
- `candidate_teacher_isolation_rate`：无 teacher-only 泄漏的任务比例。

### 8.2 Utility

- `productive_complexity_coverage`：预先声明的能力目标在最终任务中仍可观察的比例；
- `skill_causal_coverage`：selected skills 中具有 workflow/evidence/judgment/deliverable binding 的比例；
- `rubric_effective_dimension_count`：实际区分不同质量行为的非重复维度数量；
- `score_saturation_rate`：有效 solver 输出集中在极窄高分区间的任务比例；
- `informative_task_rate`：在工具合格且 grader 稳定前提下形成可解释能力差异的任务比例；
- `professional_plausibility_rate`：整体审查认为角色、材料、步骤和交付物符合真实工作的比例。

所有专业合理性和 real-worldness 指标同时报告 evidence tier；LLM proxy、人类式复核和真实领域专家不得合并成一个无来源比例。

### 8.3 Operational

- stage resume/replay 成功率；
- normalized content fingerprint 稳定性；
- canonical registry hash 不变；
- provider failure、timeout、retry 和 cost；
- 每个有效任务的 LLM、solver、grader 和人工式复核成本；
- legacy compatibility regressions。

数值 promotion 阈值由 R5 在正式 comparison 前冻结；不得在看到 R6 结果后修改。

## 九、测试与验证矩阵

| 层级 | 覆盖内容 | 是否允许外部调用 |
| --- | --- | --- |
| schema/unit | contract validation、path safety、state transition、redaction | 否 |
| negative controls | 文件名冲突、模板碰撞、原地编辑歧义、错误路径、空文件、teacher leak | 否 |
| integration | proposal→materializer→truth→export→delivery inspection | 否 |
| regression | F4.3 Slots 2/5/8 三类失败 | 否 |
| offline E2E | public fixture、legacy fingerprint、resume/rerun、registry hash | 否 |
| container | non-root、read-only rootfs、tmpfs、LibreOffice/Poppler、路径映射 | 否 |
| bounded provider smoke | public source proposal/editor contract | 需明确授权 |
| solver/grader campaign | actual delivery、business correctness、utility | 需明确授权 |
| server candidate | fixed image、offline equivalence、bounded public smoke | 需明确授权 |

任何 expensive execution 之前必须按顺序通过 schema、negative、integration、fingerprint、dry-run 和 runbook 检查。

## 十、兼容与迁移策略

- 新能力首先进入 `reconstruction_experimental` profile，不修改 legacy 默认 profile；
- contract 和 report 全部 versioned，旧 manifest 不做隐式原地升级；
- legacy runners 保持可运行，新 runner 通过 shared core 使用统一 delivery semantics；
- Milestone C public-smoke acceptance 保留为回归基线；
- 新字段优先 additive，只有在受控证据显示旧语义危险时才进行 breaking migration；
- code 放在 `src/task_generator/`，CLI/test 放在 `Test/`，运行输出放在 `artifacts/pipeline_reconstruction/`；
- `Test/v2_outputs/`、历史 artifacts、archive 和用户 dirty files 保持不动；
- canonical registry、sampler、promotion 和 release apply 均保持显式命令；
- `.env`、key 文件、provider 输出和私有任务包不得进入 tracked fixtures 或文档。

## 十一、风险与缓解

| 风险 | 表现 | 缓解措施 |
| --- | --- | --- |
| LLM hallucination | 场景自然但事实或政策无支撑 | source refs、proposal-only、deterministic materialization |
| 过度简化 | editor 为唯一答案补齐所有步骤 | complexity floor、forbidden shortcuts、repair 后能力覆盖检查 |
| 验证相关性 | generator、rubric、reviewer 共享错误前提 | black-box solver、独立视图、不同角色证据 |
| schema 再次僵化 | 新 contract 变成新模板系统 | contract 固定安全/真值边界，不固定完整任务形态 |
| 交付合同漂移 | prompt、模板和 dataset row 名称不同 | single-source `DeliverableContract` compiler |
| solver 不可比 | 模型不会保存文件或工具链异常 | tool preflight、failure taxonomy、只比较合格输出 |
| grader 饱和或不稳 | 有文件即满分、grader 分歧大 | validity 与 score 分离、多维 rubric、复评策略 |
| 成本失控 | whole-context prompt 和多模型评测昂贵 | 两级筛选、预算 ledger、最大重试、停止条件 |
| provider 不稳定 | 非 JSON、timeout、quota | frozen contract、原子 ledger、fail closed、无 mock fallback |
| gateway/tool 协议错配 | 有 token 但 agent 得到空 content/tool calls | 脱敏响应元数据、空响应 fail-fast、context/completion 拆分、一次限额探针 |
| 治理过度工程化 | schema/test/授权层增长快于真实任务证据 | 冻结 R0–R5、模块必须替代旧步骤、兼容性一次改造上限、真实性 cohort 优先 |
| 文档再次漂移 | active docs 保留历史状态 | overview 单一状态源、workstream closeout checklist |

## 十二、建议的实现切片

按以下小切片推进，每一片均要求代码、测试、报告和文档同步：

1. `Slice 1`：R0 fixtures + `DeliverableContract` schema/negative tests；
2. `Slice 2`：prompt/export/prep/runner 统一编译与 inspection；
3. `Slice 3`：Slots 2/5/8 离线回归 + container submission-path smoke；
4. `Slice 4`：`CapabilityBrief` / `TaskDesignProposal` 离线 contract；
5. `Slice 5`：LLM proposal experimental executor + source/skill binding report；
6. `Slice 6`：hybrid materializer + complexity-preserving repair loop；
7. `Slice 7`：ValidityVector、UtilityProfile 和 rubric redesign；
8. `Slice 8A`：agent response observability + 空响应 fail-fast + context/completion 拆分 + 一次兼容性探针；
9. `Slice 8B`：约 6-task 真实性金样本与独立专业抽样；
10. `Slice 9`：仅在 8A/8B 双门通过后运行三路线 screening / confirmation；
11. `Slice 10`：promotion、server candidate、rollback 和 closeout。

Slices 1–3、Slices 4–7 的离线核心、Slice 8 的 preflight/behavioral-report 本地与固定容器合同路径，以及 Slice 9 的三路线权限合同、comparison campaign、strict controls、batch proposal ingestion、route-blind staging、evidence freeze 和 R7 artifact-bound report core 均已完成。v15/v16 因占位内容冻结；v21 首个真实 V2 pair 驱动长文本换行/行高修复；v22 fresh skill-guided package 验证业务可读 enum/`Yes/No`。累计 artifact-tool 审计覆盖 115 个工作簿和 172 张预览，115/115 export 副本一致。v22 LLM-led 在 V2 schema parse 阶段失败且无已解析 proposal，因此按 feedback-only 重试合同停止；campaign 不再把 contract/provider failure 当作 proposal repair 候选。provider completion floor 保持 16,000 tokens，高价 `claude-sonnet-4-6` 继续硬阻断；后续外呼必须重新冻结指纹并绑定 immutable exact request/receipt。固定容器证据不替代真实 solver 行为证据。

`R2.1 / R3.1 schema-interface hardening` 的离线部分已经完成：

1. 用 tracked malformed V2 fixtures 覆盖缺字段、错误 union、嵌套 record 形状、enum/boolean 显示和超长 proposal；
2. 冻结 sanitized contract finding schema，证明其中没有 raw provider 字段值；
3. 比较“单体 V2 proposal”与“语义 proposal → 程序归一化执行合同”两种接口，但程序不得补造业务事实或替 LLM 决定证据关系；
4. 为归一化增加 semantic-loss、productive-complexity-loss 和 authority negative controls；
5. v25 cross-check pair 已 2/2 物化并包含一次 feedback-conditioned provenance repair；fan-in pair 也 2/2 首轮物化。policy-application 的历史 skill block、validator 修复与零外呼 replay 均保持冻结。fresh V26 policy pair 在当前指纹下 2/2 首轮通过并物化，16 个 provider-route workbooks 与 32 张 sheet 实审无内容、显示、provenance 或 export 缺陷；这仍只是单 brief provider/materialization 证据。任何下一 provider 或 behavioral slice 都必须重新冻结 campaign 并单独授权。

后续 V27 fan-in pair 进一步给出 1 个首轮物化和 1 个 deterministic content block；实审证明该 block 是旧 gate 忽略 typed `record_type` 的假阳性。fresh V28 的四个获授权 pairs 已全部完成：LLM-led 4/4、skill-guided 3/4 materialized；第三个 pair 的 skill-guided 因 provider 未给 relation join contract 而在 normalization 层 fail closed，且无 strict proposal 可 repair。最后一个 brief pair 2/2 首轮物化。V28 共 8 calls、102,082 tokens、1,076.593 秒、16 USD；47 provider-route workbooks/94 sheets 实审通过。正式 screening=`redesign_again`，冻结 block 不得覆盖，matched packages 不完整且不得启动 solver。

post-V28 离线改造已把 relation join fields 提升为 semantic provider schema 的非空 required 字段，并在 prompt 中显式禁止省略/`null`。兼容 draft schema 仅用于识别“整体可解析、局部 semantic contract 不完整”的响应；程序保存 draft 和 findings、状态为 `semantic_proposal_blocked`，但绝不合成 join key。campaign 只有在首轮实际 prompt、draft、normalization feedback 和 canonical IDs 均可验证时才允许唯一第二次 repair，并以两份实际 prompt 判断 feedback-conditioned；其他 contract/provider/materialization failure 继续停止。42 项针对性和 252 项完整 local/container 回归通过，container parity=`2178bd38...c23b`、campaign code fingerprint=`4ec4dadb...b36b`。这是 V29 readiness，不是 provider pass。

V29 `r6_formal_public_v29` 当时完成 formal public-source 冻结、四个 motif-aware strict controls、portable repair-readiness 1/1、structural preflight 和 immutable exact request `df63258c1258b91a10d7d152d21989ca9867a32608d900e89bb03bb052b1bf1d`；其随后获授权的执行结果见下段。

V29 上述 request 已消费：skill-guided 首轮通过并物化，LLM-led 首轮 duplicate skill binding 被阻断、随后唯一 feedback repair 通过并物化。3 calls、44,270 tokens、377.390 秒、6 USD，0 unconditioned retry；16 个 provider-route workbooks/32 sheets 的内容、公式、显示、provenance 与 export identity 审计全部通过。历史 screening=`redesign_again` 且不得覆盖。离线修复补齐“一 selected skill 恰好一 binding”并细分 screening reasons；253 local/container tests 通过，container parity=`989dd8bb...4fe`、code fingerprint=`c0860676...4990`。

V30 `r6_formal_public_v30` 已用 V29 首错完成 portable repair-readiness 1/1，四个 strict controls 与 structural preflight 均 pass。immutable exact request `32573db4b13f492890949495656c4b7a4d48edbd1e48def339d59a4de7c5dcf1` 只覆盖 brief `brief_93974f826477` 的 skill-guided `cmp_9a365f866100f17c` 与 LLM-led `cmp_ebf56b985922a6cc`、`gpt-5.6-sol`、最多 8 USD和受管 feedback repair；排除 solver、grader、review、registry、release 与 promotion。此处为调用前历史快照。

V30 首对已消费：skill-guided 首轮通过，LLM-led 保存 unused-source 首错后由唯一 feedback repair 通过，2/2 materialized。累计 3 calls、42,616 tokens、354.235 秒、6 USD、0 unconditioned retry；15 workbooks/30 sheets 审计通过。partial screening=`awaiting_provider_completion`，reason 仅 `provider_campaign_incomplete`。next cross-check request `74a6e65ff0eb93d85f161a8cda7928092be2005471693bea180259f67d125d47` 覆盖 `cmp_6e163b9e43cda1d2` 与 `cmp_a8ea6655de2a674c`，仍仅 `gpt-5.6-sol`、最多 8 USD并排除全部 solver/grader/review/mutation authority；此处为用户确认前历史快照。

用户授权上述 cross-check request 后，receipt 编译前审计发现 previous-slice receipt 可在不匹配 active request 的情况下把 campaign 标成 ready。scope gate 尚未调用，故该授权 0 provider calls、0 新预留。preflight 现要求 receipt request SHA 精确等于 active request SHA，否则 `authorization_receipt_active_request_mismatch` 且不改变状态。新增回归后 local/container 254/254；V30 冻结。

V31 `r6_formal_public_v31` 使用 V30 unused-source 首错完成 portable repair-readiness 1/1，四个 strict controls 与 structural preflight 均 pass。cross-check exact request `6e486b9d...0ba5` 已消费：LLM-led 首轮通过并物化；skill-guided 首轮因 mutation-authority 越界保存 `proposal_blocked`，唯一 feedback-conditioned repair 后通过并物化。累计 3 calls、58,916 tokens、501.297 秒、6 USD，0 unconditioned retry；18 workbooks/36 sheets 经 artifact-tool 导入、公式和逐图审计全部通过，18/18 candidate/export identity。partial screening=`awaiting_provider_completion`，reason 仅 `provider_campaign_incomplete`。

V31 下一 policy-application exact request `5ad5bb68c70b307f57cf4a66bb70228e22236683f318a8735a66600b160546cf` 覆盖 brief `brief_93974f826477` 的 skill-guided `cmp_000f7ca3889507c9` 与 LLM-led `cmp_f82bff62a06e402e`，仍只使用 `gpt-5.6-sol`、最多 8 USD和受管 feedback repair；排除 solver/grader/review/registry/release/promotion，external calls=0，等待 exact 授权。

上述 policy request 已消费：两路线均首轮通过并物化，2 calls、24,923 tokens、269.062 秒、4 USD，无 repair。15 workbooks/30 sheets 的 artifact-tool 导入、公式、显示、provenance 与 15/15 export identity 审计通过。V31 累计 4/8 materialized、5 calls、83,839 tokens、770.359 秒、10 USD；partial screening 仍仅有 `provider_campaign_incomplete`。

V31 下一 fan-in exact request `34b32317261856d0ceb948cb587cd2930fd08bb9701bb4b83bf6daafcdcc77c0` 覆盖 brief `brief_2630d8f77264` 的 skill-guided `cmp_5033d781118d65e2` 与 LLM-led `cmp_34da237cf93dcc20`，仍只使用 `gpt-5.6-sol`、最多 8 USD和受管 feedback repair；排除 solver/grader/review/registry/release/promotion，external calls=0，等待 exact 授权。

上述 fan-in request 已消费：两路线均首轮通过并物化，2 calls、24,060 tokens、253.124 秒、4 USD，无 repair。13 workbooks/26 sheets 的 artifact-tool 导入、公式、显示、provenance 与 13/13 export identity 审计通过。V31 累计 6/8 materialized、7 calls、107,899 tokens、1023.483 秒、14 USD；partial screening 仍仅有 `provider_campaign_incomplete`。

V31 最终 experimental evidence-to-deliverable exact request `588d7708f7389622166c51bbae7b63af53077227b7bad2b514e045d36890af3f` 已消费。skill-guided 首轮通过；LLM-led 首轮保留 unused-source `proposal_blocked`，唯一 feedback-conditioned repair 后通过。该 pair 为 3 calls、40,810 tokens、387.391 秒、6 USD；12 workbooks/24 sheets 与 12/12 export identity 审计通过。V31 最终为 8/8 materialized、10 calls、148,709 tokens、1410.874 秒、20 USD，2 feedback retries、0 unconditioned retry。`v3.provider_screening_outcome.2`=`proceed_to_behavioral_evaluation`；12/12 route-blind staging pass 且 teacher artifacts excluded。该结果不改变 motif 的 experimental 身份，也不授权 solver/grader/review/registry/release/promotion。

正式结果导入不允许人工拼表。先用 `run_v3_evaluation_calibration.py` 冻结通过同环境 tool preflight 的 weak/medium/strong panel，并分析 grader repeats；campaign 的 `evidence-template` 生成 12 题精确路径合同，补齐证据后必须执行 `evidence-freeze`，固定 comparison/staging/panel/grader/behavioral/professional 文件及其内容哈希。`evidence-analyze` 只有在 frozen input 的全部证据由 `RouteComparisonEvidenceCompiler` 编译通过后才调用 analyzer。单题、部分路线或未冻结证据不能产生排名。

## 十三、停止条件

出现以下任一情况时停止当前 slice，保存证据并回到设计层，不继续扩大：

- 输出合同 negative control 不能稳定捕获已知失败；
- 新路线必须依赖 teacher leak、手工 JSON 修补或隐藏 fallback 才能通过；
- 两个及以上合格 solver 因同一任务定义问题失败；
- productive complexity 为通过 validity 被系统性删除；
- provider/schema contract 首次失败且没有可解析 proposal，或预算超限；
- agent 连续一至两次返回有 token 但无 content/tool calls；此时按 protocol indeterminate 停止，不继续耗尽模型预算；
- 兼容性轨道已经完成一次改造和一次探针仍失败；此时换兼容模型，不继续扩充 adapter；
- 真实性 cohort 出现两个及以上同类信息充分性、岗位合理性或人为复杂度 major defect；
- grader 无法形成稳定、可解释的评价；
- canonical registry、默认 release 或 secret 边界发生未授权变化；
- 任何路线只能以相对优势通过，但未达到绝对 Validity 门槛。

## 十四、完成定义

本 workstream 只有同时满足以下条件才可关闭：

1. `DeliverableContract` 已进入通用核心链，Slots 2/5/8 已通过离线回归和受治理小规模真实复验；
2. LLM 可以在 adapter 之前生成完整、可追溯的 task design proposal；
3. 程序能从 proposal 物化 candidate files、truth、prompt 和 export，且不接受 LLM truth；
4. Validity 和 Utility 已分轴实现、报告和验收；
5. 三路线完成同源 screening，胜出路线完成 confirmation；
6. 失败归因能够区分 task、solver/tool、provider、delivery、grader 和 professional quality；
7. promotion 决策为明确的 `promote|hold|redesign_again`，并有 rollback；
8. 本地、容器和必要的服务器候选证据可复现；
9. 《项目概要》、AGENTS、架构、接口、production contract 和 runbook 已同步；
10. 本计划与详细报告迁入 archive，当前状态不再由本文件维护。

即使本 workstream 成功，也只表示下一代任务生产路线具备受治理扩量资格，不自动授权 RL/SFT。训练价值验证必须作为后续独立里程碑，以冻结训练集、训练配方和 GDPVal 等外部测试完成。

## 十五、2026-07-19 执行进展：协议探针离线闭环

Track A 的离线改造已完成：Stirrup 的上下文窗口与单次 completion 上限已拆分；每次响应只持久化内容、工具调用、推理存在性和 token 计数，不保存提示词或回复正文；连续两次空 assistant 响应会以 `solver_protocol_blocked:consecutive_empty_assistant_responses` 快速失败，并归类为 `model_gateway_agent_protocol_indeterminate`。该改造只诊断适配链，不把结果解释为模型能力。

Track B 的现实任务验收契约已加入现有 Validity/Utility 模块，固定检查角色真实性、信息充分性、自然难度、专业判断、交付物真实性和 rubric 聚焦六个维度。Reality cohort 必须包含六个唯一任务，并由生成过程之外的审查者逐题确认；它只能允许进入后续协议合并，不授予训练资格。

当前本地与固定 Linux/amd64 套件均通过 292 项测试。最新 parity 断网、只读、无 provider 凭据且清理成功。下一外部边界仍是一个 `gpt-5.6-sol`、一个公开工具 fixture、一个 attempt、最多两个 provider calls 的精确协议探针；不得复用已作废的 replacement 请求。

协议探针已经关闭：首份授权在 provider 前暴露 timeout 字段映射缺陷并被冻结；修复后本地/容器 293/293 通过。第二份 exact request `ea3afe62...aae45` 的两次真实调用都得到 token usage，但 assistant 形状为空，零 tool/sandbox/delivery，并由快速失败规则停止；完整性审计通过。Track A 因此判定为当前 Tuzi Chat Completions → Stirrup adapter 不兼容并停止继续适配。后续 behavioral solver 应切换到已通过同一公开工具 fixture 的兼容模型；`gpt-5.6-sol` 仍可在已验证的非 agent-loop 任务设计 provider 路径中使用。当前主线转入六题 reality cohort，且不包含 experimental `evidence_to_deliverable`。

Reality cohort 使用官方 `deepseek-v4-pro` 作为与生成模型不同的独立 LLM proxy，并从头形成同模型证据。每题先做 candidate-visible 五维审查，再隔离做 rubric-focus 审查；顺序固定为六题 candidate 阶段后六题 rubric 阶段。12 个有效阶段各允许一次正常调用；仅 timeout/408/429/5xx、空响应、截断、非法 JSON 或 schema 缺失可在相同冻结输入上附格式反馈补跑一次。SDK 自动重试为零，最多 24 calls，单次 12k input/4k completion，campaign 总上限 0.25 USD。全六题 pass 只产生 `screening_ready`，不能提升 expert evidence、training admission 或 promotion；任何 revise、blocked 或不完整证据分别产生 `revise_before_screening`、`redesign_required` 或 `incomplete`。Gemini 历史结果不得混入聚合。

首个官方 DeepSeek cohort 已完成 12/12 首轮调用、零补跑。六题 candidate reality 全 pass；一题 fan-in rubric 因 criteria 对 skill/evidence 的重叠绑定被判 revise，其余五题 rubric pass。因此当前 decision 为 `revise_before_screening`，不得进入 screening。由于六题计分语义相同，当前禁止选择性修改该题；先统一校准 reviewer，再根据六题一致性结果决定是否需要全局 rubric compiler 修复。不得把旧 pass 或 candidate review 扩张为 training/promotion 证据。

后续横向审计证明该单题并无独有结构缺陷：六题均为七个最终 criteria、21 个 pair，且规范化 criterion ID、权重、observable behavior 与 failure signal 完全一致。新的确定性 scoring-authority audit 将 binding 明确排除在最终权重外，并在六题上全部 pass；共同 structure signature 为 `0e4bbcae...43ca9`，共同 scoring-semantic signature 为 `1c4ffda4...b9525ec`。Rubric Focus V3 已要求完整 pairwise 判断、具体 criterion 引用及 deterministic shared-evidence 对齐；相同 semantic signature 下结论或 pair 分类不一致将 fail closed。本地完整套件 313/313 通过。任何可执行申请必须绑定文档同步后的固定容器 parity；编译 immutable exact request 后必须暂停等待 SHA 授权。该 slice 只复用原六份 candidate pass，最多 12 DeepSeek calls/0.13 USD，不授权 screening。

授权 request `63a9b799...e0897` 的真实 recalibration 在 3 calls 后按合同冻结为 `incomplete`。第一题 pass；第二题两次均以 4,000 completion tokens/`finish_reason=length` 截断，唯一格式补跑已耗尽，其余四题未运行。这是结构化 21-pair 输出体积与 completion ceiling 不匹配的接口证据，不能解释为模型对 rubric 的实质否定。后续不得续跑该 receipt；应先离线压缩 pair 输出契约或通过新实验明确提高 completion ceiling，再完成新的本地/parity/exact authorization。

当前采用压缩合同而非提高预算：Compact V4 保留 21-pair 完整分类，将非风险 pair 的重复 rationale/locator 删除，仅为风险 pair 输出 `risk_findings`。六题真实完整 prompt 估算最高 10,114 tokens，标准 pass JSON 约 977 tokens，显著低于 4k completion ceiling。V4 与 V3 结果类型并存，旧 request/receipt 可读但不得复用；新的 request 只能授权六个 `rubric_focus_v4_compact` stages，并继续复用原 candidate pass。

Compact V4 request `f96a2ab6...af1b1` 已完成 6/6 首轮调用、零补跑。所有 rubric reviews pass；每题 21-pair 分类完全一致，为 17 distinct、4 shared-evidence-distinct、0 risk findings。总 usage 为 42,476 prompt/16,285 completion tokens，reserved ceiling 0.06 USD。与冻结的六份 candidate pass 合并后 reality cohort 为 `screening_ready`；这只关闭 independent LLM proxy reality gate，不提升 professional validity，也不直接执行 screening。下一阶段必须单独制定和授权受限 12 题 matched screening。

## 十六、两路线 12 题 Matched Screening V2

当前恢复项是 DeepSeek 公共 solver preflight 的治理闭环，而不是模型调用本身。旧 exact request `789f4f85...e742a3` 因缺少 matched campaign receipt/executor 而在执行前废弃，零调用。新增实现必须具备 active/immutable request 双哈希校验、campaign/fixture/parity/source 漂移检查、子进程前消费状态、单次执行、零 retry、日志脱敏、预算/outcome/首次失败留存，并输出可供确定性 solver selection 使用的 pass/fail report。实现和文档改变 source fingerprint，因此必须重新全量测试、运行固定 Linux/amd64 parity、编译 replacement exact request 并暂停。

`33fa2c1d...bc061f` 的执行前检查进一步暴露 public fixture 编译缺口：`SolverToolPreflight.create_fixture` 只生成 case 内容，不能替代 rw-task dataset root。修复后 runner 必须生成 `<dataset>/solver_tool_preflight/dataset_row.json` 及精确四文件 case tree；request compiler 与 executor 使用同一验证函数，缺失 row、引用、交付路径或出现额外文件均在编译 exact request 前阻断。

Public preflight `c6e149b5...3bf0f1` 已通过并关闭，DeepSeek solver selection 已冻结。后续实现不修改 Stirrup wrapper/adapter，而是在 matched campaign 上增加 business receipt 与端到端 orchestration。每题 task failure 后继续独立题；authorization、fingerprint 或总预算失效立即冻结。provider/环境故障产生 `incomplete`，non-delivery/wrong-path/invalid-XLSX 作为路线结果；有效交付才允许一次实质 grader，低分不得重抽。

Business request `d9373c88...cb1b9b` 暴露单 case 输入适配缺口并以零 provider calls 冻结。修复不改变 wrapper：每题创建 `<session_input>/<blind_task_id>/dataset_row.json` 的单 case dataset view，验证只有一个 case、row identity 正确且复制树与 request 绑定的 candidate-tree SHA 相同。execution state 必须在复制前写入，任何复制/校验中断都消费 receipt 并禁止重跑。

Replacement `f3addd1f...337873` 完整执行 12 题并关闭本轮 screening：两路线均为 0/6 valid delivery，最终 `redesign_required`。56 solver calls 中没有 infrastructure failure；7 题因 tool-call JSON 截断失败，5 题被每题 1 USD contract reservation 阻断。由于没有合法交付，grader 按合同保持 0 calls。下一工作流不得调 rubric、任务生成或路线权重，而应单独设计 solver protocol/budget redesign；原 12 题结果和首次失败保持冻结，不得重抽。

首轮 replicate-B generation 已冻结为 4/6 provider materialized、1 个确定性内容门误判和 1 个无 persisted draft 的 schema failure。内容门仅增加窄映射 `corroborating/corroboration/corroborative -> support`，并保留无关角色负例；cross-check 使用原 proposal 零调用回放。不可修复失败必须落为 blocked，不能停留在 pending。唯一缺失 policy 包只可在新 exact recovery scope 下获得一次 replacement generation，不得复用 `9794d685...18a4` receipt。

下一 screening 不再把旧 V31 的 strict control 和 experimental evidence-to-deliverable 带回主线。cohort 固定为两条重构路线 × 三个非实验 motif × 两个 replicate。replicate A 是现有六个 Reality-pass 包；replicate B 从相同 source/skill/capability substrate 编译三个 sibling briefs，并为两条路线生成六个新包。

执行顺序固定为：本地/容器 parity → 六包 generation exact request → 新六包 Reality exact request → 官方 DeepSeek 公共工具 preflight exact request → 根据 DeepSeek pass 或冻结 Gemini fallback 编译十二包 business-screening exact request。每个 request 都暂停等待 exact SHA，不得把会话级许可扩张为 receipt。

screening 只使用一个合格 solver。有效交付物接受一次官方 DeepSeek 七维评分；重复评分、三模型 panel 和人工专家证据留到 confirmation。两路线全部达到绝对门槛且至少五个 matched pairs 可比较时输出 `confirmation_ready_both`；单路通过时输出 `single_route_confirmation_candidate`；基础设施缺证为 `incomplete`。任何结果均不授权训练或 promotion。

## R6.4 Codex/E2B bounded compatibility slice

The immediate solver workstream is reduced to one public probe and two fan-in tasks. The stock E2B `codex` template runs `codex exec --json --sandbox workspace-write --skip-git-repo-check`; Tuzi is configured through Codex's native custom-provider `responses` wire API. No protocol conversion, Stirrup fallback, automatic retry, cost reservation, or general agent framework is allowed. After targeted tests, the full local suite and fixed no-credential parity must pass before external execution. A passing two-task slice pauses for review and does not expand to the 12-task campaign or invoke the grader.

## R6.5 Local Codex homogeneous screening

R6.4 is closed as infrastructure diagnostic evidence. Its deliveries cannot be merged into behavioral comparison. The active implementation uses a pinned standalone official Codex CLI on the host, existing ChatGPT authentication and `gpt-5.6-sol`. It deliberately removes E2B, Stirrup, Tuzi solver adaptation and solver cost-ledger work from the active path.

The workstream is bounded to: freeze the CLI identity; pass one public synthetic XLSX probe; execute all twelve frozen blind packages once in independent local workspaces; grade only valid exact deliveries with the retained DeepSeek route-blind grader; then apply the frozen two-route analyzer. Full local tests and no-credential Linux parity precede scope compilation, but container parity covers governance code only. No result in this workstream authorizes confirmation execution, expert-validity claims, training, registry mutation, release or route promotion.

Three consumed public-probe scopes remain historical diagnostics and contain no private execution: the first inherited a desktop managed read-only policy, the second attempted an unsupported built-in-provider retry override, and the third proved that removing ambient `CODEX_*` variables does not detach the desktop policy. The active scope therefore binds `execution_isolation=outer_managed_workspace_codex_danger_full_access`: per-task projection and the outer managed workspace remain the containment boundary, while only the nested Codex sandbox is set to `danger-full-access`. Approval mode remains `never`, and the broader `--dangerously-bypass-approvals-and-sandbox` switch is forbidden.

R6.5 solver execution is now complete rather than blocked: scope `a23babbc...a3fa0` passed the public probe and delivered 12/12 valid workbooks, split 6/6 across both routes, in about 42.7 minutes with zero solver retry or infrastructure failure. Do not reopen solver adaptation. The downstream DeepSeek grader is the only incomplete component: 19 calls used 204,768 prompt and 72,726 completion tokens; 6/12 records completed and 6/12 exhausted the single format repair. Twelve of nineteen responses hit the 4,000-token completion ceiling. The six valid grades all saturated at 1.0. The next bounded workstream should compact and calibrate the grader output contract using the preserved responses, then complete missing scoring evidence without changing tasks, solver results, routes or rubrics; it must explicitly address saturation before confirmation.

## R8 Macro convergence after local-Codex validation

R0–R6 are no longer the active optimization surface. The project has sufficient evidence to promote the pinned local Codex runner to the default internal behavioral executor: one public probe and twelve independent business sessions produced 12/12 admitted workbooks, with both routes at 6/6 and no solver retry or infrastructure failure. This is an operational backend decision, not generator-route promotion or training admission. E2B, Stirrup, Tuzi solver adaptation, DeepSeek solver integration and solver budget-ledger redesign are removed from the active roadmap and retained only as historical diagnostics.

The remaining roadmap is deliberately shorter:

| Stage | Outcome | Entry/exit boundary |
| --- | --- | --- |
| R8.1 Compact evaluator | A small route-blind grading contract that completes reliably and separates defect findings from scores | Reuse frozen deliveries and raw grader responses; offline fixtures first. Regrade all twelve homogeneously only after the expected response is comfortably below the completion ceiling. Exit requires complete coverage, no systematic truncation and non-saturated score behavior. |
| R8.2 Professional calibration | Establish whether automated dimensions track real professional plausibility | Independently review at least four stratified tasks across route and motif. LLM grading remains proxy evidence; disagreement becomes a rubric/evaluator finding, not an automatic task mutation. |
| R8.3 Representative production pilot | Demonstrate the end-to-end factory beyond a twelve-task matched cohort | Produce approximately 24–30 fresh tasks across the two retained routes, three production motifs and at least one additional validated domain. Use local Codex as the sole default solver. Track real delivery, defect, duplication, review stability and operator cost. |
| R8.4 Route convergence | Select a production candidate without manufacturing a winner | Apply absolute quality gates before paired comparison. If routes are substantively tied, prefer the simpler and cheaper route and keep the other only as a challenger. No new route or motif is admitted during this decision. |
| R8.5 Training-data admission | Build an auditable SFT candidate set and test learning value | Admit only source-bound, Reality-screened, behaviorally executed, graded and professionally sampled records. Exclude hidden reasoning and raw agent logs. RL remains out of scope until SFT benefit and evaluator reliability are independently demonstrated. |

The plan now optimizes for fewer moving parts and stronger evidence. Schema, authorization and hashing work may continue only when it closes a demonstrated failure. Test count is regression evidence, not a milestone. A grader failure does not reopen solver work; a production-pilot task defect returns to the specific design, materialization or rubric layer; a tied route comparison terminates in a simplicity decision rather than another comparison framework.

R8.1 implementation is now concrete. Compact Grader V2 uses seven fixed 0–4 scores, programs normal professional adequacy at 3 rather than 4, requires explicit evidence for every exceptional 4, and requires concise findings for deductions to 2 or below. It removes per-criterion prose and limits the complete response to five findings and two exceptional-evidence records. Across all twelve frozen deliveries, full provider-message estimates are 10.3k–17.4k input tokens and the standard response is below 1,000 characters. The original 20k-input/2k-completion envelope was an offline estimate and has been disproved by the high-thinking external run described below. The external continuation must be grader-only and homogeneous across all twelve deliveries; it may not reuse V1 scores, rerun Codex or mutate task/rubric content.

The first Compact Grader V2 external scope, `ac8fcb1d...ff427b`, is frozen `incomplete` and must not be resumed or mixed into a final cohort. Its final state is 2 completed, 2 infrastructure-failed, 1 interrupted and 7 not-started tasks. Both completed reviews produced the intended non-saturated result: all seven dimensions scored 3, weighted score 0.75, no major defect and professional plausibility pass. The two failed tasks exhausted their one allowed format retry because all four responses ended with `finish_reason=length`, zero visible content and exactly 2,000 completion tokens. This demonstrates that the compact schema and score calibration work, but the 2k ceiling is incompatible with the current DeepSeek high-thinking request path; it is not a task, delivery or rubric failure.

R8.1 therefore remains open. The recommended successor is Compact Grader V2.1: retain the same route-blind schema, frozen inputs, seven-dimensional scale, high-thinking judgment mode and retry rules, but restore the completion ceiling to 4,000 tokens. It requires a fresh local regression, parity snapshot and immutable grader-only scope, then a homogeneous twelve-delivery regrade from scratch. Disabling thinking is a fallback only if 4k still truncates systematically, because it changes evaluator behavior rather than merely correcting an undersized output envelope. No further external call is authorized by the frozen V2 scope.

R8.1 is now complete under successor scope `bc38a3d7...3d6f6`. Local and fixed Linux/amd64 parity both passed 372/372 at source fingerprint `f3d52e54...60271`. The homogeneous V2.1 run completed all twelve grades with zero infrastructure failure in 16 calls, including four legal format retries. Eleven weighted scores are 0.75 and one is 0.70; every review has seven effective dimensions, professional plausibility pass, no major defect and no route identity exposure. Both routes pass every frozen absolute gate at 6/6 and all six matched pairs are comparable, so the program result is `confirmation_ready_both`.

This result closes evaluator completeness and removes full-score saturation, but it does not yet establish fine-grained evaluator sensitivity: eleven of twelve tasks share the normal-pass score. R8.2 should therefore use a different model family for a route-blind professional-calibration sample covering both routes and all three motifs. The calibration reviewer must inspect candidate requirements, the actual workbook, frozen rubric/fact anchors and the Compact V2.1 review, then report agreement or a concrete disagreement by criterion. It remains LLM proxy evidence; disagreement updates evaluator findings, not tasks or route weights. Confirmation execution, production expansion and training remain paused until this calibration is complete.

R8.2 is implemented as a bounded six-task slice rather than a new review framework. It fixes one task per route × motif cell, includes both replicate labels, and uses Tuzi `gemini-3.1-pro-preview` as the independent model family. Gemini does not receive the Compact/DeepSeek review; the program compares the persisted independent seven-score vector against Compact V2.1 afterward. The fixed consistency gate is ≥5/6 professional-plausibility agreement, 6/6 major-defect agreement, mean absolute delta ≤0.5 and maximum single-dimension delta ≤1 across 42 comparisons. Calls are capped at 12 with zero SDK retry and only one format/transport retry per task. Targeted tests are 15/15; full regression and fresh fixed parity must pass before scope compilation and execution.

The first compiled scope `74ec9ac1...d9871` made zero calls and uploaded no data because configuration resolution stopped before provider entry: the ignored project environment uses the established AGENT/GRADER aliases rather than OPENAI names. The loader now accepts those aliases without modifying or logging the environment file. Execution also recomputes the governed source fingerprint and rechecks the Compact scope/outcome and parity hashes, so the pre-fix scope is obsolete and cannot be executed after the code change. Related tests pass 21/21; a new full regression, parity and scope are required.

The final canonical scope `920977c2...f01f65` passed local/fixed parity 378/378 at `e053d45a...d2284` and entered Gemini, but was stopped after the same contract failure repeated across the first two tasks. The frozen manifest is 0 completed, 2 infrastructure-failed, 1 interrupted and 3 not-started, with four provider calls. All four responses ended normally with visible content; every response assigned 4 to all seven dimensions while supplying exceptional evidence for only two dimensions. One response also had an extra closing brace and its repair omitted `findings`. This is neither truncation nor a substantive task defect: Gemini failed the calibration scale and reproduced full-score saturation. Do not build a format adapter, retry the scope, accept the raw scores or start R8.3. R8.2 remains incomplete until an independent contract-compliant reviewer or human domain expert is available.

### R8.2 human-expert closure and revised macro boundary

The independent-review requirement is now routed to a human domain expert rather than another model adapter. A six-task route-blind packet is frozen under `expert_review_packet_v1_20260731`. It preserves the stratified two-route × three-motif sample and exposes only candidate requirements, delivery contracts, candidate-visible references, submitted workbooks, teacher rubrics and deterministic fact anchors. Route, replicate, prior model scores, solver logs and grader logs are excluded.

The packet contains 78 ZIP entries. Its manifest hashes, source delivery/rubric/fact-anchor identities and text-leak checks all pass; the unified workbook has no detected formula errors and all four sheets passed visual inspection. The ZIP SHA256 is `7b4c11522a7de8dd644f86c8186325112d19f120a8a7115021a89a5a750c9b76`; the blank review-form SHA256 is `7e2344049e89d0626cc0485972e49d4ab5e6e97e87bab070b4572e103a855859`.

R8.2 exits only after a returned workbook passes task coverage, seven-dimension completeness, evidence/issue requirements and reviewer-independence checks, followed by a programmatic comparison with Compact V2.1. Material disagreement is an evaluator/rubric finding and may block or narrow the production pilot; it does not authorize selective task edits or score reruns.

The post-review roadmap remains outcome-driven:

- R8.3 runs a 24–30 task representative production pilot only if no systematic professional-validity defect is found.
- R8.4 selects a production candidate using absolute gates before paired comparison; a substantive tie resolves in favor of the simpler route.
- R8.5 may assemble and audit a training-data candidate set, but this workstream explicitly excludes model training.

Local Codex remains the sole default behavioral executor for these stages. No further E2B, Stirrup, Tuzi-solver or DeepSeek-solver compatibility work is permitted unless new evidence invalidates the local runner itself.

### R8.2 user-directed AI-proxy waiver and R8.3 activation

On 2026-07-31 the user explicitly deferred human-expert review because no suitable reviewer is currently available and accepted the working assumption that the existing AI proxy is sufficient for a bounded engineering pilot. This supersedes the human-review entry gate above without rewriting its evidence: the packet remains optional future evidence, `expert_evidence_present` remains false, and professional validity becomes `provisional_ai_assumed_sufficient_for_pilot`.

The waiver activates R8.3 only. The representative pilot is fixed at 24 fresh assignments: 2 reconstructed routes × 3 production motifs × 2 domains × 2 matched briefs. One domain retains the validated audit/compliance substrate; the second is procurement/operations and must first pass public-source provenance, skill/capability and contamination admission. Every brief is new and no prior scenario, proposal or package fingerprint may be reused.

The pilot follows the shortest existing chain: validated source/skill substrate → whole-task LLM proposal and deterministic materialization → route-blind Reality proxy → pinned local Codex execution → Compact grader → report-only aggregation. It may produce a production-candidate recommendation, but it cannot supply human-expert evidence, production release, registry mutation, training admission or model training.

R8.3 source admission is now partially complete. Exact-URL collection added a bounded path through the existing deterministic collector; it does not add a second crawler. Three FAR sources passed collection and source-quality checks. The first DeepSeek extraction produced six candidates, five accepted and one revise, while preserving zero registry mutation. Its accepted capabilities directly cover invoice/receiving cross-checks, acquisition-threshold and competition policy application, and QA/nonconformance reconciliation. The heuristic transition graph exposed only one usable fan-in edge and warned that motif coverage lagged trace coverage.

A second, narrower three-source extraction was frozen after its only response truncated at the 12k completion ceiling. Do not retry it or enlarge the extractor contract merely to obtain motif labels. The next compiler must explicitly map the first accepted capability set into the three allowed motifs and submit all resulting briefs to formal source/skill/capability admission. Missing provenance, causal capability coverage or productive complexity blocks the relevant brief before task generation.

The source-gate implementation state passes 380/380 locally and in the fixed Linux/amd64 container at source fingerprint `8e867b2a...c4877`. Container network was disabled, the root was read-only, provider credentials were absent and cleanup succeeded. This parity closes only the exact-URL/source-gate code change; it does not imply that the 24 pilot briefs or packages already exist.

### R8.3 executable production-pilot contract

R8.3 is a fixed production pilot, not an open-ended research program. Its cohort contains exactly 12 new capability briefs and 24 route assignments:

| Axis | Frozen values |
| --- | --- |
| Route | `skill_guided_llm`, `llm_led_hybrid` |
| Motif | `fan_in_reconciliation`, `cross_check_validation`, `policy_application` |
| Domain | `audit_compliance`, `procurement_operations` |
| Fresh brief replicate | two per domain × motif cell |
| Deliverable | route-blind XLSX package |

The audit/compliance briefs may reuse validated public-source, skill and capability substrate, but must receive new brief, case, subgraph, scenario and assignment identities. Procurement/operations may use only the five accepted candidates from the first successful FAR extraction. The truncated second extraction is diagnostic evidence and is excluded. Neither domain may reuse an earlier proposal, scenario record or package fingerprint. Skill bindings remain artifact-local; the canonical registry is read-only throughout R8.3.

Execution is divided into the following bounded stages:

1. **R8.3.1 source and skill gate — complete.** Exact official URLs, normalized source records and the first accepted procurement skill set are frozen. The second extraction is not retried.
2. **R8.3.2 brief compilation and admission — complete.** Compile exactly 12 fresh briefs. Every brief must resolve its source provenance, selected skills and required capabilities; demonstrate causal skill coverage and productive complexity; use one of the three admitted motifs; and avoid missing workflow roles, `strict_template` and `evidence_to_deliverable`. All 12 briefs must pass before generation starts.
3. **R8.3.3 route proposal generation — complete.** Compile 24 assignments and use the established Tuzi `gpt-5.6-sol` whole-task proposal path. Each assignment receives one normal call. Only an already-supported persisted blocked proposal or parseable semantic draft may receive the single feedback-conditioned repair; broad provider/schema failures are not retried. Usage and first failures are recorded, but no new cost-ledger or provider adapter is introduced.
4. **R8.3.4 deterministic package admission — complete.** Every generated package must pass proposal validation, materialization, content-role checks, provenance projection, render/formula inspection, candidate/export identity and route-blind staging. A failed package remains failed evidence; it is not repaired by hand.
5. **R8.3.5 independent Reality proxy — active.** DeepSeek reviews candidate-visible reality and the rubric for all 24 admitted packages under isolated route-blind inputs. Only a complete `screening_ready` cohort may proceed. This remains `llm_proxy`; the user waiver does not convert it into expert evidence.
6. **R8.3.6 local Codex execution.** The pinned local Codex runner is the sole solver. Each task receives one independent process and no automatic retry. Only exact-path, non-empty, openable, non-copied XLSX deliveries are valid.
7. **R8.3.7 Compact grading — frozen incomplete.** The existing DeepSeek Compact V2.1 contract grades only valid deliveries. Its prompt, seven 0–4 dimensions, 4k completion ceiling and retry classification are unchanged; only the cohort binding is extended from 12 to 24 deliveries. Each delivery receives one substantive grade; only a transport or format failure may use its single controlled retry. Low scores are never redrawn. The scaled route gate requires 12/12 offline validity and skill-causal coverage, at least 10/12 valid delivery, professional plausibility and productive complexity, zero major defects, no more than 8/12 saturated scores, and at least 10 comparable route pairs. Domain summaries are mandatory.
8. **R8.3.8 aggregation and closeout — paused on grader completeness.** Report delivery, major defects, professional plausibility, productive complexity, causal skill coverage, duplication, grader stability and route/domain/motif coverage. The output is a report-only production-candidate recommendation. It does not start confirmation, training, registry mutation, release or promotion.

The stage fails closed under these conditions:

- Any of the 12 cells cannot produce an admitted fresh brief. Do not shrink the cohort and describe the remainder as the 24-task pilot.
- Procurement briefs systematically fail provenance, capability or productive-complexity admission. Stop and report instead of mutating the registry or rerunning the extractor.
- Provider, schema, fingerprint or systemic execution infrastructure fails. Freeze the affected stage and preserve first failures.
- One or more packages lack complete Reality evidence. The behavioral campaign remains `incomplete`; partial packages are not mixed with historical cohorts.
- A task or route fails a business gate. Record it as production evidence rather than reopening solver adaptation or changing thresholds after seeing the outcome.

R8.3 is accepted only when the 12-brief admission report, 24 package records, 24 Reality records, local-Codex delivery inspection, eligible Compact grades and final aggregation can be traced through immutable content hashes. Partial execution may be useful diagnostic evidence but cannot produce the final R8.3 conclusion. Model training is explicitly outside this plan.

### R8.3 generation-stage result

R8.3.2 is complete. The compiler produced 12/12 formally admitted fresh briefs and 24 unique route assignments. All six domain × motif cells contain exactly two briefs, all brief content hashes and blind task IDs are unique, and the manifest keeps training and registry mutation false. The admission-report SHA256 is `6e771404c4fac323bff98776506d62c5356583762666cc6e032eae8c9a6a08c3`.

The generation implementation passed 385/385 locally and in the fixed Linux/amd64 parity snapshot at source fingerprint `82ae77707f9a8ff406655a913b57f8a6a14ac756366b96d58aa00b9eb7c0df90`. The container had no network or provider credentials, used a read-only root, and cleaned up successfully.

R8.3.3 then completed all 24 assignments with Tuzi `gpt-5.6-sol`. It made 26 provider calls: 24 normal first attempts and two feedback-conditioned repairs of persisted `proposal_blocked` records. Both repairs succeeded. Total recorded usage was 156,688 prompt tokens, 176,856 completion tokens, 333,544 tokens overall and 3,596.187 provider seconds. No response ended by length and no provider/infrastructure failure occurred.

The immutable provider-generation record remains `incomplete`: 22 assignments materialized with 22 unique package fingerprints, while two LLM-led assignments were blocked by the same deterministic content rule:

- audit/compliance × cross-check replicate A modeled a COSO component mapping as candidate reference input;
- procurement/operations × fan-in replicate B modeled a nonconformance log as candidate reference input.

Both produced `candidate_output_modeled_as_reference_input`; skill-guided materialized 12/12 and LLM-led materialized 10/12. Report-first inspection showed that neither proposal modeled a final candidate deliverable as input. One artifact was “used to support candidate-authored mapping” and the other supplied findings “that require candidate-authored severity classifications.” The validator treated these input-to-output relations as if the reference itself were the candidate output.

The content validator now removes only explicit input-to-output relational phrases before testing for output-role leakage; the existing true-leak negative control still blocks. The two real regressions pass, and zero-provider replay of the original proposals completed proposal validation, content, provenance, visual, export and candidate/teacher-isolation gates. `RepresentativePilotPackageReadinessV1` preserves the original 22/24 result and separately binds 22 original packages plus two deterministic-false-positive replays. Its decision is `packages_ready`, with 24 unique fingerprints and zero correction-time provider calls.

The synchronized implementation and documentation pass the complete local suite at 392/392 after the JSON-safe payload fix. R8.3 is therefore at R8.3.5, pending the final fixed Linux/amd64 parity snapshot. The active Reality scope is fixed to 24 route-blind candidate stages followed by 24 Compact Rubric Focus V4 stages using official `deepseek-v4-pro`. Each stage has one normal attempt and at most one format/transport retry; SDK retries are zero, the hard ceiling is 96 calls, and package, candidate-tree, rubric, audit, parity and source fingerprints fail closed. Local Codex, Compact grading, confirmation, release and training remain unused until the complete Reality result is `screening_ready`.

The first 24-case Reality scope passed parity and preflight but froze before provider entry while persisting the first call input: an XLSX `datetime` value was not JSON serializable. Its execution manifest is immutable `incomplete` with zero provider calls and zero completed stages. The execution path now freezes one JSON-safe payload and uses that same object for evidence hashing and provider submission. The consumed scope is not reused; a fresh scope requires the updated full regression, documentation-synchronized source fingerprint and fixed parity.

The replacement scope passed the complete 392/392 local and fixed Linux/amd64 suites at source fingerprint `e5db87bb...9dcf4d`. Official `deepseek-v4-pro` then completed all 48 effective stages: 24 candidate-blind reviews followed by 24 Compact V4 rubric reviews. Three first attempts ended by length and used the only permitted controlled retry; all three retries succeeded. The campaign made 51 calls, used 320,167 prompt and 142,210 completion tokens, and preserved every first failure.

All 120 candidate dimensions pass. All 24 rubric reviews pass with a common pattern of 17 `distinct` and 4 `shared_evidence_distinct_behavior` pairs per case, zero risk findings and zero reviewer inconsistency. The cohort is `screening_ready`; result SHA256 is `db897fed616177ed97b095efc5997dedcf6743d00fc4e7958d8cca99ef69b631`. This closes R8.3.5 only. R8.3.6 local Codex execution is now active; grading, aggregation, route recommendation, release and training remain unused.

R8.3.6 reuses the existing local-Codex process runner, public probe, projection, timeout, resume and XLSX admission code. Scope V2 adds only the missing representative identity: exactly 24 bindings across two domains, two routes, three motifs and two replicates. It binds the 24-package readiness record, per-case Reality evidence, route-blind candidate trees and the pinned `@openai/codex` 0.146.0 installation. Historical 12-task scope V1 remains readable and keeps its original matrix rule. No E2B, Stirrup, Tuzi solver adapter, provider converter or budget ledger is reintroduced. The synchronized local suite passes 395/395; fixed Linux/amd64 parity remains the final scope-compilation gate.

The first V2 scope compilation failed before receipt creation because its upstream check compared the Reality/package `_tree_sha` contract with the older Codex projection `_tree` algorithm. All 24 package fingerprints still matched readiness, all candidate trees matched the Reality scope under its own algorithm and every case remained pass. The compiler now uses `_tree_sha` only to verify upstream evidence, while storing Codex `_tree` in the execution binding for the existing runner. This is a hash-interface correction, not package mutation or solver evidence. The post-fix complete local suite passes 396/396.

The post-fix fixed Linux/amd64 suite also passes 396/396 at source fingerprint `5f5a5731...c3e5df`. Scope `3c215519...4852a7` then ran the pinned local Codex CLI. The public probe passed and all 24 independent task processes produced valid exact-path XLSX deliveries with zero task failure, zero infrastructure failure and zero runner retry. Delivery coverage is 12/12 for each route, 12/12 for each domain and 8/8 for each motif. Total task-process time was 4,556.608 seconds; recorded usage was 4,763,981 input tokens, including 3,960,064 cached input tokens, and 186,809 output tokens. Solver manifest SHA256 is `4cf2c7dd43b7691869173cb9adc7cc808eda8402955942ca6d9575f1779214d4`. R8.3.6 is complete and R8.3.7 Compact grading is now active.

The representative Compact extension passed complete local and fixed Linux/amd64 regression at 398/398 under source fingerprint `aded61fc...e959`. Scope `5cfeed30...dffe` then graded all 24 frozen deliveries without rerunning Codex. The run is frozen `incomplete`: 22 valid reviews, 2 infrastructure failures and 30 provider calls. All 22 valid reviews pass professional plausibility, expose no route identity and contain no major defect; scores are twenty at 0.75, one at 0.70 and one at 0.6625, with zero saturation. The two failures are the two routes of the same procurement cross-check replicate: one exhausted both attempts at 4,000 completion tokens with empty visible content; the other first returned a substantively usable but schema-invalid overlong field, then exhausted its retry at 4,000 tokens. Eleven matched pairs remain complete. This is a grader output-contract completeness defect, not a solver or task-delivery failure. The receipt/scope is not reused, the missing reviews are not imputed, and R8.3.8 remains paused pending a deliberately smaller grader output contract or an explicit decision to accept report-only partial evidence.

The next bounded recovery uses the already-declared fallback instead of enlarging the token ceiling or changing models. Compact scope V3.1 retains the same 24 frozen inputs, seven scores, findings/exceptional-evidence invariants, JSON schema, 4k completion ceiling and retry policy, but sends official DeepSeek with thinking disabled. It starts a homogeneous cohort from zero and never mixes the prior 22 reviews. No solver, task, rubric or delivery is changed. If V3.1 completes 24/24, its programmed route/domain aggregation closes R8.3; if the same completeness failure recurs, the grader is frozen again and the project pauses before route convergence rather than building another adapter.

V3.1 passed local and fixed Linux/amd64 regression 399/399 at source fingerprint `bba2d794...ef27`, then consumed scope `c4b4c855...61ad`. It is frozen `incomplete` after 32 calls: 21 valid reviews and three schema-contract failures. Thinking disablement eliminated truncation—the six failed attempts all ended normally with 261–598 completion tokens—but did not make the model reliably honor artificial string-length caps or the exceptional-score evidence invariant. The valid reviews remain non-saturated: sixteen score 0.75 and five score 0.775–0.825, all professional-plausibility pass, with zero major defect and zero route exposure. Only nine matched pairs are complete. This second homogeneous failure disproves the “thinking-only” diagnosis. Per the stop rule, R8.3 pauses before route convergence; no V3/V3.1 mixing, field truncation, silent schema relaxation, solver rerun or further grader adapter is permitted without a revised evaluation decision.

The revised evaluation decision stops DeepSeek work and reuses the already proven local Codex CLI through its native `--output-schema` and `--output-last-message` features. This is not a provider adapter: each of the 24 route-blind workspaces contains only the candidate prompt, frozen rubric, deterministic fact anchors and delivered XLSX; one independent Codex process inspects the file and emits `grade.raw.json` under the existing Compact schema. There is one attempt per task and no model retry. Program code validates the seven dimensions, recomputes weighted score and applies the same route/domain gates. Because task generation, solving and this reviewer all use `gpt-5.6-sol`, the result is explicitly `same_model_behavioral_proxy`, not independent-model or expert evidence. It may support a report-only R8.4 simplicity decision under the user’s AI-proxy waiver, but cannot authorize training, release or promotion.

The first local-grader scope `e41ac3b1...51bee` is frozen before model reasoning. Codex rejected the Pydantic schema at request validation because strict Responses schemas require every declared property—including fields with defaults—to appear in `required`. Five identical 400 observations were recorded before the active process was stopped; one in-flight record was then persisted as interrupted, and no grade was produced. The schema compiler now recursively requires every property, forces `additionalProperties=false` and removes unsupported defaults while preserving nullable types and all substantive constraints. This is a native schema compilation correction, not response rewriting. The old scope is never resumed; final regression, parity and a new scope are required.

### R8.3 closeout and R8.4 route convergence

The replacement local-grader scope `37a227d9...e9cf` completed the homogeneous 24-task cohort. All 24 independent Codex processes produced valid structured seven-dimension reviews; there were zero infrastructure failures, zero grading failures and zero retries. The programmed result is `production_candidate_both`. Both routes have 12/12 offline validity, exact valid delivery, professional plausibility, productive-complexity coverage and skill-causal coverage, with zero major defects and zero saturated scores. The grader manifest SHA256 is `e12588f116328ee688c9f8c7d6cdd3ce894fe7d9d816d586a3b5641fcdbb1ffa`; the outcome SHA256 is `57fd039fb5f1c4609efcf90393f51bf1462bcaf4afbc90d4f4fe6ebee5ac6700`.

The score evidence does not establish a material route winner. `skill_guided_llm` has mean weighted score 0.811458 and `llm_led_hybrid` 0.795833; the 12 matched pairs split 6 skill-guided wins, 5 LLM-led wins and 1 tie. The difference is small and is driven partly by one 0.6375 LLM-led observation. Both domains and all three motifs remain above the absolute gate.

R8.4 therefore applies the predeclared simplicity tie-break instead of extending model evaluation. The report-only convergence compiler must bind the immutable grader outcome and solver/package evidence, recompute route means and matched-pair wins, and compare candidate-visible package footprint. The observed footprint is materially smaller for `llm_led_hybrid`: 52 workbooks and 329,373 bytes across 12 packages, versus 101 workbooks and 629,370 bytes for `skill_guided_llm`. The two original LLM-led materialization blocks remain classified as deterministic validator false positives because their preserved proposals passed zero-provider replay; they are not route-quality failures.

The deterministic report has now been compiled at SHA256 `0eaa56f1d6befa6cef24f6dc860deb509af6298e4020330954ce917a67ca2077`. Its recommendation is:

- `llm_led_hybrid` becomes the **report-only production candidate** because absolute quality is tied while its package topology is substantially smaller;
- `skill_guided_llm` remains the **challenger/control** because it has the slightly higher mean score and the cleaner original 12/12 materialization record;
- no default generator, registry, release or promotion state is changed by this recommendation.

The next bounded workstream is R8.5 training-data admission design, not model training. It will inventory only source-bound, Reality-screened, actually executed and validly graded records; define inclusion, exclusion, lineage and leakage checks; and emit a report-only candidate dataset manifest. Human-expert review remains explicitly deferred, so evidence is capped at `provisional_ai_assumed_sufficient_for_pilot` and `same_model_behavioral_proxy`. No SFT, RL, reward-model training or production release may start in this workstream.

R8.5 admission compilation is now complete. `CandidateDataAdmissionManifestV1` binds the representative campaign, package-readiness and Reality hashes, the local-Codex solver/grader chain and the route-convergence report. It admits 24/24 records into a report-only candidate pool: 12 LLM-led production-candidate records and 12 skill-guided challenger/control records. The manifest SHA256 is `e229994a343f7cd55d97646dcaa785e2b5a854964033863c29f7b9e366c36385`.

The manifest is intentionally not a training dataset. It permits only a future, separately reviewed export projection of candidate prompt, candidate-visible references, admitted solver delivery and structured grader feedback. Teacher-only rubric, deterministic fact anchors, Codex JSONL, hidden reasoning and authentication material are prohibited. `exported_training_example_count=0`, `dataset_export_authorized=false`, `training_authorized=false` and `training_started=false`. Any actual data export or model update requires a later explicit workstream.

### R8.6 external solver-stack comparison

R8.6 reuses the frozen 24-task representative cohort to compare deployable solver stacks rather than constructing new tasks. The retained baseline is `gpt-5.6-sol@chatgpt_codex`; it is not rerun. The two new stacks are `gemini-3.1-pro-preview@tuzi_codex` and `deepseek-v4-pro@tuzi_codex`, both executed by the pinned local Codex CLI through its native Responses custom-provider configuration. E2B, Stirrup and protocol adapters remain excluded.

Each external stack must first pass one public synthetic XLSX probe. A failed probe stops that stack before any private task workspace is created. A passing stack receives one independent process for each of the 24 route-blind packages, 30 minutes per process and no runner/provider retry. Three consecutive identical authentication, protocol, stream or service failures freeze only that stack. Exact-path, nonempty, openable, non-copied XLSX remains the delivery gate.

Every valid external delivery is graded once by the existing local `gpt-5.6-sol` seven-dimension structured grader. This makes the judge independent of Gemini and DeepSeek but same-model for the retained GPT baseline; the result is therefore an engineering proxy, not expert evidence. Capability comparison requires at least 20/24 valid deliveries, complete grading of every valid delivery and at least 20 common graded tasks. A delivery difference of three tasks, two major defects, or a common-task mean-score difference of 0.05 is substantive; otherwise the result is a practical tie.

The implementation passed 411/411 local and fixed Linux/amd64 parity tests before execution at source fingerprint `65a44da51774ba1a2b27256de9f852017c1a65309145bc92476da4548d8c6db0`; immutable scope `1e4577de...16cc4` was then consumed. Gemini failed the public probe with a high-demand service error, produced no command event or delivery, and caused zero private workspace creation. DeepSeek passed the public probe but all six attempted private tasks terminated with raw `stream disconnected before completion` events; no task completed normally and no delivery was grader-eligible. The stack froze and the remaining eighteen tasks were not run.

The result is `comparison_incomplete`: GPT retains 24/24 valid and graded baseline records, while neither external stack meets the 20-task capability or paired-comparison floor. A post-run classifier defect was isolated: scanning whole JSONL allowed candidate-visible `unauthorized/403` text to outrank terminal stream errors. Classification now reads only structured `error`/`turn.failed` events plus stderr, with a regression test; original artifacts remain frozen and the correction does not alter infrastructure-failure counts or the decision. R8.6 therefore supplies stack-compatibility evidence only and cannot change the default solver, route, release, registry, promotion or training state.

### R8.7 official DeepSeek × OpenCode

R8.7 isolates the unresolved variable from R8.6 by replacing both Tuzi and Codex custom-provider transport. The solver stack is official `deepseek-v4-pro` plus native OpenCode. E2B's official `opencode` template is preferred; a fixed WSL2 Ubuntu OpenCode installation is infrastructure fallback only. No Responses adapter, Stirrup path, desktop automation or budget ledger is introduced.

Admission is layered: public official API model/tool streaming, public OpenCode XLSX agent behavior, then the two-route matched brief. The remaining 22 tasks are released only after the matched pair is 2/2. The selected environment is cohort-wide and immutable. This separates provider/agent compatibility from task performance without creating a broad environment tournament.

DeepSeek deliveries are graded once by the frozen local GPT structured grader. Comparison requires 20/24 valid and fully graded records and 20 common tasks; the existing materiality thresholds remain unchanged. R8.7 stops after an engineering comparison report and cannot mutate the R8.4 route recommendation, R8.5 admission manifest, default solver, training, release or promotion state.

Implementation and 419-test local regression are complete. The active pre-execution gate is final documentation-synchronized Linux/amd64 parity, followed by one automatically consumed immutable scope under the user's explicit authorization. No external call or private upload occurred during implementation.

The first execution scope `5a8d5bb7...e1835` is frozen `stack_incomplete` with zero private uploads and 24/24 tasks not started. The official provider probe passed model discovery and a complete streamed tool cycle. E2B environment inspection failed before its intended runtime openpyxl installation because the diagnostic command propagated the missing-import exit code; WSL fallback also passed its local tool path through an unreliable positional argument. Both are deterministic local runner defects. The fixes force diagnostic success before the governed installation branch and quote concrete WSL paths directly. A new scope requires fresh full regression and parity; the consumed receipt is never reused.

The replacement scope `56c134a0...ed8a6` passed official provider, E2B/OpenCode and public XLSX admission. The matched pair passed 2/2. Seven private tasks then produced exact valid XLSX files before three consecutive service/stream infrastructure failures. A missing DNS classifier allowed fourteen later attempts that should not have run. The immutable execution audit preserves all raw evidence, sets the freeze point at `rp_44ce4deec29d8311`, counts only the 10-task prefix (7 pass, 3 infrastructure failure), and excludes the later 14 attempts.

The seven eligible deliveries received one local GPT grader attempt each: three completed and four failed on independent ChatGPT/Codex DNS or stream infrastructure. No solver or grader retry is permitted. Only three common scored tasks remain, so the final audited decision is `stack_incomplete` with `insufficient_common_coverage`. R8.7 therefore establishes public-stack compatibility and a bounded 7/7 pre-freeze delivery observation, but no model ranking or solver-switch authority.

### R8.8 network-recovery cohort

R8.8 is one fresh homogeneous campaign, not a continuation of R8.7. All 24 solver sessions and all eligible grader sessions start from new workspaces and output roots. R8.7 deliveries, grades and post-freeze attempts remain historical diagnostics and cannot satisfy any R8.8 coverage gate.

The recovered runner uses the audited DNS/stream taxonomy before execution. It repeats the public official-provider and E2B/OpenCode XLSX gates, requires the matched pair to pass 2/2, and freezes at three consecutive identical infrastructure failures. Every valid new delivery receives one new local GPT structured grade. Aggregation is legal only after a new execution audit and requires at least 20 valid deliveries, complete grading of every valid delivery and 20 common tasks. Failure to meet those gates closes R8.8 without a third automatic campaign.

R8.8 is now complete. After the compressed-transfer fix, targeted tests passed 11/11, the full local suite passed 421/421, and the fixed Linux/amd64 parity passed 421/421 at source fingerprint `4bb8c702...75e65` with network disabled, read-only root, no credentials and successful cleanup. Scope `eb3c3960...50506` was consumed once.

All public gates and the matched 2/2 gate passed. The new homogeneous cohort completed 24/24 solver sessions with 24 exact valid XLSX deliveries, zero infrastructure failures, zero task delivery failures and no post-freeze attempts. Immutable audit `ea7c3265...469c` accepts all 24 records. Every delivery then received one new successful local GPT structured grade; no low-score redraw occurred.

The comparison is `official_deepseek_comparison_ready`. DeepSeek/OpenCode has 24/24 valid deliveries, 14/24 professional-plausibility passes, six major defects and mean score 0.645833. The frozen GPT/Codex baseline has 24/24 validity and plausibility, zero major defects and mean score 0.803646. Across all 24 common tasks GPT wins 22, DeepSeek wins one and one ties; mean paired delta is 0.157812 in GPT's favor. DeepSeek is faster in aggregate (3439.764 versus 4556.608 seconds) but does not offset the frozen quality thresholds. `gpt_baseline` is therefore the practical winner. R8.8 closes without changing the R8.4 route recommendation, default solver, training state, release or promotion authority.

## R9 — Huago-cone productionization

R9 is active. It freezes the proven LLM-led design/materialization chain into a server release, produces one new ten-task source-to-package cohort, and measures solver separation with two judges. This is not another adapter research loop.

Order: controlled commit; two-image remote build; offline/read-only/no-credential parity; public probes; activation and rollback evidence; fresh six-page collection and scratch skill review; ten proposals/materializations; two-task cross-domain canary; remaining solver sessions; dual grading; deterministic aggregation. Fewer than eight packages stops evaluation; a model probe failure yields a partial comparison without a fallback adapter.

Professional review is deferred under the user's working assumption. Deterministic authenticity/integrity gates stay mandatory, evidence stays `assumed_for_model_comparison`, and R9 cannot mutate default solver, canonical registry, training, public release or R8 evidence.

R9 deployment is complete at release `milestone-r9-huago-cone-094cbe481df3` from commit `d70be7da0589caca4353f1a011e22642984f4d49`. Local and final Linux/amd64 suites passed 429/429; the remote candidate also passed network-disabled, read-only-root, credential-free parity and both image smokes. `current` is active, status is queryable, rollback is wired, and 137 GiB remains free.

The first fresh production run completed with `production_insufficient`: ten briefs were compiled from six freshly collected official pages and scratch-reviewed skills, but only 7/10 task-design calls materialized. The other three preserved first failures are Tuzi `gpt-5.6-sol` `InternalServerError` observations; no deterministic validation repair was applicable and no unconditional redraw occurred. All seven admitted packages pass every materialization gate, and all 31 candidate XLSX files are openable, nonempty and byte-identical to their export projections.

The frozen fewer-than-eight rule has therefore stopped R9 before any solver probe, private solver upload, grading or comparison. This is a provider-availability failure at task-design entry, not a package-quality or huago-cone deployment failure. Do not fill the cohort with R8 tasks or reinterpret 7/10 as an eligible partial comparison. The next authorized design decision should be a small production-provider reliability change, not a new execution framework.
