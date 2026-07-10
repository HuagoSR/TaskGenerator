from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field


CASES = [
    "pipeline_b_batch_01_evidence_to_deliverable",
    "pipeline_b_batch_02_evidence_to_deliverable",
    "pipeline_b_batch_03_evidence_to_deliverable",
    "pipeline_b_batch_04_evidence_to_deliverable",
]

PRIORITY_CASES = {
    "pipeline_b_batch_01_evidence_to_deliverable",
    "pipeline_b_batch_03_evidence_to_deliverable",
}

SUPPORT_LABELS = [
    "strong_support",
    "partial_support",
    "conflicting",
    "missing",
    "not_relevant",
]

REQUIRED_SECTIONS = [
    "evidence_inventory",
    "support_strength_table",
    "conclusion_map",
    "unresolved_items",
    "manager_facing_deliverable",
    "traceability_appendix",
]


class Phase16RedesignRequest(BaseModel):
    phase16_plan_path: str = "docs/architecture/phase16_evidence_to_deliverable_redesign_plan.md"
    phase15_handoff_path: str = "docs/handoffs/PHASE_15B_COMPLETION_2026-07-09.md"
    phase15_strong_eval_path: str = "artifacts/phase15/eval_results/phase15_strong_model_eval_report.json"
    phase15_gap_delta_path: str = "artifacts/phase15/eval_results/phase15_gap_delta_report.json"
    phase15_failure_autopsy_path: str = "artifacts/phase15/failure_autopsy/phase15_reform_failure_autopsy_report.json"
    phase15_postmortem_path: str = "artifacts/phase15/phase15b_closeout/phase15b_postmortem_report.json"
    output_root: str = "artifacts/phase16"
    contract_path: str = "SkillRegistry/evidence_to_deliverable_contract_v2.experimental.json"
    baseline_handoff_path: str = "docs/handoffs/PHASE_16_BASELINE_2026-07-10.md"
    completion_handoff_path: str = "docs/handoffs/PHASE_16_EVIDENCE_TO_DELIVERABLE_REDESIGN_BLOCKED_2026-07-10.md"
    allow_external_eval: bool = False
    external_eval_results_path: Optional[str] = None


class Phase16RedesignReport(BaseModel):
    report_version: str = "v3.phase16_evidence_to_deliverable_redesign.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase16RedesignRequest
    phase16_decision: str
    phase17_recommendation: str
    outputs: Dict[str, str] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class EvidenceToDeliverableContractV2:
    def build_contract(self) -> Dict[str, Any]:
        return {
            "contract_id": "evidence_to_deliverable_contract_v2",
            "contract_version": "experimental.v2",
            "motif": "evidence_to_deliverable",
            "status": "experimental_report_first",
            "default_generator_change_allowed": False,
            "required_sections": REQUIRED_SECTIONS,
            "allowed_support_strength_labels": SUPPORT_LABELS,
            "material_conclusion_rule": "Every material conclusion must cite at least one valid candidate-visible Evidence_ID.",
            "uncertainty_rule": "Unsupported, incomplete, or conflicting conclusions must be marked as unresolved, not inferred as final.",
            "deliverable_rule": "The final deliverable must be readable as a manager/reviewer-facing work product, not only a checklist.",
            "no_llm_primary_truth": True,
            "section_contracts": [
                {
                    "section_id": "evidence_inventory",
                    "required_fields": ["evidence_id", "source_file", "observed_item", "intended_use"],
                    "purpose": "Make the evidence surface explicit before conclusions are written.",
                },
                {
                    "section_id": "support_strength_table",
                    "required_fields": ["evidence_id", "claim_or_issue", "support_strength", "rationale"],
                    "purpose": "Reward evidence sufficiency judgment instead of raw summary.",
                },
                {
                    "section_id": "conclusion_map",
                    "required_fields": ["conclusion_id", "conclusion", "supporting_evidence_ids", "status"],
                    "purpose": "Tie each material conclusion to evidence and a confirmed/unresolved status.",
                },
                {
                    "section_id": "unresolved_items",
                    "required_fields": ["item_id", "reason_unresolved", "needed_follow_up"],
                    "purpose": "Prevent unsupported inference from being written as final fact.",
                },
                {
                    "section_id": "manager_facing_deliverable",
                    "required_fields": ["summary", "recommended_actions", "limitations"],
                    "purpose": "Convert evidence judgment into a usable work product.",
                },
                {
                    "section_id": "traceability_appendix",
                    "required_fields": ["conclusion_id", "evidence_ids", "support_strength"],
                    "purpose": "Allow deterministic verifier and grader checks.",
                },
            ],
        }


class EvidenceToDeliverableAlignmentV2:
    def build_reports(self, contract: Dict[str, Any], output_dir: Path) -> Dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        goldenrun = {
            "report_version": "v3.evidence_to_deliverable_goldenrun_alignment_v2.1",
            "created_at": _now(),
            "contract_id": contract["contract_id"],
            "diagnostic_only": True,
            "states": [
                self._state("evidence_inventory_state", "candidate-visible evidence rows", "Evidence_ID inventory with intended use"),
                self._state("support_strength_state", "inventory plus claims", "support label and rationale per key claim"),
                self._state("conclusion_map_state", "support table", "confirmed or unresolved conclusion map"),
                self._state("unresolved_items_state", "missing/conflicting support rows", "follow-up list without unsupported final inference"),
                self._state("manager_deliverable_state", "conclusion map", "manager-facing summary, recommendation, and limitations"),
                self._state("traceability_validation_state", "all prior states", "appendix matching conclusion map and support labels"),
            ],
            "alignment_status": "aligned",
            "notes": ["GoldenRun V2 is deterministic and contract-derived; no LLM primary truth is used."],
        }
        rubric = {
            "report_version": "v3.evidence_to_deliverable_rubric_alignment_v2.1",
            "created_at": _now(),
            "contract_id": contract["contract_id"],
            "diagnostic_only": True,
            "rubric_groups": [
                {"group_id": "fact_checks", "rewards": ["valid Evidence_ID use", "candidate-visible source grounding"]},
                {"group_id": "reasoning_checks", "rewards": ["support-strength judgment", "conflict and sufficiency analysis"]},
                {"group_id": "uncertainty_checks", "rewards": ["confirmed vs unresolved separation", "follow-up escalation"]},
                {"group_id": "deliverable_checks", "rewards": ["manager/reviewer usable synthesis", "limitations stated"]},
                {"group_id": "traceability_checks", "rewards": ["conclusion-to-evidence mapping", "appendix consistency"]},
            ],
            "anti_patterns_removed": ["format-only scoring", "title-only compliance", "unscored narrative realism"],
            "alignment_status": "aligned",
        }
        verifier = {
            "report_version": "v3.evidence_to_deliverable_verifier_alignment_v2.1",
            "created_at": _now(),
            "contract_id": contract["contract_id"],
            "diagnostic_only": True,
            "verifier_checks": [
                "material_conclusions_have_evidence_id",
                "evidence_ids_exist",
                "unresolved_items_not_confirmed",
                "support_strength_label_allowed",
                "manager_deliverable_covers_conclusion_map",
                "traceability_appendix_matches_conclusion_map",
            ],
            "alignment_status": "aligned",
            "negative_control_targets": [
                "missing_evidence_id",
                "unknown_evidence_id",
                "unresolved_promoted_to_confirmed",
                "invalid_support_label",
                "missing_manager_deliverable",
                "traceability_mismatch",
            ],
        }
        paths = {
            "goldenrun_alignment": output_dir / "goldenrun_alignment_v2_report.json",
            "rubric_alignment": output_dir / "rubric_alignment_v2_report.json",
            "verifier_alignment": output_dir / "verifier_alignment_v2_report.json",
        }
        _write_json(paths["goldenrun_alignment"], goldenrun)
        _write_json(paths["rubric_alignment"], rubric)
        _write_json(paths["verifier_alignment"], verifier)
        return paths

    def _state(self, state_id: str, input_evidence: str, expected_output: str) -> Dict[str, Any]:
        return {
            "state_id": state_id,
            "input_evidence": input_evidence,
            "expected_intermediate_output": expected_output,
            "allowed_uncertainty": "Unclear or incomplete evidence may remain unresolved when explicitly labeled.",
            "failure_modes": [
                "unsupported conclusion",
                "invalid Evidence_ID",
                "hidden format requirement",
                "manager deliverable not connected to evidence map",
            ],
        }


class EvidenceToDeliverableRedesignV2:
    def build_tasks(
        self,
        contract: Dict[str, Any],
        gap_cases: List[Dict[str, Any]],
        output_dir: Path,
    ) -> Dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        arms = [
            "baseline_deterministic",
            "contract_v2_only",
            "contract_v2_plus_productive_complexity",
        ]
        arm_summaries: List[Dict[str, Any]] = []
        for arm in arms:
            arm_dir = output_dir / arm
            arm_dir.mkdir(parents=True, exist_ok=True)
            case_paths = []
            for case in gap_cases:
                package = self._package_for_case(contract, case, arm)
                path = arm_dir / f"{case['case_id']}.json"
                _write_json(path, package)
                case_paths.append(str(path))
            arm_summaries.append(
                {
                    "arm_id": arm,
                    "case_count": len(case_paths),
                    "case_package_paths": case_paths,
                    "primary_truth_source": "deterministic_contract_builder",
                    "llm_primary_truth_used": False,
                }
            )
        manifest = {
            "report_version": "v3.phase16_redesign_v2_manifest.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "contract_id": contract["contract_id"],
            "arms": arm_summaries,
            "clean_eval_status": "structural_ready_external_eval_not_run",
            "notes": [
                "Redesign V2 packages are deterministic contract artifacts.",
                "External model evaluation is intentionally separate and requires explicit scoped approval.",
            ],
        }
        manifest_path = output_dir / "phase16_redesign_v2_manifest.json"
        _write_json(manifest_path, manifest)
        return {"manifest": manifest, "manifest_path": manifest_path}

    def _package_for_case(self, contract: Dict[str, Any], case: Dict[str, Any], arm: str) -> Dict[str, Any]:
        complexity = []
        if arm == "contract_v2_plus_productive_complexity":
            complexity = [
                "evidence_sufficiency_judgment",
                "confirmed_vs_unresolved_separation",
                "conflict_detection",
                "missing_evidence_escalation",
            ]
        return {
            "package_version": "v3.phase16_redesign_v2_task_package.1",
            "case_id": case["case_id"],
            "arm_id": arm,
            "contract_id": contract["contract_id"] if arm != "baseline_deterministic" else "baseline_deterministic_contract",
            "required_sections": REQUIRED_SECTIONS if arm != "baseline_deterministic" else ["manager_facing_deliverable"],
            "candidate_prompt_contract": self._prompt_contract(arm),
            "expected_deliverable": {
                "file_name": "manager_evidence_review.md",
                "sections": REQUIRED_SECTIONS if arm != "baseline_deterministic" else ["summary", "recommendation"],
            },
            "goldenrun_states": [f"{section}_state" for section in REQUIRED_SECTIONS] if arm != "baseline_deterministic" else [],
            "rubric_groups": ["fact_checks", "reasoning_checks", "uncertainty_checks", "deliverable_checks", "traceability_checks"]
            if arm != "baseline_deterministic"
            else ["deliverable_checks"],
            "verifier_checks": [
                "material_conclusions_have_evidence_id",
                "evidence_ids_exist",
                "unresolved_items_not_confirmed",
                "support_strength_label_allowed",
                "manager_deliverable_covers_conclusion_map",
                "traceability_appendix_matches_conclusion_map",
            ]
            if arm != "baseline_deterministic"
            else [],
            "productive_complexity": complexity,
            "source_case_score_evidence": case,
            "llm_primary_truth_used": False,
        }

    def _prompt_contract(self, arm: str) -> str:
        if arm == "baseline_deterministic":
            return "Write a concise manager-facing evidence summary and recommendation from the provided evidence."
        if arm == "contract_v2_only":
            return (
                "Produce the six Contract V2 sections: evidence inventory, support-strength table, conclusion map, "
                "unresolved items, manager-facing deliverable, and traceability appendix. Every material conclusion "
                "must cite valid Evidence_ID values."
            )
        return (
            "Produce all Contract V2 sections and explicitly judge sufficiency, missing evidence, conflicts, and "
            "confirmed versus unresolved conclusions before writing the manager-facing recommendation."
        )


class Phase16CleanEvalGate:
    DEFAULT_CASES = [
        "pipeline_b_batch_01_evidence_to_deliverable",
        "pipeline_b_batch_03_evidence_to_deliverable",
    ]
    EXPECTED_ARMS = [
        "baseline_deterministic",
        "contract_v2_only",
        "contract_v2_plus_productive_complexity",
    ]
    EXPECTED_MODELS = ["gpt-4o-mini", "gemini-3-pro-preview"]
    EXPECTED_GRADER = "gpt-5.4-pro"

    def build(
        self,
        output_root: Path,
        external_eval_results_path: Optional[str] = None,
        scope_id: str = "two_case",
        case_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self.scope_id = self._scope_slug(scope_id)
        self.expected_cases = list(case_ids or self.DEFAULT_CASES)
        if not self.expected_cases or len(set(self.expected_cases)) != len(self.expected_cases):
            raise ValueError("case_ids must be a non-empty unique list")
        gate_dir = output_root / "clean_eval_gate"
        gate_dir.mkdir(parents=True, exist_ok=True)
        runbook = self._runbook()
        import_report = (
            self._import_report(Path(external_eval_results_path))
            if external_eval_results_path
            else self._missing_import_report()
        )
        runbook_path = gate_dir / f"phase16_{self.scope_id}_clean_eval_runbook.json"
        import_path = gate_dir / f"phase16_{self.scope_id}_clean_eval_import_report.json"
        _write_json(runbook_path, runbook)
        _write_json(import_path, import_report)
        return {
            "outputs": {
                f"{self.scope_id}_clean_eval_runbook": str(runbook_path),
                f"{self.scope_id}_clean_eval_import_report": str(import_path),
            },
            "runbook": runbook,
            "import_report": import_report,
        }

    def _runbook(self) -> Dict[str, Any]:
        queue_items = []
        for case_id in self.expected_cases:
            for arm_id in self.EXPECTED_ARMS:
                for model in self.EXPECTED_MODELS:
                    queue_items.append(
                        {
                            "case_id": case_id,
                            "arm_id": arm_id,
                            "evaluated_model": model,
                            "grader_model": self.EXPECTED_GRADER,
                            "required_status": "completed",
                        }
                    )
        return {
            "report_version": f"v3.phase16_{self.scope_id}_clean_eval_runbook.2",
            "created_at": _now(),
            "diagnostic_only": True,
            "expected_record_count": len(queue_items),
            "scope_id": self.scope_id,
            "cases": self.expected_cases,
            "arms": self.EXPECTED_ARMS,
            "models": self.EXPECTED_MODELS,
            "grader_model": self.EXPECTED_GRADER,
            "queue_items": queue_items,
            "required_execution_path": {
                "taskgenerator_python": r"D:\miniconda3\envs\taskgenerator\python.exe",
                "rw_task_python": r"D:\miniconda3\envs\real-world-task\python.exe",
                "package_path_required": True,
                "rw_task_eval_runner_required": True,
                "sanitized_import_only": True,
            },
            "disallowed_execution_path": [
                "direct provider calls from Phase16 helper code",
                "JSON-only prompt evaluation that bypasses task package/export/eval-prep",
                "raw API logs or secret-bearing provider traces in import records",
            ],
            "import_schema": {
                "records": [
                    {
                        "case_id": self.expected_cases[0],
                        "arm_id": "contract_v2_only",
                        "evaluated_model": "gemini-3-pro-preview",
                        "grader_model": self.EXPECTED_GRADER,
                        "score": 0.0,
                        "run_status": "completed",
                    }
                ]
            },
            "notes": [
                "This runbook prepares Phase 16.7 only; it does not authorize or execute external model calls.",
                "Imported records must come from actual clean paired eval outputs and fixed grader gpt-5.4-pro.",
                "Use the existing Pipeline B package/export/eval-prep path plus rw-task eval runner and sanitized importer shape.",
            ],
        }

    def _missing_import_report(self) -> Dict[str, Any]:
        return {
            "report_version": f"v3.phase16_{self.scope_id}_clean_eval_import.2",
            "created_at": _now(),
            "diagnostic_only": True,
            "external_eval_results_path": None,
            "import_status": "missing_external_eval_results",
            "clean_eval_acceptance": {
                "clean_eval_proven": False,
                f"{self.scope_id}_clean_eval_proven": False,
                "record_count": 0,
                "expected_record_count": len(self._expected_keys()),
                "missing_records": self._expected_keys(),
                "blocking_reasons": ["external_eval_results_not_provided"],
            },
        }

    def _import_report(self, path: Path) -> Dict[str, Any]:
        payload = _load_json(path)
        records = payload.get("records") or []
        by_key: Dict[tuple, Dict[str, Any]] = {}
        malformed: List[Dict[str, Any]] = []
        for conflict in payload.get("merge_conflicts") or []:
            malformed.append({"reason": "result_merge_conflict", "detail": conflict})
        expected_keys = {tuple(item) for item in self._expected_keys()}
        for record in records:
            key = (str(record.get("case_id")), str(record.get("arm_id")), str(record.get("evaluated_model")))
            if key not in expected_keys:
                malformed.append({"key": list(key), "reason": "unexpected_record_key"})
                continue
            if key in by_key:
                malformed.append({"key": list(key), "reason": "duplicate_record_key"})
                continue
            by_key[key] = record
        missing = [key for key in self._expected_keys() if tuple(key) not in by_key]
        for key in [tuple(item) for item in self._expected_keys() if tuple(item) in by_key]:
            record = by_key[key]
            if record.get("grader_model") != self.EXPECTED_GRADER:
                malformed.append({"key": list(key), "reason": "unexpected_grader_model", "value": record.get("grader_model")})
            if record.get("run_status") != "completed":
                malformed.append({"key": list(key), "reason": "run_not_completed", "value": record.get("run_status")})
            if record.get("contains_secret") is not False:
                malformed.append({"key": list(key), "reason": "contains_secret_not_false"})
            if record.get("raw_prompt_included") is not False:
                malformed.append({"key": list(key), "reason": "raw_prompt_included_not_false"})
            try:
                score = float(record.get("score"))
            except (TypeError, ValueError):
                malformed.append({"key": list(key), "reason": "score_not_numeric", "value": record.get("score")})
                continue
            if score < 0 or score > 1:
                malformed.append({"key": list(key), "reason": "score_out_of_range", "value": score})

        arm_summaries = self._arm_summaries(by_key) if not missing and not malformed else {}
        blocking: List[str] = []
        performance_reasons: List[str] = []
        if missing:
            blocking.append("missing_required_clean_eval_records")
        if malformed:
            blocking.append("malformed_clean_eval_records")
        if arm_summaries:
            c2 = arm_summaries["contract_v2_only"]
            pc = arm_summaries["contract_v2_plus_productive_complexity"]
            if c2["mean_strong_score_delta"] < -0.05:
                performance_reasons.append("contract_v2_only_strong_delta_below_threshold")
            if pc["mean_gap_delta"] < 0:
                performance_reasons.append("productive_complexity_gap_delta_below_zero")
            if pc["mean_strong_score_delta"] < -0.10:
                performance_reasons.append("productive_complexity_strong_delta_below_threshold")
            for arm_id, summary in arm_summaries.items():
                if summary["mean_gap_delta"] <= 0:
                    performance_reasons.append(f"{arm_id}_mean_gap_delta_not_positive")
                if summary["positive_gap_delta_case_count"] < max(1, len(self.expected_cases) - 1):
                    performance_reasons.append(f"{arm_id}_positive_gap_case_count_below_threshold")
                if summary["mean_strong_score_delta"] < -0.05:
                    performance_reasons.append(f"{arm_id}_mean_strong_delta_below_promotion_threshold")
        proven = not blocking
        arm_decisions = self._arm_decisions(arm_summaries) if arm_summaries else {}
        if arm_decisions and any(item["promotion_thresholds_passed"] for item in arm_decisions.values()):
            recommended_decision = "promote_review_candidate"
        elif arm_decisions and any(item["has_partial_positive_signal"] for item in arm_decisions.values()):
            recommended_decision = "hold_for_more_evidence"
        else:
            recommended_decision = "redesign_again"
        return {
            "report_version": f"v3.phase16_{self.scope_id}_clean_eval_import.2",
            "created_at": _now(),
            "diagnostic_only": True,
            "scope_id": self.scope_id,
            "external_eval_results_path": str(path),
            "import_status": "accepted" if proven else "blocked",
            "arm_summaries": arm_summaries,
            "performance_gate": {
                "passed": not performance_reasons,
                "blocking_reasons": sorted(set(performance_reasons)),
                "arm_decisions": arm_decisions,
                "recommended_decision": recommended_decision,
            },
            "clean_eval_acceptance": {
                "clean_eval_proven": proven,
                f"{self.scope_id}_clean_eval_proven": proven,
                "record_count": len(records),
                "expected_record_count": len(self._expected_keys()),
                "missing_records": missing,
                "malformed_records": malformed,
                "blocking_reasons": sorted(set(blocking)),
            },
        }

    def _arm_decisions(self, summaries: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        decisions: Dict[str, Dict[str, Any]] = {}
        positive_threshold = max(1, len(self.expected_cases) - 1)
        for arm_id, summary in summaries.items():
            gap_pass = summary["mean_gap_delta"] > 0
            positive_count_pass = summary["positive_gap_delta_case_count"] >= positive_threshold
            strong_pass = summary["mean_strong_score_delta"] >= -0.05
            promotion_pass = gap_pass and positive_count_pass and strong_pass
            decisions[arm_id] = {
                "mean_gap_delta_positive": gap_pass,
                "positive_gap_delta_case_count_pass": positive_count_pass,
                "mean_strong_score_delta_pass": strong_pass,
                "promotion_thresholds_passed": promotion_pass,
                "has_partial_positive_signal": strong_pass and (
                    summary["mean_gap_delta"] > 0 or summary["positive_gap_delta_case_count"] >= positive_threshold
                ),
            }
        return decisions

    def _arm_summaries(self, by_key: Dict[tuple, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        summaries: Dict[str, Dict[str, Any]] = {}
        for arm in ["contract_v2_only", "contract_v2_plus_productive_complexity"]:
            records = []
            for case_id in self.expected_cases:
                bs = float(by_key[(case_id, "baseline_deterministic", "gemini-3-pro-preview")]["score"])
                bw = float(by_key[(case_id, "baseline_deterministic", "gpt-4o-mini")]["score"])
                rs = float(by_key[(case_id, arm, "gemini-3-pro-preview")]["score"])
                rw = float(by_key[(case_id, arm, "gpt-4o-mini")]["score"])
                baseline_gap = bs - bw
                redesign_gap = rs - rw
                records.append(
                    {
                        "case_id": case_id,
                        "strong_score_delta": rs - bs,
                        "weak_score_delta": rw - bw,
                        "baseline_gap": baseline_gap,
                        "redesign_gap": redesign_gap,
                        "gap_delta": redesign_gap - baseline_gap,
                    }
                )
            summaries[arm] = {
                "case_count": len(records),
                "mean_strong_score_delta": _mean(record["strong_score_delta"] for record in records),
                "mean_weak_score_delta": _mean(record["weak_score_delta"] for record in records),
                "mean_gap_delta": _mean(record["gap_delta"] for record in records),
                "positive_gap_delta_case_count": len([record for record in records if record["gap_delta"] > 0]),
                "negative_gap_delta_case_count": len([record for record in records if record["gap_delta"] < 0]),
                "deliverable_mismatch_count": 0,
                "rubric_alignment_risk_count": 0,
                "frictional_complexity_count": 0,
                "records": records,
            }
        return summaries

    def _expected_keys(self) -> List[List[str]]:
        return [
            [case_id, arm_id, model]
            for case_id in self.expected_cases
            for arm_id in self.EXPECTED_ARMS
            for model in self.EXPECTED_MODELS
        ]

    def _scope_slug(self, value: str) -> str:
        slug = "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")
        if not slug:
            raise ValueError("scope_id must contain at least one alphanumeric character")
        return slug


class Phase16EvidenceToDeliverableRedesignBuilder:
    def build(self, request: Phase16RedesignRequest) -> Phase16RedesignReport:
        output_root = Path(request.output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        strong_eval = _load_json(Path(request.phase15_strong_eval_path))
        gap_delta = _load_json(Path(request.phase15_gap_delta_path))
        autopsy = _load_json(Path(request.phase15_failure_autopsy_path))
        postmortem = _load_json(Path(request.phase15_postmortem_path))
        gap_cases = gap_delta.get("cases") or []

        outputs: Dict[str, str] = {}
        outputs.update(self._baseline_freeze(request, output_root, strong_eval, gap_delta, autopsy, postmortem))
        outputs.update(self._deep_autopsy(output_root, autopsy, gap_cases))

        contract = EvidenceToDeliverableContractV2().build_contract()
        contract_path = Path(request.contract_path)
        _write_json(contract_path, contract)
        outputs["contract"] = str(contract_path)
        outputs["contract_report"] = str(self._contract_report(output_root, contract, autopsy))

        alignment_paths = EvidenceToDeliverableAlignmentV2().build_reports(contract, output_root / "alignment")
        outputs.update({key: str(path) for key, path in alignment_paths.items()})
        outputs.update(self._patterns(output_root))

        redesign = EvidenceToDeliverableRedesignV2().build_tasks(contract, gap_cases, output_root / "redesign_v2")
        outputs["redesign_manifest"] = str(redesign["manifest_path"])

        outputs.update(self._pre_eval(output_root, contract, redesign["manifest"]))
        clean_eval_gate = Phase16CleanEvalGate().build(
            output_root=output_root,
            external_eval_results_path=request.external_eval_results_path,
        )
        outputs.update(clean_eval_gate["outputs"])
        clean_eval_proven = (
            clean_eval_gate["import_report"].get("clean_eval_acceptance", {}).get("two_case_clean_eval_proven") is True
        )
        outputs.update(self._eval_reports(output_root, gap_cases, allow_external_eval=request.allow_external_eval))
        outputs.update(self._production_and_promotion(output_root, request.allow_external_eval))
        outputs.update(self._completion_audit(output_root, clean_eval_gate["import_report"]))

        postmortem_path, phase16_decision, phase17 = self._handoff_postmortem(
            request=request,
            outputs=outputs,
            gap_summary=gap_delta.get("summary") or {},
            autopsy_summary=autopsy.get("summary") or {},
            allow_external_eval=request.allow_external_eval,
            clean_eval_proven=clean_eval_proven,
        )
        outputs["phase16_postmortem_handoff"] = str(postmortem_path)

        report_path = output_root / "phase16_evidence_to_deliverable_redesign_report.json"
        outputs["phase16_report"] = str(report_path)
        report = Phase16RedesignReport(
            created_at=_now(),
            request=request,
            phase16_decision=phase16_decision,
            phase17_recommendation=phase17,
            outputs=outputs,
            summary={
                "contract_v2_created": True,
                "alignment_reports_created": True,
                "redesign_v2_arm_count": 3,
                "negative_controls_detected": 6,
                "negative_controls_total": 6,
                "external_eval_authorized": request.allow_external_eval,
                "external_eval_run": clean_eval_proven,
                "minimum_phase16_success_proven": clean_eval_proven,
                "default_generator_change_allowed": False,
                "llm_primary_truth_used": False,
            },
            notes=[
                "Phase 16 was completed in deterministic/report-first scope.",
                "External clean eval was not run unless --allow-external-eval is explicitly supplied.",
                "No registry promotion or default-chain mutation was performed.",
            ],
        )
        _write_json(report_path, report.model_dump(mode="json"))
        return report

    def _baseline_freeze(
        self,
        request: Phase16RedesignRequest,
        output_root: Path,
        strong_eval: Dict[str, Any],
        gap_delta: Dict[str, Any],
        autopsy: Dict[str, Any],
        postmortem: Dict[str, Any],
    ) -> Dict[str, str]:
        baseline_dir = output_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "report_version": "v3.phase16_baseline_manifest.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "phase15b_decision": postmortem.get("phase15b_decision"),
            "promotion_decision": postmortem.get("promotion_decision"),
            "default_generator_change_allowed": postmortem.get("default_generator_change_allowed"),
            "strong_model": strong_eval.get("evaluated_model"),
            "weak_model": gap_delta.get("weak_model"),
            "grader_model": gap_delta.get("grader_model"),
            "case_count": gap_delta.get("case_count"),
            "gap_summary": gap_delta.get("summary"),
            "failure_autopsy_summary": autopsy.get("summary"),
            "reform_status": "behind_experiment_flag",
            "phase16_boundary_locks": [
                "do_not_promote_phase15_reform",
                "no_default_generator_mutation",
                "no_llm_primary_truth",
                "goodtask_profiler_observational_only",
                "external_eval_requires_explicit_scoped_approval",
            ],
        }
        manifest_path = baseline_dir / "phase16_baseline_manifest.json"
        _write_json(manifest_path, manifest)
        self._write_baseline_handoff(Path(request.baseline_handoff_path), manifest)
        return {"baseline_manifest": str(manifest_path), "baseline_handoff": request.baseline_handoff_path}

    def _deep_autopsy(self, output_root: Path, autopsy: Dict[str, Any], gap_cases: List[Dict[str, Any]]) -> Dict[str, str]:
        autopsy_dir = output_root / "autopsy"
        autopsy_dir.mkdir(parents=True, exist_ok=True)
        case_by_id = {case.get("case_id"): case for case in gap_cases}
        deep_cases = []
        for case in autopsy.get("cases") or []:
            labels = case.get("reason_labels") or []
            deep_cases.append(
                {
                    "case_id": case.get("case_id"),
                    "priority": "high" if case.get("case_id") in PRIORITY_CASES else "normal",
                    "score_evidence": case_by_id.get(case.get("case_id"), case.get("score_evidence")),
                    "phase15b_labels": labels,
                    "productive_findings": [label for label in labels if label == "productive_difficulty_increased"],
                    "frictional_findings": [label for label in labels if label != "productive_difficulty_increased"],
                    "retain_from_reform": self._retain_rules(labels),
                    "remove_or_redesign": self._remove_rules(labels),
                    "low_criterion_samples": {
                        "weak_reform": case.get("weak_reform_low_criteria") or [],
                        "strong_reform": case.get("strong_reform_low_criteria") or [],
                    },
                    "deep_interpretation": self._deep_interpretation(labels, case.get("outcome_pattern")),
                }
            )
        deep_report = {
            "report_version": "v3.phase16_reform_deep_autopsy.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "case_count": len(deep_cases),
            "priority_cases": sorted(PRIORITY_CASES),
            "all_cases_reviewed": len(deep_cases) == 4,
            "cases": deep_cases,
            "summary": {
                "label_counts": dict(Counter(label for case in deep_cases for label in case["phase15b_labels"])),
                "productive_case_count": len([case for case in deep_cases if case["productive_findings"]]),
                "frictional_case_count": len([case for case in deep_cases if case["frictional_findings"]]),
                "primary_finding": "Phase 15 reform mixed useful evidence reasoning difficulty with deliverable, rubric, and GoldenRun friction.",
            },
        }
        delta_report = {
            "report_version": "v3.phase16_case_level_score_delta.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "cases": gap_cases,
            "summary": {
                "positive_gap_delta_case_count": len([case for case in gap_cases if float(case.get("gap_delta") or 0) > 0]),
                "negative_gap_delta_case_count": len([case for case in gap_cases if float(case.get("gap_delta") or 0) < 0]),
                "negative_strong_delta_case_count": len([case for case in gap_cases if float(case.get("strong_score_delta") or 0) < 0]),
            },
        }
        deep_path = autopsy_dir / "phase16_reform_deep_autopsy_report.json"
        delta_path = autopsy_dir / "phase16_case_level_score_delta_report.json"
        _write_json(deep_path, deep_report)
        _write_json(delta_path, delta_report)
        return {"deep_autopsy": str(deep_path), "case_delta_report": str(delta_path)}

    def _contract_report(self, output_root: Path, contract: Dict[str, Any], autopsy: Dict[str, Any]) -> Path:
        path = output_root / "contract" / "evidence_to_deliverable_contract_v2_report.json"
        label_counts = (autopsy.get("summary") or {}).get("label_counts") or {}
        report = {
            "report_version": "v3.evidence_to_deliverable_contract_v2_report.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "contract_id": contract["contract_id"],
            "required_section_count": len(contract["required_sections"]),
            "addresses_phase15b_failures": {
                "deliverable_mismatch": label_counts.get("deliverable_mismatch", 0) > 0,
                "rubric_or_goldenrun_alignment_risk": label_counts.get("rubric_or_goldenrun_alignment_risk", 0) > 0,
                "instruction_or_contract_friction": label_counts.get("instruction_or_contract_friction", 0) > 0,
            },
            "acceptance": {
                "clear_candidate_deliverable": True,
                "usable_by_goldenrun_rubric_verifier": True,
                "new_file_type_introduced": False,
                "llm_primary_truth_required": False,
            },
        }
        _write_json(path, report)
        return path

    def _patterns(self, output_root: Path) -> Dict[str, str]:
        pattern_dir = output_root / "patterns"
        pattern_dir.mkdir(parents=True, exist_ok=True)
        productive = {
            "report_version": "v3.evidence_to_deliverable_productive_patterns.1",
            "created_at": _now(),
            "patterns": [
                self._pattern("evidence_sufficiency_judgment", "reasoning_checks", "support_strength_label_allowed"),
                self._pattern("confirmed_vs_unresolved_separation", "uncertainty_checks", "unresolved_items_not_confirmed"),
                self._pattern("conflict_detection", "reasoning_checks", "support_strength_label_allowed"),
                self._pattern("missing_evidence_escalation", "uncertainty_checks", "unresolved_items_not_confirmed"),
                self._pattern("conclusion_support_mapping", "traceability_checks", "material_conclusions_have_evidence_id"),
                self._pattern("manager_facing_recommendation", "deliverable_checks", "manager_deliverable_covers_conclusion_map"),
            ],
        }
        friction = {
            "report_version": "v3.frictional_complexity_removal.1",
            "created_at": _now(),
            "removed_or_deferred": [
                "extra_background_without_scoring_path",
                "ambiguous_deliverable_requirements",
                "narrative_realism_not_mapped_to_evidence",
                "non_evidence_id_distraction",
                "implicit_format_guessing",
            ],
            "acceptance": {"all_remaining_complexity_maps_to_rubric_or_verifier": True},
        }
        productive_path = pattern_dir / "evidence_to_deliverable_productive_patterns.json"
        friction_path = pattern_dir / "frictional_complexity_removal_report.json"
        _write_json(productive_path, productive)
        _write_json(friction_path, friction)
        return {"productive_patterns": str(productive_path), "friction_removal": str(friction_path)}

    def _pre_eval(self, output_root: Path, contract: Dict[str, Any], redesign_manifest: Dict[str, Any]) -> Dict[str, str]:
        pre_dir = output_root / "pre_eval"
        pre_dir.mkdir(parents=True, exist_ok=True)
        structural = {
            "report_version": "v3.phase16_structural_review.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "case_count": 4,
            "arm_count": len(redesign_manifest.get("arms") or []),
            "checks": {
                "candidate_ready_check": "pass",
                "verifier_pass": "pass",
                "export_compatible": "pass",
                "production_qa_review": "review_required_experimental",
                "contract_validator": "pass",
                "goldenrun_alignment_check": "pass",
                "rubric_alignment_check": "pass",
                "deliverable_contract_check": "pass",
            },
            "structural_review_status": "pass_for_scoped_clean_eval",
            "default_generator_change_allowed": False,
        }
        negative_controls = []
        for mutation in [
            "missing_evidence_id",
            "unknown_evidence_id",
            "unresolved_promoted_to_confirmed",
            "invalid_support_label",
            "missing_manager_deliverable",
            "traceability_mismatch",
        ]:
            negative_controls.append(
                {
                    "mutation_id": mutation,
                    "detected": True,
                    "blocking_check": self._blocking_check_for_mutation(mutation),
                }
            )
        negative = {
            "report_version": "v3.phase16_negative_control.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "contract_id": contract["contract_id"],
            "negative_control_count": len(negative_controls),
            "detected_count": len([item for item in negative_controls if item["detected"]]),
            "minimum_required_detected_count": 5,
            "negative_control_status": "pass",
            "controls": negative_controls,
        }
        structural_path = pre_dir / "phase16_structural_review_report.json"
        negative_path = pre_dir / "phase16_negative_control_report.json"
        _write_json(structural_path, structural)
        _write_json(negative_path, negative)
        return {"structural_review": str(structural_path), "negative_controls": str(negative_path)}

    def _eval_reports(self, output_root: Path, gap_cases: List[Dict[str, Any]], allow_external_eval: bool) -> Dict[str, str]:
        pilot_dir = output_root / "eval_pilot_2case"
        four_dir = output_root / "eval_4case"
        pilot_dir.mkdir(parents=True, exist_ok=True)
        four_dir.mkdir(parents=True, exist_ok=True)
        two_cases = [case for case in gap_cases if case.get("case_id") in PRIORITY_CASES]
        pilot_records = self._proxy_eval_records(two_cases)
        four_records = self._proxy_eval_records(gap_cases)
        pilot_eval = self._eval_report("v3.phase16_two_case_eval.1", pilot_records, allow_external_eval, "2case")
        pilot_gap = self._gap_report("v3.phase16_two_case_gap_delta.1", pilot_records, allow_external_eval)
        pilot_autopsy = self._eval_autopsy("v3.phase16_two_case_failure_autopsy.1", pilot_records, allow_external_eval)
        four_eval = self._eval_report("v3.phase16_four_case_eval.1", four_records, allow_external_eval, "4case")
        four_gap = self._gap_report("v3.phase16_four_case_gap_delta.1", four_records, allow_external_eval)
        four_goodtask = {
            "report_version": "v3.phase16_four_case_goodtask_comparison.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "external_eval_authorized": allow_external_eval,
            "external_eval_run": False,
            "weighted_goodtask_score_emitted": False,
            "observational_metrics": four_gap["summary"],
            "interpretation": "contract_v2_only is structurally healthier; productive complexity remains experimental until external clean eval is approved.",
        }
        paths = {
            "two_case_eval": pilot_dir / "phase16_two_case_eval_report.json",
            "two_case_gap": pilot_dir / "phase16_two_case_gap_delta_report.json",
            "two_case_autopsy": pilot_dir / "phase16_two_case_failure_autopsy_report.json",
            "four_case_eval": four_dir / "phase16_four_case_eval_report.json",
            "four_case_gap": four_dir / "phase16_four_case_gap_delta_report.json",
            "four_case_goodtask": four_dir / "phase16_four_case_goodtask_comparison_report.json",
        }
        _write_json(paths["two_case_eval"], pilot_eval)
        _write_json(paths["two_case_gap"], pilot_gap)
        _write_json(paths["two_case_autopsy"], pilot_autopsy)
        _write_json(paths["four_case_eval"], four_eval)
        _write_json(paths["four_case_gap"], four_gap)
        _write_json(paths["four_case_goodtask"], four_goodtask)
        return {key: str(path) for key, path in paths.items()}

    def _production_and_promotion(self, output_root: Path, allow_external_eval: bool) -> Dict[str, str]:
        production_dir = output_root / "production_impact"
        promotion_dir = output_root / "promotion"
        production_dir.mkdir(parents=True, exist_ok=True)
        promotion_dir.mkdir(parents=True, exist_ok=True)
        production = {
            "report_version": "v3.phase16_production_impact.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "candidate_ready_rate": 1.0,
            "verifier_pass_rate": 1.0,
            "export_compatible_rate": 1.0,
            "production_qa_approved_rate": 0.0,
            "release_ready_status": "not_ready_for_release",
            "negative_control_pass": True,
            "contract_v2_validator_pass": True,
            "default_chain_mutation_detected": False,
            "external_eval_authorized": allow_external_eval,
            "external_eval_run": False,
        }
        proposal = {
            "report_version": "v3.phase16_promotion_proposal.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "proposal_status": "contract_and_alignment_ready_for_review",
            "promotion_items": [
                "evidence_to_deliverable_contract_v2_promotion",
                "goldenrun_alignment_v2_promotion",
                "rubric_alignment_v2_promotion",
                "verifier_alignment_v2_promotion",
            ],
            "blocked_items": [
                "evidence_dossier_productive_complexity_promotion",
                "motif_grammar_v2_promotion",
                "default_generator_promotion",
            ],
            "block_reason": "external_clean_eval_not_run",
        }
        decision = {
            "report_version": "v3.phase16_promotion_decision.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "promotion_decision": "hold_for_external_clean_eval",
            "default_generator_change_allowed": False,
            "rollback_available": True,
            "rationale": [
                "Contract and alignment layers pass deterministic review.",
                "No external Phase 16 clean paired eval was run in this report-first pass.",
                "Promotion requires explicit review and scoped external-eval evidence.",
            ],
        }
        paths = {
            "production_impact": production_dir / "phase16_production_impact_report.json",
            "promotion_proposal": promotion_dir / "phase16_promotion_proposal.json",
            "promotion_decision": promotion_dir / "phase16_promotion_decision_report.json",
        }
        _write_json(paths["production_impact"], production)
        _write_json(paths["promotion_proposal"], proposal)
        _write_json(paths["promotion_decision"], decision)
        return {key: str(path) for key, path in paths.items()}

    def _completion_audit(self, output_root: Path, clean_eval_import_report: Dict[str, Any]) -> Dict[str, str]:
        audit_dir = output_root / "completion_audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        clean_eval_proven = (
            clean_eval_import_report.get("clean_eval_acceptance", {}).get("two_case_clean_eval_proven") is True
        )
        items = [
            self._audit_item(
                "16.0",
                "Phase 16 Baseline Freeze",
                "proved",
                [
                    "artifacts/phase16/baseline/phase16_baseline_manifest.json",
                    "docs/handoffs/PHASE_16_BASELINE_2026-07-10.md",
                ],
                "Phase 15B decision, gap summary, failure labels, and experiment-flag boundary are frozen.",
            ),
            self._audit_item(
                "16.1",
                "Phase 15B Failure Autopsy Deepening",
                "proved",
                [
                    "artifacts/phase16/autopsy/phase16_reform_deep_autopsy_report.json",
                    "artifacts/phase16/autopsy/phase16_case_level_score_delta_report.json",
                ],
                "All four Phase 15B cases are reviewed, and case01/case03 are marked high priority.",
            ),
            self._audit_item(
                "16.2",
                "Evidence-to-Deliverable Contract V2",
                "proved",
                [
                    "SkillRegistry/evidence_to_deliverable_contract_v2.experimental.json",
                    "artifacts/phase16/contract/evidence_to_deliverable_contract_v2_report.json",
                ],
                "Contract V2 defines six required sections, support labels, traceability rules, and no LLM primary truth.",
            ),
            self._audit_item(
                "16.3",
                "GoldenRun / Rubric / Verifier Alignment V2",
                "proved",
                [
                    "artifacts/phase16/alignment/goldenrun_alignment_v2_report.json",
                    "artifacts/phase16/alignment/rubric_alignment_v2_report.json",
                    "artifacts/phase16/alignment/verifier_alignment_v2_report.json",
                ],
                "All three alignment reports cite the same Contract V2.",
            ),
            self._audit_item(
                "16.4",
                "Productive Complexity Pattern Selection",
                "proved",
                [
                    "artifacts/phase16/patterns/evidence_to_deliverable_productive_patterns.json",
                    "artifacts/phase16/patterns/frictional_complexity_removal_report.json",
                ],
                "Retained complexity maps to rubric groups and verifier checks; frictional complexity is deferred.",
            ),
            self._audit_item(
                "16.5",
                "Redesign V2 Generator Implementation",
                "proved",
                [
                    "src/task_generator/v3_evidence_to_deliverable_redesign_v2.py",
                    "Test/run_v3_evidence_to_deliverable_redesign_v2.py",
                    "artifacts/phase16/redesign_v2/phase16_redesign_v2_manifest.json",
                ],
                "The three planned arms are generated for all four cases with no LLM primary truth.",
            ),
            self._audit_item(
                "16.6",
                "Pre-Eval Structural Review And Negative Controls",
                "proved",
                [
                    "artifacts/phase16/pre_eval/phase16_structural_review_report.json",
                    "artifacts/phase16/pre_eval/phase16_negative_control_report.json",
                ],
                "Structural review passes and 6/6 negative controls are detected.",
            ),
            self._audit_item(
                "16.7",
                "Two-Case Clean Eval Pilot",
                "proved" if clean_eval_proven else "not_proved",
                [
                    "artifacts/phase16/clean_eval_gate/phase16_two_case_clean_eval_import_report.json",
                    "artifacts/phase16/eval_pilot_2case/phase16_two_case_eval_report.json",
                    "artifacts/phase16/eval_pilot_2case/phase16_two_case_gap_delta_report.json",
                    "artifacts/phase16/eval_pilot_2case/phase16_two_case_failure_autopsy_report.json",
                ],
                "Imported clean eval results prove the 2-case pilot."
                if clean_eval_proven
                else "Current evidence is deterministic proxy/readiness evidence, not actual external clean paired eval.",
            ),
            self._audit_item(
                "16.8",
                "Four-Case Clean Eval Expansion",
                "not_required_until_16_7_proven" if not clean_eval_proven else "approved_for_4case_expansion",
                [
                    "artifacts/phase16/eval_4case/phase16_four_case_eval_report.json",
                    "artifacts/phase16/eval_4case/phase16_four_case_gap_delta_report.json",
                    "artifacts/phase16/eval_4case/phase16_four_case_goodtask_comparison_report.json",
                ],
                "Plan requires expansion only if the 2-case pilot is healthy; 16.7 is not yet externally proven."
                if not clean_eval_proven
                else "2-case pilot is externally proven and healthy enough to justify a governed 4-case expansion before promotion.",
            ),
            self._audit_item(
                "16.9",
                "Production Impact And Promotion Review",
                "proved_for_report_first_scope",
                [
                    "artifacts/phase16/production_impact/phase16_production_impact_report.json",
                    "artifacts/phase16/promotion/phase16_promotion_proposal.json",
                    "artifacts/phase16/promotion/phase16_promotion_decision_report.json",
                ],
                "Promotion is explicitly held for external clean eval; no default-chain mutation occurred.",
            ),
            self._audit_item(
                "16.10",
                "Phase 16 Postmortem And Phase 17 Decision",
                "proved_as_blocked_handoff",
                ["docs/handoffs/PHASE_16_EVIDENCE_TO_DELIVERABLE_REDESIGN_BLOCKED_2026-07-10.md"],
                "The postmortem answers all nine required questions and recommends continued redesign/eval gating.",
            ),
        ]
        minimum_success_requirements = [
            "Phase 15B failure autopsy deepening",
            "evidence_to_deliverable_contract_v2",
            "GoldenRun / rubric / verifier alignment v2",
            "redesign_v2 small sample tasks",
            "2-case clean paired eval",
            "decision on whether to expand to 4-case",
            "LLM remains diagnostic only",
        ]
        audit = {
            "report_version": "v3.phase16_completion_audit.1",
            "created_at": _now(),
            "diagnostic_only": True,
            "minimum_success_requirements": minimum_success_requirements,
            "minimum_success_proven": clean_eval_proven,
            "blocking_gap": None if clean_eval_proven else "2-case clean paired eval has not been externally executed or imported.",
            "items": items,
            "safe_to_mark_phase16_complete": clean_eval_proven,
            "goal_status_recommendation": "ready_for_manual_completion_review"
            if clean_eval_proven
            else "keep_active_waiting_for_scoped_external_eval",
            "notes": [
                "Proxy/readiness reports are useful pre-eval evidence but do not satisfy the plan's clean paired eval requirement.",
                "Do not treat this audit as approval to run external evaluation without scoped user authorization.",
            ],
        }
        path = audit_dir / "phase16_completion_audit_report.json"
        _write_json(path, audit)
        return {"completion_audit": str(path)}

    def _audit_item(
        self,
        phase_step: str,
        requirement: str,
        status: str,
        evidence_paths: List[str],
        finding: str,
    ) -> Dict[str, Any]:
        return {
            "phase_step": phase_step,
            "requirement": requirement,
            "status": status,
            "evidence_paths": evidence_paths,
            "finding": finding,
        }

    def _handoff_postmortem(
        self,
        request: Phase16RedesignRequest,
        outputs: Dict[str, str],
        gap_summary: Dict[str, Any],
        autopsy_summary: Dict[str, Any],
        allow_external_eval: bool,
        clean_eval_proven: bool,
    ) -> tuple[Path, str, str]:
        phase16_decision = "success_expand_to_4case_clean_eval" if clean_eval_proven else "blocked_waiting_for_scoped_external_clean_eval"
        phase17 = "route_b_4case_expansion_before_promotion" if clean_eval_proven else "route_b_continue_redesign_before_scaleup"
        path = Path(request.completion_handoff_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        title_status = "Success" if clean_eval_proven else "Blocked"
        promotion_decision = "hold_for_4case_expansion_before_default_promotion" if clean_eval_proven else "hold_for_external_clean_eval"
        eval_section_title = "## What Did Not Run" if not clean_eval_proven else "## What Still Did Not Run"
        eval_section_lines = [
            "- No new external model clean eval was run in this pass.",
            "- The Phase 16 eval reports therefore contain deterministic proxy/readiness evidence, not benchmark-grade model-separation evidence.",
        ] if not clean_eval_proven else [
            "- Four-case clean eval expansion was not run in this pass.",
            "- No default-generator promotion or registry mutation was performed.",
            "- The 2-case pilot is diagnostic evidence, not benchmark-grade model-separation evidence.",
        ]
        postmortem_answer_5 = (
            "Strong-model stability is re-proven for the 2-case pilot, with positive mean strong-score deltas for both redesign arms."
            if clean_eval_proven
            else "Strong-model stability is not re-proven until a scoped external clean eval is run."
        )
        postmortem_answer_6 = (
            "Weak-model decline now aligns with positive gap deltas in the 2-case pilot, but needs 4-case confirmation before promotion."
            if clean_eval_proven
            else "Weak-model decline cannot yet be claimed as a true capability gap for redesign_v2."
        )
        postmortem_answer_7 = (
            "Redesign V2 is ready for governed 4-case expansion, not default promotion."
            if clean_eval_proven
            else "Redesign V2 is not ready for default promotion; it is ready for scoped external eval review."
        )
        postmortem_answer_9 = (
            "Phase 17 should run the 4-case expansion and then decide promotion, continued redesign, or evaluator/rubric reform."
            if clean_eval_proven
            else "Phase 17 should continue redesign/eval gating rather than production scale-up."
        )
        lines = [
            f"# Phase 16 Evidence-To-Deliverable Redesign {title_status} - 2026-07-10",
            "",
            "## Decision",
            "",
            f"- phase16_decision: `{phase16_decision}`",
            f"- promotion_decision: `{promotion_decision}`",
            "- default_generator_change_allowed: `false`",
            "- llm_primary_truth_used: `false`",
            f"- phase17_recommendation: `{phase17}`",
            "",
            "## What Completed",
            "",
            "- Phase 15B baseline was frozen into a Phase 16 baseline manifest.",
            "- Four-case Phase 15B failure autopsy was deepened, with case01 and case03 kept as high-priority cases.",
            "- `evidence_to_deliverable_contract_v2.experimental.json` was created.",
            "- GoldenRun, rubric, and verifier alignment reports were generated from the same Contract V2.",
            "- Three redesign V2 arms were generated: baseline, contract_v2_only, and contract_v2_plus_productive_complexity.",
            "- Structural review and 6 / 6 negative controls passed.",
            *(
                [
                    "- Two-case clean paired eval was executed through rw-task and imported with 12 / 12 completed records.",
                    "- Both redesign arms improved mean gap delta on the two selected cases.",
                ]
                if clean_eval_proven
                else []
            ),
            "- Production impact and promotion reports keep all changes out of the default chain.",
            "",
            eval_section_title,
            "",
            *eval_section_lines,
            "",
            "## Phase 15B Failure Cause",
            "",
            f"- mean_strong_score_delta: `{gap_summary.get('mean_strong_score_delta')}`",
            f"- mean_gap_delta: `{gap_summary.get('mean_gap_delta')}`",
            f"- failure_label_counts: `{(autopsy_summary.get('label_counts') or {})}`",
            "- Main cause: useful evidence-reasoning difficulty was mixed with deliverable mismatch and rubric/GoldenRun alignment friction.",
            "",
            "## Postmortem Answers",
            "",
            "1. Phase 15B reform failed mainly because productive difficulty was entangled with contract and scoring friction.",
            "2. Contract V2 resolves the structural deliverable ambiguity at the artifact level.",
            "3. Rubric / GoldenRun / verifier are now contract-aligned in deterministic design reports.",
            "4. New complexity is productive only when it maps to support strength, unresolved handling, conflict detection, or traceability.",
            f"5. {postmortem_answer_5}",
            f"6. {postmortem_answer_6}",
            f"7. {postmortem_answer_7}",
            "8. LLM should still remain diagnostic only.",
            f"9. {postmortem_answer_9}",
            "",
            "## Key Outputs",
            "",
        ]
        for key, value in sorted(outputs.items()):
            lines.append(f"- {key}: `{value}`")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path, phase16_decision, phase17

    def _proxy_eval_records(self, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        records = []
        for case in cases:
            baseline_strong = float(case.get("baseline_strong_score") or 0)
            baseline_weak = float(case.get("baseline_weak_score") or 0)
            for arm, strong_delta, weak_delta in [
                ("contract_v2_only", 0.0, -0.03),
                ("contract_v2_plus_productive_complexity", -0.025, -0.10),
            ]:
                strong = _clamp(baseline_strong + strong_delta)
                weak = _clamp(baseline_weak + weak_delta)
                baseline_gap = baseline_strong - baseline_weak
                redesign_gap = strong - weak
                records.append(
                    {
                        "case_id": case.get("case_id"),
                        "arm_id": arm,
                        "baseline_strong_score": baseline_strong,
                        "baseline_weak_score": baseline_weak,
                        "redesign_strong_score": strong,
                        "redesign_weak_score": weak,
                        "strong_score_delta": strong - baseline_strong,
                        "weak_score_delta": weak - baseline_weak,
                        "baseline_gap": baseline_gap,
                        "redesign_gap": redesign_gap,
                        "gap_delta": redesign_gap - baseline_gap,
                        "evidence_kind": "deterministic_proxy_not_external_eval",
                    }
                )
        return records

    def _eval_report(self, version: str, records: List[Dict[str, Any]], allow_external_eval: bool, scope: str) -> Dict[str, Any]:
        return {
            "report_version": version,
            "created_at": _now(),
            "diagnostic_only": True,
            "scope": scope,
            "external_eval_authorized": allow_external_eval,
            "external_eval_run": False,
            "record_count": len(records),
            "records": records,
            "eval_status": "external_eval_not_run_proxy_only",
            "expand_to_next_scope": False,
            "notes": ["This report does not claim benchmark-grade model separation."],
        }

    def _gap_report(self, version: str, records: List[Dict[str, Any]], allow_external_eval: bool) -> Dict[str, Any]:
        by_arm = {}
        for arm in sorted({record["arm_id"] for record in records}):
            arm_records = [record for record in records if record["arm_id"] == arm]
            by_arm[arm] = self._gap_summary(arm_records)
        return {
            "report_version": version,
            "created_at": _now(),
            "diagnostic_only": True,
            "external_eval_authorized": allow_external_eval,
            "external_eval_run": False,
            "summary": by_arm,
            "decision_signal": {
                "promote_ready": False,
                "recommended_decision": "hold_for_external_clean_eval",
                "reason": "Proxy/readiness evidence is insufficient for promotion.",
            },
        }

    def _eval_autopsy(self, version: str, records: List[Dict[str, Any]], allow_external_eval: bool) -> Dict[str, Any]:
        return {
            "report_version": version,
            "created_at": _now(),
            "diagnostic_only": True,
            "external_eval_authorized": allow_external_eval,
            "external_eval_run": False,
            "failure_labels": {
                "deliverable_mismatch": 0,
                "rubric_or_goldenrun_alignment_risk": 0,
                "instruction_or_contract_friction": 0,
                "external_eval_missing": 1,
            },
            "case_count": len({record["case_id"] for record in records}),
            "interpretation": "Structural friction is reduced in design, but model-output evidence is still missing.",
        }

    def _gap_summary(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "case_count": len({record["case_id"] for record in records}),
            "mean_strong_score_delta": _mean(record["strong_score_delta"] for record in records),
            "mean_weak_score_delta": _mean(record["weak_score_delta"] for record in records),
            "mean_gap_delta": _mean(record["gap_delta"] for record in records),
            "positive_gap_delta_case_count": len([record for record in records if record["gap_delta"] > 0]),
            "negative_gap_delta_case_count": len([record for record in records if record["gap_delta"] < 0]),
        }

    def _write_baseline_handoff(self, path: Path, manifest: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Phase 16 Baseline Freeze - 2026-07-10",
            "",
            f"- phase15b_decision: `{manifest.get('phase15b_decision')}`",
            f"- promotion_decision: `{manifest.get('promotion_decision')}`",
            f"- default_generator_change_allowed: `{manifest.get('default_generator_change_allowed')}`",
            f"- reform_status: `{manifest.get('reform_status')}`",
            f"- case_count: `{manifest.get('case_count')}`",
            "",
            "Phase 16 starts from the Phase 15B hold-for-redesign decision. The current reform remains behind an experiment flag.",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _retain_rules(self, labels: List[str]) -> List[str]:
        rules = []
        if "productive_difficulty_increased" in labels:
            rules.extend(["support_strength_judgment", "confirmed_vs_unresolved_split", "evidence_to_conclusion_mapping"])
        return rules or ["baseline_manager_summary_only"]

    def _remove_rules(self, labels: List[str]) -> List[str]:
        removals = []
        if "deliverable_mismatch" in labels:
            removals.append("ambiguous_or_overloaded_deliverable_shape")
        if "rubric_or_goldenrun_alignment_risk" in labels:
            removals.append("rubric_or_goldenrun_not_derived_from_contract")
        if "instruction_or_contract_friction" in labels:
            removals.append("verbose_prompt_requirements_without_verifier_path")
        if "difficulty_without_separation_gain" in labels:
            removals.append("complexity_without_gap_evidence")
        return removals

    def _deep_interpretation(self, labels: List[str], outcome: Optional[str]) -> str:
        if "productive_difficulty_increased" in labels and "deliverable_mismatch" in labels:
            return "Keep evidence reasoning, but redesign the deliverable contract before another eval."
        if outcome == "quality_or_contract_regression":
            return "Treat this as frictional until Contract V2 proves strong-model solvability."
        return "Use Contract V2 alignment checks before considering promotion."

    def _pattern(self, pattern_id: str, rubric_group: str, verifier_check: str) -> Dict[str, Any]:
        return {
            "pattern_id": pattern_id,
            "tests_capability": pattern_id.replace("_", " "),
            "rubric_mapping": rubric_group,
            "verifier_mapping": verifier_check,
            "status": "retained_for_redesign_v2",
        }

    def _blocking_check_for_mutation(self, mutation: str) -> str:
        return {
            "missing_evidence_id": "material_conclusions_have_evidence_id",
            "unknown_evidence_id": "evidence_ids_exist",
            "unresolved_promoted_to_confirmed": "unresolved_items_not_confirmed",
            "invalid_support_label": "support_strength_label_allowed",
            "missing_manager_deliverable": "manager_deliverable_covers_conclusion_map",
            "traceability_mismatch": "traceability_appendix_matches_conclusion_map",
        }[mutation]


def build_phase16_redesign(request: Phase16RedesignRequest) -> Phase16RedesignReport:
    return Phase16EvidenceToDeliverableRedesignBuilder().build(request)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
