import os
import json
import logging
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

import skill_api_tools

# ==========================================
# 1. 拦截器与日志系统配置
# ==========================================
LOG_DIR = os.path.join(os.path.dirname(__file__), "agent_logs")
os.makedirs(LOG_DIR, exist_ok=True)

log_filename = os.path.join(LOG_DIR, f"agent6_registrar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(asctime)s - [Agent 6 Tool Call] - %(message)s'
)


def execute_tool_with_log(func_name: str, kwargs: dict) -> str:
    logging.info(f"⚡ LLM 请求调用: {func_name} | 参数: {json.dumps(kwargs, ensure_ascii=False)}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚡ 执行工具: {func_name}")

    try:
        func = getattr(skill_api_tools, func_name)
        result = func(**kwargs)
        logging.info(f"执行结果: {result}")
        print(f"  └─ 结果: {str(result)[:100]}...")
        return str(result)
    except Exception as e:
        error_msg = f"Error executing {func_name}: {str(e)}"
        logging.error(error_msg)
        print(f"  └─ 报错: {error_msg}")
        return error_msg


# ==========================================
# 2. Agent 6 专属工具箱 (仅限查重与写入)
# ==========================================
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": "通过关键字在题库中查重，确保不会重复创建相同的考点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "考点的业务关键字"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_skill",
            "description": "在系统中正式创建一个新的考点并物理写入 JSON 题库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "skill_name": {"type": "string"},
                    "node_type": {"type": "string", "enum": ["base", "mutator", "trap", "global"]},
                    "operator_class": {"type": "string"},
                    "requires": {"type": "array", "items": {"type": "string"},
                                 "description": "从节点的 ports.requires 中提取"},
                    "provides": {"type": "array", "items": {"type": "string"},
                                 "description": "从节点的 ports.provides 中提取"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "intents": {"type": "array", "items": {"type": "string"}},
                    "rubrics": {"type": "array", "items": {"type": "string"}},
                    "data_params": {"type": "object"}
                },
                "required": ["skill_id", "skill_name", "node_type", "operator_class", "requires", "provides",
                             "keywords", "intents", "rubrics", "data_params"]
            }
        }
    }
]

# ==========================================
# 3. Agent 6 主控逻辑
# ==========================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
model_name = os.getenv("OPENAI_MODEL", "gemini-3-pro-preview")


SYSTEM_PROMPT = """
You are the Database Registrar (Agent 6). You will receive an array of fully validated, perfect JSON nodes.

Your MISSION is to commit these nodes to the database safely.

# Execution Workflow (STRICT RULES):
1. **Deduplication First**: For EVERY node, you MUST first call `search_skills` to check if a node with this specific `skill_id` or business logic already exists.
2. **Handling Duplicates (CRITICAL)**: If the search reveals that the skill ALREADY EXISTS, you MUST NOT call `create_skill`! Simply acknowledge its existence, retain its `skill_id` in your mind, and move on to the next node.
3. **Creation**: ONLY if the search confirms the node does NOT exist, extract `"requires"` and `"provides"` as flat arrays, and call `create_skill`.

Do NOT attempt to connect the nodes. 
Once all nodes are processed (either successfully skipped or created), reply EXACTLY with "ALL NODES REGISTERED SUCCESSFULLY".
"""



def run_agent_6_registrar(finalized_nodes: list) -> list:
    print(f"Agent 6 启动 (查重与注册员) | 引擎: {model_name}")
    print("-" * 50)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",
         "content": f"Please register the following finalized nodes into the database:\n{json.dumps(finalized_nodes, indent=2)}"}
    ]

    while True:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                temperature=0.1
            )

            response_message = response.choices[0].message
            messages.append(response_message)

            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    function_response = execute_tool_with_log(func_name, func_args)
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": func_name,
                        "content": function_response,
                    })
            else:
                print("\nAgent 6 注册完成！考点已全部落盘。")
                print(response_message.content)
                # 注册完成后，将原来的节点原封不动地返回，以便直接传给 Agent 7 去做连线
                return finalized_nodes

        except Exception as e:
            print(f"\nAPI 请求报错: {e}")
            break


# ==========================================
# 运行测试
# ==========================================
if __name__ == "__main__":
    # 模拟输入：Agent 5 刚才输出的完美 JSON 节点
    agent_5_output = [
        {
            "skill_id": "load_festival_transaction_data",
            "skill_name": "Load Festival Transaction Data",
            "node_type": "base",
            "operator_class": "BaseDataGeneratorOperator",
            "keywords": [
                "Load",
                "Festival",
                "Transaction",
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
                "intents": [
                    "Load the initial dataset containing music festival transaction records."
                ],
                "rubrics": []
            },
            "data_params": {
                "table_name": "festival_transactions",
                "output_columns": [
                    {
                        "name": "PreTax",
                        "generator_type": "float_range",
                        "kwargs": {
                            "min": 10.0,
                            "max": 500.0
                        }
                    },
                    {
                        "name": "Region",
                        "generator_type": "categorical",
                        "kwargs": {
                            "categories": [
                                "France",
                                "Germany",
                                "UK",
                                "Spain",
                                "Italy"
                            ]
                        }
                    }
                ]
            }
        },
        {
            "skill_id": "handle_null_revenue_records",
            "skill_name": "Handle Null Revenue Records",
            "node_type": "trap",
            "operator_class": "CellPerturbationOperator",
            "keywords": [
                "Null",
                "Revenue",
                "Data Cleaning"
            ],
            "ports": {
                "requires": [
                    "Financial:PreTax"
                ],
                "provides": []
            },
            "semantics": {
                "intents": [
                    "Identify and process records where the '{target_field}' field contains null values."
                ],
                "rubrics": [
                    "Verify that exactly 5 records in the 'PreTax' column have been set to null."
                ]
            },
            "data_params": {
                "target_field": "PreTax",
                "perturbation_mode": "to_null",
                "trap_count": 5
            }
        },
        {
            "skill_id": "filter_host_country",
            "skill_name": "Filter Host Country",
            "node_type": "mutator",
            "operator_class": "CategoricalFilterOperator",
            "keywords": [
                "Filter",
                "Country",
                "Region"
            ],
            "ports": {
                "requires": [
                    "Dimension:Region"
                ],
                "provides": []
            },
            "semantics": {
                "intents": [
                    "Filter the records where the host country is either '{country_1}' or '{country_2}'."
                ],
                "rubrics": [
                    "Verify that all remaining records in the 'Region' column are either 'France' or 'Germany'."
                ]
            },
            "data_params": {
                "country_1": "France",
                "country_2": "Germany"
            }
        },
        {
            "skill_id": "calculate_compliant_revenue",
            "skill_name": "Calculate Compliant Revenue",
            "node_type": "mutator",
            "operator_class": "ColumnArithmeticOperator",
            "keywords": [
                "Calculate",
                "Revenue",
                "Compliance",
                "Multiplier"
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
                    "Multiply the '{source_col}' by a factor of {multiplier} to generate a new column named '{new_col}'."
                ],
                "rubrics": [
                    "Verify that the 'CompliantAmount' column is equal to the 'PreTax' column multiplied by 1.05."
                ]
            },
            "data_params": {
                "source_col": "PreTax",
                "multiplier": 1.05,
                "new_col": "CompliantAmount"
            }
        }
    ]

    run_agent_6_registrar(agent_5_output)