from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json
from typing import Any, Dict, List

from task_generator.Prompt.prompt_weaver import PromptWeaver


DEFAULT_SKILL_CONFIG_PATH = ROOT / "src" / "task_generator" / "Skill" / "skills_config.json"


class GraphCompiler:
    """Legacy graph compiler smoke helper for the old skill-config prototype."""

    def __init__(self, db_path: str | Path = DEFAULT_SKILL_CONFIG_PATH):
        self.db_path = Path(db_path)
        self.db = self._load_db()
        self.weaver = PromptWeaver()

    def _load_db(self) -> dict:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Skill config file not found: {self.db_path}")
        with self.db_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def compile(self, task_skill_ids: List[str], semantic_context: dict | None = None) -> Dict[str, Any]:
        print("\n[Graph Compiler] Compiling legacy graph nodes...")

        data_generators = []
        solvers = []
        global_constraints = []
        evaluation_anchors = []

        for skill_id in task_skill_ids:
            node = self.db.get(skill_id)
            if not node:
                print(f"[Warning] Skill id not found, skipping: {skill_id}")
                continue

            role = node.get("sandbox_role", "")
            if role == "Data_Generator":
                data_generators.append(node)
            elif role == "Solver":
                solvers.append(node)
            elif role == "Global_Constraint":
                global_constraints.append(node)

            anchor = node.get("semantics", {}).get("evaluation_anchor")
            if anchor:
                evaluation_anchors.append(
                    {
                        "skill_id": skill_id,
                        "category": anchor.get("category"),
                        "assertion_logic": anchor.get("assertion_logic"),
                        "data_profile": node.get("data_profile", {}),
                    }
                )

        return {
            "sandbox_prompt": self._build_sandbox_prompt(data_generators),
            "candidate_prompt": self._build_candidate_prompt(
                data_generators,
                solvers,
                global_constraints,
                semantic_context or {},
            ),
            "evaluation_anchors": evaluation_anchors,
        }

    def _build_sandbox_prompt(self, generators: List[dict]) -> str:
        prompt = (
            "You are an expert Python data generation script writer operating within a strict sandbox.\n"
            "Write a Python script using pandas to generate realistic .xlsx or .csv datasets based on the "
            "requirements below.\n"
            "CRITICAL: You MUST inject the specified data anomalies directly during data generation.\n\n"
        )

        prompt += "### 1. Base Data Structures\n"
        for node in generators:
            if node.get("node_type") == "base":
                profile = node.get("data_profile", {})
                prompt += f"- Context: {profile.get('business_context', '')}\n"
                prompt += f"- Schemas: {json.dumps(profile.get('declarative_schemas', {}), indent=2)}\n"
                prompt += f"- Suggested Scale: {json.dumps(profile.get('suggested_scale', {}))}\n\n"

        prompt += "### 2. Trap Injections\n"
        trap_count = 0
        for node in generators:
            if node.get("node_type") == "trap":
                trap_count += 1
                profile = node.get("data_profile", {})
                intents = node.get("semantics", {}).get("intents", [])
                prompt += f"Trap {trap_count}:\n"
                prompt += f"- Intent: {intents[0] if intents else 'Inject anomalies'}\n"
                prompt += f"- Specs: {json.dumps(profile)}\n\n"

        prompt += "Output ONLY raw executable Python code. Do not include markdown fences."
        return prompt

    def _build_candidate_prompt(self, generators, solvers, global_constraints, semantic_context) -> str:
        all_intents = []
        all_constraints = []

        for node in generators + solvers:
            if node.get("node_type") == "trap":
                continue
            all_intents.extend(node.get("semantics", {}).get("intents", []))

        for node in global_constraints:
            all_constraints.extend(node.get("semantics", {}).get("hard_constraints", []))

        brief = {
            "Role": semantic_context.get("role", "Data Analyst"),
            "Task_Goal": semantic_context.get("task_goal", "Process the provided datasets."),
            "Intents": all_intents,
            "Constraints": all_constraints,
        }
        return self.weaver.weave(brief)


if __name__ == "__main__":
    compiler = GraphCompiler()
    result = compiler.compile(
        list(compiler.db.keys()),
        semantic_context={"role": "Finance Lead", "task_goal": "Create a P&L report"},
    )

    print("\n" + "=" * 50)
    print("1. Sandbox Prompt")
    print("=" * 50)
    print(result["sandbox_prompt"])

    print("\n" + "=" * 50)
    print("2. Candidate Prompt")
    print("=" * 50)
    print(result["candidate_prompt"])

    print("\n" + "=" * 50)
    print(f"3. Evaluation Anchors: {len(result['evaluation_anchors'])}")
    print("=" * 50)
    for anchor in result["evaluation_anchors"]:
        print(f"- [{anchor['category']}] {anchor['assertion_logic']}")
