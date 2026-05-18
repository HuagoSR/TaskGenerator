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
log_filename = os.path.join(LOG_DIR, f"agent4_matcher_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(asctime)s - [Agent 4] - %(message)s'
)


def execute_tool_with_log(func_name: str, kwargs: dict) -> str:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚡ 执行工具: {func_name}")
    try:
        func = getattr(skill_api_tools, func_name)
        result = func(**kwargs)
        if func_name == "request_new_operator":
            print(f"  └─ 结果: 已成功向人类提交开发工单！")
        else:
            print(f"  └─ 结果: 调用成功")
        return str(result)
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"  └─ 报错: {error_msg}")
        return error_msg


# ==========================================
# 2. Agent 4 专属工具箱 (查阅 + 提工单)
# ==========================================
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "list_available_operators",
            "description": "查看系统所有可用的底层 Python 算子。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_operator_source_code",
            "description": "阅读算子源码，对齐 data_params 参数格式。",
            "parameters": {
                "type": "object",
                "properties": {"operator_name": {"type": "string"}},
                "required": ["operator_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_new_operator",
            "description": "如果没有任何现有算子满足需求，调用此工具向人类工程师发起求助工单！",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent_description": {"type": "string", "description": "详细描述你想实现什么业务逻辑"},
                    "proposed_data_params": {"type": "object", "description": "你希望这个新算子接受什么参数结构"},
                    "required_pandas_logic": {"type": "string",
                                              "description": "提示人类这是属于造基础数据的(Scenario A)，还是变异计算的(Scenario B)"}
                },
                "required": ["intent_description", "proposed_data_params", "required_pandas_logic"]
            }
        }
    }
]

# ==========================================
# 3. Agent 4 主控逻辑
# ==========================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
model_name = os.getenv("OPENAI_MODEL", "gemini-3-pro-preview")

SYSTEM_PROMPT = """
You are the Operator Matcher & Evaluator (Agent 4).
You DO NOT write Python code. Your job is to match JSON nodes to existing classes, or request human help.

# WORKFLOW:
1. Call `list_available_operators`.
2. For each node, if a class matches, call `get_operator_source_code` to format `data_params` exactly as the source code expects.
3. **CRITICAL (HUMAN-IN-THE-LOOP)**: If NO existing operator fits, you MUST call `request_new_operator` to submit a ticket to the human dev team. 
   - After submitting the ticket, you MUST set `"operator_class": "PENDING_HUMAN_REVIEW"` for that specific node in the JSON.
   - Leave its `data_params` exactly as they were proposed.

# OUTPUT RULE:
Reply ONLY with the upgraded JSON object. No markdown, no conversational text.
{"proposed_nodes": [...]}
"""


def run_agent_4_matcher(abstracted_nodes: list) -> list:
    print(f"Agent 4 启动 (算子匹配与工单派发) | 引擎: {model_name}")
    print("-" * 50)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",
         "content": f"Please process this array and assign operators or request human help:\n{json.dumps(abstracted_nodes, indent=2)}"}
    ]

    while True:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                temperature=0.0  # 匹配与派单必须绝对严谨
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
                        "content": function_response
                    })
            else:
                print("\nAgent 4 匹配/派单处理完成！")
                content = response_message.content.strip()
                if content.startswith("```json"):
                    content = content[7:-3].strip()
                elif content.startswith("```"):
                    content = content[3:-3].strip()

                try:
                    return json.loads(content).get("proposed_nodes", [])
                except json.JSONDecodeError as e:
                    print(f"JSON 解析失败: {e}")
                    return abstracted_nodes

        except Exception as e:
            print(f"\nAPI 请求报错: {e}")
            return abstracted_nodes


# ==========================================
# 运行测试
# ==========================================
if __name__ == "__main__":
    # 模拟输入 Agent 3 的输出，其中包含一个目前没有算子支持的业务
    mock_agent_3_output = [
        {
            "skill_id": "filter_host_country",
            "skill_name": "Filter Host Country",
            "node_type": "mutator",
            "keywords": ["Filter", "Country"],
            "ports": {
                "requires": ["Dimension:Region"],
                "provides": []
            },
            "semantics": {
                "intents": ["Filter the records to only include host countries present in {allowed_values}."]
            },
            "data_params": {
                "allowed_values": ["France", "Germany"]
            }
        },
        {
            "skill_id": "apply_fourier_transform",
            "skill_name": "Apply Fourier Transform",
            "node_type": "mutator",
            "keywords": ["Math", "Fourier", "Transform"],
            "ports": {
                "requires": ["Financial:DailyRevenue"],
                "provides": ["Financial:FrequencyDomain"]
            },
            "semantics": {
                "intents": ["Apply a Fast Fourier Transform to the '{input_col}' and store it in '{output_col}'."]
            },
            "data_params": {
                "input_col": "daily_revenue",
                "output_col": "fft_result"
            }
        }
    ]

    print("输入：Agent 3 抽象后的草稿数据 (包含一个常规业务，一个特殊业务)")
    print("-" * 50)

    processed_nodes = run_agent_4_matcher(mock_agent_3_output)

    print("\n最终输出的 JSON 状态：")
    print(json.dumps(processed_nodes, ensure_ascii=False, indent=2))