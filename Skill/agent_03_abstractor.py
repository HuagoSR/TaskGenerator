import os
import json
import logging
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# ==========================================
# 1. 基础配置与日志系统
# ==========================================
load_dotenv()
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)
model_name = os.getenv("OPENAI_MODEL", "gemini-3-pro-preview")

# 配置辩论日志 (Debate Logs)
LOG_DIR = os.path.join(os.path.dirname(__file__), "debate_logs")
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(LOG_DIR, f"agent3_debate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# 设置日志格式
logger = logging.getLogger("Agent3_Debate")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(log_filename, encoding='utf-8')
fh.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
logger.addHandler(fh)

def load_validation_guide() -> str:
    """读取同目录下的错题本文件/规则书"""
    guide_path = os.path.join(os.path.dirname(__file__), "agent_3_validation_guide.txt")
    if os.path.exists(guide_path):
        with open(guide_path, "r", encoding="utf-8") as f:
            return f.read()
    return "No custom validation guide found."

# 获取统一的规则文本
GLOBAL_RULEBOOK = load_validation_guide()

# ==========================================
# 2. 系统指令配置
# ==========================================
SYSTEM_PROMPT = """
You are an expert Data Pipeline Architect for an LLM-Sandbox evaluation system. Your sole responsibility is to translate and abstract concrete business requirements into a strict, declarative ENGLISH JSON schema.

1. **File Extensions (NO CSV)**: ANY generated table, output dataset, or spreadsheet deliverable MUST end with `.xlsx` (e.g., `festival_transactions.xlsx`). NEVER use `.csv` or `.txt` for output files. Other non-spreadsheet formats like `.pdf` are acceptable if required.
2. **Sandbox Role Assignment (CRITICAL)**: You MUST assign a `sandbox_role` to each node. It MUST be exactly one of the following three:
   - `"Data_Generator"`: For "base" or "trap" nodes that require the sandbox to physically generate or sabotage initial data tables.
   - `"Solver"`: For "mutator" nodes that represent business logic, calculations, or filtering that the golden solver needs to execute.
   - `"Global_Constraint"`: For "global" nodes that dictate final deliverable formats.
3. **Data Profile Mandates (NO HARDCODED PARAMETERS)**: 
   - DO NOT use rigid statistical generators (like `uniform`, `min/max`, `categorical`). 
   - INSTEAD, use `data_profile` to describe the business reality. 
   - For `node_type: "base"`, `data_profile` MUST include:
     - `business_context`: A rich natural language description of the scenario (e.g., "Simulate the 2024 Fall Music Tour financial records with realistic European venue capacities").
     - `suggested_scale`: A dictionary mapping EXACT file names to an integer row count. (e.g., `{"raw_tour.xlsx": 150}`).
     - `declarative_schemas`: A dictionary mapping table names to a simple list of column descriptions. You MUST hallucinate background columns (ID, Date, City) to make it realistic. (e.g., `["Txn_ID", "Country", "Gross Revenue (Realistic distribution)"]`).
4. **Intent Clarity**: The `intents` MUST describe the business action clearly. For "trap" nodes, do not explain *how* to solve the trap; just state the disruption intent (e.g., "Inject implicit null entries to simulate disconnected data flows").

# Core Directives
1. **ALL ENGLISH ONLY**: Everything you output (skill_name, keywords, intents, parameter names, etc.) MUST be translated into professional English.
2. **De-concretization**: Extract specific business references into the `data_profile` object.
3. **Template Intents**: Write the `intents` using `{}` placeholders. The placeholder names MUST perfectly match the keys in `data_profile`.
4. **STRICT EXCLUSIONS**: 
   - DO NOT generate `rubrics` or `evaluation_anchor` (this will be handled by a downstream Validator agent).
   - DO NOT generate `operator_class`.

# Strict JSON Schema Requirement
Your output must be a JSON object containing a "proposed_nodes" array. Every node MUST strictly follow this structure:
{
  "proposed_nodes": [
    {
      "skill_id": "load_data", 
      "skill_name": "Load Data",
      "node_type": "base", 
      "sandbox_role": "Data_Generator",
      "keywords": ["Load", "Data", "Financials"],
      "ports": {
        "requires": [],
        "provides": ["Financial:PreTax", "Dimension:Region"]
      },
      "semantics": {
        "intents": ["Load the initial music festival transaction dataset from '{deliverable_file}'."],
        "deliverables": ["raw_tour.xlsx"]
      },
      "data_profile": {
        "business_context": "High-frequency cross-border transactions under the 2024 Fall Music Tour.",
        "deliverable_file": "raw_tour.xlsx",
        "suggested_scale": {"raw_tour.xlsx": 150},
        "declarative_schemas": {
          "raw_tour.xlsx": [
            "Txn_ID",
            "Concert_Date",
            "City",
            "Revenue (Realistic distribution between $1000 and $5000)"
          ]
        }
      }
    }
  ]
}

# CRITICAL RULEBOOK
{GLOBAL_RULEBOOK}
"""


def load_validation_guide() -> str:
    """读取同目录下的错题本文件"""
    guide_path = os.path.join(os.path.dirname(__file__), "agent_3_validation_guide.txt")
    if os.path.exists(guide_path):
        with open(guide_path, "r", encoding="utf-8") as f:
            return f.read()
    return "No custom validation guide found. Just verify basic JSON format."


# 裁判的 System Prompt
JUDGE_SYSTEM_PROMPT = JUDGE_SYSTEM_PROMPT = f"""
You are a strict JSON formatting and Logic Auditor (The Judge).
Your job is to review a JSON payload generated by another AI and determine if it strictly adheres to the project rules.

Here is your Validation Guide (The Rulebook):
=============================================
{GLOBAL_RULEBOOK}
=============================================

Your output MUST be a JSON object with this exact structure:
{{
    "pass": true or false,
    "feedback": "If pass is false, provide a harsh, specific explanation of what rule was violated and how to fix it. If pass is true, output 'All rules met'."
}}
"""


# ==========================================
# 3. 核心辩论执行循环
# ==========================================
def run_agent_3_abstractor(enriched_steps: list, max_retries: int = 5) -> list:
    print(f"Agent 3 启动 (Actor-Critic 裁判机制) | 引擎: {model_name}")
    logger.info(f"=== 新的抽象任务开始 ===")

    # 构造 Generator 的初始对话上下文
    user_content = f"Please abstract and parameterize the following steps into the required ENGLISH JSON format:\n{json.dumps(enriched_steps, ensure_ascii=False)}"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]

    for attempt in range(1, max_retries + 1):
        print(f"\n--- 正在生成草稿 (第 {attempt}/{max_retries} 次尝试) ---")
        logger.info(f"--- 尝试 {attempt}/{max_retries} ---")

        try:
            # 1. 演员 (Generator) 产出草稿
            gen_response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3  # 稍微给一点发散能力去造 schema
            )
            draft_content = gen_response.choices[0].message.content
            logger.info(f"【Generator 输出】:\n{draft_content}")

            # 【第一道防线：Python 原生裁判】拦截截断报错
            try:
                parsed_draft = json.loads(draft_content)
            except json.JSONDecodeError as e:
                error_msg = f"FATAL ERROR: JSON parsing failed. It looks like your output was truncated or malformed. Error: {e}. Please rewrite the ENTIRE JSON structure properly."
                print(f"Python 原生裁判拦截: JSON 解析失败 (可能是截断)。")
                logger.error(f"【Python 原生裁判驳回】: {error_msg}")

                messages.append({"role": "assistant", "content": draft_content})
                messages.append({"role": "user", "content": error_msg})
                continue  # 直接进入下一轮重试，不需要呼叫 LLM 裁判

            # 2. 裁判员 (Judge) 登场校验
            print("--- 裁判正在校验 JSON 格式及业务逻辑 ---")
            judge_response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Please review this JSON draft:\n{draft_content}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.0  # 裁判必须绝对严谨，0 幻觉
            )

            judge_result = json.loads(judge_response.choices[0].message.content)
            is_pass = judge_result.get("pass", False)
            feedback = judge_result.get("feedback", "No feedback provided.")

            logger.info(f"【Judge 判决结果】: Pass={is_pass}\n【Judge 反馈】: {feedback}")

            # 3. 判决执行
            if is_pass:
                print("裁判判定通过！")
                logger.info("=== 任务成功结束 ===")

                if isinstance(parsed_draft, list):
                    return parsed_draft
                elif isinstance(parsed_draft, dict):
                    return parsed_draft.get("proposed_nodes", [])
                return []
            else:
                print(f"裁判驳回！反馈意见: {feedback}")
                # 将错误草稿和严厉反馈塞回 Generator 的历史记录，逼迫它在下一轮修正
                messages.append({"role": "assistant", "content": draft_content})
                messages.append({
                    "role": "user",
                    "content": f"CRITICAL FEEDBACK FROM AUDITOR:\nYour previous JSON violated the rules. Here is the feedback:\n{feedback}\n\nPlease reflect on this and output a fully corrected JSON object immediately."
                })

        except Exception as e:
            print(f"发生网络或未知异常: {e}")
            logger.error(f"发生异常: {e}")
            # 如果是 API 本身断开，可以小睡一会或继续重试
            continue

    print("\n达到最大重试次数，无法产出合格的 JSON。请检查 debate_logs 寻找原因。")
    logger.error("=== 任务失败，达到最大重试次数 ===")
    return []


# ==========================================
# 运行测试
# ==========================================
if __name__ == "__main__":
    # 使用 Agent 2 输出的那 4 个步骤进行测试
    agent_2_output = [
  {
    "action_type": "Base",
    "description": "Load the 'Population' spreadsheet containing Anti-Financial Crime Risk Metrics for Q2 and Q3 2024.",
    "requires": [],
    "provides": [
      "Data:PopulationMetrics"
    ]
  },
  {
    "action_type": "Trap",
    "description": "Identify missing financial metrics in columns H (Q2) and I (Q3).",
    "requires": [
      "Data:PopulationMetrics"
    ],
    "provides": [
      "Data:MissingMetricsIdentified"
    ]
  },
  {
    "action_type": "Mutate",
    "description": "Replace all identified missing values in columns H and I with 0.",
    "requires": [
      "Data:MissingMetricsIdentified"
    ],
    "provides": [
      "Data:ImputedMetrics"
    ]
  },
  {
    "action_type": "Mutate",
    "description": "Calculate the quarter-on-quarter variance between Q2 and Q3 and record the results in column J.",
    "requires": [
      "Data:ImputedMetrics"
    ],
    "provides": [
      "Data:MetricsWithVariance"
    ]
  },
  {
    "action_type": "Mutate",
    "description": "Calculate the required audit sample size using a 90% confidence level and a 10% tolerable error rate.",
    "requires": [
      "Data:MetricsWithVariance"
    ],
    "provides": [
      "Metric:SampleSize"
    ]
  },
  {
    "action_type": "Mutate",
    "description": "Filter rows where variance in column J is greater than 20%.",
    "requires": [
      "Data:MetricsWithVariance"
    ],
    "provides": [
      "Data:VarianceFiltered"
    ]
  },
  {
    "action_type": "Mutate",
    "description": "Filter rows for entities: CB Cash Italy, CB Correspondent Banking Greece, IB Debt Markets Luxembourg, CB Trade Finance Brazil, and PB EMEA UAE.",
    "requires": [
      "Data:VarianceFiltered"
    ],
    "provides": [
      "Data:EntityFiltered"
    ]
  },
  {
    "action_type": "Mutate",
    "description": "Filter rows for metrics A1 and C1.",
    "requires": [
      "Data:EntityFiltered"
    ],
    "provides": [
      "Data:MetricFiltered"
    ]
  },
  {
    "action_type": "Mutate",
    "description": "Filter rows where values in both column H and column I are zero.",
    "requires": [
      "Data:MetricFiltered"
    ],
    "provides": [
      "Data:ZeroValueFiltered"
    ]
  },
  {
    "action_type": "Mutate",
    "description": "Filter rows belonging to Trade Finance and Correspondent Banking businesses.",
    "requires": [
      "Data:ZeroValueFiltered"
    ],
    "provides": [
      "Data:BusinessFiltered"
    ]
  },
  {
    "action_type": "Mutate",
    "description": "Filter rows for countries: Cayman Islands, Pakistan, and UAE.",
    "requires": [
      "Data:BusinessFiltered"
    ],
    "provides": [
      "Data:CountryFiltered"
    ]
  },
  {
    "action_type": "Mutate",
    "description": "Select a subset of rows from the filtered criteria to ensure coverage across all Divisions and sub-Divisions.",
    "requires": [
      "Data:CountryFiltered",
      "Metric:SampleSize"
    ],
    "provides": [
      "Data:StratifiedSample"
    ]
  },
  {
    "action_type": "Mutate",
    "description": "Mark the final selected sample rows in column K with the value '1'.",
    "requires": [
      "Data:StratifiedSample"
    ],
    "provides": [
      "Data:MarkedSample"
    ]
  },
  {
    "action_type": "Export",
    "description": "Save the processed data into a new spreadsheet titled 'Sample', with Tab 1 containing the selected sample rows and Tab 2 containing the sample size calculation workings.",
    "requires": [
      "Data:MarkedSample",
      "Metric:SampleSize"
    ],
    "provides": [
      "Deliverable:SampleSpreadsheet"
    ]
  }
]

    abstracted_nodes = run_agent_3_abstractor(agent_2_output)