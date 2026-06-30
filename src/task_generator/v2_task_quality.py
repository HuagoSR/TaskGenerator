import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class TaskQualityResult:
    task_id: str
    total_score: float
    component_scores: Dict[str, float]
    diagnostics: Dict[str, object]
    recommendation: str


class FinanceTaskQualityScorer:
    def score_case_dir(self, case_dir: str | Path, rw_task_case_dir: str | Path) -> TaskQualityResult:
        case_path = Path(case_dir)
        rw_task_path = Path(rw_task_case_dir)

        blueprint = self._load_json(case_path / "task_blueprint.json")
        training_annotation = self._load_json(case_path / "training_annotation.json")
        golden_anchors = self._load_json(case_path / "golden_run" / "golden_grading_anchors.json")
        dataset_row = self._load_json(rw_task_path / "dataset_row.json")
        rubric_items = json.loads(dataset_row["rubric_json"])

        structural = self._score_structural_complexity(blueprint, golden_anchors, rubric_items)
        reasoning = self._score_reasoning_depth(blueprint, training_annotation, rubric_items)
        supervision = self._score_result_supervision(golden_anchors, rubric_items)
        realism = self._score_prompt_realism(dataset_row["prompt"], blueprint)
        challenge = self._score_challenge_balance(golden_anchors)

        component_scores = {
            "structural_complexity": structural,
            "reasoning_depth": reasoning,
            "result_supervision": supervision,
            "prompt_realism": realism,
            "challenge_balance": challenge,
        }
        total_score = round(sum(component_scores.values()) / len(component_scores), 2)

        diagnostics = self._build_diagnostics(blueprint, golden_anchors, rubric_items, component_scores)
        recommendation = self._recommend(total_score, diagnostics)

        return TaskQualityResult(
            task_id=dataset_row["task_id"],
            total_score=total_score,
            component_scores=component_scores,
            diagnostics=diagnostics,
            recommendation=recommendation,
        )

    def score_batch(self, batch_dir: str | Path, rw_task_batch_dir: str | Path) -> List[TaskQualityResult]:
        batch_path = Path(batch_dir)
        rw_task_path = Path(rw_task_batch_dir)
        results = []

        for case_dir in sorted(batch_path.glob("TASK_*")):
            if not case_dir.is_dir():
                continue
            rw_case_dir = rw_task_path / case_dir.name
            if not rw_case_dir.exists():
                continue
            results.append(self.score_case_dir(case_dir, rw_case_dir))

        return sorted(results, key=lambda item: item.total_score, reverse=True)

    def write_batch_reports(
        self,
        batch_dir: str | Path,
        rw_task_batch_dir: str | Path,
        output_json_path: str | Path,
        output_md_path: str | Path,
    ) -> List[TaskQualityResult]:
        results = self.score_batch(batch_dir, rw_task_batch_dir)
        json_payload = [
            {
                "task_id": result.task_id,
                "total_score": result.total_score,
                "component_scores": result.component_scores,
                "diagnostics": result.diagnostics,
                "recommendation": result.recommendation,
            }
            for result in results
        ]
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(json_payload, f, ensure_ascii=False, indent=2)

        lines = ["# Finance Batch Quality Summary", ""]
        for idx, result in enumerate(results, start=1):
            lines.append(f"## {idx}. {result.task_id}")
            lines.append(f"- total_score: {result.total_score}")
            lines.append(f"- recommendation: {result.recommendation}")
            for key, value in result.component_scores.items():
                lines.append(f"- {key}: {round(value, 2)}")
            lines.append(
                f"- diagnostics: traps={result.diagnostics['trap_count']}, rubric_items={result.diagnostics['rubric_item_count']}, "
                f"hidden_requirements={result.diagnostics['hidden_requirement_count']}, source_count={result.diagnostics['source_count']}, "
                f"net_margin={result.diagnostics['net_margin_ratio']}"
            )
            lines.append("")

        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return results

    def _score_structural_complexity(self, blueprint: Dict[str, object], golden_anchors: Dict[str, object], rubric_items: List[Dict[str, object]]) -> float:
        reference_files = blueprint["data_spec"]["reference_files"]
        trap_spec = blueprint["trap_spec"]
        intermediate_states = golden_anchors["intermediate_targets"]["required_states"]
        row_targets = sum(
            sheet["row_count_target"]
            for file_spec in reference_files
            for sheet in file_spec["sheet_specs"]
        )
        score = 12.0
        score += min(len(reference_files) * 8.0, 24.0)
        score += min(len(trap_spec) * 9.0, 18.0)
        score += min(len(intermediate_states) * 3.0, 18.0)
        score += min(len(rubric_items) * 0.45, 10.0)
        score += min(row_targets / 120.0, 10.0)
        return min(score, 100.0)

    def _score_reasoning_depth(self, blueprint: Dict[str, object], annotation: Dict[str, object], rubric_items: List[Dict[str, object]]) -> float:
        hidden_requirement_count = len(blueprint["prompt_spec"]["hidden_requirements"])
        intermediate_outcomes = len(annotation["supervision_targets"]["intermediate_outcomes"])
        reasoning_rows = sum(1 for item in rubric_items if "reasoning" in (item.get("tags") or []))
        robustness_rows = sum(1 for item in rubric_items if "robustness" in (item.get("tags") or []))
        trap_count = len(blueprint["trap_spec"])
        score = 10.0
        score += min(hidden_requirement_count * 4.5, 22.5)
        score += min(intermediate_outcomes * 7.0, 21.0)
        score += min(reasoning_rows * 1.8, 12.0)
        score += min(robustness_rows * 3.0, 9.0)
        score += min(trap_count * 4.0, 12.0)
        return min(score, 100.0)

    def _score_result_supervision(self, golden_anchors: Dict[str, object], rubric_items: List[Dict[str, object]]) -> float:
        golden_targets = golden_anchors["golden_targets"]
        source_rows = golden_targets["final_pnl_totals"]["expected_value"]["by_source"]
        overall_totals = golden_targets["final_pnl_totals"]["expected_value"]["overall_totals"]
        revenue_line_items = golden_targets.get("revenue_line_items", {}).get("expected_value", [])
        withholding_by_country = golden_targets.get("withholding_by_country", {}).get("expected_value", [])
        expense_category_totals = golden_targets.get("expense_category_totals", {}).get("expected_value", [])
        executable_targets = golden_anchors.get("executable_verification_targets", {})
        outcome_rows = sum(1 for item in rubric_items if "outcome" in (item.get("tags") or []))
        distinct_numeric_checks = (
            len(source_rows) * 4
            + len(overall_totals)
            + len(revenue_line_items) * 3
            + len(withholding_by_country)
            + len(expense_category_totals)
        )
        tolerance = golden_targets["final_pnl_totals"].get("tolerance", 0.0)
        score = 16.0
        score += min(outcome_rows * 2.0, 22.0)
        score += min(distinct_numeric_checks * 0.8, 28.0)
        score += min(len(executable_targets) * 2.0, 12.0)
        if tolerance <= 0.05:
            score += 7.0
        return min(score, 100.0)

    def _score_prompt_realism(self, prompt: str, blueprint: Dict[str, object]) -> float:
        length = len(prompt)
        style_constraints = blueprint["prompt_spec"]["style_constraints"]
        visible_requirements = blueprint["prompt_spec"]["visible_requirements"]
        reference_files = blueprint["data_spec"]["reference_files"]
        score = 18.0
        if 900 <= length <= 2600:
            score += 30.0
        elif 600 <= length < 900 or 2600 < length <= 3500:
            score += 20.0
        else:
            score += 10.0
        if "realistic business memo tone" in style_constraints:
            score += 12.0
        if "no trap disclosure" in style_constraints:
            score += 10.0
        score += min(len(visible_requirements) * 2.0, 8.0)
        required_sections = [
            "**Role:**",
            "**Engagement Context:**",
            "**Objective:**",
            "**Working Expectations:**",
            "**Required Deliverables:**",
            "**Quality Bar:**",
        ]
        score += min(sum(1 for section in required_sections if section in prompt) * 1.5, 9.0)
        if "sole working data sources" in prompt and len(reference_files) >= 3:
            score += 5.0
        return min(score, 100.0)

    def _score_challenge_balance(self, golden_anchors: Dict[str, object]) -> float:
        summary = golden_anchors["golden_targets"]["final_pnl_totals"]["expected_value"]
        by_source = summary["by_source"]
        overall = summary["overall_totals"]
        revenue = abs(float(overall["revenue_usd"])) or 1.0
        net_income = float(overall["net_income_usd"])
        net_margin_ratio = abs(net_income) / revenue
        positive_sources = sum(1 for row in by_source if float(row["net_income_usd"]) > 0)
        negative_sources = sum(1 for row in by_source if float(row["net_income_usd"]) < 0)
        revenue_shares = [abs(float(row["revenue_usd"])) / revenue for row in by_source]
        max_share = max(revenue_shares) if revenue_shares else 1.0

        score = 15.0
        if positive_sources and negative_sources:
            score += 20.0
        if 0.02 <= net_margin_ratio <= 0.12:
            score += 22.0
        elif 0.01 <= net_margin_ratio <= 0.2:
            score += 14.0
        else:
            score += 6.0
        if max_share <= 0.82:
            score += 15.0
        elif max_share <= 0.9:
            score += 8.0
        tax_usd = abs(float(overall["tax_usd"]))
        if tax_usd / revenue >= 0.03:
            score += 8.0
        expense_pressure = abs(float(overall["expense_usd"])) / revenue
        if 0.55 <= expense_pressure <= 0.85:
            score += 15.0
        elif 0.45 <= expense_pressure <= 0.95:
            score += 8.0
        return min(score, 100.0)

    def _build_diagnostics(
        self,
        blueprint: Dict[str, object],
        golden_anchors: Dict[str, object],
        rubric_items: List[Dict[str, object]],
        component_scores: Dict[str, float],
    ) -> Dict[str, object]:
        overall = golden_anchors["golden_targets"]["final_pnl_totals"]["expected_value"]["overall_totals"]
        revenue = abs(float(overall["revenue_usd"])) or 1.0
        net_margin_ratio = round(abs(float(overall["net_income_usd"])) / revenue, 4)
        return {
            "trap_count": len(blueprint["trap_spec"]),
            "rubric_item_count": len(rubric_items),
            "hidden_requirement_count": len(blueprint["prompt_spec"]["hidden_requirements"]),
            "source_count": len(golden_anchors["golden_targets"]["final_pnl_totals"]["expected_value"]["by_source"]),
            "executable_verification_target_count": len(golden_anchors.get("executable_verification_targets", {})),
            "net_margin_ratio": net_margin_ratio,
            "top_component": max(component_scores, key=component_scores.get),
            "weakest_component": min(component_scores, key=component_scores.get),
        }

    def _recommend(self, total_score: float, diagnostics: Dict[str, object]) -> str:
        if total_score >= 82.0:
            return "prioritize_for_rw_task_eval"
        if total_score >= 72.0:
            return "keep_in_training_pool"
        if diagnostics["weakest_component"] == "challenge_balance":
            return "revise_financial_balance_before_eval"
        return "revise_prompt_or_supervision"

    def _load_json(self, path: Path) -> Dict[str, object]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

