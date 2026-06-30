import os
import json
import sys
from typing import List, Dict, Any


sys.path.append("..")
from Prompt.prompt_weaver import PromptWeaver


class GraphCompiler:
    """
    图谱编译器 (Graph Compiler)
    任务：将 DAG 图谱中的声明式考点，折叠编译为沙盒执行指令、考生题干和核验锚点。
    """

    def __init__(self, db_path: str = "../Skill/skills_config.json"):
        self.db_path = db_path
        self.db = self._load_db()
        self.weaver = PromptWeaver()

    def _load_db(self) -> dict:
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"找不到题库文件: {self.db_path}")
        with open(self.db_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def compile(self, task_skill_ids: List[str], semantic_context: dict = None) -> Dict[str, Any]:
        """
        核心编译方法
        :param task_skill_ids: 本次考试抽中的考点 ID 列表 (需按拓扑顺序排列)
        :param semantic_context: 业务背景 (例如: {"role": "Auditor", "task_goal": "..."})
        """
        print("\n[Graph Compiler] 正在编译图谱节点...")

        data_generators = []
        solvers = []
        global_constraints = []
        evaluation_anchors = []

        # 1. 节点分流
        for sid in task_skill_ids:
            node = self.db.get(sid)
            if not node:
                print(f"[警告] 找不到考点 {sid}，已跳过。")
                continue

            role = node.get("sandbox_role", "")
            if role == "Data_Generator":
                data_generators.append(node)
            elif role == "Solver":
                solvers.append(node)
            elif role == "Global_Constraint":
                global_constraints.append(node)

            # 收集所有的评分锚点
            anchor = node.get("semantics", {}).get("evaluation_anchor")
            if anchor:
                evaluation_anchors.append({
                    "skill_id": sid,
                    "category": anchor.get("category"),
                    "assertion_logic": anchor.get("assertion_logic"),
                    "data_profile": node.get("data_profile", {})  # 保留参数供替换
                })

        # 2. 编译沙盒创世指令 (Sandbox Data Genesis Prompt)
        sandbox_prompt = self._build_sandbox_prompt(data_generators)

        # 3. 编译最终考试题干 (Candidate Exam Prompt)
        candidate_prompt = self._build_candidate_prompt(data_generators, solvers, global_constraints, semantic_context)

        print("[Graph Compiler] 编译完成！成功折叠数据意图与对账锚点。")
        return {
            "sandbox_prompt": sandbox_prompt,
            "candidate_prompt": candidate_prompt,
            "evaluation_anchors": evaluation_anchors
        }

    def _build_sandbox_prompt(self, generators: List[dict]) -> str:
        """折叠 Data_Generator 节点，生成用于 Stirrup 沙盒的 Python 编写指令"""
        prompt = (
            "You are an expert Python data generation script writer operating within a strict sandbox.\n"
            "Write a Python script using pandas to generate realistic `.xlsx` or `.csv` datasets based on the requirements below.\n"
            "CRITICAL: You MUST inject the specified data anomalies (Traps) directly during the data generation process.\n\n"
        )

        prompt += "### 1. Base Data Structures (基底数据要求):\n"
        for node in generators:
            if node.get("node_type") == "base":
                profile = node.get("data_profile", {})
                prompt += f"- Context: {profile.get('business_context', '')}\n"
                prompt += f"- Schemas: {json.dumps(profile.get('declarative_schemas', {}), indent=2)}\n"
                prompt += f"- Suggested Scale: {json.dumps(profile.get('suggested_scale', {}))}\n\n"

        prompt += "### 2. Trap Injections (必须植入的脏数据/异常):\n"
        trap_count = 0
        for node in generators:
            if node.get("node_type") == "trap":
                trap_count += 1
                profile = node.get("data_profile", {})
                intents = node.get("semantics", {}).get("intents", [])
                prompt += f"Trap {trap_count}:\n"
                prompt += f"- Intent: {intents[0] if intents else 'Inject anomalies'}\n"
                prompt += f"- Specs: {json.dumps(profile)}\n\n"

        prompt += "Output ONLY the raw executable Python code. Do not include markdown blocks like ```python."
        return prompt

    def _build_candidate_prompt(self, generators, solvers, globals_cons, semantic_context) -> str:
        """调用 Prompt Weaver，将业务逻辑封装为最终题干"""
        all_intents = []
        all_constraints = []

        # 收集解题相关的业务动作
        for node in (generators + solvers):
            # 注意：Trap 节点的 intents 绝对不能放进去！否则就等于剧透了！
            if node.get("node_type") == "trap":
                continue
            intents = node.get("semantics", {}).get("intents", [])
            all_intents.extend(intents)

        # 收集全局约束 (文件命名格式等)
        for node in globals_cons:
            constraints = node.get("semantics", {}).get("hard_constraints", [])
            all_constraints.extend(constraints)

        # 构建给 PromptWeaver 的大纲
        brief = {
            "Role": semantic_context.get("role", "Financial Auditor") if semantic_context else "Data Analyst",
            "Task_Goal": semantic_context.get("task_goal",
                                              "Process the provided datasets.") if semantic_context else "Process the data.",
            "Intents": all_intents,
            "Constraints": all_constraints
        }

        # 调用 PromptWeaver 编织题干
        return self.weaver.weave(brief)


# ==========================================
# 本地单文件测试入口
# ==========================================
if __name__ == "__main__":
    real_db_path = "../Skill/skills_config.json"
    compiler = GraphCompiler(db_path=real_db_path)
    test_ids = list(compiler.db.keys())

    result = compiler.compile(test_ids, semantic_context={"role": "Finance Lead", "task_goal": "Create a P&L report"})

    print("\n" + "=" * 50)
    print("1. [给沙盒的代码指令 Sandbox Prompt] (绝密，大模型专用):")
    print("=" * 50)
    print(result["sandbox_prompt"])

    print("\n" + "=" * 50)
    print("2. [给考生的考试题干 Candidate Prompt] (公开，题目文本):")
    print("=" * 50)
    print(result["candidate_prompt"])

    print("\n" + "=" * 50)
    print(f"3. [对账裁判锚点 Evaluation Anchors] (共提取 {len(result['evaluation_anchors'])} 个):")
    print("=" * 50)
    for anchor in result['evaluation_anchors']:
        print(f"- [{anchor['category']}] {anchor['assertion_logic']}")