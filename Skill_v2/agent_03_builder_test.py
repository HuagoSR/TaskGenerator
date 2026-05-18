import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# 1. 基础配置
load_dotenv()
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)
model_name = os.getenv("OPENAI_MODEL", "gemini-3-pro-preview")

# 2. Agent 3 的系统指令 (The Builder & Parameterizer)
SYSTEM_PROMPT_AGENT_3 = """
你是一位底层算子映射与参数化专家 (Operator Architect)。
你会收到一组已经推演好端口的“具象业务步骤”。你的任务是将这些具象的业务描述，转化为可以存入题库的【抽象模板】和【执行参数】。

# 核心任务
对于每一个步骤，你需要做三件事：
1. 【算子匹配】：根据 `action_type` 和业务逻辑，从以下支持的算子中挑选一个：
   - "BaseDataGeneratorOperator" (适用于 Base，生成或加载表)
   - "CellPerturbationOperator" (适用于 Trap，比如处理空值或负数)
   - "ForeignKeyDictionaryOperator" (适用于 Mutate，字典匹配、比例乘法)
2. 【参数提取】：将具象描述中的特定数值（如 1.05）、国家（如法国、德国）、字段名，提取成 JSON 键值对，存入 `data_params` 字典。
3. 【语义抽象】：将原来的具象描述改写成一段英文的 `intents` 模板，以及一个 `rubrics` (评分点)。将原来具体的数值用大括号 `{}` 占位符替代（占位符名称必须与 data_params 中的键对应）。

# Output Format (JSON Mode)
必须输出包含 "skills_draft" 数组的 JSON 对象。格式示例如下：
{
  "skills_draft": [
    {
      "proposed_skill_id": "mut_compliance_tax", // 依据业务取一个英文ID
      "operator_class": "ForeignKeyDictionaryOperator",
      "requires": ["Financial:PreTax"],
      "provides": ["Financial:PostCompliance"],
      "semantics": {
        "intents": ["Multiply the input by the factor defined in '{dict_table_name}' to calculate '{out_result_col}'."],
        "rubrics": ["Verify if the '{out_result_col}' correctly reflects the multiplier for specified regions."]
      },
      "data_params": {
        "dict_table_name": "Compliance_Rates.csv",
        "out_result_col": "Compliance_Revenue",
        "dict_columns": {
          "Region": ["France", "Germany"],
          "Rate": [1.05, 1.05]
        }
      }
    }
  ]
}
"""


def run_builder_dry_run(enriched_steps: list) -> list:
    print(f"Agent 3 [算子匹配与参数化] 正在将具象业务转化为抽象配置... (Model: {model_name})")

    user_content = f"【带端口的具象业务步骤】:\n{json.dumps(enriched_steps, ensure_ascii=False, indent=2)}"

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_AGENT_3},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )

        json_data = json.loads(response.choices[0].message.content)
        return json_data.get("skills_draft", [])

    except Exception as e:
        print(f"API 请求或解析失败: {e}")
        return []


# ==========================================
# 本地测试 (承接 Agent 2 的输出)
# ==========================================
if __name__ == "__main__":
    # 这是刚才 Agent 2 完美输出的带端口数据
    agent_2_output = [
        {
            "action_type": "Base",
            "description": "加载初始的音乐节流水数据集。",
            "requires": [],
            "provides": ["Financial:PreTax", "Dimension:Region"]
        },
        {
            "action_type": "Trap",
            "description": "处理原始数据中收入字段为空值的记录。",
            "requires": ["Financial:PreTax"],
            "provides": []
        },
        {
            "action_type": "Filter",
            "description": "筛选出举办国家为法国或德国的场次记录。",
            "requires": ["Dimension:Region"],
            "provides": []
        },
        {
            "action_type": "Mutate",
            "description": "将基础门票收入乘以1.05，生成名为‘合规后收入’的新列。",
            "requires": ["Financial:PreTax"],
            "provides": ["Financial:PostCompliance"]
        }
    ]

    print("输入：Agent 2 的端口推演结果")
    print("-" * 50)

    draft_skills = run_builder_dry_run(agent_2_output)

    print("\nAgent 3 提炼的入库配置草稿：")
    print(json.dumps(draft_skills, ensure_ascii=False, indent=2))