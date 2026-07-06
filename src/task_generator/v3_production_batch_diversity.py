from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


class ProductionBatchDiversityRequest(BaseModel):
    production_batch_manifest_path: str
    output_dir: str


class ProductionBatchDiversityCaseSnapshot(BaseModel):
    case_id: str
    motif: str
    blueprint_id: Optional[str] = None
    subgraph_id: Optional[str] = None
    template_family: Optional[str] = None
    deliverable_signature: str = ""
    selected_skill_signature: str = ""
    workflow_context_fit: Optional[str] = None
    real_worldness_score: Optional[float] = None
    difficulty_overall: Optional[float] = None


class DuplicateGroup(BaseModel):
    signature: str
    case_ids: List[str] = Field(default_factory=list)
    count: int = 0


class ProductionBatchDiversitySummary(BaseModel):
    case_count: int = 0
    unique_motif_count: int = 0
    unique_subgraph_count: int = 0
    duplicate_subgraph_count: int = 0
    unique_blueprint_count: int = 0
    duplicate_blueprint_count: int = 0
    unique_template_family_count: int = 0
    unique_deliverable_signature_count: int = 0
    duplicate_deliverable_signature_count: int = 0
    unique_skill_signature_count: int = 0
    duplicate_skill_signature_count: int = 0
    motif_counts: Dict[str, int] = Field(default_factory=dict)
    template_family_counts: Dict[str, int] = Field(default_factory=dict)
    workflow_context_fit_counts: Dict[str, int] = Field(default_factory=dict)


class ProductionBatchDiversityDiagnostics(BaseModel):
    repeated_subgraph_ids: List[DuplicateGroup] = Field(default_factory=list)
    repeated_blueprint_ids: List[DuplicateGroup] = Field(default_factory=list)
    repeated_deliverable_signatures: List[DuplicateGroup] = Field(default_factory=list)
    repeated_skill_signatures: List[DuplicateGroup] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ProductionBatchDiversityReport(BaseModel):
    production_batch_diversity_version: str = "v3.production_batch_diversity.1"
    request: ProductionBatchDiversityRequest
    production_batch_id: str
    case_snapshots: List[ProductionBatchDiversityCaseSnapshot] = Field(default_factory=list)
    summary: ProductionBatchDiversitySummary
    diagnostics: ProductionBatchDiversityDiagnostics
    notes: List[str] = Field(default_factory=list)


class ProductionBatchDiversityBuilder:
    def build(
        self,
        production_batch_manifest_path: str | Path,
        output_dir: str | Path,
    ) -> ProductionBatchDiversityReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = ProductionBatchDiversityRequest(
            production_batch_manifest_path=str(production_batch_manifest_path),
            output_dir=str(output_path),
        )
        manifest = load_json_file(str(production_batch_manifest_path))
        batch_id = str((manifest.get("request") or {}).get("production_batch_id") or "unknown_batch")
        cases = list(manifest.get("cases") or [])
        snapshots = [self._snapshot(case) for case in cases if isinstance(case, dict)]
        summary = self._summary(snapshots)
        diagnostics = self._diagnostics(snapshots, summary)
        report = ProductionBatchDiversityReport(
            request=request,
            production_batch_id=batch_id,
            case_snapshots=snapshots,
            summary=summary,
            diagnostics=diagnostics,
            notes=[
                "Production diversity is a report-only layer over the production batch manifest.",
                "It tracks repeated motifs, subgraphs, blueprints, deliverable signatures, and selected-skill signatures without changing any task state.",
                "Use this report to decide whether a production batch is too concentrated before explicit production QA review.",
            ],
        )
        (output_path / "production_batch_diversity_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _snapshot(self, case: Dict[str, object]) -> ProductionBatchDiversityCaseSnapshot:
        deliverable_signature = self._signature(case.get("deliverable_file_names"))
        selected_skill_signature = self._signature(case.get("selected_skill_ids"))
        return ProductionBatchDiversityCaseSnapshot(
            case_id=str(case.get("case_id") or "unknown_case"),
            motif=str(case.get("motif") or "unknown"),
            blueprint_id=self._optional_str(case.get("blueprint_id")),
            subgraph_id=self._optional_str(case.get("subgraph_id")),
            template_family=self._optional_str(case.get("template_family")),
            deliverable_signature=deliverable_signature,
            selected_skill_signature=selected_skill_signature,
            workflow_context_fit=self._optional_str(case.get("workflow_context_fit")),
            real_worldness_score=self._optional_float(case.get("real_worldness_score")),
            difficulty_overall=self._difficulty_for_case(case),
        )

    def _summary(
        self,
        snapshots: List[ProductionBatchDiversityCaseSnapshot],
    ) -> ProductionBatchDiversitySummary:
        motif_counts = Counter(snapshot.motif for snapshot in snapshots)
        template_counts = Counter(
            snapshot.template_family for snapshot in snapshots if snapshot.template_family
        )
        workflow_counts = Counter(
            snapshot.workflow_context_fit for snapshot in snapshots if snapshot.workflow_context_fit
        )
        subgraph_counts = Counter(
            snapshot.subgraph_id for snapshot in snapshots if snapshot.subgraph_id
        )
        blueprint_counts = Counter(
            snapshot.blueprint_id for snapshot in snapshots if snapshot.blueprint_id
        )
        deliverable_counts = Counter(
            snapshot.deliverable_signature
            for snapshot in snapshots
            if snapshot.deliverable_signature
        )
        skill_counts = Counter(
            snapshot.selected_skill_signature
            for snapshot in snapshots
            if snapshot.selected_skill_signature
        )
        return ProductionBatchDiversitySummary(
            case_count=len(snapshots),
            unique_motif_count=len(motif_counts),
            unique_subgraph_count=len(subgraph_counts),
            duplicate_subgraph_count=sum(1 for count in subgraph_counts.values() if count > 1),
            unique_blueprint_count=len(blueprint_counts),
            duplicate_blueprint_count=sum(1 for count in blueprint_counts.values() if count > 1),
            unique_template_family_count=len(template_counts),
            unique_deliverable_signature_count=len(deliverable_counts),
            duplicate_deliverable_signature_count=sum(1 for count in deliverable_counts.values() if count > 1),
            unique_skill_signature_count=len(skill_counts),
            duplicate_skill_signature_count=sum(1 for count in skill_counts.values() if count > 1),
            motif_counts=dict(sorted(motif_counts.items())),
            template_family_counts=dict(sorted(template_counts.items())),
            workflow_context_fit_counts=dict(sorted(workflow_counts.items())),
        )

    def _diagnostics(
        self,
        snapshots: List[ProductionBatchDiversityCaseSnapshot],
        summary: ProductionBatchDiversitySummary,
    ) -> ProductionBatchDiversityDiagnostics:
        diagnostics = ProductionBatchDiversityDiagnostics(
            repeated_subgraph_ids=self._duplicate_groups(snapshots, "subgraph_id"),
            repeated_blueprint_ids=self._duplicate_groups(snapshots, "blueprint_id"),
            repeated_deliverable_signatures=self._duplicate_groups(snapshots, "deliverable_signature"),
            repeated_skill_signatures=self._duplicate_groups(snapshots, "selected_skill_signature"),
        )
        if summary.case_count >= 3 and summary.unique_motif_count <= 1:
            diagnostics.warnings.append("single_motif_concentration")
        if summary.case_count >= 3 and summary.unique_template_family_count <= 1:
            diagnostics.warnings.append("single_template_family_concentration")
        if summary.case_count >= 3 and summary.unique_deliverable_signature_count <= 1:
            diagnostics.warnings.append("single_deliverable_signature_concentration")
        if summary.duplicate_subgraph_count > 0:
            diagnostics.warnings.append("repeated_subgraph_ids_present")
        if summary.duplicate_skill_signature_count > 0:
            diagnostics.warnings.append("repeated_skill_signatures_present")
        return diagnostics

    def _duplicate_groups(
        self,
        snapshots: List[ProductionBatchDiversityCaseSnapshot],
        field_name: str,
    ) -> List[DuplicateGroup]:
        grouped: Dict[str, List[str]] = defaultdict(list)
        for snapshot in snapshots:
            value = getattr(snapshot, field_name)
            if not value:
                continue
            grouped[str(value)].append(snapshot.case_id)
        duplicates = [
            DuplicateGroup(signature=signature, case_ids=case_ids, count=len(case_ids))
            for signature, case_ids in grouped.items()
            if len(case_ids) > 1
        ]
        duplicates.sort(key=lambda item: (-item.count, item.signature))
        return duplicates

    def _difficulty_for_case(self, case: Dict[str, object]) -> Optional[float]:
        value = case.get("difficulty_overall")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _signature(self, value: object) -> str:
        if not isinstance(value, list):
            return ""
        normalized = sorted(str(item) for item in value)
        return " | ".join(normalized)

    def _optional_str(self, value: object) -> Optional[str]:
        if value is None:
            return None
        return str(value)

    def _optional_float(self, value: object) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        return None
