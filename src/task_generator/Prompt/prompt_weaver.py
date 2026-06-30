import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


class PromptWeaver:
    """Wrap raw technical intents into a business-realistic exam prompt."""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv("OPENAI_BASE_URL")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is missing. Check the project .env file.")

        kwargs = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self.client = OpenAI(**kwargs)

    def weave(self, semantic_brief: dict) -> str:
        intents = "\n".join([f"- {item}" for item in semantic_brief["Intents"]])
        constraints = "\n".join([f"- {item}" for item in semantic_brief["Constraints"]])

        master_system_prompt = """
You are an expert exam designer for a top-tier financial audit firm.
Translate raw technical intents into a cohesive, high-level business audit scenario.

Rules:
- Do not give step-by-step programming instructions.
- State business objectives and required output fields separately.
- Preserve exact hard constraints and deliverable names.
- Frame data-quality concerns as business assumptions or notes.
- Require a clear audit trail in the final deliverable.
"""

        user_prompt = (
            f"Raw Technical Intents:\n{intents}\n\n"
            f"Hard Constraints to Include:\n{constraints}\n\n"
            "Please generate the final exam prompt now."
        )

        print(f"[Prompt Weaver] Calling {self.model} to produce a business-realistic prompt...")
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.4,
            messages=[
                {"role": "system", "content": master_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        final_prompt = response.choices[0].message.content
        return self._verify_and_fix(final_prompt, semantic_brief["Constraints"])

    def _verify_and_fix(self, final_prompt: str, constraints: list) -> str:
        missing_constraints = [constraint for constraint in constraints if constraint.strip() not in final_prompt]

        if missing_constraints:
            print("[Prompt Weaver] Missing hard constraints detected; appending them.")
            final_prompt += "\n\n### Critical Auto-Appended Constraints:\n"
            for constraint in missing_constraints:
                final_prompt += f"- {constraint}\n"
        else:
            print("[Prompt Weaver] Hard constraints verified.")

        return final_prompt
