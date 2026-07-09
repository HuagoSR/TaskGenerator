from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


BundleStatus = Literal["ready_for_permitted_environment", "blocked"]


class Phase15PermittedEvalBundleRequest(BaseModel):
    runbook_path: str
    results_template_path: str
    output_dir: str
    bundle_name: str = "phase15_first_pair_gpt4omini_permitted_eval_bundle"
    python_executable_hint: str = "D:\\miniconda3\\envs\\real-world-task\\python.exe"
    create_zip: bool = True


class Phase15BundledItem(BaseModel):
    item_id: str
    arm_id: str
    case_id: str
    model: str
    source_eval_input_dir: str
    bundled_eval_input_dir: str
    bundled_result_dir: str
    bundled_grade_dir: str
    file_count: int
    byte_count: int


class Phase15PermittedEvalBundleReport(BaseModel):
    report_version: str = "v3.phase15_permitted_eval_bundle.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15PermittedEvalBundleRequest
    bundle_status: BundleStatus
    bundle_dir: str
    zip_path: str | None = None
    item_count: int = 0
    bundled_items: List[Phase15BundledItem] = Field(default_factory=list)
    generated_files: Dict[str, str] = Field(default_factory=dict)
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15PermittedEvalBundleBuilder:
    """Build a portable local bundle for running the Phase 15 first eval pair elsewhere."""

    def build(self, request: Phase15PermittedEvalBundleRequest) -> Phase15PermittedEvalBundleReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        bundle_dir = output_dir / request.bundle_name
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        bundle_dir.mkdir(parents=True, exist_ok=True)

        runbook = self._load_json(Path(request.runbook_path))
        template = self._load_json(Path(request.results_template_path))
        items = [item for item in runbook.get("items") or [] if isinstance(item, dict)]

        blocking_reasons = self._validate_inputs(items, Path(request.results_template_path), template)
        bundled_items: List[Phase15BundledItem] = []
        generated_files: Dict[str, str] = {}
        warnings: List[str] = []

        if not blocking_reasons:
            eval_inputs_root = bundle_dir / "eval_inputs"
            for index, item in enumerate(items, start=1):
                bundled_items.append(self._copy_item(index, item, eval_inputs_root))
            generated_files = self._write_bundle_files(bundle_dir, request, runbook, template, bundled_items)
            if request.create_zip:
                zip_path = output_dir / f"{request.bundle_name}.zip"
                if zip_path.exists():
                    zip_path.unlink()
                self._zip_dir(bundle_dir, zip_path)
                generated_files["zip"] = str(zip_path)
            else:
                zip_path = None
        else:
            zip_path = None

        report = Phase15PermittedEvalBundleReport(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            bundle_status="blocked" if blocking_reasons else "ready_for_permitted_environment",
            bundle_dir=str(bundle_dir),
            zip_path=str(zip_path) if zip_path else None,
            item_count=len(bundled_items),
            bundled_items=bundled_items,
            generated_files=generated_files,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            notes=[
                "This builder only creates a local portable bundle; it does not call external APIs.",
                "The bundle intentionally excludes .env, API key files, provider logs, and generated model outputs.",
                "Run the bundled script only in an environment permitted to send this task package to external model/API services.",
                "Execute one item at a time; the generated script stops immediately if an item fails.",
            ],
        )
        (output_dir / "phase15_permitted_eval_bundle_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _load_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists() or path.is_dir():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _validate_inputs(
        self,
        items: List[Dict[str, Any]],
        template_path: Path,
        template: Dict[str, Any],
    ) -> List[str]:
        blockers: List[str] = []
        if len(items) != 2:
            blockers.append("runbook_must_contain_exactly_first_pair_two_items")
        arms = {str(item.get("arm_id")) for item in items}
        if arms != {"baseline_deterministic", "generator_reform_only"}:
            blockers.append("runbook_first_pair_arms_not_matched")
        models = {str(item.get("model")) for item in items}
        cases = {str(item.get("case_id")) for item in items}
        if len(models) != 1 or "gpt-4o-mini" not in models:
            blockers.append("runbook_model_must_be_gpt_4o_mini_for_first_pair_bundle")
        if len(cases) != 1 or "pipeline_b_batch_01_evidence_to_deliverable" not in cases:
            blockers.append("runbook_case_must_be_first_evidence_to_deliverable_case")
        if not template_path.exists() or not template:
            blockers.append("external_eval_results_template_missing")
        for item in items:
            eval_input_dir = Path(str(item.get("eval_input_dir") or ""))
            prep_report = Path(str(item.get("prep_report_path") or ""))
            if not eval_input_dir.exists() or not eval_input_dir.is_dir():
                blockers.append(f"eval_input_dir_missing:{item.get('item_id')}")
            if not prep_report.exists() or not prep_report.is_file():
                blockers.append(f"prep_report_missing:{item.get('item_id')}")
        return sorted(set(blockers))

    def _copy_item(self, index: int, item: Dict[str, Any], eval_inputs_root: Path) -> Phase15BundledItem:
        source_dir = Path(str(item["eval_input_dir"]))
        item_dir_name = f"{index:02d}_{item['arm_id']}__{item['case_id']}__{str(item['model']).replace('-', '_')}"
        target_dir = eval_inputs_root / item_dir_name
        shutil.copytree(source_dir, target_dir)
        file_count, byte_count = self._dir_stats(target_dir)
        return Phase15BundledItem(
            item_id=str(item["item_id"]),
            arm_id=str(item["arm_id"]),
            case_id=str(item["case_id"]),
            model=str(item["model"]),
            source_eval_input_dir=str(source_dir),
            bundled_eval_input_dir=str(target_dir.relative_to(eval_inputs_root.parents[0])),
            bundled_result_dir=str((Path("results") / item_dir_name).as_posix()),
            bundled_grade_dir=str((Path("grades") / item_dir_name).as_posix()),
            file_count=file_count,
            byte_count=byte_count,
        )

    def _write_bundle_files(
        self,
        bundle_dir: Path,
        request: Phase15PermittedEvalBundleRequest,
        runbook: Dict[str, Any],
        template: Dict[str, Any],
        bundled_items: List[Phase15BundledItem],
    ) -> Dict[str, str]:
        runbook_path = bundle_dir / "phase15_external_eval_runbook.json"
        template_path = bundle_dir / "phase15_external_eval_results_template.json"
        script_path = bundle_dir / "run_phase15_first_pair_permitted_eval.ps1"
        readme_path = bundle_dir / "README_PHASE15_PERMITTED_EVAL.md"
        checksums_path = bundle_dir / "checksums.sha256.json"

        portable_runbook = dict(runbook)
        portable_runbook["portable_bundle"] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "bundle_items": [item.model_dump() for item in bundled_items],
            "python_executable_hint": request.python_executable_hint,
        }
        runbook_path.write_text(json.dumps(portable_runbook, ensure_ascii=False, indent=2), encoding="utf-8")
        template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        script_path.write_text(self._script_text(request, bundled_items), encoding="utf-8")
        readme_path.write_text(self._readme_text(bundled_items), encoding="utf-8")
        checksums_path.write_text(
            json.dumps(self._checksums(bundle_dir), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "portable_runbook": str(runbook_path),
            "results_template": str(template_path),
            "powershell_script": str(script_path),
            "readme": str(readme_path),
            "checksums": str(checksums_path),
        }

    def _script_text(self, request: Phase15PermittedEvalBundleRequest, bundled_items: List[Phase15BundledItem]) -> str:
        lines = [
            "$ErrorActionPreference = 'Stop'",
            f"$PythonExe = '{request.python_executable_hint}'",
            "$BundleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path",
            "$ResultsRoot = Join-Path $BundleRoot 'results'",
            "$GradesRoot = Join-Path $BundleRoot 'grades'",
            "New-Item -ItemType Directory -Force -Path $ResultsRoot | Out-Null",
            "New-Item -ItemType Directory -Force -Path $GradesRoot | Out-Null",
            "",
        ]
        for item in bundled_items:
            lines.extend(
                [
                    f"Write-Host 'Running {item.item_id}'",
                    f"$InputDir = Join-Path $BundleRoot '{item.bundled_eval_input_dir}'",
                    f"$ResultDir = Join-Path $BundleRoot '{item.bundled_result_dir}'",
                    f"$GradeDir = Join-Path $BundleRoot '{item.bundled_grade_dir}'",
                    "New-Item -ItemType Directory -Force -Path $ResultDir | Out-Null",
                    "New-Item -ItemType Directory -Force -Path $GradeDir | Out-Null",
                    f"& $PythonExe -m task_generator.v3_rw_task_eval_stirrup_wrapper $InputDir --output $ResultDir -w 1 --model '{item.model}' --max-tokens 16384",
                    "if ($LASTEXITCODE -ne 0) { throw 'eval wrapper failed' }",
                    "& $PythonExe -m bench_standalone.grade_deliverables $ResultDir --out-dir $GradeDir",
                    "if ($LASTEXITCODE -ne 0) { throw 'grading failed' }",
                    "",
                ]
            )
        lines.append("Write-Host 'Phase 15 first-pair permitted eval completed. Fill the sanitized results template next.'")
        return "\n".join(lines) + "\n"

    def _readme_text(self, bundled_items: List[Phase15BundledItem]) -> str:
        item_lines = "\n".join(
            f"- `{item.arm_id} / {item.case_id} / {item.model}` -> `{item.bundled_eval_input_dir}`"
            for item in bundled_items
        )
        return f"""# Phase 15 First-Pair Permitted Eval Bundle

This bundle contains only the first Phase 15 paired eval inputs:

{item_lines}

Run `run_phase15_first_pair_permitted_eval.ps1` only in an environment that is permitted to send these task packages to external model/API services.

After execution, fill `phase15_external_eval_results_template.json` with sanitized item-level results only. Do not add API keys, bearer tokens, raw provider logs, or secret-bearing environment files.
"""

    def _dir_stats(self, path: Path) -> tuple[int, int]:
        file_count = 0
        byte_count = 0
        for file_path in path.rglob("*"):
            if file_path.is_file():
                file_count += 1
                byte_count += file_path.stat().st_size
        return file_count, byte_count

    def _checksums(self, bundle_dir: Path) -> Dict[str, str]:
        checksums: Dict[str, str] = {}
        for file_path in sorted(path for path in bundle_dir.rglob("*") if path.is_file()):
            if file_path.name == "checksums.sha256.json":
                continue
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            checksums[str(file_path.relative_to(bundle_dir).as_posix())] = digest
        return checksums

    def _zip_dir(self, source_dir: Path, zip_path: Path) -> None:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(path for path in source_dir.rglob("*") if path.is_file()):
                archive.write(file_path, file_path.relative_to(source_dir.parent))
