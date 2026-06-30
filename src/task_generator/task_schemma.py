import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class StirrupRubricItem(BaseModel):
    """Rubric item compatible with the Stirrup/rw-task row format."""

    score: int = Field(..., description="Point value for this rubric item.")
    criterion: str = Field(..., description="Concrete grading criterion.")
    required: Optional[bool] = None
    rubric_item_id: str = Field(..., description="Stable rubric item id, such as G_001 or R_005.")
    author_type: str = Field(default="model")
    tags: List[str] = Field(default_factory=lambda: ["outcome"], description="Rubric tags.")
    read_only: Optional[bool] = None
    form_content: Optional[Any] = None


class SemanticBrief(BaseModel):
    """Brief passed to an LLM-as-compiler prompt writer."""

    role: str = Field(default="Financial Auditor", description="Professional role for the task actor.")
    task_goal: str = Field(..., description="High-level task goal.")
    input_files: List[str] = Field(default_factory=list, description="Reference files used by the task.")
    business_intents: List[str] = Field(default_factory=list, description="Narrative goals and reasoning steps.")
    hard_constraints: List[str] = Field(default_factory=list, description="Constraints that must be preserved exactly.")

    def to_llm_prompt(self) -> str:
        """Render the semantic brief as a system prompt for prompt compilation."""

        return (
            f"You are acting as a task designer. Write a professional task briefing for a {self.role}.\n"
            f"Goal: {self.task_goal}\n\n"
            f"Business Intents (Weave these smoothly into the narrative):\n"
            f"{chr(10).join(['- ' + intent for intent in self.business_intents])}\n\n"
            f"Hard Constraints (CRITICAL: MUST be listed EXACTLY as bullet points at the end of your prompt. "
            f"DO NOT rephrase these):\n"
            f"{chr(10).join(['- ' + c for c in self.hard_constraints])}"
        )


class TaskSchema(BaseModel):
    """Final dataset-row shape used by legacy task export scripts."""

    task_id: str
    sector: str = Field(..., description="Industry or sector.")
    occupation: str = Field(default="Tax Auditor")
    motif: str = Field(default="extract-organize-calculate")
    prompt: str = Field(..., description="Final task prompt.")
    reference_files: List[str] = Field(default_factory=list)
    deliverable_files: List[str] = Field(default_factory=list)
    rubric: str = Field(..., description="Human-readable Markdown rubric.")
    rubric_json: str = Field(..., description="Stringified list of StirrupRubricItem records.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Ground truth and audit metadata.")

    @classmethod
    def create_package(cls, rubrics: List[StirrupRubricItem], **kwargs):
        if "rubric" not in kwargs:
            kwargs["rubric"] = "\n".join([f"- [+{r.score} pts] {r.criterion}" for r in rubrics])

        kwargs["rubric_json"] = json.dumps([r.model_dump() for r in rubrics], ensure_ascii=False)
        return cls(**kwargs)

    def export_to_json(self) -> str:
        """Export in dataset_row.json-compatible JSON form."""

        return self.model_dump_json(indent=2)
