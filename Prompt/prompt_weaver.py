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

        # 1. 提取动态传入的 System Prompt 和要素
        system_prompt = semantic_brief.get("System_Prompt", "You are a helpful task designer.")
        intents = "\n".join([f"- {i}" for i in semantic_brief["Intents"]])
        constraints = "\n".join([f"- {c}" for c in semantic_brief["Constraints"]])

        user_prompt = f"Business Intents:\n{intents}\n\nHard Constraints:\n{constraints}"

        print(f"[Prompt Weaver] 正在呼叫 {self.model} 进行业务包装...")

        # 2. 调用大模型
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.3,  # 温度稍低，保证专业性和遵守约束
            messages=[
                {"role": "system", "content": system_prompt},
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