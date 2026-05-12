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

log_filename = os.path.join(LOG_DIR, f"agent3_execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(asctime)s - [Agent 3 Tool Call] - %(message)s'
)


def execute_tool_with_log(func_name: str, kwargs: dict) -> str:
    """拦截器：记录大模型的动作，并调用本地 Python 函数"""
    logging.info(f"⚡ LLM 请求调用: {func_name} | 参数: {json.dumps(kwargs, ensure_ascii=False)}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚡ 执行工具: {func_name}")

    try:
        # 使用反射动态调用 skill_api_tools 中的函数
        func = getattr(skill_api_tools, func_name)
        result = func(**kwargs)
        logging.info(f"✅ 执行结果: {result}")
        print(f"  └─ 结果: {str(result)[:100]}...")  # 终端只打印前100个字符防刷屏
        return str(result)
    except Exception as e:
        error_msg = f"Error executing {func_name}: {str(e)}"
        logging.error(error_msg)
        print(f"  └─ ❌ 报错: {error_msg}")
        return error_msg


# ==========================================
# 2. 定义提供给 LLM 的工具清单 (JSON Schema)
# ==========================================
# 这里将你 skill_api_tools 里的函数翻译成 OpenAI 认识的格式
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "list_available_operators",
            "description": "查询系统当前支持哪些底层算子。在决定选用哪个 operator_class 之前必须调用此工具。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_operator",
            "description": "【高权限工具】当 list_available_operators 返回的算子中没有任何一个能实现当前业务时，调用此工具动态生成一段 Python 算子类代码并注入到底层。",
            "parameters": {
                "type": "object",
                "properties": {
                    "operator_name": {"type": "string",
                                      "description": "算子类名，必须以 Operator 结尾（如 FilterOperator）"},
                    "source_code": {"type": "string",
                                    "description": "完整的 Python 类源代码。必须继承 SkillNode 且包含 on_join_graph 或 register_data_operations 方法。"}
                },
                "required": ["operator_name", "source_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": "通过关键字或端口在题库中查重，检查是否已经有同类考点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "业务关键字"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_skill",
            "description": "在系统中正式创建一个新的考点并写入 JSON 题库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "skill_name": {"type": "string"},
                    "node_type": {"type": "string", "enum": ["base", "mutator", "trap", "global"]},
                    "operator_class": {"type": "string"},
                    "requires": {"type": "array", "items": {"type": "string"}},
                    "provides": {"type": "array", "items": {"type": "string"}},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "intents": {"type": "array", "items": {"type": "string"}},
                    "rubrics": {"type": "array", "items": {"type": "string"}},
                    "data_params": {"type": "object"}
                },
                "required": ["skill_id", "skill_name", "node_type", "operator_class", "requires", "provides", "intents",
                             "rubrics", "data_params"]
            }
        }
    }
]

# ==========================================
# 3. Agent 3 主控逻辑 (The ReAct Loop)
# ==========================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
model_name = os.getenv("OPENAI_MODEL", "gemini-3-pro-preview")

SYSTEM_PROMPT = """
你是一位顶尖的“图谱入库架构师兼 Python 研发工程师”。你的任务是将上游传来的具象业务描述，转化为抽象考点并物理存入系统。

【执行铁律 (必须按顺序进行思考与动作)】：
1. 【查算子】：面对一个步骤，首先调用 `list_available_operators` 查看当前库中有哪些算子。
2. 【写算子】(按需触发)：如果需要的算子（比如 FilterOperator）不存在，绝不能乱编名字！你必须调用 `create_operator` 亲自编写一段使用 Pandas 语法的 Python 算子类并注入系统。
3. 【查重】：调用 `search_skills` 检查图谱里是否已经有了类似功能的节点。
4. 【入库】：如果无重复，提取具体数值放入 `data_params`，把描述变成占位符模板，调用 `create_skill` 正式建点。

注意：处理完所有输入步骤后，回复“所有步骤处理完毕”。
"""


def run_agent_3_workflow(enriched_steps: list):
    print(f"Agent 3 启动 | 引擎: {model_name}")
    print("-" * 50)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",
         "content": f"请逐一处理以下带有端口的步骤并建库：\n{json.dumps(enriched_steps, ensure_ascii=False)}"}
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

            # 如果大模型想要调用工具
            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)

                    # 拦截并执行本地函数
                    function_response = execute_tool_with_log(func_name, func_args)

                    # 把本地函数的执行结果“喂”回给大模型
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": func_name,
                        "content": function_response,
                    })
            else:
                # 大模型没有调用工具，说明它认为任务完成了，输出了普通文本
                print("\nAgent 3 报告任务完成：")
                print(response_message.content)
                break

        except Exception as e:
            print(f"\nAPI 请求报错: {e}")
            break


# ==========================================
# 运行测试
# ==========================================
if __name__ == "__main__":
    # 使用 Agent 2 输出的那 4 个步骤进行测试
    agent_2_output = [
        {
            "action_type": "Filter",
            "description": "筛选出举办国家为法国或德国的场次记录。",
            "requires": ["Dimension:Region"],
            "provides": []
        }
    ]

    run_agent_3_workflow(agent_2_output)