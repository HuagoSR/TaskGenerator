import os
import json
import sys
import uuid
from typing import List, Dict, Any
from dataclasses import dataclass, field

sys.path.append("..")
from Skill.skill_graph import build_greedy_graph, SkillGraph
from Skill.skill_bank import SKILL_REGISTRY
from FileGenerator.blueprint_core import VirtualFileSystem
from task_schemma import StirrupRubricItem, TaskSchema
from Prompt.prompt_weaver import PromptWeaver


# ==========================================
# 1. 任务配置中心
# ==========================================
@dataclass
class TaskConfig:
    """任务流水线的全局配置中心"""
    # 基础信息
    task_id_prefix: str = "TASK"
    task_output_dir: str = "test_outputs/Task_01"

    # 考点配置
    base_skill_id: str = "base_pnl_01"
    global_skill_ids: List[str] = field(default_factory=lambda: ["global_req_01"])

    # 交付物与元数据
    deliverable_files: List[str] = field(default_factory=lambda: ["Music_Tour_PnL_Result.xlsx"])
    sector: str = "Financial Audit"
    occupation: str = "Senior Auditor"
    motif: str = "extract-organize-calculate"

    # 判分与数据生成配置
    rubric_default_score: int = 3
    default_row_count: int = 10


# ==========================================
# 2. 流水线核心类
# ==========================================
class TaskGenerationPipeline:
    """端到端的自动化题目生成流水线"""

    def __init__(self, config: TaskConfig):
        self.config = config
        self.graph = None
        self.vfs = VirtualFileSystem()
        self.semantic_brief = {}
        self.final_prompt = ""

        # 自动生成绝对唯一的 Task ID
        self.task_id = f"{self.config.task_id_prefix}_{uuid.uuid4().hex[:8].upper()}"

    def phase_1_build_graph(self):
        print("\n=== [Phase 1] 启动引擎：图谱自动生长 ===")
        # 1. 执行贪婪生长
        self.graph = build_greedy_graph(self.config.base_skill_id)

        # 2. 动态空降所有全局节点
        for g_skill_id in self.config.global_skill_ids:
            if g_skill_id in SKILL_REGISTRY:
                GlobalClass = SKILL_REGISTRY[g_skill_id]
                global_node = GlobalClass(node_id=f"{g_skill_id}_inst_1")
                self.graph.add_node(global_node)
                global_node.on_join_graph(self.graph)
                print(f"成功空降全局独立节点: {global_node.name}")
            else:
                print(f"警告: 未在注册表中找到全局考点 {g_skill_id}")

    def phase_2_compile_semantics(self):
        print("\n=== [Phase 2] 编译语义大纲 ===")
        self.semantic_brief = self.graph.compile_semantics()
        print(json.dumps(self.semantic_brief, indent=4, ensure_ascii=False))

    def phase_3_register_blueprints(self):
        print("\n=== [Phase 3] 图引擎向 VFS 注册蓝图 ===")
        execution_order = self.graph.topological_sort()
        for node in execution_order:
            print(f"调度节点: {node.name} ({node.node_id})")
            node.register_data_operations(self.vfs, self.graph)

    def phase_4_collapse_vfs(self):
        print("\n=== [Phase 4] 物理坍缩：生成并导出真实文件 ===")
        auto_collapse_order = self.vfs.get_auto_collapse_order()
        print(f"自动计算坍缩路径: {' -> '.join(auto_collapse_order)}")

        # 动态计算每个表的行数
        dynamic_row_counts = {table: self.config.default_row_count for table in auto_collapse_order}
        dynamic_row_counts.update(self.semantic_brief.get("Suggested_Rows", {}))

        for table, count in dynamic_row_counts.items():
            print(f"设定规模: {table} -> {count} 行")

        self.vfs.collapse_all(auto_collapse_order, dynamic_row_counts)

    def phase_5_save_reference_files(self):
        print("\n=== [Phase 5] 数据验收与落盘 (严格对齐评测框架) ===")
        ref_dir = os.path.join(self.config.task_output_dir, "reference_files")
        os.makedirs(ref_dir, exist_ok=True)

        for file_name, df in self.vfs.collapsed_data.items():
            output_path = os.path.join(ref_dir, file_name)
            if file_name.endswith(".csv"):
                df.to_csv(output_path, index=False)
            elif file_name.endswith((".xlsx", ".xls")):
                df.to_excel(output_path, index=False)
            print(f"已保存附件: {output_path}")

        print("\n--- Ground Truth (案发现场判分依据) ---")
        print(json.dumps(self.vfs.global_ground_truth, indent=4, ensure_ascii=False))

    def phase_6_weave_prompt(self):
        print("\n=== [Phase 6] Prompt Weaver：生成最终任务书 ===")
        weaver = PromptWeaver()
        self.final_prompt = weaver.weave(self.semantic_brief)

        # 可选：将 Markdown 也保存在任务目录下
        prompt_path = os.path.join(self.config.task_output_dir, "Final_Task_Prompt.md")
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(self.final_prompt)
        print(f"任务书已生成: {prompt_path}")

    def phase_7_package_and_export(self):
        print("\n=== [Phase 7] 组装 Rubric 并打包为最终数据集 ===")

        # 1. 组装判分点
        rubric_objects = []
        raw_rubrics = self.semantic_brief.get("Rubrics", [])
        for index, criterion_text in enumerate(raw_rubrics):
            r_id = f"R_{index + 1:03d}"
            item = StirrupRubricItem(
                score=self.config.rubric_default_score,
                criterion=criterion_text,
                required=True,
                rubric_item_id=r_id,
                author_type="model",
                tags=["outcome"]
            )
            rubric_objects.append(item)
            print(f"生成判分点 [{r_id}]: {criterion_text[:30]}...")

        # 2. 组装输入附件与输出要求
        ref_files_with_path = [f"reference_files/{fname}" for fname in self.vfs.collapsed_data.keys()]

        dynamic_deliverables = self.semantic_brief.get("Deliverables", [])
        dynamic_deliverables = [f"deliverable_files/{d}" for d in dynamic_deliverables]


        # 3. 实例化打包
        final_task_package = TaskSchema.create_package(
            task_id=self.task_id,
            sector=self.config.sector,
            occupation=self.config.occupation,
            motif=self.config.motif,
            prompt=self.final_prompt,
            reference_files=ref_files_with_path,
            deliverable_files=dynamic_deliverables,
            rubrics=rubric_objects,
            extra={"ground_truth": self.vfs.global_ground_truth}
        )

        # 4. 落地 JSON
        output_json_path = os.path.join(self.config.task_output_dir, "dataset_row.json")
        with open(output_json_path, "w", encoding="utf-8") as f:
            f.write(final_task_package.export_to_json())

        print("\n==================================================")
        print(f"最终数据包已落盘: {output_json_path}")
        print("==================================================\n")

    def run(self):
        """一键执行完整流水线"""
        self.phase_1_build_graph()
        self.phase_2_compile_semantics()
        self.phase_3_register_blueprints()
        self.phase_4_collapse_vfs()
        self.phase_5_save_reference_files()
        self.phase_6_weave_prompt()
        self.phase_7_package_and_export()


# ==========================================
# 3. 主程序入口
# ==========================================
if __name__ == "__main__":
    custom_config = TaskConfig(
        task_id_prefix="TASK_NEW",
        task_output_dir="test_outputs/Task_NEW",
        base_skill_id="base_pnl_01",
        global_skill_ids=["global_req_01"],
        rubric_default_score=3,
        sector="Financial Audit"
    )

    # 实例化并运行流水线
    pipeline = TaskGenerationPipeline(custom_config)
    pipeline.run()