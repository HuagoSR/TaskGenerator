from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_pipeline_b_batch_runner import PipelineBBatchRunReport
from task_generator.v3_source_schema import load_json_file


ObservationConfidence = Literal["low", "medium", "high"]
ObservationStatus = Literal["observed_only"]


class TransitionPriorStoreRequest(BaseModel):
    batch_report_path: str
    store_output_path: str
    report_output_path: str


class TransitionPriorObservation(BaseModel):
    transition_observation_id: str
    case_id: str
    workflow_archetype_id: Optional[str] = None
    motif_type: str
    task_graph_shape: Optional[str] = None
    from_skill_id: str
    to_skill_id: str
    from_role: Optional[str] = None
    to_role: Optional[str] = None
    resource_bridge: str = ""
    source_trace_evidence_count: int = 0
    task_usage_count_increment: int = 1
    outcome: str
    quality_reason_codes: List[str] = Field(default_factory=list)
    verifier_status: Optional[str] = None
    eval_evidence_status: str = "not_run"
    confidence: ObservationConfidence = "low"
    status: ObservationStatus = "observed_only"


class TransitionPriorStoreDiagnostics(BaseModel):
    observation_count: int = 0
    candidate_ready_observation_count: int = 0
    revise_observation_count: int = 0
    reject_observation_count: int = 0
    motif_counts: Dict[str, int] = Field(default_factory=dict)
    role_context_count: int = 0
    source_trace_backed_count: int = 0
    notes: List[str] = Field(default_factory=list)


class TransitionPriorStoreArtifact(BaseModel):
    transition_prior_store_version: str = "v0.observed"
    request: TransitionPriorStoreRequest
    observations: List[TransitionPriorObservation] = Field(default_factory=list)
    diagnostics: TransitionPriorStoreDiagnostics
    notes: List[str] = Field(default_factory=list)


class TransitionPriorStoreBuilder:
    def build(
        self,
        batch_report_path: str | Path,
        store_output_path: str | Path,
        report_output_path: str | Path,
    ) -> TransitionPriorStoreArtifact:
        batch_report = PipelineBBatchRunReport.model_validate(load_json_file(str(batch_report_path)))
        request = TransitionPriorStoreRequest(
            batch_report_path=str(batch_report_path),
            store_output_path=str(store_output_path),
            report_output_path=str(report_output_path),
        )
        observations: List[TransitionPriorObservation] = []
        for case in batch_report.cases:
            if case.status != "completed":
                continue
            case_dir = Path(case.case_dir)
            subgraph_path = case_dir / "subgraph_sampler" / "pipeline_b_subgraph_report.json"
            if not subgraph_path.exists():
                continue
            observations.extend(self._case_observations(case=case.model_dump(), subgraph=load_json_file(str(subgraph_path))))

        diagnostics = self._diagnostics(observations)
        artifact = TransitionPriorStoreArtifact(
            request=request,
            observations=observations,
            diagnostics=diagnostics,
            notes=[
                "TransitionPriorStore V0 is observational only and does not influence sampling.",
                "These observations are intended as future evidence for transition, motif, and role priors after explicit review.",
            ],
        )
        self.write_outputs(artifact, store_output_path=store_output_path, report_output_path=report_output_path)
        return artifact

    def write_outputs(
        self,
        artifact: TransitionPriorStoreArtifact,
        store_output_path: str | Path,
        report_output_path: str | Path,
    ) -> None:
        store_path = Path(store_output_path)
        report_path = Path(report_output_path)
        store_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        report_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")

    def _case_observations(self, case: Dict[str, Any], subgraph: Dict[str, Any]) -> List[TransitionPriorObservation]:
        diagnostics = subgraph.get("diagnostics") or {}
        role_assignments = list(subgraph.get("role_assignments") or [])
        role_map: Dict[str, List[str]] = {}
        for assignment in role_assignments:
            skill_id = assignment.get("selected_skill_id")
            role_name = assignment.get("role_name")
            if not skill_id or not role_name:
                continue
            role_map.setdefault(str(skill_id), []).append(str(role_name))

        observations: List[TransitionPriorObservation] = []
        skill_edges = [
            edge
            for edge in (subgraph.get("subgraph_edges") or [])
            if str(edge.get("from_id") or "").startswith("skill_")
            and str(edge.get("to_id") or "").startswith("skill_")
        ]
        if not skill_edges:
            selected_skill_ids = [item.get("skill_id") for item in (subgraph.get("selected_skills") or []) if item.get("skill_id")]
            for index in range(len(selected_skill_ids) - 1):
                observations.append(
                    self._build_observation(
                        case=case,
                        diagnostics=diagnostics,
                        from_skill_id=str(selected_skill_ids[index]),
                        to_skill_id=str(selected_skill_ids[index + 1]),
                        from_role=self._role_label(role_map.get(str(selected_skill_ids[index]))),
                        to_role=self._role_label(role_map.get(str(selected_skill_ids[index + 1]))),
                        resource_bridge="selected_skill_order_fallback",
                        source_trace_evidence_count=0,
                        confidence="low",
                    )
                )
            return observations

        for edge in skill_edges:
            confidence_value = float(edge.get("confidence") or 0.0)
            observations.append(
                self._build_observation(
                    case=case,
                    diagnostics=diagnostics,
                    from_skill_id=str(edge.get("from_id")),
                    to_skill_id=str(edge.get("to_id")),
                    from_role=self._role_label(role_map.get(str(edge.get("from_id")))),
                    to_role=self._role_label(role_map.get(str(edge.get("to_id")))),
                    resource_bridge=str(edge.get("relation_type") or ""),
                    source_trace_evidence_count=1 if edge.get("evidence_mode") == "local_source_trace" else 0,
                    confidence=self._confidence_label(confidence_value),
                )
            )
        return observations

    def _build_observation(
        self,
        case: Dict[str, Any],
        diagnostics: Dict[str, Any],
        from_skill_id: str,
        to_skill_id: str,
        from_role: Optional[str],
        to_role: Optional[str],
        resource_bridge: str,
        source_trace_evidence_count: int,
        confidence: ObservationConfidence,
    ) -> TransitionPriorObservation:
        case_id = str(case.get("case_id") or "unknown")
        motif = str(case.get("motif") or "unknown")
        obs_id = f"obs_{case_id}_{from_skill_id}_{to_skill_id}"
        return TransitionPriorObservation(
            transition_observation_id=obs_id,
            case_id=case_id,
            workflow_archetype_id=diagnostics.get("workflow_archetype_id"),
            motif_type=motif,
            task_graph_shape=case.get("task_graph_shape_assumption") or diagnostics.get("task_graph_shape_assumption"),
            from_skill_id=from_skill_id,
            to_skill_id=to_skill_id,
            from_role=from_role,
            to_role=to_role,
            resource_bridge=resource_bridge,
            source_trace_evidence_count=source_trace_evidence_count,
            task_usage_count_increment=1,
            outcome=str(case.get("quality_decision") or case.get("status") or "unknown"),
            quality_reason_codes=list(case.get("reason_codes") or []),
            verifier_status=case.get("verifier_status"),
            eval_evidence_status=self._eval_evidence_status(case),
            confidence=confidence,
            status="observed_only",
        )

    def _diagnostics(self, observations: List[TransitionPriorObservation]) -> TransitionPriorStoreDiagnostics:
        motif_counts = Counter(item.motif_type for item in observations)
        outcome_counts = Counter(item.outcome for item in observations)
        return TransitionPriorStoreDiagnostics(
            observation_count=len(observations),
            candidate_ready_observation_count=outcome_counts.get("candidate_ready", 0),
            revise_observation_count=outcome_counts.get("revise", 0),
            reject_observation_count=outcome_counts.get("reject", 0),
            motif_counts=dict(sorted(motif_counts.items())),
            role_context_count=sum(1 for item in observations if item.from_role or item.to_role),
            source_trace_backed_count=sum(1 for item in observations if item.source_trace_evidence_count > 0),
            notes=[
                "Observations are currently derived from completed batch cases and local subgraph reports.",
                "Role context may be sparse when the sampler falls back to unstructured or repeated-role assignments.",
            ],
        )

    def _role_label(self, roles: Optional[List[str]]) -> Optional[str]:
        if not roles:
            return None
        return "|".join(sorted(set(str(item) for item in roles if item)))

    def _confidence_label(self, value: float) -> ObservationConfidence:
        if value >= 0.7:
            return "high"
        if value >= 0.4:
            return "medium"
        return "low"

    def _eval_evidence_status(self, case: Dict[str, Any]) -> str:
        run_status = str(case.get("eval_run_status") or "")
        eval_mode = str(case.get("eval_mode") or "")
        if run_status in {"completed", "summarized"}:
            return "diagnostic_only"
        if eval_mode == "candidate_ready_eval_candidate" and run_status == "dry_run_ready":
            return "not_run"
        if eval_mode == "draft_inspection_only":
            return "diagnostic_only"
        return "not_run"
