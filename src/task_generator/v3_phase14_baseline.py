from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Field

from task_generator.v3_gdpval_local_mirror import GDPValLocalMirrorBuilder, GDPValLocalMirrorManifest
from task_generator.v3_gdpval_subset_selector import (
    GDPValSubsetManifest,
    GDPValSubsetSelectionReport,
    GDPValSubsetSelector,
)
from task_generator.v3_source_schema import load_json_file


DEFAULT_RELEASE_MANIFEST = Path(
    "artifacts/releases/finance_audit_mvp_v0_1_pilot8_diversity_final_reviewed_strict/release_manifest.json"
)


class Phase14BaselineRequest(BaseModel):
    output_root: str
    docs_scope_path: str
    handoff_path: str
    release_manifest_paths: List[str] = Field(default_factory=list)
    target_subset_count: int = 10
    allow_network: bool = False
    mirror_limit: int = 0
    include_rubrics: bool = True


class Phase14GeneratedBaselineRecord(BaseModel):
    release_manifest_path: str
    release_id: str
    task_count: int
    source_production_batch_id: str
    intended_use: List[str] = Field(default_factory=list)
    not_benchmark_grade: bool = True


class Phase14BaselineManifest(BaseModel):
    phase14_baseline_manifest_version: str = "v3.phase14_baseline.1"
    request: Phase14BaselineRequest
    created_at: str
    phase_scope: str = "14.0-14.2"
    gdpval_use: str = "eval_calibration_only"
    generated_task_use: str = "generated_training_candidate"
    llm_mode: str = "shadow_or_candidate_diagnostics_only"
    scope_in: List[str] = Field(default_factory=list)
    scope_out: List[str] = Field(default_factory=list)
    generated_release_baselines: List[Phase14GeneratedBaselineRecord] = Field(default_factory=list)
    mirror_manifest_path: str = ""
    subset_manifest_path: str = ""
    subset_report_path: str = ""
    notes: List[str] = Field(default_factory=list)


class Phase14BaselineArtifact(BaseModel):
    baseline_manifest_path: str
    scope_doc_path: str
    handoff_path: str
    baseline_manifest: Phase14BaselineManifest
    mirror_manifest: GDPValLocalMirrorManifest
    subset_manifest: GDPValSubsetManifest
    subset_report: GDPValSubsetSelectionReport


class Phase14BaselineBuilder:
    def build(
        self,
        *,
        output_root: str | Path,
        release_manifest_paths: List[str | Path] | None = None,
        target_subset_count: int = 10,
        allow_network: bool = False,
        mirror_limit: int = 0,
        include_rubrics: bool = True,
        docs_scope_path: str | Path | None = None,
        handoff_path: str | Path | None = None,
    ) -> Phase14BaselineArtifact:
        root = Path(output_root)
        baseline_dir = root / "baseline"
        mirror_dir = root / "gdpval_local_mirror"
        subset_dir = root / "gdpval_subset"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        release_paths = [Path(path) for path in (release_manifest_paths or [DEFAULT_RELEASE_MANIFEST])]
        request = Phase14BaselineRequest(
            output_root=str(root),
            docs_scope_path=str(docs_scope_path or Path("docs/architecture/phase_14_scope.md")),
            handoff_path=str(handoff_path or Path(f"docs/handoffs/PHASE_14_BASELINE_{date.today().isoformat()}.md")),
            release_manifest_paths=[str(path) for path in release_paths],
            target_subset_count=target_subset_count,
            allow_network=allow_network,
            mirror_limit=mirror_limit,
            include_rubrics=include_rubrics,
        )

        generated_records = [self._load_release_baseline(path) for path in release_paths]
        mirror_manifest = GDPValLocalMirrorBuilder().build(
            output_dir=mirror_dir,
            allow_network=allow_network,
            limit=mirror_limit,
            include_rubrics=include_rubrics,
        )
        subset_manifest, subset_report = GDPValSubsetSelector().build(
            mirror_manifest_path=mirror_dir / "dataset_manifest.json",
            output_dir=subset_dir,
            target_count=target_subset_count,
        )

        baseline_manifest = Phase14BaselineManifest(
            request=request,
            created_at=datetime.now(timezone.utc).isoformat(),
            scope_in=[
                "GDPVal finance/audit/accounting/compliance-like calibration subset",
                "Current TaskGenerator finance/audit reviewed release tasks",
                "Current deterministic production pipeline and rw-task diagnostic path",
                "LLM shadow and candidate diagnostics only",
            ],
            scope_out=[
                "Rewriting GDPVal into training tasks",
                "Running all GDPVal tasks as a single first-pass campaign",
                "Benchmark-grade model separation claims",
                "LLM primary task generation or primary rubric truth",
                "UCB or bandit-driven sampler changes",
                "Cross-domain expansion and new file ecosystems",
            ],
            generated_release_baselines=generated_records,
            mirror_manifest_path=str(mirror_dir / "dataset_manifest.json"),
            subset_manifest_path=str(subset_dir / "gdpval_finance_audit_subset_manifest.json"),
            subset_report_path=str(subset_dir / "gdpval_subset_selection_report.json"),
            notes=[
                "Phase 14 baseline fixes the evaluation/training boundary before GDPVal anatomy, profiler, or LLM shadow work starts.",
                "GDPVal artifacts remain isolated under artifacts/phase14 and must not flow into TaskGenerator training generation.",
                "Generated release tasks remain the comparison baseline for later generated-vs-GDPVal analysis.",
            ],
        )

        scope_doc = Path(request.docs_scope_path)
        handoff_doc = Path(request.handoff_path)
        self._write_scope_doc(scope_doc, baseline_manifest)
        self._write_handoff_doc(handoff_doc, baseline_manifest, mirror_manifest, subset_manifest)

        baseline_manifest_path = baseline_dir / "phase14_baseline_manifest.json"
        baseline_manifest_path.write_text(baseline_manifest.model_dump_json(indent=2), encoding="utf-8")
        return Phase14BaselineArtifact(
            baseline_manifest_path=str(baseline_manifest_path),
            scope_doc_path=str(scope_doc),
            handoff_path=str(handoff_doc),
            baseline_manifest=baseline_manifest,
            mirror_manifest=mirror_manifest,
            subset_manifest=subset_manifest,
            subset_report=subset_report,
        )

    def _load_release_baseline(self, path: Path) -> Phase14GeneratedBaselineRecord:
        payload = load_json_file(str(path))
        return Phase14GeneratedBaselineRecord(
            release_manifest_path=str(path),
            release_id=str(payload.get("release_id") or ""),
            task_count=int(payload.get("task_count") or 0),
            source_production_batch_id=str(payload.get("source_production_batch_id") or ""),
            intended_use=[str(item) for item in payload.get("intended_use") or []],
            not_benchmark_grade=bool(payload.get("not_benchmark_grade", True)),
        )

    def _write_scope_doc(self, path: Path, manifest: Phase14BaselineManifest) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Phase 14 Scope",
            "",
            "## Purpose",
            "",
            "Phase 14 establishes the calibration boundary for GDPVal and the first comparison baseline for TaskGenerator generated tasks.",
            "",
            "## Fixed Uses",
            "",
            f"- GDPVal mirror use: `{manifest.gdpval_use}`",
            f"- Generated release use: `{manifest.generated_task_use}`",
            f"- LLM mode: `{manifest.llm_mode}`",
            "",
            "## In Scope",
            "",
        ]
        lines.extend(f"- {item}" for item in manifest.scope_in)
        lines.extend(
            [
                "",
                "## Out Of Scope",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in manifest.scope_out)
        lines.extend(
            [
                "",
                "## Baseline Comparison Assets",
                "",
            ]
        )
        for record in manifest.generated_release_baselines:
            lines.append(
                f"- `{record.release_id}` from `{record.source_production_batch_id}` with `{record.task_count}` tasks"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_handoff_doc(
        self,
        path: Path,
        baseline_manifest: Phase14BaselineManifest,
        mirror_manifest: GDPValLocalMirrorManifest,
        subset_manifest: GDPValSubsetManifest,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# Phase 14 Baseline - {date.today().isoformat()}",
            "",
            "## What Was Frozen",
            "",
            f"- GDPVal use: `{baseline_manifest.gdpval_use}`",
            f"- Generated task use: `{baseline_manifest.generated_task_use}`",
            f"- LLM mode: `{baseline_manifest.llm_mode}`",
            "",
            "## Mirror",
            "",
            f"- mirrored task count: `{mirror_manifest.task_count}`",
            f"- mirrored reference file count: `{mirror_manifest.mirrored_reference_file_count}`",
            f"- mirror manifest: `{baseline_manifest.mirror_manifest_path}`",
            "",
            "## Initial Calibration Subset",
            "",
            f"- selected task count: `{subset_manifest.selected_count}`",
            f"- selected task ids: `{', '.join(subset_manifest.selected_task_ids)}`",
            f"- subset manifest: `{baseline_manifest.subset_manifest_path}`",
            "",
            "## Comparison Baseline",
            "",
        ]
        for record in baseline_manifest.generated_release_baselines:
            lines.append(
                f"- `{record.release_id}` with `{record.task_count}` tasks from `{record.source_production_batch_id}`"
            )
        lines.append("")
        lines.append("## Notes")
        lines.append("")
        lines.extend(f"- {note}" for note in baseline_manifest.notes)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
