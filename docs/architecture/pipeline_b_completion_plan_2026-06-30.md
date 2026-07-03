# Pipeline B Completion Plan - 2026-06-30

## Purpose

This document is the working plan for completing Pipeline B after the `src/task_generator` package migration.

Pipeline B should become a batch-capable Skill-To-Task factory. Its job is not only to produce a plausible prompt. Its job is to turn Pipeline A registry skills into complete, evidence-grounded, trainable, and eventually rw-task-evaluable task packages.

Current baseline:

- Pipeline A has a persistent skill registry and readiness reports.
- Pipeline B has a report-first resource-aware sampler that can read the seed set and registry, build a `PipelineBSubgraph`, and emit Pipeline A feedback.
- Pipeline B prototype can still read the seed set directly, and can now also consume a sampler `pipeline_b_subgraph_report.json` to emit a draft `TaskBlueprint`.
- Pipeline B now has deterministic reference-file planning/generation, teacher-input validation, TeacherRunner V1, TrainingAnnotationBuilder V1, RubricBuilder V1, a package-level Quality Gate V1, staged package assembly, V3 rw-task draft export, export validation, eval input prep, a guarded eval runner, eval summarization, and eval-feedback analysis.
- The current chain now reaches an authorized real rw-task draft smoke. It is still pre-formal model-separation evaluation because the sample package remains `revise_only`.
- The current rubric contract separates complete internal diagnostics from grader-facing rw-task criteria: full `rubric.json` can keep candidate criteria, teacher diagnostics, and Pipeline A feedback criteria, while exported `rubric_json` includes only candidate-visible, candidate-actionable criteria.

The next work should convert Pipeline B from "draft blueprint prototype" into "complete task package generator".

## Implementation Progress - 2026-07-01

Completed slices:

1. Resource-aware subgraph sampler.
   - Module: `src/task_generator/v3_pipeline_b_sampler.py`
   - CLI: `Test/run_v3_pipeline_b_subgraph_sampler.py`
   - Default inputs: `SkillRegistry/v3_pipeline_b_seed_set_report.json` and `SkillRegistry/v3_skill_registry.json`
   - Default output: `artifacts/pipeline_b/scratch/subgraph_sampler_smoke/`
   - Current smoke result selects 4 `sample_ready` skills for `evidence_to_deliverable`.
   - Current confidence is `low_due_to_resource_fallback` because selected persistent registry entries still lack typed `SemanticResource` coverage.
   - The sampler emits `pipeline_b_subgraph_report.json` and `pipeline_a_feedback.json` without mutating registry files.

2. Blueprint Assembler V2 entrypoint.
   - Module: `src/task_generator/v3_pipeline_b_prototype.py`
   - CLI: `Test/run_v3_pipeline_b_prototype.py`
   - New argument: `--subgraph-report`
   - Old seed-report mode remains supported.
   - Subgraph mode preserves `subgraph_id`, `subgraph_confidence`, and `subgraph_missing_signals` in the prototype report.
   - The draft blueprint includes subgraph-derived selected skills, resource hints, prompt constraints, and GoldenRun skeleton diagnostics.

3. Reference-file planning layer.
   - Module: `src/task_generator/v3_reference_file_planner.py`
   - CLI: `Test/run_v3_reference_file_planner.py`
   - Input: a draft `TaskBlueprint`, optionally plus `pipeline_b_subgraph_report.json`
   - Output: `reference_file_plan.json`
   - The plan assigns stable file IDs, table IDs, text-section IDs, column IDs, and evidence IDs.
   - Planned files now also record `preferred_generation_strategy`, `supported_generation_strategies`, and `validation_contract`.
   - The plan separates candidate-visible evidence anchors from future teacher-only notes.
   - The plan carries forward subgraph confidence, missing Pipeline A signals, unresolved gaps, typed/fallback resource counts, and planner warnings.
   - Current smoke result plans 2 reference files, 1 table, 4 text sections, and 9 evidence anchors.

4. Deterministic table-first reference-file generation.
   - Module: `src/task_generator/v3_reference_file_generator.py`
   - CLI: `Test/run_v3_reference_file_generator.py`
   - Input: `reference_file_plan.json`
   - Output: generated candidate-visible files under `reference_files/`, plus `generated_file_manifest.json`, `evidence_index.json`, `evidence_index_proposal.json`, and `generation_trace.json`
   - Generated files now record `generation_strategy`, `trust_level`, `validator_status`, and `evidence_mapping_status`.
   - Current smoke result generates `source_evidence.xlsx` and `policy_reference.docx`, writes a `policy_reference_clause_map.json` sidecar, and emits 9 finalized evidence mappings.
   - Generated workbook validation checks file existence, sheet existence, row counts, and exact column lists; the policy doc path checks visible clause IDs and required sections.

5. Teacher input contract.
   - Module: `src/task_generator/v3_teacher_input_builder.py`
   - CLI: `Test/run_v3_teacher_input_builder.py`
   - Inputs: `draft_task_blueprint.json`, `pipeline_b_subgraph_report.json`, `reference_file_plan.json`, `generated_file_manifest.json`, and optional `pipeline_a_feedback.json`
   - Outputs: `teacher_input_manifest.json` and `teacher_input_validation_report.json`
   - The manifest explicitly separates `candidate_view` from `teacher_view`.
   - The teacher view carries skill intentions, hidden requirements, deferred assets, evidence contracts, and Pipeline A uncertainty.
   - Current smoke result is `partial_ready`, with 2 generated candidate-visible files, 0 deferred files, 9 evidence-contract items, and 2 structural relationship checks.

6. TeacherRunner V1.
   - Module: `src/task_generator/v3_teacher_runner.py`
   - CLI: `Test/run_v3_teacher_runner.py`
   - Inputs: `teacher_input_manifest.json` and `teacher_input_validation_report.json`
   - Outputs: `golden_run.json` and `teacher_runner_report.json`
   - The runner deterministically builds teacher-visible intermediate states, skill-linked golden steps, final checks, and unresolved-gap reporting.
   - Current smoke result is `partial_ready`, with 6 intermediate states, 4 golden steps, 3 final checks, and no blocked steps.
   - All current steps remain intentionally `partial` because the sampled subgraph still carries fallback-confidence and support-evidence warnings.

7. TrainingAnnotationBuilder V1.
   - Module: `src/task_generator/v3_training_annotation_builder.py`
   - CLI: `Test/run_v3_training_annotation_builder.py`
   - Inputs: `golden_run.json`, `teacher_runner_report.json`, and `teacher_input_manifest.json`
   - Outputs: `training_annotation.json` and `training_annotation_report.json`
   - The builder converts teacher intermediate states, golden steps, final checks, unresolved gaps, and warning codes into training supervision objects.
   - The artifact also embeds a V2-compatible `TrainingAnnotation` projection for older downstream consumers.
   - Current smoke result is `partial_ready`, with 13 supervision items, 4 failure modes, 8 hidden traps, and 10 unresolved gaps carried forward explicitly.

8. RubricBuilder V1.
   - Module: `src/task_generator/v3_rubric_builder.py`
   - CLI: `Test/run_v3_rubric_builder.py`
   - Inputs: `training_annotation.json`, `training_annotation_report.json`, `golden_run.json`, and `teacher_runner_report.json`
   - Outputs: `rubric.json` and `rubric_report.json`
   - The rubric is JSON-only in this slice; no Markdown summary is emitted.
   - The builder converts supervision items, failure modes, rubric projection summaries, and unresolved gaps into four structured sections: `fact_checks`, `reasoning_checks`, `robustness_checks`, and `compliance_checks`.
   - Current smoke result is `partial_ready`, with 4 sections, 37 criteria, and 30 criteria marked `partial`.

9. Pipeline B Quality Gate V1.
   - Module: `src/task_generator/v3_pipeline_b_quality_gate.py`
   - CLI: `Test/run_v3_pipeline_b_quality_gate.py`
   - Inputs: `generated_file_manifest.json`, `teacher_input_validation_report.json`, `teacher_runner_report.json`, `training_annotation_report.json`, and `rubric_report.json`
   - Output: `pipeline_b_quality_report.json`
   - The gate is deterministic, JSON-only, and does not call LLMs or external APIs.
   - Decision space is fixed to `reject`, `revise`, and `candidate_ready`.
   - Current smoke result is `revise`, with reason codes now focused on `low_subgraph_confidence`, `single_source_support`, `partial_intermediate_state`, `pipeline_a_signal_gaps`, and `partial_ready_chain`.

10. Pipeline B Package Assembler V1.
   - Module: `src/task_generator/v3_pipeline_b_package_assembler.py`
   - CLI: `Test/run_v3_pipeline_b_package_assembler.py`
   - Inputs: the current blueprint, generated-file manifest, teacher-input artifacts, GoldenRun, training annotation, rubric, and quality report
   - Outputs: `package_manifest.json`, `dataset_row_draft.json`, copied JSON artifacts, and copied generated reference files
   - This is a staging layer before final `rw-task` export, not the final evaluator-facing export.
   - Current smoke result is `package_readiness=revise_only`, copies 2 generated reference files, preserves the policy clause-map sidecar, and records only the quality-gate `revise` decision as an export blocker.

11. V3 rw-task Draft Export Adapter.
   - Module: `src/task_generator/v3_rw_task_exporter.py`
   - CLI: `Test/run_v3_rw_task_exporter.py`
   - Input: `package_manifest.json`, plus the sibling `dataset_row_draft.json`
   - Output: `dataset_row.json`, `reference_files/`, `deliverable_files/`, `artifacts/`, and `rw_task_export_report.json`
   - The exporter is structural only; it does not run rw-task evaluation, models, LLMs, or Stirrup.
   - Default behavior blocks formal export unless `package_readiness=candidate_ready`.
   - Current smoke result blocks default export for the `revise_only` package, while explicit `--allow-revise-only` produces an inspection-only draft export with 2 candidate-visible reference files.

12. V3 rw-task Export Validation.
   - Module: `src/task_generator/v3_rw_task_export_validator.py`
   - CLI: `Test/run_v3_rw_task_export_validator.py`
   - Input: an exported rw-task-style case directory
   - Output: `rw_task_export_validation_report.json`
   - The validator checks local compatibility only: required `dataset_row.json` fields, copied reference files, deliverable expectations, draft/final export flags, structured rubric JSON, and support-artifact visibility.
   - Current smoke result is `validation_status=draft_compatible`; this means the case is structurally inspectable but still not final training data.

13. V3 rw-task Evaluation Prep Dry-Run.
   - Module: `src/task_generator/v3_rw_task_eval_prep.py`
   - CLI: `Test/run_v3_rw_task_eval_prep.py`
   - Inputs: a validated exported case directory plus optional `rw_task_export_validation_report.json`
   - Outputs: a batch-style eval input directory and `rw_task_eval_prep_report.json`
   - The prep layer copies the case into `eval_input/<case_id>/`, preserves draft-vs-final truthfulness, and records the exact `stirrup_batch` plus `grade_deliverables` commands that would be run later.
   - Current smoke result is `prep_status=prepared` with `evaluation_mode=draft_inspection_only`; it does not run any models or rw-task commands.

14. V3 rw-task Eval Runner.
   - Module: `src/task_generator/v3_rw_task_eval_runner.py`
   - CLI: `Test/run_v3_rw_task_eval_runner.py`
   - Input: `rw_task_eval_prep_report.json`
   - Output: `rw_task_eval_run_report.json`
   - Default behavior is dry-run metadata only: verify the prep report, keep warning codes visible, and do not call `bench_standalone.stirrup_batch`, `grade_deliverables`, external APIs, or model providers.
   - Explicit execution requires `--run-eval`; the current `draft_inspection_only` sample additionally requires `--allow-draft-eval`.
   - Current dry-run smoke result is `run_status=dry_run_ready` and `commands_executed=false`.
   - Early explicit local smoke evidence exposed two environment boundaries: missing process-level `E2B_API_KEY`, then blocked outbound E2B connectivity under the Codex sandbox.
   - Authorized external smoke with runtime env loaded from `E:\THU\2026Spring\SRT\rw-task\.env` completed both prepared commands: `stirrup_batch` succeeded for 1/1 case and `grade_deliverables` wrote a grader JSON.

15. V3 rw-task Eval Summarizer.
   - Module: `src/task_generator/v3_rw_task_eval_summarizer.py`
   - CLI: `Test/run_v3_rw_task_eval_summarizer.py`
   - Inputs: `rw_task_eval_run_report.json` plus a grader JSON or grade directory
   - Output: `pipeline_b_eval_summary_report.json`
   - The summarizer is report-only and does not update registries, transition priors, quality gates, or package readiness.
   - Current smoke result is `summary_status=summarized`, `toolchain_completed=true`, `evidence_use=draft_quality_observation`, 1 successful sample, and average score ratio `0.625` (`20/32`).

16. V3 Pipeline B Eval Feedback Analyzer.
   - Module: `src/task_generator/v3_pipeline_b_eval_feedback_analyzer.py`
   - CLI: `Test/run_v3_pipeline_b_eval_feedback_analyzer.py`
   - Inputs: `pipeline_b_eval_summary_report.json`, `rubric.json`, `training_annotation.json`, `teacher_runner_report.json`, and `pipeline_b_quality_report.json`
   - Output: `pipeline_b_eval_feedback_report.json`
   - The analyzer is report-only and does not update registries, transition priors, quality gates, package readiness, or sampling weights.
   - Current smoke result is `feedback_status=analyzed`, with 6 low-scoring criteria, 5 prioritized Pipeline B actions, 3 Pipeline A feedback items, and 14 candidate-ready blockers.

17. Prompt + Teacher Contract Strengthening Slice.
   - Updated modules:
     - `src/task_generator/v3_pipeline_b_prototype.py`
     - `src/task_generator/v3_teacher_input_builder.py`
     - `src/task_generator/v3_teacher_runner.py`
     - `src/task_generator/v3_training_annotation_builder.py`
   - Purpose: apply the first eval-feedback findings without using LLMs by making the deterministic task contract more explicit.
   - Current changes:
     - visible prompt requirements now explicitly name the deliverable path, require supported-conclusion / confirmed-exception / unresolved-item separation, and require policy-sensitive conclusions to cite both evidence IDs and policy clause IDs
     - teacher hints now carry an explicit deliverable contract summary and policy-clause citation reminder
     - GoldenPlan intermediate states now include `deliverable_outline` and `policy_clause_evidence_map`
     - final checks now include `deliverable_requirement_coverage` and `policy_clause_traceability`
     - teacher evidence matching now includes policy-clause artifacts for policy-oriented states and steps
   - Current smoke result:
     - `teacher_runner`: 8 intermediate states, 5 final checks
     - `training_annotation`: 17 supervision items
     - `rubric`: 43 criteria
     - `package_assembler`: `package_readiness=revise_only`
     - `rw_task_eval_prep`: `prep_status=prepared`, `evaluation_mode=draft_inspection_only`

18. rw-task Compatibility + Grading Model Alignment Fix.
   - Updated modules:
     - `src/task_generator/v3_rw_task_exporter.py`
     - `src/task_generator/v3_rw_task_export_validator.py`
     - `src/task_generator/v3_rw_task_eval_runner.py`
   - Purpose: preserve V3 internal rubric richness while exporting a legacy-compatible rw-task grading contract, and keep grading on the intended model instead of drifting to `rw-task/.env` defaults.
   - Current changes:
     - exporter now converts V3 `rubric_json` objects into stringified rw-task rubric-item lists
     - validator now accepts both structured rubric payloads and stringified rubric-item lists
     - eval runner now sets `GRADER_MODEL` from eval-prep `model` when invoking `bench_standalone.grade_deliverables`
   - Verified result:
     - first repaired real smoke no longer failed on missing `total_score`
     - latest real smoke result is `run_status=completed`
     - grader model is now `gpt-5.4-pro`
     - latest summary is `draft_quality_observation` with total score `59 / 81` and score ratio `0.7283950617283951`
     - latest eval feedback reports 13 low-scoring criteria, 2 Pipeline B actions, and 3 Pipeline A feedback items

19. Feedback-Driven Rubric Audience Split.
   - Updated modules:
     - `src/task_generator/v3_rubric_builder.py`
     - `src/task_generator/v3_pipeline_b_package_assembler.py`
     - `src/task_generator/v3_rw_task_exporter.py`
   - Purpose: prevent Pipeline A/teacher/generator diagnostics from being graded as if they were candidate-solvable task requirements.
   - Current changes:
     - each `RubricCriterion` now records `audience` and `export_to_rw_task`
     - `RubricDiagnostics` records candidate, diagnostic, and rw-task-exportable criterion counts
     - package draft rubric text includes only rw-task-exportable criteria
     - V3 rw-task export filters `rubric_json` to candidate-visible criteria and records how many diagnostic criteria were retained outside the grader-facing contract
   - Current filter smoke result:
     - full rubric: 43 criteria
     - candidate/exportable criteria: 28
     - teacher/Pipeline-A diagnostic criteria: 15
     - exported rw-task draft case remains `draft_exported`
     - export validator remains `draft_compatible`
     - exported `dataset_row.json` keeps `extra.rw_task_rubric_filter` with the dropped diagnostic counts and reason codes
     - authorized filtered draft rw-task smoke completed both `stirrup_batch` and `grade_deliverables`
     - filtered draft score is `53 / 62` (`0.8548387096774194`), compared with the previous strengthened baseline `59 / 81` (`0.7283950617283951`)
     - low-scoring criteria dropped from 13 to 5 after removing grader-facing Pipeline A diagnostics
     - remaining low-score feedback is now concentrated on teacher-step operationalization and policy-reference prompting

20. Candidate Contract Strengthening From Filtered Feedback.
   - Updated modules:
     - `src/task_generator/v3_pipeline_b_prototype.py`
     - `src/task_generator/v3_teacher_runner.py`
   - Purpose: address the remaining candidate-facing low-score feedback without changing readiness, hiding Pipeline A gaps, or weakening the task.
   - Current changes:
     - candidate prompt now explicitly requires `Evidence inventory`, `Deliverable outline`, `Evidence-to-conclusion map`, and `Policy clause mapping` sections
     - policy-sensitive conclusions must now be supported by a visible policy-clause mapping with clause ID, governed evidence ID, applied conclusion, and unresolved policy uncertainty
     - TeacherRunner intermediate-state purposes now use the same section-oriented wording that the candidate sees
     - GoldenStep expected actions now emphasize evidence inventory, manager-ready outline, and policy-clause mapping outputs
   - Current deterministic smoke result:
     - new blueprint: `bp_pipeline_b_276dc466`
     - teacher input: `partial_ready`, 2 generated candidate-visible files, 9 evidence-contract items, no warning relationship checks
     - teacher runner: 8 intermediate states, 4 partial golden steps, 5 final checks, no blocked steps
     - training annotation: 17 supervision items, 10 hidden traps, 10 unresolved gaps
     - rubric: 43 total criteria, 28 candidate/exportable criteria, 15 diagnostic criteria
     - quality gate: `revise`, 23 revise findings, no blocking findings
     - rw-task export: default blocked, explicit draft export succeeds with 2 references and 28 grader-facing rubric items
     - export validator: `draft_compatible`
     - eval prep: `prepared`, `draft_inspection_only`
     - eval runner dry-run: `dry_run_ready`
     - authorized external smoke completed both `stirrup_batch` and `grade_deliverables`
     - contract-strengthened draft score is `58 / 62` (`0.9354838709677419`), compared with the previous filtered draft `53 / 62` (`0.8548387096774194`)
     - low-scoring criteria dropped from 5 to 4
     - remaining low-score feedback is split between reference-evidence traceability and teacher-step operationalization

Current validation commands:

```powershell
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_pipeline_b_sampler.py src\task_generator\v3_pipeline_b_prototype.py Test\run_v3_pipeline_b_subgraph_sampler.py Test\run_v3_pipeline_b_prototype.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_subgraph_sampler.py --output-dir artifacts\pipeline_b\scratch\subgraph_sampler_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_prototype.py --subgraph-report artifacts\pipeline_b\scratch\subgraph_sampler_smoke\pipeline_b_subgraph_report.json --output-dir artifacts\pipeline_b\scratch\prototype_from_subgraph_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_prototype.py --output-dir artifacts\pipeline_b\scratch\prototype_legacy_seed_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_reference_file_planner.py Test\run_v3_reference_file_planner.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_reference_file_planner.py --blueprint artifacts\pipeline_b\scratch\prototype_from_subgraph_smoke\draft_task_blueprint.json --subgraph-report artifacts\pipeline_b\scratch\subgraph_sampler_smoke\pipeline_b_subgraph_report.json --output-dir artifacts\pipeline_b\scratch\reference_file_plan_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_reference_file_generator.py Test\run_v3_reference_file_generator.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_reference_file_generator.py --reference-file-plan artifacts\pipeline_b\scratch\reference_file_plan_smoke\reference_file_plan.json --output-dir artifacts\pipeline_b\scratch\reference_file_generation_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_teacher_input_builder.py Test\run_v3_teacher_input_builder.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_teacher_input_builder.py --output-dir artifacts\pipeline_b\scratch\teacher_input_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_teacher_runner.py Test\run_v3_teacher_runner.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_teacher_runner.py --output-dir artifacts\pipeline_b\scratch\teacher_runner_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_training_annotation_builder.py Test\run_v3_training_annotation_builder.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_training_annotation_builder.py --output-dir artifacts\pipeline_b\scratch\training_annotation_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_rubric_builder.py Test\run_v3_rubric_builder.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rubric_builder.py --output-dir artifacts\pipeline_b\scratch\rubric_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_pipeline_b_quality_gate.py Test\run_v3_pipeline_b_quality_gate.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_quality_gate.py --output-dir artifacts\pipeline_b\scratch\quality_gate_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_pipeline_b_package_assembler.py Test\run_v3_pipeline_b_package_assembler.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_package_assembler.py --output-dir artifacts\pipeline_b\scratch\package_assembler_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_rw_task_exporter.py Test\run_v3_rw_task_exporter.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_exporter.py --output-dir artifacts\pipeline_b\scratch\rw_task_export_blocked_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_exporter.py --allow-revise-only --output-dir artifacts\pipeline_b\scratch\rw_task_export_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_rw_task_export_validator.py Test\run_v3_rw_task_export_validator.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_export_validator.py --case-dir artifacts\pipeline_b\scratch\rw_task_export_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_rw_task_eval_prep.py Test\run_v3_rw_task_eval_prep.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_eval_prep.py --case-dir artifacts\pipeline_b\scratch\rw_task_export_smoke --eval-input-dir artifacts\pipeline_b\scratch\rw_task_eval_input_smoke --overwrite
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_rw_task_eval_runner.py Test\run_v3_rw_task_eval_runner.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_eval_runner.py --prep-report artifacts\pipeline_b\scratch\rw_task_eval_input_smoke\rw_task_eval_prep_report.json --output-dir artifacts\pipeline_b\scratch\rw_task_eval_run_dry_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_rw_task_eval_summarizer.py Test\run_v3_rw_task_eval_summarizer.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_eval_summarizer.py --run-report artifacts\pipeline_b\scratch\rw_task_eval_run_real_smoke_e2b_escalated\rw_task_eval_run_report.json --grade-dir artifacts\pipeline_b\scratch\rw_task_eval_input_smoke_e2b_grades --output-dir artifacts\pipeline_b\scratch\rw_task_eval_summary_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_pipeline_b_eval_feedback_analyzer.py Test\run_v3_pipeline_b_eval_feedback_analyzer.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_eval_feedback_analyzer.py --output-dir artifacts\pipeline_b\scratch\eval_feedback_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_pipeline_b_prototype.py src\task_generator\v3_teacher_input_builder.py src\task_generator\v3_teacher_runner.py src\task_generator\v3_training_annotation_builder.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_prototype.py --subgraph-report artifacts\pipeline_b\scratch\subgraph_sampler_smoke\pipeline_b_subgraph_report.json --output-dir artifacts\pipeline_b\scratch\prototype_from_subgraph_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_teacher_input_builder.py --output-dir artifacts\pipeline_b\scratch\teacher_input_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_teacher_runner.py --output-dir artifacts\pipeline_b\scratch\teacher_runner_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_training_annotation_builder.py --output-dir artifacts\pipeline_b\scratch\training_annotation_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rubric_builder.py --output-dir artifacts\pipeline_b\scratch\rubric_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_package_assembler.py --output-dir artifacts\pipeline_b\scratch\package_assembler_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_exporter.py --package-manifest artifacts\pipeline_b\scratch\package_assembler_smoke\package_manifest.json --allow-revise-only --output-dir artifacts\pipeline_b\scratch\rw_task_export_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_export_validator.py --case-dir artifacts\pipeline_b\scratch\rw_task_export_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_eval_prep.py --case-dir artifacts\pipeline_b\scratch\rw_task_export_smoke --eval-input-dir artifacts\pipeline_b\scratch\rw_task_eval_input_smoke --overwrite
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_rw_task_exporter.py src\task_generator\v3_rw_task_export_validator.py src\task_generator\v3_rw_task_eval_runner.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_exporter.py --package-manifest artifacts\pipeline_b\scratch\package_assembler_smoke\package_manifest.json --allow-revise-only --output-dir artifacts\pipeline_b\scratch\rw_task_export_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_export_validator.py --case-dir artifacts\pipeline_b\scratch\rw_task_export_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_eval_prep.py --case-dir artifacts\pipeline_b\scratch\rw_task_export_smoke --eval-input-dir artifacts\pipeline_b\scratch\rw_task_eval_input_smoke --overwrite
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_eval_summarizer.py --run-report artifacts\pipeline_b\scratch\rw_task_eval_run_real_smoke_strengthened\rw_task_eval_run_report.json --grade-report artifacts\pipeline_b\scratch\rw_task_eval_input_smoke_grades\eval_20260702_164743.json --output-dir artifacts\pipeline_b\scratch\rw_task_eval_summary_smoke_strengthened
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_eval_feedback_analyzer.py --eval-summary-report artifacts\pipeline_b\scratch\rw_task_eval_summary_smoke_strengthened\pipeline_b_eval_summary_report.json --output-dir artifacts\pipeline_b\scratch\eval_feedback_smoke_strengthened
```

Both subgraph-mode and legacy seed-mode draft blueprints should validate with `TaskBlueprint.model_validate`.

Next implementation choices:

1. Use the new `draft_quality_observation` (`59 / 81`) plus `eval_feedback_smoke_strengthened` to target the remaining low-scoring rubric dimensions, especially partial intermediate states and visible handling of Pipeline A uncertainty.
2. Improve Pipeline A typed resources, support diversity, and transition evidence until at least one package can naturally reach `candidate_ready`.
3. Keep `teacher_input_validation_report.json`, `teacher_runner_report.json`, `training_annotation_report.json`, `rubric_report.json`, `pipeline_b_quality_report.json`, and `package_manifest.json` as readiness gates for downstream export and evaluation.
4. Extend reference-file generation toward additional document, media, and folder-style file packages beyond the current deterministic workbook plus policy-doc path.
5. Decide where LLM/Stirrup generators should enter as proposal-producing strategies under the same manifest and validation contract.
6. Keep draft eval results out of registry and transition-prior updates until there is an explicit, trustworthy feedback-updater design.

LLM timing policy:

- Current Quality Gate V1 does not call LLMs.
- LLM teacher mode should run after quality gating, or under an explicit later exploration mode that records partial readiness honestly.
- LLM output should be stored as teacher proposals, scenario/prose drafts, or reference-document drafts.
- LLM output must not become grading truth unless validated against candidate-visible evidence or explicitly marked as teacher-only supervision.

Draft evaluation policy:

- A `draft_inspection_only` package may be used to smoke-test the rw-task toolchain, but this is not task-quality evidence.
- Real smoke execution must record command lines, model name, output dirs, exit codes, failure reasons, and whether grading ran.
- Current evidence shows that successful dry-run and eval-prep are not enough by themselves; real smoke also depends on runtime env injection and outbound E2B connectivity.
- Authorized external smoke completed successfully, but its grader result is still a draft-quality observation because the package remains `revise_only`.
- Formal model-separation evidence should wait for `candidate_ready` packages.
- The smoke runner must not update the registry, transition priors, or any feedback store as a side effect.

## Final System Objective

The long-term target is not a one-way generator. The project should become a closed-loop dataset factory:

```text
sources -> reusable skills -> composable skill graph -> sampled task subgraph
        -> generated task package -> quality/evaluation feedback
        -> updated skill/edge/motif priors
```

Pipeline A should not only accumulate isolated atomic skills. It should gradually build a composable graph substrate that Pipeline B can sample from. Pipeline B should not only consume that graph. It should generate feedback that teaches the graph which skill combinations, transition edges, and motifs actually produce good tasks.

The three most important long-term layers are still missing:

1. Persistent transition prior store.
   - Current transition graphs are per-run reports.
   - There is not yet a durable `SkillTransitionPriorStore`.
   - The future store should live outside `SkillRegistryEntry` and track edge/motif evidence such as `from_skill_id`, `to_skill_id`, `relation_type`, `motif_type`, `observed_count`, `success_count`, `failure_count`, `prior_score`, `posterior_score`, `exploration_bonus`, source evidence, and last-updated metadata.

2. True probabilistic graph/subgraph sampler.
   - Current readiness, motif, graph-role, and edge-score reports are static heuristics.
   - The future sampler should convert those signals into a probability distribution over executable subgraphs.
   - UCB1 or a related bandit strategy should balance exploitation of high-performing skill combinations with exploration of under-tested but plausible combinations.
   - This should not be implemented prematurely. Bandit scores only become meaningful after Pipeline B produces task-quality feedback.

3. Pipeline B feedback loop.
   - Generated-task results do not yet update edge, motif, or skill weights.
   - Future Pipeline B runs should emit structured feedback that can update transition priors, motif priors, sampling weights, and Pipeline A governance reports.
   - Feedback should include sampled skill IDs, edge IDs, motif IDs, generated-file status, GoldenRun status, rubric status, quality-gate outcome, failure reason codes, and model-separation signals when available.

This means the immediate Pipeline B work should be designed as the first executable bridge to that closed loop, not as another isolated single-task prototype.

## Non-Goals

- Do not let Pipeline B mutate `SkillRegistry/v3_skill_registry.json`.
- Do not let Pipeline B consume every Pipeline A accepted candidate file directly.
- Do not bulk-admit graph calibration candidates as a side effect of task generation.
- Do not treat LLM-generated final answers as grading truth unless they are validated against visible source evidence or explicitly marked teacher-only.
- Do not return to the legacy operator-heavy skill node design where semantic skill, executable data generation, prompt text, and rubric text are mixed into one object.
- Do not write static `possible_successors` lists back into skill entries.
- Do not treat the first sampler as a real bandit sampler before quality feedback exists.

## Stable Pipeline A Inputs

Pipeline B should initially consume only stable or explicitly selected Pipeline A artifacts:

- `SkillRegistry/v3_skill_registry.json`
- `SkillRegistry/v3_registry_sampling_readiness_report.json`
- `SkillRegistry/v3_pipeline_b_seed_set_report.json`
- `SkillRegistry/v3_graph_calibration_report.json`
- selected per-run `skill_transition_graph_report.json`
- selected per-run `composition_readiness_report.json`

Interpretation rules:

- `sample_ready` is the default sampling pool.
- `sample_with_caution` is exploratory only and must preserve provenance/risk notes.
- `exclude_until_revised` must not be sampled unless a later explicit revision/admission step changes its status.
- Motif hints are task-shape constraints, not task blueprints.
- Transition graph reports are evidence for compatibility, not registry mutation instructions.

## Target End State

A complete Pipeline B run should produce a task package directory containing:

- `task_blueprint.json`
- generated reference files
- candidate-facing prompt
- `golden_run.json`
- `training_annotation.json`
- executable or semi-executable rubric JSON
- rw-task-compatible export
- quality report
- provenance/debug report

The generated task should be:

- grounded in visible reference files
- solvable by a competent model or human
- auditable through intermediate states
- gradeable through machine-readable anchors
- exportable into training and evaluation formats
- traceable back to Pipeline A skills and source evidence

## Batch Factory Success Criteria

The architecture should eventually be judged at the factory level, not by whether one hand-tuned task looks good.

Useful success metrics:

- source batches collected and normalized
- accepted skill growth by domain, motif, and resource type
- graph coverage, including typed-resource coverage, trace-edge coverage, and motif coverage
- sampled subgraphs attempted, accepted, revised, or rejected
- generated task packages completed
- reference-file, GoldenRun, rubric, and export pass rates
- quality-gate pass rate and stable failure reason distribution
- model-separation results on a filtered evaluation subset
- transition/motif/skill priors updated from task outcomes

The first implementation slices will not meet all of these metrics. They should still record enough provenance to make the future closed-loop update possible.

## Phase 0: Keep The Current Interface Stable

Goal:

Preserve the working handoff while adding richer Pipeline B components.

Work:

- Keep `Test/run_v3_pipeline_b_seed_set.py` as the seed-set report CLI.
- Keep `Test/run_v3_pipeline_b_prototype.py` working while new modules are added.
- Treat `SkillRegistry/v3_pipeline_b_seed_set_report.json` as the current first sampling entrypoint.
- Continue writing generated Pipeline B artifacts under `artifacts/pipeline_b/`.

Acceptance checks:

- `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_seed_set.py`
- `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_prototype.py --output-dir artifacts\pipeline_b\scratch\prototype_smoke`
- Generated draft blueprint validates with `TaskBlueprint.model_validate`.

## Phase 1: Resource-Aware Skill/Subgraph Sampler

Status:

- Implemented in `src/task_generator/v3_pipeline_b_sampler.py`.
- CLI implemented in `Test/run_v3_pipeline_b_subgraph_sampler.py`.
- Current behavior is deterministic, report-first, and registry-non-mutating.
- Current smoke reports `low_due_to_resource_fallback`, which is expected until Pipeline A typed resources are backfilled into the persistent registry.

Goal:

Upgrade Pipeline B from "choose several related skills" to "assemble a small executable skill-resource subgraph".

Why this comes first:

The current prototype selects by motif and seed score. That proves the handoff works, but it does not prove the selected skills can execute together as a task. The sampler must expose whether Pipeline A has enough typed resources, graph roles, and transition evidence.

New module:

- `src/task_generator/v3_pipeline_b_sampler.py`

Expected objects:

- `PipelineBSamplingRequest`
- `PipelineBSelectedSkill`
- `PipelineBResourceNode`
- `PipelineBSubgraphEdge`
- `PipelineBSubgraph`
- `PipelineBSamplingDiagnostics`

Inputs:

- registry entries
- seed set report
- readiness report
- optional transition graph report
- optional composition readiness report
- motif target
- skill count bounds
- domain constraints

Selection policy:

1. Filter to `sample_ready` by default.
2. Optionally allow a small number of `sample_with_caution` entries only in exploratory mode.
3. Choose a target motif such as `evidence_to_deliverable`, `fan_in_reconciliation`, `cross_check_validation`, or `policy_application`.
4. Prefer a role mix:
   - starter
   - transform
   - fan_in
   - validator
   - synthesis
5. Prefer typed-resource compatibility:
   - a provided resource can satisfy a required resource
   - subtype/domain attributes should increase compatibility
   - exact string equality is not required
6. Use legacy semantic contracts only as fallback evidence.
7. Use transition priors as soft scores, not hard requirements.

Important limitation:

- Phase 1 is still a static, diagnostic sampler.
- It should expose missing resources, weak compatibility, and absent transition evidence.
- It should not claim to implement UCB1 or learned next-skill prediction.
- It should emit the identifiers and diagnostics needed for a future `SkillTransitionPriorStore`.

Diagnostics:

- selected skills
- rejected candidates and reasons
- role coverage
- required/provided resource coverage
- unresolved resource gaps
- motif coverage
- transition evidence used
- fallback evidence used
- Pipeline A feedback items

Acceptance checks:

- Sampler can produce at least one subgraph from the current seed set.
- Sampler reports low confidence when typed resources are missing instead of pretending compatibility is proven.
- Sampler never samples `exclude_until_revised`.
- Sampler can run in report-only mode without changing registry files.

## Phase 2: Blueprint Assembler V2

Status:

- Initial subgraph-consuming entrypoint implemented in `src/task_generator/v3_pipeline_b_prototype.py`.
- CLI `Test/run_v3_pipeline_b_prototype.py` now supports `--subgraph-report`.
- Legacy seed-report mode remains supported for backward compatibility.
- Current output is still a draft `TaskBlueprint`; it does not generate files, run teacher mode, build rubrics, or export rw-task packages.

Goal:

Generate `TaskBlueprint` from a sampled subgraph, not directly from a flat skill list.

New or revised module:

- extend `src/task_generator/v3_pipeline_b_prototype.py`, or split into `src/task_generator/v3_pipeline_b_blueprint.py`

Work:

- Convert `PipelineBSubgraph` into:
  - scenario metadata
  - business context
  - reference file needs
  - deliverable requirements
  - trap candidates
  - prompt requirements
  - GoldenRun plan
- Keep `TaskBlueprint` compatible with `src/task_generator/v2_schema.py`.
- Add explicit provenance fields where the schema already supports them.
- If the current schema is insufficient, add a schema extension conservatively and update docs.

Acceptance checks:

- Blueprint validates with `TaskBlueprint.model_validate`.
- Blueprint records selected Pipeline A skill IDs.
- Blueprint includes enough reference-file specification for a generator to create files.
- Blueprint includes enough GoldenRun plan information for teacher solving.

## Phase 3: General Reference File Generator

Status:

- The planning layer is implemented in `src/task_generator/v3_reference_file_planner.py`.
- CLI `Test/run_v3_reference_file_planner.py` emits `reference_file_plan.json`.
- Deterministic table-first generation is now implemented in `src/task_generator/v3_reference_file_generator.py`.
- CLI `Test/run_v3_reference_file_generator.py` emits concrete files plus manifest/index/trace artifacts.
- Current smoke generates `source_evidence.xlsx` and `policy_reference.docx`, writes `policy_reference_clause_map.json`, and keeps generation-strategy metadata for future deterministic, LLM, Stirrup, and imported-file generators.
- The next implementation step should broaden supported file types and deepen validation without weakening evidence-index traceability.

Goal:

Turn blueprint file specs into concrete candidate-visible files.

New module:

- `src/task_generator/v3_reference_file_generator.py`
- existing planning module: `src/task_generator/v3_reference_file_planner.py`

Initial scope:

- Start with deterministic generation for table-heavy evidence packages.
- Support `.xlsx`, `.csv`, `.json`, and simple `.md`/`.txt` references first.
- Defer polished `.docx` generation unless a task needs it.

Generation principles:

- Generated data must satisfy the blueprint and subgraph needs.
- Every grading target should be traceable to visible evidence unless marked teacher-only.
- Numeric targets should be generated deterministically or validated after generation.
- Every generated file should have a manifest entry.

Expected artifacts:

- `reference_files/`
- `reference_file_manifest.json`
- `evidence_index.json`
- `generation_trace.json`

Acceptance checks:

- Files exist and match blueprint file names.
- Tables have required columns and row counts within expected ranges.
- Evidence IDs are unique and referenced consistently.
- A sanity validator can read all generated files.

## Phase 4: TeacherRunner / GoldenRun

Status:

- The pre-TeacherRunner contract now exists in `src/task_generator/v3_teacher_input_builder.py`.
- CLI `Test/run_v3_teacher_input_builder.py` emits `teacher_input_manifest.json` and `teacher_input_validation_report.json`.
- `src/task_generator/v3_teacher_runner.py` now consumes those artifacts and emits `golden_run.json` plus `teacher_runner_report.json`.
- Current teacher readiness remains `partial_ready`, mainly because sampled subgraph confidence remains low, selected skills still have single-source support, and Pipeline A typed-resource / transition evidence is incomplete.

Goal:

Generate a teacher-mode solution with intermediate states, evidence citations, final outputs, and grading anchors.

New module:

- `src/task_generator/v3_teacher_runner.py`

Current implemented objects:

- `TeacherRunRequest`
- `GoldenEvidenceUse`
- `GoldenIntermediateState`
- `GoldenStep`
- `GoldenFinalCheck`
- `GoldenRun`
- `TeacherRunnerDiagnostics`
- `TeacherRunnerReport`

Modes:

- deterministic teacher mode for templates with code-solvable calculations
- LLM teacher mode for open-ended memo/review tasks

LLM teacher input should include:

- task blueprint
- generated reference file manifest
- evidence index
- selected Pipeline A skills
- hidden traps or teacher-only checklists
- required intermediate states

Validation rules:

- final claims must cite visible evidence where applicable
- exact numbers must be reproducible from reference files or marked teacher-only
- intermediate states must cover the core sampled skills
- teacher output must not leak hidden solution details into the candidate prompt

Acceptance checks:

- `golden_run.json` is produced.
- GoldenRun includes intermediate states, not only final answer prose.
- Evidence citations resolve to generated reference files.
- Teacher validation report is pass/warn/fail with clear reasons.

## Phase 5: Rubric Builder

Goal:

Convert blueprint plus GoldenRun into machine-readable grading anchors.

New module:

- `src/task_generator/v3_rubric_builder.py`

Rubric categories:

- deliverable presence and format
- evidence citation correctness
- calculation or classification correctness
- exception handling
- reasoning/intermediate-state coverage
- final conclusion support

Output:

- `rubric.json`
- optional human-readable `rubric.md`

Rules:

- Rubrics should not be prose only.
- Every exact target should point to a source evidence path or teacher-only marker.
- Tolerances should be explicit for numeric checks.
- Reasoning checks should be separated from final-result checks.

Acceptance checks:

- Rubric references valid GoldenRun anchors.
- Rubric references valid file/evidence IDs.
- Rubric can be serialized into the current `rw_task_adapter` path or a new adapter path.

## Phase 6: Training Annotation Builder

Goal:

Produce training supervision artifacts from the same blueprint and GoldenRun.

New module:

- `src/task_generator/v3_training_annotation_builder.py`

Output:

- `training_annotation.json`

Contents:

- selected skill IDs and skill rationales
- expected reasoning path
- hidden traps
- common failure modes
- evidence provenance
- teacher-only notes
- final answer summary

Acceptance checks:

- Annotation links back to Pipeline A skill IDs.
- Annotation links to GoldenRun intermediate states.
- Annotation separates candidate-visible evidence from teacher-only supervision.

## Phase 7: Export Adapter Integration

Goal:

Package generated tasks for training and rw-task evaluation.

Modules:

- reuse or extend `src/task_generator/rw_task_adapter.py`
- add `src/task_generator/v3_pipeline_b_export.py` if needed

Exports:

- inspection package for debugging
- training package for RL data use
- rw-task-compatible package for evaluation

Acceptance checks:

- Exported package includes prompt, reference files, deliverable expectations, rubric, and metadata.
- Paths are relative and portable inside the task package.
- Existing rw-task adapter compatibility is preserved where possible.

## Phase 8: Pipeline B Quality Gate

Goal:

Reject invalid or low-confidence generated tasks before expensive evaluation.

New module:

- `src/task_generator/v3_pipeline_b_quality_gate.py`

Checks:

- schema validation
- subgraph compatibility
- reference-file readability
- evidence-index consistency
- GoldenRun completion
- rubric-anchor consistency
- no hidden-solution leakage in candidate prompt
- basic prompt realism
- export package completeness

Output:

- `pipeline_b_quality_report.json`

Acceptance checks:

- Every failure has a stable reason code.
- Quality gate can run on a single generated task package.
- Quality gate can be used by a batch runner to filter outputs.

## Phase 9: Batch Runner

Goal:

Generate multiple candidate tasks and record success/failure statistics.

New CLI:

- `Test/run_v3_pipeline_b_batch.py`

Inputs:

- registry path
- seed set path
- output directory
- motif list
- target count
- optional exploratory flag

Output:

- one directory per generated task
- aggregate batch report
- accepted/rejected counts
- failure reason counts
- Pipeline A feedback summary

Acceptance checks:

- Batch runner can generate a small batch without external LLM calls in deterministic/reference-generator-only mode.
- Batch runner can optionally call LLM teacher mode only with explicit provider/upload approval.
- Repeated runs write to isolated output directories under `artifacts/pipeline_b/`.

## Phase 10: Model-Separation Evaluation Loop

Goal:

Use rw-task or a compatible evaluator late in the funnel to check whether generated tasks produce meaningful model separation.

Work:

- Select only quality-gate-passing tasks.
- Export to rw-task format.
- Run a small model comparison batch.
- Record model outputs, grader outputs, and separation signals.
- Feed results back into task templates, sampler weights, and Pipeline A motif/transition diagnostics.

Acceptance checks:

- Evaluation is optional and late-stage.
- Evaluation artifacts are stored under ignored/generated output directories unless intentionally promoted.
- Static score is not treated as a replacement for model-separation evidence.

## Pipeline A Feedback Loop

Pipeline B should report Pipeline A deficiencies instead of silently working around them.

Feedback categories:

- missing typed resources in persistent registry entries
- weak or absent provided/required resource matching
- seed skill has only single-source support
- motif hint too broad or missing
- graph role missing for an otherwise useful skill
- transition evidence only exists as candidate-local calibration evidence
- useful calibration candidate should be considered for explicit admission

Feedback output:

- `pipeline_a_feedback.json` inside each Pipeline B run directory
- aggregate feedback in batch reports
- sampled skill, edge, motif, and subgraph identifiers for future prior updates
- task-quality outcome fields that can later become reward signals

Registry rule:

- Feedback does not mutate registry records.
- Any admission, quarantine, revision, or schema migration remains a separate Pipeline A governance step.

Future prior-update rule:

- Transition-prior updates should be a separate explicit step, not a hidden side effect of task generation.
- Early Pipeline B runs should write feedback reports first.
- After enough successful and failed task packages exist, a later updater can convert feedback into `observed_count`, `success_count`, `failure_count`, posterior scores, and exploration bonuses.

## Suggested Implementation Order

1. Implement `v3_pipeline_b_sampler.py`.
2. Add a minimal Pipeline B feedback schema/report, even before full task generation.
3. Refactor prototype builder so it consumes `PipelineBSubgraph`.
4. Add reference-file generator for table-first evidence packages.
5. Add deterministic sanity validators for generated files.
6. Add `TeacherRunner` schema and deterministic teacher mode for the first template.
7. Add LLM teacher mode behind explicit external-upload permission.
8. Add rubric builder from GoldenRun anchors.
9. Add training annotation builder.
10. Integrate rw-task export.
11. Add Pipeline B quality gate.
12. Add batch runner.
13. Add a report-first transition-prior updater only after task-quality feedback exists.
14. Run late-stage model-separation evaluation only on filtered outputs.
15. Consider UCB1 or another bandit policy only after there are enough prior-update records to support exploration/exploitation.

## Current Next Slice

The current code change is policy/evidence operationalization on top of the local traceability-tightened draft feedback.

Minimal scope:

- Require exact candidate-visible workbook `Evidence_ID` values, such as `EVID-001`, instead of accepting source labels as evidence support.
- Require policy-sensitive bullets to pair `POL-###` clause IDs with exact workbook evidence IDs in the same local support bracket.
- Align TeacherRunner final checks, state purposes, expected actions, and TrainingAnnotation/Rubric descriptions with exact `Evidence_ID` support.
- Preserve the existing rubric audience split and draft/export semantics.
- Keep the package `revise_only`; do not upgrade readiness because the grader-facing contract is clearer.
- Never mutate `SkillRegistry/*.json`.

This slice answered whether the V3 package can make policy-sensitive evidence support concrete enough for a stricter draft-only external smoke. It did not convert the current `revise_only` sample into formal training data or model-separation evidence.

The next likely implementation slice is Evidence inventory template/ordering: make the required Evidence inventory a fixed early section with explicit columns or bullet fields, so the model cannot satisfy the task by moving the detailed inventory after Follow-up. A Pipeline A typed-resource/support-diversity improvement pass remains the next substrate-level blocker for `candidate_ready`.

## Test Plan For The Current Next Slice

Commands:

```powershell
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_subgraph_sampler.py --output-dir artifacts\pipeline_b\scratch\subgraph_sampler_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_prototype.py --subgraph-report artifacts\pipeline_b\scratch\subgraph_sampler_smoke\pipeline_b_subgraph_report.json --output-dir artifacts\pipeline_b\scratch\prototype_from_subgraph_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_reference_file_planner.py Test\run_v3_reference_file_planner.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_reference_file_planner.py --blueprint artifacts\pipeline_b\scratch\prototype_from_subgraph_smoke\draft_task_blueprint.json --subgraph-report artifacts\pipeline_b\scratch\subgraph_sampler_smoke\pipeline_b_subgraph_report.json --output-dir artifacts\pipeline_b\scratch\reference_file_plan_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_reference_file_generator.py Test\run_v3_reference_file_generator.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_reference_file_generator.py --reference-file-plan artifacts\pipeline_b\scratch\reference_file_plan_smoke\reference_file_plan.json --output-dir artifacts\pipeline_b\scratch\reference_file_generation_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_teacher_input_builder.py Test\run_v3_teacher_input_builder.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_teacher_input_builder.py --output-dir artifacts\pipeline_b\scratch\teacher_input_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_teacher_runner.py Test\run_v3_teacher_runner.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_teacher_runner.py --output-dir artifacts\pipeline_b\scratch\teacher_runner_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_training_annotation_builder.py Test\run_v3_training_annotation_builder.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_training_annotation_builder.py --output-dir artifacts\pipeline_b\scratch\training_annotation_smoke
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_rubric_builder.py src\task_generator\v3_pipeline_b_package_assembler.py src\task_generator\v3_rw_task_exporter.py Test\run_v3_rubric_builder.py Test\run_v3_pipeline_b_package_assembler.py Test\run_v3_rw_task_exporter.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rubric_builder.py --output-dir artifacts\pipeline_b\scratch\rubric_filter_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_quality_gate.py --rubric-report artifacts\pipeline_b\scratch\rubric_filter_smoke\rubric_report.json --output-dir artifacts\pipeline_b\scratch\quality_gate_filter_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_package_assembler.py --rubric artifacts\pipeline_b\scratch\rubric_filter_smoke\rubric.json --rubric-report artifacts\pipeline_b\scratch\rubric_filter_smoke\rubric_report.json --quality-report artifacts\pipeline_b\scratch\quality_gate_filter_smoke\pipeline_b_quality_report.json --output-dir artifacts\pipeline_b\scratch\package_assembler_filter_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_exporter.py --package-manifest artifacts\pipeline_b\scratch\package_assembler_filter_smoke\package_manifest.json --allow-revise-only --output-dir artifacts\pipeline_b\scratch\rw_task_export_filter_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_export_validator.py --case-dir artifacts\pipeline_b\scratch\rw_task_export_filter_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_eval_prep.py --case-dir artifacts\pipeline_b\scratch\rw_task_export_filter_smoke --eval-input-dir artifacts\pipeline_b\scratch\rw_task_eval_input_filter_smoke --overwrite
D:\miniconda3\envs\gdpval\python.exe -m py_compile src\task_generator\v3_pipeline_b_prototype.py src\task_generator\v3_teacher_runner.py Test\run_v3_pipeline_b_prototype.py Test\run_v3_teacher_runner.py
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_prototype.py --subgraph-report artifacts\pipeline_b\scratch\subgraph_sampler_smoke\pipeline_b_subgraph_report.json --output-dir artifacts\pipeline_b\scratch\prototype_contract_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_reference_file_planner.py --blueprint artifacts\pipeline_b\scratch\prototype_contract_smoke\draft_task_blueprint.json --subgraph-report artifacts\pipeline_b\scratch\subgraph_sampler_smoke\pipeline_b_subgraph_report.json --output-dir artifacts\pipeline_b\scratch\reference_file_plan_contract_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_reference_file_generator.py --reference-file-plan artifacts\pipeline_b\scratch\reference_file_plan_contract_smoke\reference_file_plan.json --output-dir artifacts\pipeline_b\scratch\reference_file_generation_contract_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_teacher_input_builder.py --blueprint artifacts\pipeline_b\scratch\prototype_contract_smoke\draft_task_blueprint.json --subgraph-report artifacts\pipeline_b\scratch\subgraph_sampler_smoke\pipeline_b_subgraph_report.json --reference-file-plan artifacts\pipeline_b\scratch\reference_file_plan_contract_smoke\reference_file_plan.json --generated-file-manifest artifacts\pipeline_b\scratch\reference_file_generation_contract_smoke\generated_file_manifest.json --pipeline-a-feedback artifacts\pipeline_b\scratch\subgraph_sampler_smoke\pipeline_a_feedback.json --prototype-report artifacts\pipeline_b\scratch\prototype_contract_smoke\pipeline_b_prototype_report.json --output-dir artifacts\pipeline_b\scratch\teacher_input_contract_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_teacher_runner.py --teacher-input-manifest artifacts\pipeline_b\scratch\teacher_input_contract_smoke\teacher_input_manifest.json --teacher-input-validation-report artifacts\pipeline_b\scratch\teacher_input_contract_smoke\teacher_input_validation_report.json --output-dir artifacts\pipeline_b\scratch\teacher_runner_contract_smoke
D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_eval_runner.py --prep-report artifacts\pipeline_b\scratch\rw_task_eval_input_contract_smoke\rw_task_eval_prep_report.json --output-dir artifacts\pipeline_b\scratch\rw_task_eval_run_contract_dry_smoke
```

Expected results:

- The sampler emits a report-only subgraph.
- The prototype emits a draft blueprint from that subgraph.
- The planner emits `reference_file_plan.json`.
- The generator emits concrete table files where supported and a `generated_file_manifest.json`.
- The teacher-input builder emits `teacher_input_manifest.json` and `teacher_input_validation_report.json`.
- The teacher-runner emits `golden_run.json` and `teacher_runner_report.json`.
- The training-annotation builder emits `training_annotation.json` and `training_annotation_report.json`.
- The rubric builder emits `rubric.json` and `rubric_report.json`.
- The rubric report shows full and exportable criteria separately.
- The current filter smoke keeps 28 candidate/exportable criteria and 15 diagnostic criteria out of 43 total criteria.
- The current teacher run stays `partial_ready` rather than hiding low-confidence subgraph and Pipeline A signal gaps.
- The rw-task export report records `rw_task_rubric_item_count=28` and `diagnostic_rubric_item_count=15`.
- The exported `dataset_row.json.rubric_json` does not contain Pipeline A graph-signal diagnostic criteria.
- No registry files are modified.
- The plan records file specs, evidence IDs, resource coverage, unresolved gaps, and provenance hooks.
- If the current registry lacks typed resources for selected skills, the plan carries that warning forward instead of hiding it.
- The eval prep emits a new `draft_inspection_only` batch input for the filtered draft case.
- Authorized filtered external smoke completes and produces a draft-quality observation of `53/62`.
- Eval feedback reports 5 remaining low-scoring criteria, not the previous Pipeline A diagnostic-heavy 13.
- Contract-strengthened candidate prompt contains `Evidence inventory`, `Deliverable outline`, `Evidence-to-conclusion map`, and `Policy clause mapping`.
- Contract-strengthened dry-run reaches `rw_task_eval_run_contract_dry_smoke` with `run_status=dry_run_ready`.
- Authorized contract-strengthened external smoke completes and produces a draft-quality observation of `58/62`.
- Eval feedback reports 4 remaining low-scoring criteria: 2 reference-evidence traceability items and 2 teacher-step operationalization items.
- Traceability-tightened candidate prompt requires local bracketed support such as `[Evidence: EV-###]` or `[Evidence: EV-###; Policy: POL-###]` on material conclusion bullets.
- Traceability-tightened deterministic smoke reaches `rw_task_eval_run_traceability_dry_smoke` with `run_status=dry_run_ready`.
- Authorized traceability-tightened external smoke completes and produces a stricter draft-quality observation of `53/62`.
- Traceability eval feedback reports 8 low-scoring criteria, concentrated in `policy_reference_prompting` and `teacher_step_operationalization`; this is a sharper diagnostic baseline, not a readiness regression.
- Policy/evidence operationalization prompt requires exact workbook `Evidence_ID` values such as `EVID-001`, rejects source-label-only citations, and pairs `POL-###` clauses with exact evidence IDs in policy-sensitive bullets.
- Policy/evidence deterministic smoke reaches `rw_task_eval_run_policy_operationalization_dry_smoke` with `run_status=dry_run_ready`.
- Authorized policy/evidence external smoke completes and produces a draft-quality observation of `58/62`.
- Policy/evidence eval feedback reports 3 remaining low-scoring criteria, all tied to Evidence inventory ordering / teacher-step operationalization.
- The current draft eval path remains `draft_inspection_only` and is not final training data.
- A local explicit smoke can surface environment blockers such as missing `E2B_API_KEY` or blocked outbound E2B connections before any task-quality conclusion is possible.

## Open Design Questions

- Should Pipeline B support exploratory sampling from `sample_with_caution`, or keep that behind a CLI flag?
- Should typed resource backfill happen as a Pipeline A migration, or should Pipeline B keep a temporary inference layer until more graph-ready registry entries exist?
- Should the first full generated task target a workbook deliverable, a memo deliverable, or a mixed evidence package?
- Should LLM teacher mode be introduced before or after deterministic reference-file generation has a stable evidence index?
- What should count as the first reward signal for transition priors: quality-gate pass, GoldenRun validation, rubric validation, model-separation score, or a weighted combination?
- Should UCB-style exploration happen at the edge level, motif level, complete subgraph level, or all three with separate budgets?
- How conservative should the sampler be when a subgraph has high motif promise but weak typed-resource compatibility?

Current recommended answers:

- Keep `sample_with_caution` behind a CLI flag.
- Do not backfill registry as a Pipeline B side effect.
- Start with an evidence package to memo/workpaper deliverable because it matches current seed motifs.
- Add LLM teacher mode only after generated files have a stable manifest and evidence index.
- Use quality-gate and GoldenRun validation as the first reward signals; model-separation evidence should be added later because it is expensive.
- Start with static subgraph sampling and feedback logging; implement bandit/UCB only after several batches have produced comparable feedback records.
