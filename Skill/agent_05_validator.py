import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# ==========================================
# 1. 基础配置
# ==========================================
load_dotenv()
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)
model_name = os.getenv("OPENAI_MODEL", "gemini-3-pro-preview")

# ==========================================
# 2. Agent 5 系统指令 (专注对齐与写 Rubric)
# ==========================================
SYSTEM_PROMPT = """
You are the RL Reward Designer & Schema Validator. You will receive a JSON array of "proposed_nodes" that have already been assigned physical Python operators.

Your ONLY MISSION is to finalize the semantics and generate Reinforcement Learning (RL) reward rules. You DO NOT execute code or save to databases.

# Execution Workflow:
1. **Alignment Check (Crucial)**: 
   - Look at the keys in `"data_params"`. 
   - Look at the placeholders in `"intents"` (e.g., `{multiplier}`).
   - If they do not match perfectly, REWRITE the `"intents"` string so its placeholders exactly match the keys in `"data_params"`.

2. **RL Rubrics Generation (Reward Shaping)**:
   - You must generate a `"rubrics"` array inside `"semantics"`.
   - For `base` nodes: The rubric MUST BE EMPTY (`[]`). Loading data is a prerequisite, not a scorable skill.
   - For `trap` and `mutator` nodes: Write highly objective, code-verifiable rubrics. Think like a Python `assert` statement. (e.g., "Verify df['output'] == df['input'] * 1.05").

3. **Format Validation**: Ensure the output strictly follows the required JSON schema, preserving `"operator_class"`, `"ports"`, etc.

# Output Rule:
Reply ONLY with the finalized JSON object. No markdown, no conversational text.
{
  "proposed_nodes": [ ... ]
}
"""


def run_agent_5_validator(upgraded_nodes: list) -> list:
    print(f"Agent 5 启动 (奖励设计与校验师) | 引擎: {model_name}")
    print("-" * 50)

    # 转换为字符串喂给大模型
    user_content = f"Please align placeholders and generate RL rubrics for these nodes:\n{json.dumps(upgraded_nodes, indent=2)}"

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.1  # 必须保持极低温度以确保格式与逻辑严谨
        )

        content = response.choices[0].message.content
        print("\nAgent 5 校验与奖励设计完成！输出可入库 JSON：\n")
        print(content)

        # 清理并解析 JSON
        clean_content = content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:-3].strip()
        elif clean_content.startswith("```"):
            clean_content = clean_content[3:-3].strip()

        json_data = json.loads(clean_content)
        return json_data.get("proposed_nodes", [])

    except Exception as e:
        print(f"\nAPI 请求或解析报错: {e}")
        return []


# ==========================================
# 运行测试
# ==========================================
if __name__ == "__main__":
    # 模拟输入：Agent 4 刚才生成的带有 operator 的 JSON
    agent_4_output = [
    {
      "skill_id": "load_festival_transactions",
      "skill_name": "Load Festival Transactions",
      "node_type": "base",
      "operator": "BaseDataGeneratorOperator",
      "keywords": [
        "Load",
        "Festival",
        "Transactions",
        "Dataset"
      ],
      "ports": {
        "requires": [],
        "provides": [
          "Financial:PreTax",
          "Dimension:Region"
        ]
      },
      "semantics": {
        "deliverables": [
          "Festival_Compliance_Result.csv"
        ],
        "intents": [
          "Load the initial music festival transaction dataset from '{input_file}'.",
          "Export the final processed result to '{output_file}'."
        ]
      },
      "data_params": {
        "table_name": "festival_transactions",
        "output_columns": [
          {
            "name": "base_ticket_revenue",
            "generator_type": "uniform",
            "kwargs": {
              "min": 100.0,
              "max": 1000.0
            }
          },
          {
            "name": "host_country",
            "generator_type": "categorical",
            "kwargs": {
              "categories": [
                "France",
                "Germany",
                "USA",
                "UK"
              ]
            }
          }
        ],
        "input_file": "festival_transactions.csv",
        "output_file": "Festival_Compliance_Result.csv",
        "suggested_row_counts": {
          "festival_transactions.csv": 100
        }
      }
    },
    {
      "skill_id": "handle_null_revenue",
      "skill_name": "Handle Null Revenue",
      "node_type": "trap",
      "operator": "CellPerturbationOperator",
      "keywords": [
        "Null",
        "Missing",
        "Revenue",
        "Handle"
      ],
      "ports": {
        "requires": [
          "Financial:PreTax"
        ],
        "provides": []
      },
      "semantics": {
        "intents": [
          "Handle records in the raw data where the '{target_column}' field contains null values."
        ]
      },
      "data_params": {
        "target_column": "base_ticket_revenue",
        "perturbation_mode": "to_null",
        "trap_count": 5
      }
    },
    {
      "skill_id": "filter_host_country",
      "skill_name": "Filter Host Country",
      "node_type": "mutator",
      "operator": "FilterOperator",
      "keywords": [
        "Filter",
        "Country",
        "France",
        "Germany"
      ],
      "ports": {
        "requires": [
          "Dimension:Region"
        ],
        "provides": []
      },
      "semantics": {
        "intents": [
          "Filter the records where '{filter_col}' is either '{country_1}' or '{country_2}'."
        ]
      },
      "data_params": {
        "filter_col": "host_country",
        "country_1": "France",
        "country_2": "Germany"
      }
    },
    {
      "skill_id": "calculate_compliant_revenue",
      "skill_name": "Calculate Compliant Revenue",
      "node_type": "mutator",
      "operator": "ColumnArithmeticOperator",
      "keywords": [
        "Multiply",
        "Revenue",
        "Compliant",
        "Calculate"
      ],
      "ports": {
        "requires": [
          "Financial:PreTax"
        ],
        "provides": [
          "Financial:CompliantAmount"
        ]
      },
      "semantics": {
        "intents": [
          "Multiply the '{source_col}' by {multiplier} to generate a new column named '{new_col}'."
        ]
      },
      "data_params": {
        "source_col": "base_ticket_revenue",
        "multiplier": 1.05,
        "new_col": "compliant_revenue"
      }
    }
  ]

    final_nodes = run_agent_5_validator(agent_4_output)