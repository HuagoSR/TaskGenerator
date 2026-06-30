from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import List

from task_generator.FileGenerator.blueprint_core import VirtualFileSystem
from task_generator.Prompt.prompt_weaver import PromptWeaver
from task_generator.Skill.skill_bank import SKILL_REGISTRY
from task_generator.Skill.skill_graph import build_greedy_graph
from task_generator.task_schemma import StirrupRubricItem, TaskSchema


@dataclass
class TaskConfig:
    """Configuration for the legacy end-to-end task generation demo."""

    task_id_prefix: str = "TASK"
    task_output_dir: str = "test_outputs/Task_01"
    base_skill_id: str = "base_pnl_01"
    global_skill_ids: List[str] = field(default_factory=lambda: ["global_req_01"])
    deliverable_files: List[str] = field(default_factory=lambda: ["Music_Tour_PnL_Result.xlsx"])
    sector: str = "Financial Audit"
    occupation: str = "Senior Auditor"
    motif: str = "extract-organize-calculate"
    rubric_default_score: int = 3
    default_row_count: int = 10


class TaskGenerationPipeline:
    """Legacy graph-to-task demo kept for compatibility with the old skill bank."""

    def __init__(self, config: TaskConfig):
        self.config = config
        self.graph = None
        self.vfs = VirtualFileSystem()
        self.semantic_brief = {}
        self.final_prompt = ""
        self.task_id = f"{self.config.task_id_prefix}_{uuid.uuid4().hex[:8].upper()}"

    def phase_1_build_graph(self):
        print("\n=== Phase 1: Build Skill Graph ===")
        self.graph = build_greedy_graph(self.config.base_skill_id)

        for skill_id in self.config.global_skill_ids:
            if skill_id not in SKILL_REGISTRY:
                print(f"Warning: global skill not found in registry: {skill_id}")
                continue

            global_class = SKILL_REGISTRY[skill_id]
            global_node = global_class(node_id=f"{skill_id}_inst_1")
            self.graph.add_node(global_node)
            global_node.on_join_graph(self.graph)
            print(f"Added global node: {global_node.name}")

    def phase_2_compile_semantics(self):
        print("\n=== Phase 2: Compile Semantic Brief ===")
        self.semantic_brief = self.graph.compile_semantics()
        print(json.dumps(self.semantic_brief, indent=4, ensure_ascii=False))

    def phase_3_register_blueprints(self):
        print("\n=== Phase 3: Register Data Blueprints ===")
        for node in self.graph.topological_sort():
            print(f"Scheduling node: {node.name} ({node.node_id})")
            node.register_data_operations(self.vfs, self.graph)

    def phase_4_collapse_vfs(self):
        print("\n=== Phase 4: Materialize Reference Files ===")
        collapse_order = self.vfs.get_auto_collapse_order()
        print(f"Collapse order: {' -> '.join(collapse_order)}")

        row_counts = {table: self.config.default_row_count for table in collapse_order}
        row_counts.update(self.semantic_brief.get("Suggested_Rows", {}))

        for table, count in row_counts.items():
            print(f"Row count: {table} -> {count}")

        self.vfs.collapse_all(collapse_order, row_counts)

    def phase_5_save_reference_files(self):
        print("\n=== Phase 5: Save Reference Files ===")
        ref_dir = os.path.join(self.config.task_output_dir, "reference_files")
        os.makedirs(ref_dir, exist_ok=True)

        for file_name, df in self.vfs.collapsed_data.items():
            output_path = os.path.join(ref_dir, file_name)
            if file_name.endswith(".csv"):
                df.to_csv(output_path, index=False)
            elif file_name.endswith((".xlsx", ".xls")):
                df.to_excel(output_path, index=False)
            print(f"Saved reference file: {output_path}")

        print("\n--- Ground Truth ---")
        print(json.dumps(self.vfs.global_ground_truth, indent=4, ensure_ascii=False))

    def phase_6_weave_prompt(self):
        print("\n=== Phase 6: Weave Final Prompt ===")
        self.final_prompt = PromptWeaver().weave(self.semantic_brief)

        os.makedirs(self.config.task_output_dir, exist_ok=True)
        prompt_path = os.path.join(self.config.task_output_dir, "Final_Task_Prompt.md")
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(self.final_prompt)
        print(f"Saved task prompt: {prompt_path}")

    def phase_7_package_and_export(self):
        print("\n=== Phase 7: Package Dataset Row ===")
        rubric_objects = []
        for index, criterion_text in enumerate(self.semantic_brief.get("Rubrics", [])):
            rubric_objects.append(
                StirrupRubricItem(
                    score=self.config.rubric_default_score,
                    criterion=criterion_text,
                    required=True,
                    rubric_item_id=f"R_{index + 1:03d}",
                    author_type="model",
                    tags=["outcome"],
                )
            )

        final_task_package = TaskSchema.create_package(
            task_id=self.task_id,
            sector=self.config.sector,
            occupation=self.config.occupation,
            motif=self.config.motif,
            prompt=self.final_prompt,
            reference_files=[f"reference_files/{name}" for name in self.vfs.collapsed_data.keys()],
            deliverable_files=[f"deliverable_files/{name}" for name in self.semantic_brief.get("Deliverables", [])],
            rubrics=rubric_objects,
            extra={"ground_truth": self.vfs.global_ground_truth},
        )

        output_json_path = os.path.join(self.config.task_output_dir, "dataset_row.json")
        with open(output_json_path, "w", encoding="utf-8") as f:
            f.write(final_task_package.export_to_json())

        print(f"Saved final dataset row: {output_json_path}")

    def run(self):
        self.phase_1_build_graph()
        self.phase_2_compile_semantics()
        self.phase_3_register_blueprints()
        self.phase_4_collapse_vfs()
        self.phase_5_save_reference_files()
        self.phase_6_weave_prompt()
        self.phase_7_package_and_export()


if __name__ == "__main__":
    custom_config = TaskConfig(
        task_id_prefix="TASK_NEW",
        task_output_dir="test_outputs/Task_NEW_5",
        base_skill_id="load_financial_data",
        global_skill_ids=["global_req_01"],
        rubric_default_score=3,
        sector="Financial Audit",
    )
    TaskGenerationPipeline(custom_config).run()
