import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OptimizationAction:
    action_id: str
    priority: str
    target_layer: str
    problem_signal: str
    recommended_change: str
    expected_effect: str


@dataclass
class FinanceOptimizationPlan:
    batch_id: str
    task_count: int
    gate_pass_count: int
    weak_component_counts: dict[str, int]
    actions: list[OptimizationAction] = field(default_factory=list)
    task_routes: list[dict[str, Any]] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "task_count": self.task_count,
            "gate_pass_count": self.gate_pass_count,
            "weak_component_counts": self.weak_component_counts,
            "actions": [asdict(action) for action in self.actions],
            "task_routes": self.task_routes,
        }


class FinanceOptimizationPlanner:
    COMPONENT_ACTIONS = {
        "result_supervision": OptimizationAction(
            action_id="improve_result_supervision",
            priority="high",
            target_layer="GoldenRun + rw_task_adapter",
            problem_signal="Static quality reports result_supervision as the weakest component.",
            recommended_change=(
                "Add more executable grading anchors for worksheet-level outputs: show-level FX-normalized revenue, "
                "country-level withholding, source-level P&L subtotals, and formula-error checks. Keep the rubric layout-tolerant, "
                "but make the numeric evidence easier for graders and scripts to locate."
            ),
            expected_effect="Raise supervision reliability and make free-form workbook outputs easier to grade without forcing one fixed layout.",
        ),
        "challenge_balance": OptimizationAction(
            action_id="rebalance_financial_profile",
            priority="high",
            target_layer="FileGenerator finance profiles",
            problem_signal="Static quality reports challenge_balance as the weakest component.",
            recommended_change=(
                "Tune selected finance profiles so net margin stays in the preferred band and the task has both meaningful revenue-side "
                "and cost-side pressure. Adjust production-cost totals or tour revenue profiles instead of changing the prompt after the fact."
            ),
            expected_effect="Reduce cases that are structurally valid but too easy, too extreme, or numerically less discriminative.",
        ),
        "structural_complexity": OptimizationAction(
            action_id="increase_structural_variety",
            priority="medium",
            target_layer="TaskBlueprint + reference-file generation",
            problem_signal="Static quality reports structural_complexity as the weakest component.",
            recommended_change=(
                "Introduce one additional realistic source table or a small supporting schedule only when it creates a real dependency. "
                "Avoid adding sheets just for apparent complexity."
            ),
            expected_effect="Increase task richness while preserving auditability.",
        ),
        "prompt_realism": OptimizationAction(
            action_id="improve_prompt_realism",
            priority="medium",
            target_layer="TaskBlueprint prompt construction",
            problem_signal="Static quality reports prompt_realism as the weakest component.",
            recommended_change=(
                "Make scenario context more client-realistic and role-specific, while keeping hidden traps undisclosed. "
                "Prefer concise business instructions over tutorial wording."
            ),
            expected_effect="Improve GDPVal-style realism without weakening the intended challenge.",
        ),
        "reasoning_depth": OptimizationAction(
            action_id="increase_reasoning_depth",
            priority="medium",
            target_layer="SemanticSkill selection + trap design",
            problem_signal="Static quality reports reasoning_depth as the weakest component.",
            recommended_change=(
                "Combine the primary finance skill with one additional dependent reasoning step, such as source reconciliation, "
                "exception handling, or consistency checks across schedules."
            ),
            expected_effect="Create deeper tasks where correct output requires more than one isolated reasoning move.",
        ),
    }

    def build_plan(
        self,
        quality_report_path: str | Path,
        funnel_report_path: str | Path,
        batch_id: str = "finance_batch_01",
    ) -> FinanceOptimizationPlan:
        quality_rows = json.loads(Path(quality_report_path).read_text(encoding="utf-8"))
        funnel_rows = json.loads(Path(funnel_report_path).read_text(encoding="utf-8"))
        funnel_by_task = {row["task_id"]: row for row in funnel_rows}

        weak_component_counts: dict[str, int] = {}
        task_routes: list[dict[str, Any]] = []
        for row in quality_rows:
            task_id = row["task_id"]
            weakest = row["diagnostics"]["weakest_component"]
            weak_component_counts[weakest] = weak_component_counts.get(weakest, 0) + 1
            funnel_row = funnel_by_task.get(task_id, {})
            task_routes.append(
                {
                    "task_id": task_id,
                    "gate_passed": bool(funnel_row.get("gate_passed", False)),
                    "total_score": row["total_score"],
                    "weakest_component": weakest,
                    "recommendation": row["recommendation"],
                    "optimization_action": self.COMPONENT_ACTIONS.get(weakest, self.COMPONENT_ACTIONS["result_supervision"]).action_id,
                }
            )

        actions = []
        for component, _count in sorted(weak_component_counts.items(), key=lambda item: (-item[1], item[0])):
            if component in self.COMPONENT_ACTIONS:
                actions.append(self.COMPONENT_ACTIONS[component])

        gate_pass_count = sum(1 for row in funnel_rows if row.get("gate_passed"))
        return FinanceOptimizationPlan(
            batch_id=batch_id,
            task_count=len(quality_rows),
            gate_pass_count=gate_pass_count,
            weak_component_counts=weak_component_counts,
            actions=actions,
            task_routes=task_routes,
        )


def render_markdown(plan: FinanceOptimizationPlan) -> str:
    lines: list[str] = [
        f"# Finance Optimization Playbook: {plan.batch_id}",
        "",
        "## Batch Diagnosis",
        "",
        f"- task_count: {plan.task_count}",
        f"- gate_pass_count: {plan.gate_pass_count}",
        f"- weak_component_counts: {plan.weak_component_counts}",
        "",
        "## Recommended Actions",
        "",
    ]

    for idx, action in enumerate(plan.actions, start=1):
        lines.append(f"### {idx}. {action.action_id}")
        lines.append("")
        lines.append(f"- priority: {action.priority}")
        lines.append(f"- target_layer: {action.target_layer}")
        lines.append(f"- problem_signal: {action.problem_signal}")
        lines.append(f"- recommended_change: {action.recommended_change}")
        lines.append(f"- expected_effect: {action.expected_effect}")
        lines.append("")

    lines.extend(
        [
            "## Task Routing",
            "",
            "| Task | Gate | Score | Weakest Component | Action |",
            "|---|---:|---:|---|---|",
        ]
    )
    for route in plan.task_routes:
        lines.append(
            f"| {route['task_id']} | {route['gate_passed']} | {float(route['total_score']):.2f} | "
            f"{route['weakest_component']} | {route['optimization_action']} |"
        )
    lines.append("")
    return "\n".join(lines)
