import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# 1. 鍩虹閰嶇疆
load_dotenv()
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)
model_name = os.getenv("OPENAI_MODEL", "gemini-3-pro-preview")
PORTS_DICT_PATH = os.path.join(os.path.dirname(__file__), "ports_dict.json")


# 2. 鍔ㄦ€佸姞杞藉叏灞€绔彛瀛楀吀
def load_ports_dict() -> dict:
    if not os.path.exists(PORTS_DICT_PATH):
        return {"Data:Generic": "Generic data flow port."}
    with open(PORTS_DICT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# 3. Agent 2 鐨勭郴缁熸寚浠?
SYSTEM_PROMPT_AGENT_2 = """
You are a top-tier Port Architect for a Directed Acyclic Graph (DAG) system.
Your task is to receive "atomic data operation steps" and deduce the input ports (`requires`) and output ports (`provides`) for each step, ensuring a logical, connected data flow.

# Core Constraints
1. Dictionary First: You MUST prioritize using the provided global port dictionary names!
2. Strict Naming: If you must invent a new port, strictly follow the `Category:Detail` UpperCamelCase format (e.g., `Text:RawDocument`, `Dimension:EmployeeLevel`).
3. Dependency Deduction Rules by Action Type:
   - "Base" (Start Node): Reads external data. It does NOT require upstream graph inputs. `requires` MUST be exactly `[]`. It MUST have `provides`.
   - "Mutate" / "Trap" (Process Nodes): Consumes upstream data and outputs processed data. BOTH `requires` and `provides` MUST NOT be empty.
   - "Export" (End Node): Consumes the final processed data to generate deliverables. `requires` MUST contain the upstream final data ports. `provides` can be `[]` or specific artifact ports like `Deliverable:FinalReport`.
4. Coherence: The `provides` of an upstream step often becomes the `requires` of a downstream step. Ensure a closed-loop data flow without isolated nodes.

# Output Format
Output ONLY a valid JSON object. No markdown, no explanations.
{
  "steps": [
    {
      "action_type": "Export",
      "description": "Export the final compliant dataset to an Excel file.",
      "requires": ["Financial:CompliantAmount", "Dimension:Region"],
      "provides": []
    }
  ]
}
"""


def run_port_inference_agent(sliced_steps: list) -> list:
    print(f"Agent 2 [绔彛鎺ㄦ紨] 姝ｅ湪缁撳悎鍏ㄥ眬瀛楀吀鏋勫缓鏁版嵁娴?.. (Model: {model_name})")

    ports_dict = load_ports_dict()

    # 灏嗙幇鏈夊瓧鍏稿拰 Agent 1 鐨勮緭鍑虹粍瑁呬负涓婁笅鏂?
    user_content = f"""
    銆愮郴缁熷綋鍓嶅凡娉ㄥ唽鐨勬爣鍑嗙鍙ｅ瓧鍏搞€?
    {json.dumps(ports_dict, ensure_ascii=False, indent=2)}

    銆愰渶瑕佹帹婕旇繛绾跨殑鍘熷瓙鎿嶄綔姝ラ銆?
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
            temperature=0.1  # 閫昏緫鎺ㄦ紨闇€瑕佷弗璋紝浣庢俯搴?
        )

        json_data = json.loads(response.choices[0].message.content)
        return json_data.get("steps", [])

    except Exception as e:
        print(f"API 璇锋眰鎴栬В鏋愬け璐? {e}")
        return []


# ==========================================
# 鏈湴鑱斿姩娴嬭瘯 (妯℃嫙 Agent 1 -> Agent 2 鐨勬祦姘寸嚎)
# ==========================================
if __name__ == "__main__":
    # 杩欐槸 Agent 1 涔嬪墠鍒囩墖杈撳嚭鐨勭粡鍏告渚?
    agent_1_output = [{'action_type': 'Base', 'description': "Load the 'Population' spreadsheet containing Anti-Financial Crime Risk Metrics for Q2 and Q3 2024."}, {'action_type': 'Trap', 'description': 'Identify missing financial metrics in columns H (Q2) and I (Q3).'}, {'action_type': 'Mutate', 'description': 'Replace all identified missing values in columns H and I with 0.'}, {'action_type': 'Mutate', 'description': 'Calculate the quarter-on-quarter variance between Q2 and Q3 and record the results in column J.'}, {'action_type': 'Mutate', 'description': 'Calculate the required audit sample size using a 90% confidence level and a 10% tolerable error rate.'}, {'action_type': 'Mutate', 'description': 'Filter rows where variance in column J is greater than 20%.'}, {'action_type': 'Mutate', 'description': 'Filter rows for entities: CB Cash Italy, CB Correspondent Banking Greece, IB Debt Markets Luxembourg, CB Trade Finance Brazil, and PB EMEA UAE.'}, {'action_type': 'Mutate', 'description': 'Filter rows for metrics A1 and C1.'}, {'action_type': 'Mutate', 'description': 'Filter rows where values in both column H and column I are zero.'}, {'action_type': 'Mutate', 'description': 'Filter rows belonging to Trade Finance and Correspondent Banking businesses.'}, {'action_type': 'Mutate', 'description': 'Filter rows for countries: Cayman Islands, Pakistan, and UAE.'}, {'action_type': 'Mutate', 'description': 'Select a subset of rows from the filtered criteria to ensure coverage across all Divisions and sub-Divisions.'}, {'action_type': 'Mutate', 'description': "Mark the final selected sample rows in column K with the value '1'."}, {'action_type': 'Export', 'description': "Save the processed data into a new spreadsheet titled 'Sample', with Tab 1 containing the selected sample rows and Tab 2 containing the sample size calculation workings."}]


    print("杈撳叆锛欰gent 1 鐨勫垏鐗囩粨鏋?)
    print("-" * 50)

    enriched_steps = run_port_inference_agent(agent_1_output)

    print("\nAgent 2 绔彛鎺ㄦ紨缁撴灉锛?)
    print(json.dumps(enriched_steps, ensure_ascii=False, indent=2))
