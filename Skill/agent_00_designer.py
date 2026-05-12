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
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "skills_config.json")


# 2. 获取系统中所有的“陷阱”
def get_available_traps() -> str:
    if not os.path.exists(DATABASE_PATH):
        return "当前系统暂无可用陷阱。"
    with open(DATABASE_PATH, "r", encoding="utf-8") as f:
        db = json.load(f)

    traps = []
    for s_id, config in db.items():
        if config.get("node_type") == "trap":
            desc = config.get("semantics", {}).get("rubrics", [""])[0]
            traps.append(f"- ID: {s_id} | Name: {config.get('skill_name')} | Desc: {desc}")
    return "\n".join(traps)


# 3. Agent 0 的系统指令 (针对现有文本的陷阱显形)
SYSTEM_PROMPT_AGENT_0 = """
你是一位顶尖的“数据分析考题审查与漏洞注入专家”。
你会收到一段【现有的真实自然语言任务/题目】，以及当前系统可用的【陷阱考点库】。

# 你的工作流：
1. 仔细阅读原题。
2. 逐个审视陷阱库中的陷阱，思考：这个陷阱的逻辑能否合理地融入到当前题目中？
3. 检查原题：如果原题中已经明确提到了该陷阱的处理（例如原题已经说了“请注意处理空值”），则跳过该陷阱，绝不重复添加。
4. 文本重写（陷阱现形）：如果发现合适的、且原题未包含的陷阱，请重写原自然语言文本。将陷阱逻辑以连贯、自然的语气无缝融入到业务描述中。
5. 暗线标记：在重写后的文本最末尾，必须使用 `[内部出题指令：注入陷阱 <陷阱ID>]` 的格式，把所有（包含原题自带的和你新加入的）陷阱显式地标记出来，供下游的切片机器人读取。

# 输出规范：
直接输出重写后连贯的自然语言文本，末尾附带内部指令。不要输出多余的解释。
"""


def run_trap_injector_agent(original_text: str) -> str:
    print(f"Agent 0 [陷阱显形] 正在扫描原题并匹配陷阱... (Model: {model_name})")

    available_traps = get_available_traps()
    user_content = f"【当前可用陷阱库】:\n{available_traps}\n\n【原始自然语言题目】:\n{original_text}"

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_AGENT_0},
                {"role": "user", "content": user_content}
            ],
            temperature=0.3  # 保持较低温度，确保重写逻辑的严密性
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"API 请求失败: {e}")
        return original_text


# ==================== 测试 ====================
if __name__ == "__main__":
    # 模拟一段没有提到任何脏数据的“干净”原题
    clean_original_text = """
    我们需要对去年的音乐节流水进行合规复核。
    请仔细筛选出所有在法国和德国举办的场次。
    把这些场次的基础门票收入乘以 1.05 的惩罚系数，单独列一列叫‘合规后收入’。
    这周五下午 5 点前必须把分析报告发给我，并且存为 PDF 格式。
    """

    print("【原始干净文本】")
    print(clean_original_text.strip())
    print("-" * 50)

    enhanced_text = run_trap_injector_agent(clean_original_text)
    print("\nAgent 0 注入陷阱并重写后的文本：\n")
    print(enhanced_text)