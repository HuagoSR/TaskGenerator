import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class PromptWeaver:
    def __init__(self):
        # 自动从环境变量读取，代码里绝不出现明文 Key
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv("OPENAI_BASE_URL")
        if not self.api_key:
            raise ValueError("未找到 OPENAI_API_KEY，请检查 .env 文件是否配置正确！")

        self.client = OpenAI(api_key=self.api_key)

    def weave(self, semantic_brief: dict) -> str:
        """核心方法：将 JSON 大纲编织成最终任务书"""

        # 1. 提取动态传入的要素
        intents = "\n".join([f"- {i}" for i in semantic_brief["Intents"]])
        constraints = "\n".join([f"- {c}" for c in semantic_brief["Constraints"]])

        # 注入极具统治力的出题专家 System Prompt
        master_system_prompt = """
        You are an expert Exam Designer for a top-tier financial audit firm. 
        Your task is to translate a list of raw, step-by-step technical intents into a professional, cohesive, and high-level business audit scenario.

        🏛️ THE "DECLARATIVE SCHEMA" PHILOSOPHY (CRITICAL):
        To ensure the candidate outputs all necessary intermediate columns (variances, flags) without giving them a step-by-step coding tutorial, you MUST separate the "Business Objectives" from the "Required Output Format".
        - DO NOT use imperative programming verbs like "Create a flag", "Generate a column", "Calculate the difference", or "Assign 1 or 0".
        - INSTEAD, define the rules abstractly, and then provide a "Data Dictionary" or "Output Schema" at the end, listing the required fields they need to append.

        🚫 ANTI-ROBOT & ABSTRACTION RULES:
        1. **NO Hand-holding:** Consolidate all the risk conditions (High variance, specific entities, zero-values, etc.) into a single, flowing business paragraph describing the "Target Risk Profile". 
        2. **Hide Data Cleaning:** Frame missing values and negative numbers merely as "Data Quality Assumptions" or "Notes", not as action steps.
        3. **No Step-by-step logic:** Never explain HOW to combine the flags. Just state the final optimization goal (e.g., "Extract a sample of the calculated size that ensures coverage across all Divisions while maximizing exposure to the Target Risk Profiles.").

        🎭 PERSONA & STRUCTURE:
        - **Context:** "You are an auditor tasked with a substantive review..."
        - **Audit Objectives:** A high-level description of the variance analysis, the sample size calculation (90% conf, 10% err), and the complex sampling constraints (the OR-logic over the risk profiles).
        - **Working Paper Format (The Schema):** Explicitly list the conceptual columns that MUST be appended to the final exported `.xlsx` file to maintain the audit trail (e.g., "To maintain a clear audit trail, your final dataset must append indicator columns representing: QoQ Variance, High-Risk Entity Match, Dormant Account Status, ..., and the Final Selection Indicator.").
        - **Hard Constraints & Deliverables:** Exact file names.
        """

        user_prompt = f"Raw Technical Intents:\n{intents}\n\nHard Constraints to Include:\n{constraints}\n\nPlease generate the final exam prompt now."

        print(f"[Prompt Weaver] 正在呼叫 {self.model} 进行业务包装，转换为高级审计题...")

        # 2. 调用大模型
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.4,  # 稍微提高一点温度，给它一些润色和编排语言的创造力
            messages=[
                {"role": "system", "content": master_system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        final_prompt = response.choices[0].message.content

        # 3. 启动硬性约束校验
        return self._verify_and_fix(final_prompt, semantic_brief["Constraints"])

    def _verify_and_fix(self, final_prompt: str, constraints: list) -> str:
        """安检机制：如果大模型漏掉了约束，强行补上"""
        missing_constraints = [c for c in constraints if c.strip() not in final_prompt]

        if missing_constraints:
            print("[警告] 发现丢失硬性约束！正在自动修复尾部...")
            final_prompt += "\n\n### Critical Auto-Appended Constraints:\n"
            for mc in missing_constraints:
                final_prompt += f"- {mc}\n"
        else:
            print("[校验通过] 硬性约束一字不差保留！")

        return final_prompt