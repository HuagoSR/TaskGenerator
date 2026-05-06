import json
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any


class StirrupRubricItem(BaseModel):
    """严格贴合 Stirrup 评测框架底层要求的单一评分项"""
    score: int = Field(..., description="该规则的分值")
    criterion: str = Field(..., description="评分标准的具体描述")
    required: Optional[bool] = None
    rubric_item_id: str = Field(..., description="规则的唯一标识符 (例如 G_001, R_005)")
    author_type: str = Field(default="model")
    tags: List[str] = Field(default_factory=lambda: ["outcome"], description="如 outcome, quality_gate, holistic")
    read_only: Optional[bool] = None
    form_content: Optional[Any] = None


# ==========================================
# 语义大纲 (Semantic Brief)
# ==========================================
class SemanticBrief(BaseModel):
    """交给 LLM 编译器 (LLM-as-a-Compiler) 进行重写的核心要素"""
    role: str = Field(default="Financial Auditor", description="要求大模型扮演的业务角色")
    task_goal: str = Field(..., description="宏观任务目标，如 'Prepare a structured Excel profit and loss report'")
    input_files: List[str] = Field(default_factory=list, description="涉及到的参考文件列表")

    # 柔性部分：LLM 可以自由发挥、串联、设定情景的业务逻辑
    business_intents: List[str] = Field(default_factory=list, description="业务逻辑与推导步骤")

    # 刚性部分：LLM 绝对不能篡改的底线
    hard_constraints: List[str] = Field(default_factory=list, description="必须一字不差附在提示词末尾的硬性要求")

    def to_llm_prompt(self) -> str:
        """生成喂给 LLM 编译器的 System Prompt"""
        return (
            f"You are acting as a task designer. Write a professional task briefing for a {self.role}.\n"
            f"Goal: {self.task_goal}\n\n"
            f"Business Intents (Weave these smoothly into the narrative):\n"
            f"{chr(10).join(['- ' + intent for intent in self.business_intents])}\n\n"
            f"Hard Constraints (CRITICAL: MUST be listed EXACTLY as bullet points at the end of your prompt. DO NOT rephrase these):\n"
            f"{chr(10).join(['- ' + c for c in self.hard_constraints])}"
        )


# ==========================================
# TaskSchema
# ==========================================
class TaskSchema(BaseModel):
    """完全兼容 dataset_row.json 的最终交付骨架"""
    task_id: str
    sector: str = Field(..., description="行业领域")
    occupation: str = Field(default="Tax Auditor")
    motif: str = Field(default="extract-organize-calculate")
    prompt: str = Field(..., description="最终任务题干")

    reference_files: List[str] = Field(default_factory=list)
    deliverable_files: List[str] = Field(default_factory=list)

    rubric: str = Field(..., description="人类可读的 Markdown 格式评分标准")
    rubric_json: str = Field(..., description="被 stringify 的 StirrupRubricItem JSON 列表")

    extra: Dict[str, Any] = Field(default_factory=dict, description="存放 ground_truth 和审计信息")

    @classmethod
    def create_package(cls, rubrics: List[StirrupRubricItem], **kwargs):
        # 1. 自动生成 Markdown
        if "rubric" not in kwargs:
            rubric_md = "\n".join([f"- [+{r.score}分] {r.criterion}" for r in rubrics])
            kwargs["rubric"] = rubric_md

        # 2. 自动处理 Stirrup 的 JSON 字符串化要求
        rubric_dicts = [r.model_dump() for r in rubrics]
        kwargs["rubric_json"] = json.dumps(rubric_dicts, ensure_ascii=False)

        return cls(**kwargs)

    def export_to_json(self) -> str:
        """导出为 dataset_row.json 格式"""
        return self.model_dump_json(indent=2)