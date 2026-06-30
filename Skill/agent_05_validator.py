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
# 2. Agent 5 系统指令 (专注定义高维核验锚点)
# ==========================================
SYSTEM_PROMPT = """
You are a Senior Audit Manager and Sandbox Evaluation Designer.
Your task is to review proposed workflow nodes (which contain `sandbox_role` and `data_profile`) and generate an `evaluation_anchor` for each node.

Since the actual physical data and baseline answers will be generated dynamically later in a Sandbox (the "Golden Run"), you CANNOT hardcode specific numerical answers or static checking rules. Instead, you must define WHAT needs to be checked against the Golden Run result.

# The Evaluation Anchor Categories
You MUST classify each node into one of these 4 categories and write the corresponding `assertion_logic`:

1. **Fact (事实维度)**: 
   - Used for nodes calculating specific metrics. 
   - Logic: Compare the examinee's final number against the Golden Run.
   - Example: "Verify that the final calculated metric matches the exact numerical result produced by the Golden Solver."

2. **Reasoning (推理维度)**:
   - Used for nodes where business logic (like tax deduction order or currency conversion) is implicitly required but not explicitly given in the prompt.
   - Example: "Check if the model correctly deduced the local tax deduction order, matching the Golden Run's intermediate column values."

3. **Robustness (鲁棒性维度)**:
   - MUST be used for "trap" nodes (where dirty data is injected).
   - Logic: Ensure the pipeline doesn't crash and anomalies are handled.
   - Example: "Verify that downstream aggregations do not propagate #DIV/0! or NaN, gracefully handling the injected null values while preserving valid rows."

4. **Compliance (合规/全局约束)**:
   - Used for "global" or "export" nodes regarding file formats and naming.
   - Example: "Assert file_exists('{deliverable_file}') in the final submission."

# OUTPUT FORMAT
- You must return the original JSON array exactly as provided, preserving ALL fields (`skill_id`, `ports`, `sandbox_role`, `data_profile`, etc.).
- You will ADD an `"evaluation_anchor"` object inside the `"semantics"` object of each node. DO NOT output legacy `"rubrics"` arrays.
- The `"evaluation_anchor"` MUST have two keys: `"category"` (from the 4 above) and `"assertion_logic"` (a professional English string).
- **STRICT PARAMETERIZATION RULE**: Do NOT hardcode specific table names or column names if they are parameterized. Use placeholders `{}` that match the keys in the node's `data_profile`.

Example insertion inside the node:
"semantics": {
  "intents": ["..."],
  "evaluation_anchor": {
    "category": "Robustness",
    "assertion_logic": "The Golden Solver handles the {trap_count} null anomalies gracefully..."
  }
}
"""


def run_agent_5_validator(upgraded_nodes: list) -> list:
    print(f"Agent 5 启动 (高维核验锚点设计师) | 引擎: {model_name}")
    print("-" * 50)

    # 转换为字符串喂给大模型 (修改了提示语)
    user_content = f"Please process these nodes. Keep all original fields (like data_profile and sandbox_role) and inject the 'evaluation_anchor' into the semantics object:\n{json.dumps(upgraded_nodes, indent=2)}"

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
        print("\nAgent 5 核验锚点设计完成！输出可入库 JSON：\n")
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
            return json_data
        elif isinstance(json_data, dict):
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