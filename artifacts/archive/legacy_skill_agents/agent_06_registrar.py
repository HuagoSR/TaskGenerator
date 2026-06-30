import os
import json
import logging
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

from task_generator.Skill import skill_api_tools
# ==========================================
# 1. 鎷︽埅鍣ㄤ笌鏃ュ織绯荤粺閰嶇疆
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
    logging.info(f"鈿?LLM 璇锋眰璋冪敤: {func_name} | 鍙傛暟: {json.dumps(kwargs, ensure_ascii=False)}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 鈿?鎵ц宸ュ叿: {func_name}")

    try:
        func = getattr(skill_api_tools, func_name)
        result = func(**kwargs)
        logging.info(f"鎵ц缁撴灉: {result}")
        print(f"  鈹斺攢 缁撴灉: {str(result)[:100]}...")
        return str(result)
    except Exception as e:
        error_msg = f"Error executing {func_name}: {str(e)}"
        logging.error(error_msg)
        print(f"  鈹斺攢 鎶ラ敊: {error_msg}")
        return error_msg

    # ==========================================


# 2. Agent 6 涓撳睘宸ュ叿绠?(宸查槈鍓插啓鍏ユ潈闄愶紝浠呴檺鏌ラ噸)
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
# 3. Agent 6 涓绘帶閫昏緫
# ==========================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
model_name = os.getenv("OPENAI_MODEL", "gemini-3-pro-preview")

# 璋冩暣 Prompt锛屽憡鐭ュ畠鐜板湪鏀跺埌鐨勬槸瀹屾暣鐨勬暟鎹畾涔?
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
    mode_str = "鍚敤 LLM 鏌ラ噸" if enable_deduplication else "璺宠繃鏌ラ噸锛岀洿鎺ュ己琛屽叆搴?
    print(f"Agent 6 鍚姩 (娉ㄥ唽鍛? | 妯″紡: {mode_str} | 寮曟搸: {model_name}")
    print("-" * 50)

    registered_nodes = []

    for perfect_node in finalized_nodes:
        skill_id = perfect_node.get("skill_id")
        skill_name = perfect_node.get("skill_name")

        # ==========================================
        # 鏍稿績鍒嗘敮锛氭槸鍚﹀惎鐢ㄦ煡閲?
        # ==========================================
        if not enable_deduplication:
            print(f"\n> [閫熼€氭ā寮廬 鍑嗗鍐欏叆鑰冪偣: {skill_name} ({skill_id})")
            decision = {"is_duplicate": False, "reason": "Deduplication disabled by default"}
        else:
            print(f"\n> [瀹℃煡妯″紡] 姝ｅ湪瀹℃煡鍊欓€夎€冪偣: {skill_name} ({skill_id})")
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
                    print(f"\nAPI 璇锋眰鎶ラ敊: {e}")
                    final_decision_str = '{"is_duplicate": false, "reason": "API Exception Fallback"}'
                    break

                    # --- Python 鏈湴瑙ｆ瀽瑁佸垽缁撴灉 ---
            try:
                decision = json.loads(final_decision_str)
            except json.JSONDecodeError:
                print(f"Agent 6 杩斿洖浜嗛潪鏍囧噯 JSON銆傚師濮嬪唴瀹? {final_decision_str}")
                decision = {"is_duplicate": False, "reason": "Fallback to pass"}

        # ==========================================
        # 鏈湴缁勮涓庡叆搴撻€昏緫 (鍏叡璺緞)
        # ==========================================
        if decision.get("is_duplicate") is True:
            print(f"鏌ラ噸椹冲洖锛佹嫤鎴師鍥? {decision.get('reason')}")
        else:
            if enable_deduplication:
                print(f"鏌ラ噸閫氳繃锛佸噯璁告斁琛屻€?{decision.get('reason')})")

            try:
                # 鏍稿績淇锛氫笉瑕佸啀灞曞钩 Ports锛岀洿鎺ユ妸瀹屾暣鐨勫０鏄庡紡鑺傜偣閫忎紶缁欏簳灞傚伐鍏?
                execute_tool_with_log("create_skill", perfect_node.copy())

                registered_nodes.append(perfect_node)
                print(f"[{skill_id}] 宸叉垚鍔熷瓨鍏ユ暟鎹簱銆係chema 瀹屾暣鏃犳崯銆?)
            except Exception as e:
                print(f"褰撴墽琛屾湰鍦版敞鍐屾椂鍙戠敓閿欒: {e}")

    print("\n=== Agent 6 娉ㄥ唽娴佺▼鍏ㄩ儴缁撴潫 ===")
    return finalized_nodes
# ==========================================
# 杩愯娴嬭瘯
# ==========================================
if __name__ == "__main__":
    # 妯℃嫙杈撳叆锛欰gent 5 鍒氭墠杈撳嚭鐨勫畬缇?JSON 鑺傜偣
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
