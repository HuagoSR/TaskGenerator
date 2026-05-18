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

# 2. Agent 3 的严格系统指令
SYSTEM_PROMPT = """
You are an expert Data Pipeline Architect. Your sole responsibility is to translate and abstract concrete Chinese business requirements into a strict, parameterized ENGLISH JSON schema.

#  VFS DOMAIN IRON RULES (CRITICAL) 
1. **File Extensions**: ANY table name or file name MUST end with `.csv` or `.xlsx` (e.g., `festival_transactions.csv`). Never use a raw string without an extension.
2. **Base Node Mandates**: If the `node_type` is `"base"`, you MUST include two specific fields in the JSON:
   - `semantics.deliverables`: An array of the final output file names the user expects (e.g., `["Festival_Compliance_Result.csv"]`).
   - `data_params.suggested_row_counts`: A dictionary specifying the number of rows to generate for the base table (e.g., `{"festival_transactions.csv": 50}`).
3. **Intent Clarity**: The `intents` for a base node MUST include an instruction to export the final result to the file specified in `deliverables`.

# Core Directives
1. **ALL ENGLISH ONLY**: Everything you output (skill_name, keywords, intents, parameter names, etc.) MUST be translated into professional English.
2. **De-concretization (Parameter Extraction)**: Extract concrete values (e.g., '1.05', 'France', specific column names) into the `data_params` object.
3. **Template Intents**: Write the `intents` using `{}` placeholders. The placeholder names MUST perfectly match the keys in `data_params`.
4. **STRICT EXCLUSIONS**: 
   - DO NOT generate `rubrics` (this is forbidden at this stage).
   - DO NOT generate `operator_class` (this will be handled by a downstream agent).
   - DO NOT generate `possible_successors`.

# Strict JSON Schema Requirement
Your output must be a JSON object containing a "proposed_nodes" array. Every node MUST strictly follow this structure:
{
  "proposed_nodes": [
    {
      "skill_id": "filter_host_country", // Use snake_case
      "skill_name": "Filter Festival Host Country",
      "node_type": "mutator", // Only use: "base", "mutator", "trap", "global"
      "keywords": ["Filter", "Country", "Festival"],
      "ports": {
        "requires": ["Dimension:Region"],
        "provides": []
      },
      "semantics": {
        "intents": ["Filter the records where '{filter_col}' is either '{country_1}' or '{country_2}'."]
      },
      "data_params": {
        "filter_col": "country",
        "country_1": "France",
        "country_2": "Germany"
      }
    }
  ]
}
"""


def run_agent_3_abstractor(enriched_steps: list) -> list:
    print(f"Agent 3 启动 (纯语义抽象与参数化) | 引擎: {model_name}")
    print("-" * 50)

    # 将输入转化为字符串
    user_content = f"Please abstract and parameterize the following steps into the required ENGLISH JSON format:\n{json.dumps(enriched_steps, ensure_ascii=False)}"

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.1  # 必须保持极低温度以确保格式严格
        )

        content = response.choices[0].message.content
        print("\nAgent 3 抽象完成！纯净英文 JSON 模板：\n")
        print(content)

        json_data = json.loads(content)
        return json_data.get("proposed_nodes", [])

    except Exception as e:
        print(f"\nAPI 请求或解析报错: {e}")
        return []


# ==========================================
# 运行测试
# ==========================================
if __name__ == "__main__":
    # 使用 Agent 2 输出的那 4 个步骤进行测试
    agent_2_output = [
        {
            "action_type": "Base",
            "description": "加载初始的音乐节流水数据集。",
            "requires": [],
            "provides": [
                "Financial:PreTax",
                "Dimension:Region"
            ]
        },
        {
            "action_type": "Trap",
            "description": "处理原始数据中收入字段为空值的记录。",
            "requires": [
                "Financial:PreTax"
            ],
            "provides": []
        },
        {
            "action_type": "Filter",
            "description": "筛选出举办国家为法国或德国的场次记录。",
            "requires": [
                "Dimension:Region"
            ],
            "provides": []
        },
        {
            "action_type": "Mutate",
            "description": "将基础门票收入乘以1.05，生成名为‘合规后收入’的新列。",
            "requires": [
                "Financial:PreTax"
            ],
            "provides": [
                "Financial:CompliantAmount"
            ]
        }
    ]

    abstracted_nodes = run_agent_3_abstractor(agent_2_output)