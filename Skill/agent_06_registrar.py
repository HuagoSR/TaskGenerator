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


# 2. Agent 6 专属工具箱 (已阉割写入权限，仅限查重)
# ==========================================
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": "Search the database by keyword to check for duplicates to ensure the exact same logic does not exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "The business keyword of the skill node to search for"}
                }
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

# 调整 Prompt，告知它现在收到的是完整的数据定义
SYSTEM_PROMPT = """   
You are the Database Duplication Checker (Agent 6).
You will receive the FULL JSON definition of ONE candidate node at a time (including its schemas, ports, intents, and data_params).

Your ONLY MISSION is to determine if this exact business logic already exists in the database.

# Execution Workflow (STRICT RULES):
1. You MUST use the `search_skills` tool to search the database using the candidate's keywords, intents, or skill_id.
2. Carefully analyze the search results against the candidate's full configuration to determine if it is a true duplicate.
3. You MUST respond with a STRICT JSON object in the following format, and output nothing else:
{
    "is_duplicate": true,  // or false 
    "reason": "Brief explanation of your finding."
}
"""


def run_agent_6_registrar(finalized_nodes: list, enable_deduplication: bool = False) -> list:
    mode_str = "启用 LLM 查重" if enable_deduplication else "跳过查重，直接强行入库"
    print(f"Agent 6 启动 (注册员) | 模式: {mode_str} | 引擎: {model_name}")
    print("-" * 50)

    registered_nodes = []

    for perfect_node in finalized_nodes:
        skill_id = perfect_node.get("skill_id")
        skill_name = perfect_node.get("skill_name")

        # ==========================================
        # 核心分支：是否启用查重
        # ==========================================
        if not enable_deduplication:
            print(f"\n> [速通模式] 准备写入考点: {skill_name} ({skill_id})")
            decision = {"is_duplicate": False, "reason": "Deduplication disabled by default"}
        else:
            print(f"\n> [审查模式] 正在审查候选考点: {skill_name} ({skill_id})")
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",
                 "content": f"Candidate Node Full Definition:\n{json.dumps(perfect_node, indent=2, ensure_ascii=False)}"}
            ]

            while True:
                try:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        tools=tools_schema,
                        tool_choice="auto",
                        temperature=0.1,
                        response_format={"type": "json_object"}
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
                        final_decision_str = response_message.content
                        break

                except Exception as e:
                    print(f"\nAPI 请求报错: {e}")
                    final_decision_str = '{"is_duplicate": false, "reason": "API Exception Fallback"}'
                    break

                    # --- Python 本地解析裁判结果 ---
            try:
                decision = json.loads(final_decision_str)
            except json.JSONDecodeError:
                print(f"Agent 6 返回了非标准 JSON。原始内容: {final_decision_str}")
                decision = {"is_duplicate": False, "reason": "Fallback to pass"}

        # ==========================================
        # 本地组装与入库逻辑 (公共路径)
        # ==========================================
        if decision.get("is_duplicate") is True:
            print(f"查重驳回！拦截原因: {decision.get('reason')}")
        else:
            if enable_deduplication:
                print(f"查重通过！准许放行。({decision.get('reason')})")

            try:
                # 核心修复：不要再展平 Ports，直接把完整的声明式节点透传给底层工具
                execute_tool_with_log("create_skill", perfect_node.copy())

                registered_nodes.append(perfect_node)
                print(f"[{skill_id}] 已成功存入数据库。Schema 完整无损。")
            except Exception as e:
                print(f"当执行本地注册时发生错误: {e}")

    print("\n=== Agent 6 注册流程全部结束 ===")
    return finalized_nodes
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