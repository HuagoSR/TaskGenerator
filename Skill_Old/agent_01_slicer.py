import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
model_name = os.getenv("OPENAI_MODEL", "gemini-3-pro-preview")  # 默认使用你的变量

if not api_key or not base_url:
    raise ValueError("未在 .env 文件中找到 OPENAI_API_KEY 或 OPENAI_BASE_URL，请检查配置！")


client = OpenAI(
    api_key=api_key,
    base_url=base_url
)


SYSTEM_PROMPT = """
你是一位极其严谨的资深数据架构师。你的任务是从冗长、复杂的业务需求或考试题目中，剔除无关的背景废话，提取出纯粹的“原子化数据操作步骤”。

# Constraints
1. 忽略一切诸如政策背景、截止日期、团队问候、交付格式（如“存为PDF”）等与数据处理动作无关的噪音信息。
2. 必须将复合的业务逻辑切分为“不可再分”的原子操作。例如：“找出逾期数据并扣除 5% 违约金”必须切分为两步：[筛选逾期数据] 和 [乘法计算违约金]。
3. 请为每个切片分配一个 `action_type`，仅限以下四种：
   - "Base": 基础数据的拉取或汇总。
   - "Mutate": 基于原有数据生成新列、比率计算、连表匹配等变换。
   - "Filter": 数据的行级筛选。
   - "Trap": 异常值（缺失值、负数、格式错误）的发现与清洗。
4. 【隐含数据源推断】：任何数据流都必定有起点。即使文本没有明说，你输出的第一个切片必须是 action_type: "Base"，代表读取或生成初始的业务数据表。例如描述为“加载初始的XX数据集，其中包含数据xxx”。
5. 每一个步骤需要的数据必须在前面的步骤明确指出，除非`action_type`为‘Base’。例如步骤“找出逾期数据”前面必须有步骤中明确出现“逾期数据”或相同含义的表达。

# Output Format
你必须且只能输出一个合法的 JSON 对象，包含一个名为 "steps" 的数组。不要输出任何 Markdown 标记。格式如下：
{
  "steps": [
    {
      "action_type": "Filter",
      "description": "筛选出举办国家为法国或德国的演出记录。"
    }
  ]
}
"""


def run_dehydration_agent(raw_text: str) -> list:
    """
    运行脱水与切片 Agent
    """
    print(f"Agent 1 [脱水与切片] 正在思考中... (使用的模型: {model_name})")

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw_text}
            ],
            # 开启 JSON Mode，强制模型输出标准 JSON (要求 Prompt 中必须明确提示输出 JSON)
            response_format={"type": "json_object"},
            temperature=0.1
        )

        # 提取模型返回的文本内容
        content = response.choices[0].message.content

        # 解析 JSON 并提取 steps 列表
        json_data = json.loads(content)
        return json_data.get("steps", [])

    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}\n大模型原始输出:\n{content}")
        return []
    except Exception as e:
        print(f"API 请求失败: {e}")
        return []


# ==========================================
# 本地测试
# ==========================================
if __name__ == "__main__":
    messy_requirement = """
    各位团队成员注意，鉴于欧盟最近出台了新的环保法案（法案编号EU-2026-04），
    我们需要对去年的音乐节流水进行严格的合规复核。
    请仔细筛选出所有在法国和德国举办的场次。
    由于这两个国家要求强制购买碳排放指标，请把这些场次的基础门票收入乘以 1.05 的惩罚系数，单独列一列叫‘合规后收入’。
    另外，这周五下午 5 点前必须把分析报告发给我，并且存为 PDF 格式！
    差点忘了，原始数据里有些场次没填收入，记得把这些空值处理掉！
    """

    print("原始需求：")
    print(messy_requirement.strip())
    print("-" * 50)

    # 运行 Agent
    result_slices = run_dehydration_agent(messy_requirement)

    print("\n结果：")
    for i, step in enumerate(result_slices, 1):
        print(f"步骤 {i} [{step['action_type']}]: {step['description']}")