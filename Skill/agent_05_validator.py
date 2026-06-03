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
You are a Senior Audit Manager designing the grading rubric for a complex financial data assessment task.
Your task is to review the proposed workflow steps and generate natural language grading rubrics  that verify if the candidate has successfully completed the task.
Your rubrics must be written in clear, professional, verifiable ENGLISH sentences, exactly like a grading sheet for a human auditor.
Your rubrics must comply with industry standards. In particular, when “node_type” is set to “trap,” you must ensure that your rubric strictly adheres to actual industry standards. If you find it difficult to determine specific data processing methods based on the existing context, you may provide a more general, non-specific rubric; however, you must explicitly state in the generated rubric that it should follow “industry standards” or similar wording.

You must evaluate the FINAL deliverable artifact (e.g., the final CSV/Excel). Generate rubrics across these 4 categories:

1. **Formatting & Structure**:
   - Verify the existence of required columns, specific sheet names, or correct output file names.
   - Example: "The final deliverable contains a column named '{new_col}'."

2. **Mathematical Accuracy & Formulas**:
   - Describe the exact mathematical relationship expected in the final result.
   - Example: "The variance rate in '{new_col}' is correctly computed as the difference between '{col_q3}' and '{col_q2}', divided by '{col_q2}'."

3. **Data Cleaning & Edge Cases**:
   - Verify how dirty data was handled in the final output.
   - Example: "All negative values in '{col_q2}' and '{col_q3}' have been converted to their absolute values."
   - Example: "Rows where '{col_q2}' is zero are handled gracefully without producing #DIV/0! or infinite errors."

4. **Conditional Sampling (OR-Logic)**:
   - For filtering/sampling tasks, use "at least one" or "if present" logic. Do NOT demand that the entire file only contains specific rows.
   - Example: "If there are rows belonging to '{entity_1}', at least one such row is correctly flagged in the final sample."

# OUTPUT FORMAT
- You must return the original JSON array exactly as provided, preserving ALL fields (`skill_id`, `ports`, `data_params`, `operator_class`, etc.).
- You will only ADD or MODIFY the `"rubrics"` array inside the `"semantics"` object of each node.
- Each string inside the `"rubrics"` array must be a professional English sentence following the guidelines above. 
- 🚫 **STRICT PARAMETERIZATION RULE**: You MUST NOT hardcode concrete business values (e.g., file names, specific column names, country names, multipliers) in the rubrics. You MUST use the exact `{placeholder}` keys found in the `data_params` (and `{deliverables}` for file names) to refer to these values.
  - BAD: "The final deliverable is named 'Tour_Financial_Report.xlsx'."
  - GOOD: "The final deliverable is named {deliverables}."
  - BAD: "Verify that the 'CompliantAmount' column..."
  - GOOD: "Verify that the '{new_col}' column..."
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

        # ====== 防呆加固核心逻辑 ======
        if isinstance(json_data, list):
            # 如果大模型直接返回了纯数组，直接透传
            return json_data
        elif isinstance(json_data, dict):
            # 如果大模型听话地返回了包裹对象，安全使用 .get()
            return json_data.get("proposed_nodes", [])
        else:
            return []
        # ==================================

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