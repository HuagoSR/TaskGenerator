import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_pipeline_b_package_assembler import PipelineBPackageAssembler
from task_generator.v3_pipeline_b_prototype import DEFAULT_MOTIF_PRIORITY, PipelineBPrototypeBuilder
from task_generator.v3_pipeline_b_quality_gate import PipelineBQualityGate
from task_generator.v3_pipeline_b_sampler import PipelineBSubgraphSampler
from task_generator.v3_reference_file_generator import ReferenceFileGenerator
from task_generator.v3_reference_file_planner import ReferenceFilePlanner
from task_generator.v3_rubric_builder import RubricBuilder
from task_generator.v3_rw_task_eval_prep import (
    DEFAULT_REAL_WORLD_TASK_PYTHON,
    DEFAULT_RW_TASK_ROOT,
    RwTaskEvalPrep,
)
from task_generator.v3_rw_task_eval_runner import RwTaskEvalRunner
from task_generator.v3_rw_task_export_validator import RwTaskExportValidator
from task_generator.v3_rw_task_exporter import PipelineBRwTaskExporter
from task_generator.v3_teacher_input_builder import TeacherInputBuilder
from task_generator.v3_teacher_runner import TeacherRunner
from task_generator.v3_training_annotation_builder import TrainingAnnotationBuilder


BatchCaseStatus = Literal["completed", "failed"]


class PipelineBBatchRunRequest(BaseModel):
    registry_path: str
    seed_report_path: str
    output_dir: str
    motifs: List[str] = Field(default_factory=list)
    skill_count: int = 4
    max_cases: int = 3
    allow_caution: bool = False
    model: str = "gpt-5.4-pro"
    workers: int = 1
    rw_task_root: str = str(DEFAULT_RW_TASK_ROOT)
    python_exe: str = str(DEFAULT_REAL_WORLD_TASK_PYTHON)


class PipelineBBatchCaseSummary(BaseModel):
    case_index: int
    case_id: str
    case_dir: str
    status: BatchCaseStatus
    motif: str
    subgraph_id: Optional[str] = None
    subgraph_confidence: Optional[str] = None
    selected_skill_count: int = 0
    blueprint_id: Optional[str] = None
    quality_decision: Optional[str] = None
    package_readiness: Optional[str] = None
    export_decision: Optional[str] = None
    validation_status: Optional[str] = None
    eval_prep_status: Optional[str] = None
    eval_mode: Optional[str] = None
    eval_run_status: Optional[str] = None
    reason_codes: List[str] = Field(default_factory=list)
    warning_reason_codes: List[str] = Field(default_factory=list)
    error_type: Optional[str] = None
    error_message: Optional[str] = None


class PipelineBBatchDiagnostics(BaseModel):
    case_count: int = 0
    completed_case_count: int = 0
    failed_case_count: int = 0
    unique_subgraph_count: int = 0
    duplicate_subgraph_count: int = 0
    status_counts: Dict[str, int] = Field(default_factory=dict)
    quality_decision_counts: Dict[str, int] = Field(default_factory=dict)
    package_readiness_counts: Dict[str, int] = Field(default_factory=dict)
    subgraph_confidence_counts: Dict[str, int] = Field(default_factory=dict)
    reason_code_counts: Dict[str, int] = Field(default_factory=dict)
    repeated_reason_codes: List[str] = Field(default_factory=list)
    repeated_subgraph_ids: List[str] = Field(default_factory=list)
    batch_warnings: List[str] = Field(default_factory=list)


class PipelineBBatchRunReport(BaseModel):
    batch_runner_version: str = "v3.pipeline_b_batch_runner.1"
    request: PipelineBBatchRunRequest
    cases: List[PipelineBBatchCaseSummary] = Field(default_factory=list)
    diagnostics: PipelineBBatchDiagnostics
    notes: List[str] = Field(default_factory=list)


class PipelineBBatchRunner:
    """Run a small deterministic Pipeline B batch smoke without external evaluation."""

    def run(
        self,
        registry_path: str | Path,
        seed_report_path: str | Path,
        output_dir: str | Path,
        motifs: Optional[List[str]] = None,
        skill_count: int = 4,
        max_cases: int = 3,
        allow_caution: bool = False,
        model: str = "gpt-5.4-pro",
        workers: int = 1,
        rw_task_root: str | Path = DEFAULT_RW_TASK_ROOT,
        python_exe: str | Path = DEFAULT_REAL_WORLD_TASK_PYTHON,
    ) -> PipelineBBatchRunReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        selected_motifs = self._motifs(motifs, max_cases)
        request = PipelineBBatchRunRequest(
            registry_path=str(registry_path),
            seed_report_path=str(seed_report_path),
            output_dir=str(output_path),
            motifs=selected_motifs,
            skill_count=skill_count,
            max_cases=max_cases,
            allow_caution=allow_caution,
            model=model,
            workers=workers,
            rw_task_root=str(rw_task_root),
            python_exe=str(python_exe),
        )

        cases: List[PipelineBBatchCaseSummary] = []
        for index, motif in enumerate(selected_motifs, start=1):
            case_id = f"pipeline_b_batch_{index:02d}_{self._slug(motif)}"
            case_dir = output_path / case_id
            try:
                cases.append(
                    self._run_case(
                        case_index=index,
                        case_id=case_id,
                        case_dir=case_dir,
                        motif=motif,
                        registry_path=registry_path,
                        seed_report_path=seed_report_path,
                        skill_count=skill_count,
                        allow_caution=allow_caution,
                        model=model,
                        workers=workers,
                        rw_task_root=rw_task_root,
                        python_exe=python_exe,
                    )
                )
            except Exception as exc:
                cases.append(
                    PipelineBBatchCaseSummary(
                        case_index=index,
                        case_id=case_id,
                        case_dir=str(case_dir),
                        status="failed",
                        motif=motif,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )

        report = PipelineBBatchRunReport(
            request=request,
            cases=cases,
            diagnostics=self._diagnostics(cases),
            notes=[
                "This batch runner is deterministic and report-first.",
                "It does not call LLMs, external APIs, Stirrup, or real rw-task evaluation.",
                "Draft revise-only exports are generated only for local structure inspection.",
                "Single-case feedback should remain diagnostic; repeated batch-level reason codes should drive priorities.",
            ],
        )
        self.write_report(report, output_path / "pipeline_b_batch_report.json")
        return report

    def write_report(self, report: PipelineBBatchRunReport, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def _run_case(
        self,
        case_index: int,
        case_id: str,
        case_dir: Path,
        motif: str,
        registry_path: str | Path,
        seed_report_path: str | Path,
        skill_count: int,
        allow_caution: bool,
        model: str,
        workers: int,
        rw_task_root: str | Path,
        python_exe: str | Path,
    ) -> PipelineBBatchCaseSummary:
        subgraph_dir = case_dir / "subgraph_sampler"
        prototype_dir = case_dir / "prototype"
        reference_plan_dir = case_dir / "reference_file_plan"
        reference_generation_dir = case_dir / "reference_file_generation"
        teacher_input_dir = case_dir / "teacher_input"
        teacher_runner_dir = case_dir / "teacher_runner"
        annotation_dir = case_dir / "training_annotation"
        rubric_dir = case_dir / "rubric"
        quality_dir = case_dir / "quality_gate"
        package_dir = case_dir / "package"
        export_dir = case_dir / "rw_task_export"
        eval_input_dir = case_dir / "rw_task_eval_input"
        eval_run_dir = case_dir / "rw_task_eval_run_dry"

        sampler = PipelineBSubgraphSampler()
        subgraph = sampler.build_subgraph(
            registry_path=registry_path,
            seed_report_path=seed_report_path,
            motif=motif,
            skill_count=skill_count,
            allow_caution=allow_caution,
        )
        sampler.write_outputs(subgraph, subgraph_dir)
        subgraph_report_path = subgraph_dir / "pipeline_b_subgraph_report.json"
        pipeline_a_feedback_path = subgraph_dir / "pipeline_a_feedback.json"

        prototype = PipelineBPrototypeBuilder()
        prototype_report = prototype.build_report_from_subgraph_report(
            subgraph_report_path=subgraph_report_path,
            registry_path=registry_path,
        )
        prototype.write_outputs(prototype_report, prototype_dir)
        blueprint_path = prototype_dir / "draft_task_blueprint.json"
        prototype_report_path = prototype_dir / "pipeline_b_prototype_report.json"

        planner = ReferenceFilePlanner()
        plan = planner.build_plan(
            blueprint_path=blueprint_path,
            subgraph_report_path=subgraph_report_path,
        )
        planner.write_outputs(plan, reference_plan_dir)
        reference_plan_path = reference_plan_dir / "reference_file_plan.json"

        generator = ReferenceFileGenerator()
        generated_manifest = generator.build_from_plan(
            reference_file_plan_path=reference_plan_path,
            output_dir=reference_generation_dir,
        )
        generated_manifest_path = reference_generation_dir / "generated_file_manifest.json"

        teacher_input_builder = TeacherInputBuilder()
        teacher_manifest, teacher_validation = teacher_input_builder.build(
            blueprint_path=blueprint_path,
            subgraph_report_path=subgraph_report_path,
            reference_file_plan_path=reference_plan_path,
            generated_file_manifest_path=generated_manifest_path,
            pipeline_a_feedback_path=pipeline_a_feedback_path,
            prototype_report_path=prototype_report_path,
        )
        teacher_input_builder.write_outputs(teacher_manifest, teacher_validation, teacher_input_dir)
        teacher_manifest_path = teacher_input_dir / "teacher_input_manifest.json"
        teacher_validation_path = teacher_input_dir / "teacher_input_validation_report.json"

        teacher_runner = TeacherRunner()
        golden_run, teacher_report = teacher_runner.build(
            teacher_input_manifest_path=teacher_manifest_path,
            teacher_input_validation_report_path=teacher_validation_path,
        )
        teacher_runner.write_outputs(golden_run, teacher_report, teacher_runner_dir)
        golden_run_path = teacher_runner_dir / "golden_run.json"
        teacher_report_path = teacher_runner_dir / "teacher_runner_report.json"

        annotation_builder = TrainingAnnotationBuilder()
        annotation, annotation_report = annotation_builder.build(
            golden_run_path=golden_run_path,
            teacher_runner_report_path=teacher_report_path,
            teacher_input_manifest_path=teacher_manifest_path,
        )
        annotation_builder.write_outputs(annotation, annotation_report, annotation_dir)
        annotation_path = annotation_dir / "training_annotation.json"
        annotation_report_path = annotation_dir / "training_annotation_report.json"

        rubric_builder = RubricBuilder()
        rubric, rubric_report = rubric_builder.build(
            training_annotation_path=annotation_path,
            training_annotation_report_path=annotation_report_path,
            golden_run_path=golden_run_path,
            teacher_runner_report_path=teacher_report_path,
        )
        rubric_builder.write_outputs(rubric, rubric_report, rubric_dir)
        rubric_path = rubric_dir / "rubric.json"
        rubric_report_path = rubric_dir / "rubric_report.json"

        quality_gate = PipelineBQualityGate()
        quality_report = quality_gate.build(
            generated_file_manifest_path=generated_manifest_path,
            teacher_input_validation_report_path=teacher_validation_path,
            teacher_runner_report_path=teacher_report_path,
            training_annotation_report_path=annotation_report_path,
            rubric_report_path=rubric_report_path,
        )
        quality_gate.write_outputs(quality_report, quality_dir)
        quality_report_path = quality_dir / "pipeline_b_quality_report.json"

        package_assembler = PipelineBPackageAssembler()
        package_manifest = package_assembler.build(
            blueprint_path=blueprint_path,
            generated_file_manifest_path=generated_manifest_path,
            teacher_input_manifest_path=teacher_manifest_path,
            teacher_input_validation_report_path=teacher_validation_path,
            golden_run_path=golden_run_path,
            teacher_runner_report_path=teacher_report_path,
            training_annotation_path=annotation_path,
            training_annotation_report_path=annotation_report_path,
            rubric_path=rubric_path,
            rubric_report_path=rubric_report_path,
            quality_report_path=quality_report_path,
            output_dir=package_dir,
        )
        package_manifest_path = package_dir / "package_manifest.json"

        exporter = PipelineBRwTaskExporter()
        export_report = exporter.export(
            package_manifest_path=package_manifest_path,
            output_dir=export_dir,
            case_id=case_id,
            allow_revise_only=True,
        )

        validator = RwTaskExportValidator()
        validation_report = validator.validate(case_dir=export_dir)
        validation_report_path = export_dir / "rw_task_export_validation_report.json"

        eval_prep = RwTaskEvalPrep()
        prep_report = eval_prep.prepare(
            case_dir=export_dir,
            validation_report_path=validation_report_path,
            eval_input_dir=eval_input_dir,
            model=model,
            workers=workers,
            rw_task_root=rw_task_root,
            python_exe=python_exe,
            overwrite=True,
        )
        prep_report_path = eval_input_dir / "rw_task_eval_prep_report.json"

        eval_runner = RwTaskEvalRunner()
        eval_run_report = eval_runner.run(
            prep_report_path=prep_report_path,
            output_dir=eval_run_dir,
            run_eval=False,
            allow_draft_eval=False,
            command_timeout_seconds=0,
        )

        reason_codes = self._merged_reason_codes(
            quality_report.decision.reason_codes,
            export_report.reason_codes,
            prep_report.warnings,
            eval_run_report.warnings,
        )
        warning_reason_codes = self._merged_reason_codes(
            teacher_manifest.diagnostics.warning_reason_codes,
            teacher_report.diagnostics.warning_reason_codes,
            annotation_report.diagnostics.warning_reason_codes,
            rubric_report.diagnostics.warning_reason_codes,
            package_manifest.diagnostics.warning_reason_codes,
        )

        return PipelineBBatchCaseSummary(
            case_index=case_index,
            case_id=case_id,
            case_dir=str(case_dir),
            status="completed",
            motif=motif,
            subgraph_id=subgraph.subgraph_id,
            subgraph_confidence=subgraph.diagnostics.confidence,
            selected_skill_count=len(subgraph.selected_skills),
            blueprint_id=quality_report.blueprint_id,
            quality_decision=quality_report.decision.decision,
            package_readiness=package_manifest.package_readiness,
            export_decision=export_report.export_decision,
            validation_status=validation_report.validation_status,
            eval_prep_status=prep_report.prep_status,
            eval_mode=prep_report.evaluation_mode,
            eval_run_status=eval_run_report.run_status,
            reason_codes=reason_codes,
            warning_reason_codes=warning_reason_codes,
        )

    def _diagnostics(self, cases: List[PipelineBBatchCaseSummary]) -> PipelineBBatchDiagnostics:
        status_counts = Counter(case.status for case in cases)
        quality_counts = Counter(case.quality_decision for case in cases if case.quality_decision)
        readiness_counts = Counter(case.package_readiness for case in cases if case.package_readiness)
        confidence_counts = Counter(case.subgraph_confidence for case in cases if case.subgraph_confidence)
        reason_counts = Counter(code for case in cases for code in case.reason_codes + case.warning_reason_codes)
        subgraph_counts = Counter(case.subgraph_id for case in cases if case.subgraph_id)
        repeated_subgraphs = sorted([subgraph_id for subgraph_id, count in subgraph_counts.items() if count > 1])
        batch_warnings: List[str] = []
        if repeated_subgraphs:
            batch_warnings.append("duplicate_subgraph_ids")
        if len(set(case.motif for case in cases)) < len(cases):
            batch_warnings.append("motif_diversity_below_case_count")
        if any(case.status == "failed" for case in cases):
            batch_warnings.append("case_failures_present")
        if not cases:
            batch_warnings.append("empty_batch")

        return PipelineBBatchDiagnostics(
            case_count=len(cases),
            completed_case_count=status_counts.get("completed", 0),
            failed_case_count=status_counts.get("failed", 0),
            unique_subgraph_count=len(subgraph_counts),
            duplicate_subgraph_count=sum(count - 1 for count in subgraph_counts.values() if count > 1),
            status_counts=dict(sorted(status_counts.items())),
            quality_decision_counts=dict(sorted(quality_counts.items())),
            package_readiness_counts=dict(sorted(readiness_counts.items())),
            subgraph_confidence_counts=dict(sorted(confidence_counts.items())),
            reason_code_counts=dict(sorted(reason_counts.items())),
            repeated_reason_codes=sorted([code for code, count in reason_counts.items() if count > 1]),
            repeated_subgraph_ids=repeated_subgraphs,
            batch_warnings=batch_warnings,
        )

    def _motifs(self, motifs: Optional[List[str]], max_cases: int) -> List[str]:
        source = [motif for motif in (motifs or DEFAULT_MOTIF_PRIORITY) if motif]
        if not source:
            source = list(DEFAULT_MOTIF_PRIORITY)
        selected: List[str] = []
        while len(selected) < max_cases:
            selected.append(source[len(selected) % len(source)])
        return selected[:max_cases]

    def _merged_reason_codes(self, *groups: List[str]) -> List[str]:
        codes = []
        for group in groups:
            codes.extend(group or [])
        return sorted(set(codes))

    def _slug(self, value: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_") or "case"


def write_batch_report(report: PipelineBBatchRunReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
