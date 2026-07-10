# TaskGenerator 下一大阶段计划：Candidate Ready & Quality Closure

> 定位：从“全局接口建设阶段”转入“质量闭环突破阶段”
> 核心目标：不再优先新增大模块，而是利用 Phase 0–10 已建成的全局诊断、验证、评估、晋升体系，推动至少一个任务包从 `revise_only` 自然进入 `candidate_ready`，并把这一过程沉淀为可重复的质量闭环。

---

## 1. 当前阶段判断

截至当前版本，TaskGenerator 已经完成了一次关键架构跃迁：项目不再只是两条流水线，而是形成了四层闭环架构：

```text
第一层：Source / Skill / Resource Substrate
第二层：Workflow / Motif / Task-graph Planning
第三层：Task Package Generation
第四层：Validity / Evaluation / Feedback / Promotion
```

这说明项目已经从“能否跑通任务生成链路”的阶段，进入了“能否稳定产出合格任务包”的阶段。当前已有的 WorkflowEpisode、WorkflowArchetype、MotifGraphGrammar、Global Validity、TaskVerifier、Promotion Manager、Eval Orchestrator、ModelSeparationProfile、Global Dashboard 等模块，已经足够支撑全局诊断和质量治理。

但项目还没有完成真正的生产能力验证。当前最核心的问题不是缺少模块，而是：

```text
诊断能力很强，
治理接口已具备，
评估链路已闭合，
但仍没有 candidate_ready 任务包。
```

因此，下一大阶段不应继续以“新增功能模块”为主，而应以“质量闭环打通”为主。

---

## 2. 阶段总目标

本阶段的总目标是：

> 在不降低质量门标准、不隐藏 Pipeline A 缺口、不把 draft evidence 误判为正式模型区分度证据的前提下，推动至少一个任务包自然达到 `candidate_ready`，并建立可重复的 candidate-ready 生产流程。

这意味着本阶段不是为了“凑出一个高分任务”，而是为了验证下面这条闭环：

```text
Global Dashboard 发现问题
→ Pipeline A Substrate Audit 定位根因
→ Typed Resource / Source Evidence / Transition Evidence 修复
→ Promotion Manager 显式晋升
→ Batch Runner 重跑
→ Global Validity / Verifier / Quality Gate 复查
→ Package 从 revise_only 进入 candidate_ready
→ 外部评估从 draft smoke 升级为候选诊断证据
→ 形成可重复质量流程
```

---

## 3. 本阶段北极星指标

本阶段不以“新增多少模块”作为成功标准，而以以下结果作为成功标准。

### 3.1 必达目标

```text
至少 1 个任务包达到 candidate_ready
```

必须满足：

* 不通过降低 quality gate 标准实现；
* 不通过忽略 Pipeline A signal gaps 实现；
* 不通过手工硬编码单 case workaround 实现；
* Verifier 无 blocking findings；
* Global Validity 无关键执行图阻断；
* Package readiness 从 `revise_only` 升级为 `candidate_ready`；
* rw-task export 从 draft-only 路径进入正式可导出路径，或至少达到 `candidate_ready_compatible`。

### 3.2 次级目标

```text
3-case 或 5-case batch 中至少出现 1 个 candidate_ready，且其余 case 不明显回退。
```

关注指标：

* `candidate_ready_count >= 1`
* `reject_count` 不增加；
* `low_subgraph_confidence` 出现率下降；
* `single_source_support` 出现率下降；
* `partial_ready_chain` 出现率下降；
* `verifier_blocking_count == 0`，至少在目标 case 上成立；
* `promotion_applied_count >= 1`，且有 rollback record；
* `typed_resource_coverage` 在目标 sampled skills 上明显提升。

### 3.3 暂不追求目标

本阶段暂不追求：

* 大规模 benchmark-grade 数据集；
* 全自动 UCB / bandit sampler；
* 大规模跨领域扩展；
* 复杂 PDF / OCR / 图片证据生态；
* 正式多模型 model-separation campaign；
* LLM Teacher 完全替代 deterministic TeacherRunner。

这些都重要，但应在第一个 `candidate_ready` 闭环完成后再推进。

---

## 4. 本阶段核心原则

### 原则 1：Dashboard-first，不再单任务盲修

任何修复都应先从 `global_pipeline_dashboard_report.json` 出发，明确问题属于哪一层：

```text
pipeline_a
workflow_graph
package_generation
teacher_operationalization
rubric_and_quality
evaluation
promotion_governance
```

不要看到某个 case 低分就直接调 prompt。先判断它是系统性问题、motif-specific 问题，还是 case-specific 问题。

---

### 原则 2：先修 substrate，再修 prompt

当前跨案例问题仍主要来自 Pipeline A substrate，包括 typed resources、support diversity 和 transition evidence。只要这些问题没有改善，继续强化 candidate prompt 或 rubric 只会产生局部收益。

优先级应为：

```text
typed resource contract
→ source evidence support
→ transition evidence
→ workflow / motif role coverage
→ teacher operationalization
→ prompt / rubric micro-adjustment
```

---

### 原则 3：Promotion 必须显式

任何写入 canonical registry 或影响采样行为的改动，都必须走：

```text
proposal
→ review
→ scratch apply
→ rerun / compare
→ canonical apply
→ rollback record
```

禁止 task generation 过程隐式修改注册表。

---

### 原则 4：candidate_ready 不能靠放宽标准获得

如果 `candidate_ready` 是通过删除 blocking checks、降低 verifier 严格度、隐藏 `partial_ready` 或把 diagnostic finding 移出报告获得的，那么这不是成功。

本阶段的目标是让任务质量真正上升，而不是让判定变松。

---

### 原则 5：外部评估仍放在漏斗末端

只有当目标 case 接近或达到 `candidate_ready` 后，才运行更昂贵的外部评估。Draft smoke 可以继续作为工具链诊断，但不能作为正式模型区分度证据。

---

## 5. 阶段工作流总览

本阶段采用固定迭代循环：

```text
1. Baseline Freeze
2. Dashboard-first Case Selection
3. Root-cause Triage
4. Controlled Promotion / Repair
5. Batch Rerun
6. Verifier + Validity + Quality Gate Review
7. Candidate-ready Decision
8. Guarded Evaluation
9. Postmortem + Rule Extraction
```

每一轮迭代都要回答：

```text
这次修复针对哪个 dashboard finding？
预期哪个 reason code 会下降？
是否涉及 registry / grammar / sampler 行为？
是否需要 promotion？
是否能 rollback？
是否改善了 batch，而不是只改善单 case？
```

---

## 6. Phase 11.0：基线冻结与工作区收口

### 目标

在进入 candidate-ready sprint 之前，先固定当前基线，避免后续无法判断修复是否有效。

### 工作内容

1. 确认当前工作区干净：

   * `.env` 不进入 staged files；
   * scratch outputs 不误提交；
   * 当前 governance 增强已提交或明确留在本地。

2. 固定一份 baseline dashboard：

   * `global_pipeline_dashboard_report.json`
   * `pipeline_b_batch_report.json`
   * `pipeline_b_batch_feedback_report.json`
   * `pipeline_a_substrate_audit_report.json`
   * `typed_resource_patch_proposal_report.json`
   * `promotion_manager_report.json`
   * `evaluation_orchestration_report.json`，如果本轮需要 eval evidence。

3. 新增一份阶段记录：

```text
docs/handoffs/PHASE_11_BASELINE_<date>.md
```

记录：

* 当前 batch case 数；
* 当前 `revise / reject / candidate_ready` 数；
* 当前 repeated reason codes；
* 当前 top dashboard findings；
* 当前可用 high-confidence promotion candidates；
* 当前 eval evidence 是否仅为 draft diagnostic。

### 输出

```text
artifacts/pipeline_b/scratch/phase_11_baseline/
docs/handoffs/PHASE_11_BASELINE_<date>.md
```

### 验收标准

* 有一份可复现 baseline；
* 后续每次修复都能和这份 baseline 比较；
* 明确当前没有 `candidate_ready`；
* 明确当前首要问题是否仍是 Pipeline A substrate。

---

## 7. Phase 11.1：Candidate Case Selection

### 目标

从现有 batch 中选出最适合冲击 `candidate_ready` 的目标 case。

### 选择标准

优先选择：

```text
quality_decision = revise
而不是 reject
```

并且满足：

* reference files 已生成成功；
* export validator 已通过或接近通过；
* verifier findings 少且可解释；
* global validity 没有执行图结构性阻断；
* subgraph 使用的技能有可审核 typed-resource patch；
* missing role 数量较少；
* motif grammar role coverage 较高；
* 不是当前最失败的 motif case。

不优先选择：

* `reject` case；
* 文件生成失败 case；
* verifier 有大量 unsupported conclusion 的 case；
* 需要新增大量源材料才能修复的 case；
* 依赖低置信 typed-resource patch 过多的 case。

### 输出

```text
phase_11_candidate_case_selection_report.json
```

建议字段：

```json
{
  "selected_case_id": "...",
  "selection_reason": "...",
  "current_quality_decision": "revise",
  "main_blockers": [],
  "expected_repair_path": [],
  "excluded_cases": [],
  "case_risk_level": "low|medium|high"
}
```

### 验收标准

* 明确选中 1 个 primary target case；
* 可选 1 个 backup case；
* 每个 case 的选择或排除理由清楚；
* 不以外部 smoke 分数作为唯一选择依据。

---

## 8. Phase 11.2：Pipeline A Substrate Repair Sprint

### 目标

解决目标 case 的最核心 substrate 缺口，尤其是 typed resources、support diversity 和 transition evidence。

### 工作内容 A：Typed Resource Patch Triage

对当前 31 个 typed-resource proposal 做分级：

```text
Tier A: 高置信，可进入 scratch apply
Tier B: 中置信，需要人工确认或补充 source span
Tier C: 低置信，不应用
Tier D: needs_source_evidence，先补源材料
```

重点不是一次性处理全部 31 个，而是优先处理目标 case sampled skills 涉及的资源。

### 工作内容 B：Scratch Apply + Rerun

对 Tier A proposal 执行：

```text
proposal
→ approved
→ scratch apply
→ rerun target case
→ compare dashboard / quality / verifier
```

不要直接 canonical apply。

### 工作内容 C：Canonical Apply

只有当 scratch apply 证明：

* subgraph confidence 改善；
* typed resource coverage 改善；
* quality reason code 减少；
* 没有引入新的 verifier blocking；
* batch 中其他 case 没有明显回退；

才进入 canonical apply。

### 输出

```text
typed_resource_patch_review_report.json
promotion_scratch_apply_report.json
promotion_canonical_apply_report.json
promotion_rollback_record.json
substrate_repair_comparison_report.json
```

### 验收标准

* 至少 1 个高置信 typed-resource patch 完成 scratch apply；
* 至少 1 个 patch 完成 canonical apply，或明确记录为何不应 apply；
* 目标 case 的 `low_subgraph_confidence` 或相关 Pipeline A reason code 有可观测改善；
* 所有 apply 都有 rollback record。

---

## 9. Phase 11.3：Source Evidence Expansion

### 目标

处理 `needs_source_evidence` 和 `single_source_support` 问题。

### 工作内容

对目标 case 中仍然关键但证据不足的技能，执行小范围 Pipeline A evidence expansion：

1. 从 substrate audit 中找到：

   * exact single-source skills；
   * transition evidence absent/local-only skills；
   * needs_source_evidence proposals。

2. 对这些 skill 运行小规模 SourceCollector / SkillExtractor / Reviewer / Graph Diagnostics。

3. 输出新的 source evidence proposal，而不是直接 registry mutation。

4. 如果新 evidence 支撑已有 skill：

   * 生成 `source_support_patch_proposal`；
   * 进入 promotion review。

5. 如果发现更好的 skill candidate：

   * 进入 registry admission proposal；
   * 不直接写入 registry。

### 输出

```text
source_evidence_expansion_report.json
source_support_patch_proposals.json
registry_admission_candidate_report.json
transition_evidence_proposal_report.json
```

### 验收标准

* 目标 case 的关键 single-source skill 至少有 1 条新增 support candidate；
* transition evidence 不再完全依赖 local-only 信号，或明确说明仍不可晋升；
* 不因新源材料引入过宽、任务级、不可复用 skill；
* 所有新增 evidence 都可追溯到 source span。

---

## 10. Phase 11.4：Role Coverage 与 Motif Repair

### 目标

让目标 case 不只是资源接口更清楚，也要在 workflow / motif 结构上更完整。

### 工作内容

1. 读取目标 case 的：

   * `pipeline_b_subgraph_report.json`
   * `filled_roles`
   * `missing_roles`
   * `role_fit_scores`
   * `workflow_context_fit`
   * `task_graph_shape_assumption`

2. 针对 selected motif grammar 检查：

   * required roles 是否都被填充；
   * filled skill 是否真的适合 role；
   * missing role 是否导致 GoldenRun partial；
   * role 缺失是否可以通过已有 skill 填补；
   * role 缺失是否需要新的 Pipeline A skill evidence。

3. 优先修复以下 role：

   * evidence extractor；
   * rule / policy extractor；
   * exception handler；
   * cross-check validator；
   * deliverable synthesizer；
   * traceability validator。

4. 不要把 workflow archetype 变成固定模板；只修 role coverage，不硬编码单任务路径。

### 输出

```text
motif_role_coverage_repair_report.json
workflow_context_fit_report.json
sampler_role_filling_comparison_report.json
```

### 验收标准

* 目标 case 的 required role coverage 提升；
* missing role 数量下降；
* role filling 后 subgraph 不再只是 skill list，而是能解释每个 skill 的 graph role；
* Quality Gate 中与 workflow / graph role 相关的 findings 减少。

---

## 11. Phase 11.5：Teacher Operationalization Closure

### 目标

减少 `partial_intermediate_state`、`partial_ready_chain` 和 teacher-step operationalization 问题。

### 判断原则

如果 GoldenRun partial 的原因是 Pipeline A substrate 缺失，不应强行在 TeacherRunner 里补假确定性。
如果 partial 的原因是 execution plan 不够明确，则应修 TeacherRunner / ExecutionPlanDAG。

### 工作内容

1. 从 `ExecutionPlanDAG` 中检查：

   * stage 是否完整；
   * stage requires/provides 是否可闭合；
   * stage 与 candidate-visible sections 是否一致；
   * final checks 是否覆盖所有 material conclusion。

2. 从 `TaskVerifier` 中检查：

   * unsupported conclusion；
   * missing evidence citation；
   * missing policy citation；
   * rubric criterion 不可操作；
   * candidate-visible requirement 与 GoldenRun 不一致。

3. 将 TeacherRunner 的 deterministic output 进一步绑定到：

   * evidence inventory；
   * policy clause mapping；
   * evidence-to-conclusion map；
   * unresolved issue list；
   * final deliverable validation。

4. 如果 deterministic teacher 无法自然完成，记录为：

   * `requires_llm_teacher_shadow_mode`
   * 而不是硬编码答案。

### 输出

```text
teacher_operationalization_repair_report.json
execution_plan_dag_comparison_report.json
task_verifier_comparison_report.json
```

### 验收标准

* 目标 case 的 `partial_intermediate_state` 数量下降；
* Verifier blocking findings 为 0；
* unsupported conclusion 为 0 或全部转为 unresolved；
* GoldenRun 的每条 material conclusion 都能追踪 evidence / policy；
* 仍不启用正式 LLM Teacher 作为主链路。

---

## 12. Phase 11.6：Candidate Ready Gate Attempt

### 目标

在完成 substrate、role coverage、teacher operationalization 修复后，重新运行完整链路，尝试让目标 case 达到 `candidate_ready`。

### 必跑链路

```text
subgraph sampler
→ blueprint assembler
→ reference file planner
→ reference file generator
→ teacher input builder
→ teacher runner
→ training annotation builder
→ rubric builder
→ quality gate
→ package assembler
→ rw-task exporter
→ export validator
→ global validity
→ task verifier
→ global dashboard
```

### 判定条件

目标 case 进入 `candidate_ready` 需要至少满足：

```text
quality_gate_decision = candidate_ready
package_readiness = candidate_ready
export_validation_status = candidate_ready_compatible
verifier_blocking_findings = 0
global_validity_blocking_findings = 0
critical_pipeline_a_signal_gaps = resolved_or_non_blocking
```

### 输出

```text
candidate_ready_attempt_report.json
candidate_ready_quality_gate_report.json
candidate_ready_export_validation_report.json
candidate_ready_global_dashboard_report.json
```

### 成功标准

* 至少一个 case 进入 `candidate_ready`；
* 如果失败，失败原因必须比 baseline 更具体，不能仍然停留在泛泛的 `low_subgraph_confidence`；
* 如果失败，输出下一轮最小修复建议。

---

## 13. Phase 11.7：Small Batch Regression Check

### 目标

确认目标 case 的修复不是单点 hack，没有破坏其他 case。

### 工作内容

重新运行小批量：

```text
max_cases = 3 或 5
```

比较 baseline 与 repair 后：

| 指标                              | 预期  |
| ------------------------------- | --- |
| `candidate_ready_count`         | 上升  |
| `reject_count`                  | 不上升 |
| `low_subgraph_confidence_count` | 下降  |
| `single_source_support_count`   | 下降  |
| `partial_ready_chain_count`     | 下降  |
| `verifier_blocking_count`       | 下降  |
| `role_coverage`                 | 上升  |
| `typed_resource_coverage`       | 上升  |

### 输出

```text
phase_11_batch_regression_report.json
phase_11_before_after_dashboard_diff.json
```

### 验收标准

* 至少 1 个目标 case 改善；
* batch 整体没有明显退化；
* 如果某个 motif 退化，记录 motif-specific finding；
* 修复不是单 case prompt hack。

---

## 14. Phase 11.8：Guarded Candidate Evaluation

### 目标

只有当目标 case 达到或接近 `candidate_ready` 后，才进行更可信的外部评估。

### 评估原则

仍然保持保守解释：

```text
candidate_ready eval evidence
≠ benchmark-grade model separation evidence
```

但它比 draft smoke 更有价值。

### 建议评估配置

第一轮：

```text
case_count: 1 candidate_ready case
models:
  - strong model
  - weak model
runs_per_model: 1
```

第二轮，如果第一轮稳定：

```text
case_count: 2-3 cases
models:
  - strong model
  - medium model
  - weak model
runs_per_model: 2
```

### 记录内容

```text
evaluated_model_name
grader_model
score_ratio
rubric_item_scores
discriminative_items
format_noise_items
failure_modes
retry_variance
toolchain_status
```

### 输出

```text
candidate_eval_orchestration_report.json
candidate_model_separation_profile.json
candidate_eval_feedback_report.json
```

### 验收标准

* `evaluated_model_name` 与 `grader_model` 不混淆；
* 至少能解释强弱模型差异来自哪些 rubric item；
* 如果差异主要来自格式遵循，则标记为 weak model-separation evidence；
* 不把一次分数差异升级为正式 benchmark 结论。

---

## 15. Phase 11.9：TransitionPriorStore V0 Observational

### 目标

开始为未来概率采样器和 UCB/bandit 积累结构化记录，但暂不让它影响采样行为。

### 为什么现在只做 observational

当前反馈样本仍少，credit assignment 还不完全稳定。如果直接让 UCB 或 transition posterior 影响采样，容易制造“看似智能、实则过拟合”的假闭环。

### 工作内容

新增只读/只写记录结构：

```json
{
  "transition_prior_record_id": "...",
  "from_skill_id": "...",
  "to_skill_id": "...",
  "workflow_archetype_id": "...",
  "motif_type": "...",
  "role_context": "...",
  "source_trace_count": 0,
  "task_usage_count": 0,
  "candidate_ready_success_count": 0,
  "revise_count": 0,
  "reject_count": 0,
  "reason_code_distribution": {},
  "confidence": "low",
  "status": "observed_only"
}
```

### 关键约束

* 不改变 sampler score；
* 不引入 UCB；
* 不自动更新 registry；
* 不把 draft evidence 当成功样本；
* 只记录 candidate-ready 或 high-quality diagnostic case 的 outcome。

### 输出

```text
transition_prior_store.observed.json
transition_prior_observation_report.json
```

### 验收标准

* 每个 batch case 的 skill edge / role assignment / motif context 能被记录；
* candidate_ready outcome 能被结构化记录；
* 未来可以接入 prior updater；
* 当前不影响任何采样决策。

---

## 16. Phase 11.10：Postmortem 与流程固化

### 目标

无论是否成功达到 `candidate_ready`，都要把本阶段经验沉淀为可重复流程。

### 如果成功

输出：

```text
docs/handoffs/PHASE_11_CANDIDATE_READY_SUCCESS_<date>.md
```

记录：

* 初始 blockers；
* 哪些 repair 有效；
* 哪些 promotion 被 applied；
* 哪些指标改善；
* 第一个 candidate_ready case 的完整 artifact path；
* 该 case 是否适合进入后续 model-separation campaign；
* 哪些流程应加入默认开发循环。

### 如果失败

输出：

```text
docs/handoffs/PHASE_11_CANDIDATE_READY_BLOCKED_<date>.md
```

记录：

* 为什么仍未 candidate_ready；
* 当前最大 blocker 是 Pipeline A、Workflow Graph、TeacherRunner、Verifier 还是 Rubric；
* 哪些 repair 没有效果；
* 是否需要回滚；
* 下一轮最小修复集是什么。

### 验收标准

* 有明确 postmortem；
* 不因失败继续盲目加模块；
* 下一轮行动项不超过 3 个；
* 每个行动项都能对应 dashboard finding。

---

## 17. 本阶段建议任务优先级

### P0：必须优先

1. 固定 baseline dashboard。
2. 选择最接近 `candidate_ready` 的目标 case。
3. 审核并应用 1–3 个高置信 typed-resource patch。
4. 重跑 batch，比较 reason code 是否改善。
5. 尝试让目标 case 通过 quality gate。
6. 记录 candidate-ready attempt report。

### P1：紧随其后

1. 对 `needs_source_evidence` skill 做小范围 source expansion。
2. 修复目标 motif 的 missing roles。
3. 降低 TeacherRunner partial states。
4. 让 verifier blocking findings 清零。
5. 做 3-case regression check。

### P2：条件满足后做

1. 对 candidate-ready case 做 guarded external eval。
2. 记录 candidate model separation profile。
3. 建 TransitionPriorStore V0 observational。
4. 准备 LLM Teacher Shadow Mode。

### P3：继续暂缓

1. UCB / bandit sampler。
2. 大规模正式 model separation campaign。
3. 第二领域扩展。
4. 复杂 PDF / OCR / 图片证据生态。
5. 全自动 registry mutation。

---

## 18. 推荐目录结构

```text
docs/
  architecture/
    phase_11_candidate_ready_quality_closure_plan.md
  handoffs/
    PHASE_11_BASELINE_<date>.md
    PHASE_11_CANDIDATE_READY_SUCCESS_<date>.md
    PHASE_11_CANDIDATE_READY_BLOCKED_<date>.md

artifacts/
  pipeline_b/
    scratch/
      phase_11_baseline/
      phase_11_candidate_selection/
      phase_11_substrate_repair/
      phase_11_candidate_ready_attempt/
      phase_11_batch_regression/
      phase_11_candidate_eval/

SkillRegistry/
  promotion_reviews/
    typed_resource_patch_review_<date>.json
  transition_prior_store.observed.json
```

---

## 19. 本阶段成功后的项目状态

如果 Phase 11 成功，项目将从：

```text
全局诊断型任务工厂 V1
```

升级为：

```text
可产出 candidate_ready 的闭环任务工厂 V1
```

这代表项目完成了一个关键转变：

```text
能发现问题
→ 能定位问题
→ 能受控修复问题
→ 能证明修复改善质量
→ 能产出合格任务包
```

此时再推进以下方向才更稳：

* 多 case candidate-ready production；
* LLM Teacher Shadow Mode；
* small-scale model separation campaign；
* TransitionPriorStore updater；
* cautious UCB / bandit exploration；
* 第二领域扩展；
* benchmark-grade task curation。

---

## 20. 本阶段失败时的判断

如果 Phase 11 没能产生 `candidate_ready`，也不是无效阶段。它至少应该回答：

```text
candidate_ready 被什么真正阻挡？
```

可能答案包括：

1. Pipeline A 注册表质量不足；
2. typed resource patch 无法从 legacy semantic strings 可靠恢复；
3. source evidence support 太弱；
4. workflow/motif role grammar 与现有 skill 不匹配；
5. deterministic TeacherRunner 无法生成足够完整的 GoldenRun；
6. quality gate 标准与当前生成能力不匹配；
7. verifier 发现当前任务本身不可被证据闭合；
8. reference file ecosystem 太模板化，无法支持真实任务质量。

如果能明确回答这个问题，下一阶段仍然是成功的，因为它将项目从“泛泛地知道有问题”推进到了“知道真正瓶颈在哪里”。

---

## 21. 最终一句话

Phase 11 的核心不是继续证明“系统能跑”，而是证明：

> 系统能利用自己的诊断、验证、晋升和批量反馈能力，把一个不合格任务包修成合格任务包。

这一步完成后，TaskGenerator 才真正从“复杂任务生成原型”进入“闭环真实世界任务工厂”的阶段。
