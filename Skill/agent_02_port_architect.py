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
PORTS_DICT_PATH = os.path.join(os.path.dirname(__file__), "ports_dict.json")


# 2. 动态加载全局端口字典
def load_ports_dict() -> dict:
    if not os.path.exists(PORTS_DICT_PATH):
        return {"Data:Generic": "Generic data flow port."}
    with open(PORTS_DICT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# 3. Agent 2 的系统指令
SYSTEM_PROMPT_AGENT_2 = """
你是一位顶尖的图谱连线架构师 (Port Architect)。
你的任务是接收一组“原子化数据操作步骤”，并为每一个步骤推演出它需要的输入端口 (requires) 和输出端口 (provides)，从而将它们串联成一个数据流图 (DAG)。

# 核心约束 (Constraints)
1. 【字典优先】：你必须极度优先使用系统当前提供的端口名！
2. 【严格命名】：如果现有字典完全无法表达新业务（比如出现了非财务类的文本、代码等），允许你发明新端口，但必须严格遵循 `Category:Detail` 的大驼峰命名法（如 `Text:RawDocument`, `Code:PythonScript`, `Dimension:EmployeeLevel`）。
3. 【依赖推演】：
   - "Base" (起点节点)：通常是从外部读入数据，它不需要图谱内部的前置输入，因此 requires 应为 []。它必定有 provides。
   - "Mutate" (变换节点)：必须消费前置数据并产生新数据，requires 和 provides 都不能为空。
   - "Filter" / "Trap" (清洗节点)：通常只是破坏或过滤现有数据，不产生新的概念维度，因此 recommends provides 设为 []（除非它显式生成了清洗标记列）。
4. 【上下文连贯】：上一步的 provides，往往是下一步的 requires，注意保持数据流的逻辑闭环。

# 输出规范
必须且只能输出一个合法的 JSON 对象，不要包含任何 Markdown 标记或多余的解释。
{
  "steps": [
    {
      "action_type": "...",
      "description": "...",
      "requires": ["..."],
      "provides": ["..."]
    }
  ]
}
"""


def run_port_inference_agent(sliced_steps: list) -> list:
    print(f"Agent 2 [端口推演] 正在结合全局字典构建数据流... (Model: {model_name})")

    ports_dict = load_ports_dict()

    # 将现有字典和 Agent 1 的输出组装为上下文
    user_content = f"""
    【系统当前已注册的标准端口字典】:
    {json.dumps(ports_dict, ensure_ascii=False, indent=2)}

    【需要推演连线的原子操作步骤】:
    {json.dumps(sliced_steps, ensure_ascii=False, indent=2)}
    """

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_AGENT_2},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.1  # 逻辑推演需要严谨，低温度
        )

        json_data = json.loads(response.choices[0].message.content)
        return json_data.get("steps", [])

    except Exception as e:
        print(f"API 请求或解析失败: {e}")
        return []


# ==========================================
# 本地联动测试 (模拟 Agent 1 -> Agent 2 的流水线)
# ==========================================
if __name__ == "__main__":
    # 这是 Agent 1 之前切片输出的经典案例
    agent_1_output = [
        {
            "action_type": "Base",
            "description": "加载初始的音乐节流水数据集。"
        },
        {
            "action_type": "Trap",
            "description": "处理原始数据中收入字段为空值的记录。"
        },
        {
            "action_type": "Filter",
            "description": "筛选出举办国家为法国或德国的场次记录。"
        },
        {
            "action_type": "Mutate",
            "description": "将基础门票收入乘以1.05，生成名为‘合规后收入’的新列。"
        }
    ]

    print("输入：Agent 1 的切片结果")
    print("-" * 50)

    enriched_steps = run_port_inference_agent(agent_1_output)

    print("\nAgent 2 端口推演结果：")
    print(json.dumps(enriched_steps, ensure_ascii=False, indent=2))