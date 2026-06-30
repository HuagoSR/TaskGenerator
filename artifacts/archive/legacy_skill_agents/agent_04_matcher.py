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
log_filename = os.path.join(LOG_DIR, f"agent4_matcher_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(asctime)s - [Agent 4] - %(message)s'
)


def execute_tool_with_log(func_name: str, kwargs: dict) -> str:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 鈿?鎵ц宸ュ叿: {func_name}")
    try:
        func = getattr(skill_api_tools, func_name)
        result = func(**kwargs)
        if func_name == "request_new_operator":
            print(f"  鈹斺攢 缁撴灉: 宸叉垚鍔熷悜浜虹被鎻愪氦寮€鍙戝伐鍗曪紒")
        else:
            print(f"  鈹斺攢 缁撴灉: 璋冪敤鎴愬姛")
        return str(result)
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"  鈹斺攢 鎶ラ敊: {error_msg}")
        return error_msg

    # ==========================================


# 2. Agent 4 涓撳睘宸ュ叿绠?(鏌ラ槄 + 鎻愬伐鍗?
# ==========================================
tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "list_available_operators",
            "description": "鏌ョ湅绯荤粺鎵€鏈夊彲鐢ㄧ殑搴曞眰 Python 绠楀瓙銆?,
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_operator_source_code",
            "description": "闃呰绠楀瓙婧愮爜锛屽榻?data_params 鍙傛暟鏍煎紡銆?,
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
            "description": "濡傛灉娌℃湁浠讳綍鐜版湁绠楀瓙婊¤冻闇€姹傦紝璋冪敤姝ゅ伐鍏峰悜浜虹被宸ョ▼甯堝彂璧锋眰鍔╁伐鍗曪紒",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent_description": {"type": "string", "description": "璇︾粏鎻忚堪浣犳兂瀹炵幇浠€涔堜笟鍔￠€昏緫"},
                    "proposed_data_params": {"type": "object", "description": "浣犲笇鏈涜繖涓柊绠楀瓙鎺ュ彈浠€涔堝弬鏁扮粨鏋?},
                    "required_pandas_logic": {"type": "string",
                                              "description": "鎻愮ず浜虹被杩欐槸灞炰簬閫犲熀纭€鏁版嵁鐨?Scenario A)锛岃繕鏄彉寮傝绠楃殑(Scenario B)"}
                },
                "required": ["intent_description", "proposed_data_params", "required_pandas_logic"]
            }
        }
    }
]

# ==========================================
# 3. Agent 4 涓绘帶閫昏緫
# ==========================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
model_name = os.getenv("OPENAI_MODEL", "gemini-3-pro-preview")

SYSTEM_PROMPT = """   
You are a Senior "Data Analysis Exam Setter".
You receive an abstracted array of exam skill nodes. Your task is to assign a low-level Python operator (`operator_class`) to each node, while STRICTLY keeping all original fields intact.

# Core Concept: Distinguish "Engine Action" vs "Examinee Action"
You must determine if a step requires the Engine to "create or sabotage data physically at T=0" OR if it requires the Examinee to "process, deal with, or clean data".

# Branch A: Pure Examinee Actions (No Engine Data Generation Needed)
- Applies to: `node_type` of "mutator" or "global". ALSO applies to "trap" nodes whose Intents are about "Handling", "Replacing", "Filling", or "Cleaning" abnormal data (these are Exam questions to test the examinee, not engine sabotage).
- Execution Actions:
  1. [MANDATORY] DO NOT call `list_available_operators` for these nodes.
  2. If it is a standard calculation/processing node ("mutator" / "global"), assign `"operator_class": "PhantomTaskOperator"`.
  3. If it is a semantic trap node meant for the examinee to clean/handle (e.g., Handle missing costs/categories), assign `"operator_class": "PhantomTrapOperator"`.
  4. CRITICAL: DO NOT change the existing `"node_type"`. Let a "trap" remain a "trap". You may keep any examinee-related reference parameters (like `replacement_value` or `default_category`) inside `data_params` undisturbed.

# Branch B: Engine Actions (Physical Data Creation or Physical Sabotage)
- Applies to: Real "base" data generators OR real "trap" nodes that EXPLICITLY require the Engine to physically inject/sabotage/perturb data (e.g., "Inject missing values into the raw dataset").
- Execution Actions:
  1. You MUST call `list_available_operators` and `get_operator_source_code`.
  2. Find the correct matching low-level class name and set it as `"operator_class"`.
  3. CRITICAL LIMITATION: You must strictly align your `data_params` keys with the exact variables required by the operator's source code (e.g., `perturbation_mode` and `trap_count` for Perturbation operators). NEVER invent fake operational parameters here.
  4. You are COMPLETELY FORBIDDEN to delete, modify, or abbreviate predefined complex fields like `schemas`, `port_to_column_mapping`, and `suggested_row_counts`. They MUST be passed through exactly as they are.
  5. Only if absolutely no operator works, call `request_new_operator` to submit a ticket, and set `"operator_class": "PENDING_HUMAN_REVIEW"`.

# Mandatory Output Format (CRITICAL STRUCTURE RULES)
1. The root MUST be a JSON object with a single key `"proposed_nodes"`.
2. [FULL INHERITANCE]: Never delete any existing fields from the input JSON (skill_id, skill_name, ports, semantics, etc.). You only ADD `operator_class` or adjust the specific keys within `data_params`.
3. Example Structure:
{   
  "proposed_nodes": [   
    {   
      "skill_id": "...",   
      "skill_name": "...",   
      "node_type": "trap",   
      "operator_class": "PhantomTrapOperator",   
      "keywords": [...],   
      "ports": {...},   
      "semantics": {...},   
      "data_params": {...}   
    }   
  ]   
}   
"""


def run_agent_4_matcher(abstracted_nodes: list) -> list:
    print(f"Agent 4 鍚姩 (绠楀瓙鍖归厤涓庡伐鍗曟淳鍙? | 寮曟搸: {model_name}")
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
                temperature=0.0
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
                print("\nAgent 4 鍖归厤/娲惧崟澶勭悊瀹屾垚锛?)
                content = response_message.content.strip()
                if content.startswith("```json"):
                    content = content[7:-3].strip()
                elif content.startswith("```"):
                    content = content[3:-3].strip()

                try:
                    return json.loads(content).get("proposed_nodes", [])
                except json.JSONDecodeError as e:
                    print(f"JSON 瑙ｆ瀽澶辫触: {e}")
                    return abstracted_nodes

        except Exception as e:
            print(f"\nAPI 璇锋眰鎶ラ敊: {e}")
            return abstracted_nodes

# ==========================================
# 杩愯娴嬭瘯
# ==========================================
if __name__ == "__main__":
    # 妯℃嫙杈撳叆 Agent 3 鐨勮緭鍑?
    mock_agent_3_output = [
        {
            "skill_id": "load_population_data",
            "skill_name": "Load Population Dataset",
            "node_type": "base",
            "keywords": [
                "Load",
                "Population",
                "Dataset"
            ],
            "ports": {
                "requires": [],
                "provides": [
                    "Data:Generic",
                    "Metric:TotalRows",
                    "Metric:Q2Data",
                    "Metric:Q3Data",
                    "Dimension:Division",
                    "Dimension:SubDivision",
                    "Dimension:Entity",
                    "Dimension:Metric",
                    "Dimension:Business",
                    "Dimension:Country"
                ]
            },
            "semantics": {
                "intents": [
                    "Load the initial population dataset from '{input_file}' containing columns for total rows, quarterly data, divisions, entities, and metrics.",
                    "Export the final processed sampling results to '{output_file}'."
                ],
                "deliverables": [
                    "Population_Sampling_Result.csv"
                ]
            },
            "data_params": {
                "input_file": "population_data.csv",
                "output_file": "Population_Sampling_Result.csv",
                "suggested_row_counts": {
                    "population_data.csv": 1000
                }
            }
        },
        {
            "skill_id": "calculate_sample_size",
            "skill_name": "Calculate Statistical Sample Size",
            "node_type": "mutator",
            "keywords": [
                "Sample Size",
                "Confidence Level",
                "Error Rate"
            ],
            "ports": {
                "requires": [
                    "Metric:TotalRows"
                ],
                "provides": [
                    "Metric:SampleSize"
                ]
            },
            "semantics": {
                "intents": [
                    "Calculate the required sample size based on the total row count using a confidence level of '{confidence_level}' and a tolerable error rate of '{error_rate}'."
                ]
            },
            "data_params": {
                "confidence_level": 0.9,
                "error_rate": 0.1
            }
        },
        {
            "skill_id": "clean_missing_quarterly_data",
            "skill_name": "Clean Missing Quarterly Values",
            "node_type": "trap",
            "keywords": [
                "Missing Values",
                "Data Cleaning",
                "Quarterly Data"
            ],
            "ports": {
                "requires": [
                    "Metric:Q2Data",
                    "Metric:Q3Data"
                ],
                "provides": []
            },
            "semantics": {
                "intents": [
                    "Identify and clean missing values within the '{q2_col}' and '{q3_col}' columns."
                ]
            },
            "data_params": {
                "q2_col": "q2_data",
                "q3_col": "q3_data"
            }
        },
        {
            "skill_id": "convert_to_absolute_values",
            "skill_name": "Normalize Negative Values to Absolute",
            "node_type": "trap",
            "keywords": [
                "Absolute Value",
                "Negative Values",
                "Normalization"
            ],
            "ports": {
                "requires": [
                    "Metric:Q2Data",
                    "Metric:Q3Data"
                ],
                "provides": [
                    "Metric:Q2DataAbs",
                    "Metric:Q3DataAbs"
                ]
            },
            "semantics": {
                "intents": [
                    "Detect negative outliers in '{q2_col}' and '{q3_col}' and convert them to their absolute values."
                ]
            },
            "data_params": {
                "q2_col": "q2_data",
                "q3_col": "q3_data"
            }
        },
        {
            "skill_id": "calculate_qoq_variance",
            "skill_name": "Calculate Quarter-on-Quarter Variance",
            "node_type": "mutator",
            "keywords": [
                "Variance",
                "QoQ",
                "Growth Rate"
            ],
            "ports": {
                "requires": [
                    "Metric:Q2DataAbs",
                    "Metric:Q3DataAbs"
                ],
                "provides": [
                    "Metric:QoQVariance"
                ]
            },
            "semantics": {
                "intents": [
                    "Calculate the quarter-on-quarter variance rate based on the absolute values of '{q2_col}' and '{q3_col}'."
                ]
            },
            "data_params": {
                "q2_col": "q2_data_abs",
                "q3_col": "q3_data_abs"
            }
        },
        {
            "skill_id": "flag_high_variance",
            "skill_name": "Flag High Variance Records",
            "node_type": "mutator",
            "keywords": [
                "Flag",
                "Threshold",
                "High Variance"
            ],
            "ports": {
                "requires": [
                    "Metric:QoQVariance"
                ],
                "provides": [
                    "Flag:HighVariance"
                ]
            },
            "semantics": {
                "intents": [
                    "Create a boolean flag '{flag_name}' for records where the variance exceeds '{threshold}'."
                ]
            },
            "data_params": {
                "threshold": 0.2,
                "flag_name": "is_high_variance"
            }
        },
        {
            "skill_id": "flag_target_entities",
            "skill_name": "Flag Specific Business Entities",
            "node_type": "mutator",
            "keywords": [
                "Entity",
                "Filter",
                "Flag"
            ],
            "ports": {
                "requires": [
                    "Dimension:Entity"
                ],
                "provides": [
                    "Flag:TargetEntity"
                ]
            },
            "semantics": {
                "intents": [
                    "Generate a boolean flag '{flag_name}' if the entity belongs to the list: {target_entities}."
                ]
            },
            "data_params": {
                "target_entities": [
                    "CB Cash Italy",
                    "CB Correspondent Banking Greece",
                    "IB Debt Markets Luxembourg",
                    "CB Trade Finance Brazil",
                    "PB EMEA UAE"
                ],
                "flag_name": "is_target_entity"
            }
        },
        {
            "skill_id": "flag_target_metrics",
            "skill_name": "Flag Specific Metrics",
            "node_type": "mutator",
            "keywords": [
                "Metric",
                "Flag",
                "Selection"
            ],
            "ports": {
                "requires": [
                    "Dimension:Metric"
                ],
                "provides": [
                    "Flag:TargetMetric"
                ]
            },
            "semantics": {
                "intents": [
                    "Generate a boolean flag '{flag_name}' if the metric is either '{metric_1}' or '{metric_2}'."
                ]
            },
            "data_params": {
                "metric_1": "A1",
                "metric_2": "C1",
                "flag_name": "is_target_metric"
            }
        },
        {
            "skill_id": "flag_zero_quarters",
            "skill_name": "Flag Zero Value Quarters",
            "node_type": "mutator",
            "keywords": [
                "Zero Value",
                "Flag",
                "Quarterly"
            ],
            "ports": {
                "requires": [
                    "Metric:Q2DataAbs",
                    "Metric:Q3DataAbs"
                ],
                "provides": [
                    "Flag:BothQuartersZero"
                ]
            },
            "semantics": {
                "intents": [
                    "Create a boolean flag '{flag_name}' for records where both '{q2_col}' and '{q3_col}' are zero."
                ]
            },
            "data_params": {
                "q2_col": "q2_data_abs",
                "q3_col": "q3_data_abs",
                "flag_name": "is_both_quarters_zero"
            }
        },
        {
            "skill_id": "flag_target_businesses",
            "skill_name": "Flag Specific Business Lines",
            "node_type": "mutator",
            "keywords": [
                "Business",
                "Flag",
                "Trade Finance"
            ],
            "ports": {
                "requires": [
                    "Dimension:Business"
                ],
                "provides": [
                    "Flag:TargetBusiness"
                ]
            },
            "semantics": {
                "intents": [
                    "Generate a boolean flag '{flag_name}' if the business is '{biz_1}' or '{biz_2}'."
                ]
            },
            "data_params": {
                "biz_1": "Trade Finance",
                "biz_2": "Correspondent Banking",
                "flag_name": "is_target_business"
            }
        },
        {
            "skill_id": "flag_target_countries",
            "skill_name": "Flag Specific Countries",
            "node_type": "mutator",
            "keywords": [
                "Country",
                "Flag",
                "Jurisdiction"
            ],
            "ports": {
                "requires": [
                    "Dimension:Country"
                ],
                "provides": [
                    "Flag:TargetCountry"
                ]
            },
            "semantics": {
                "intents": [
                    "Generate a boolean flag '{flag_name}' if the country is in the list: {target_countries}."
                ]
            },
            "data_params": {
                "target_countries": [
                    "Cayman Islands",
                    "Pakistan",
                    "UAE"
                ],
                "flag_name": "is_target_country"
            }
        },
        {
            "skill_id": "execute_stratified_sampling",
            "skill_name": "Execute Multi-Condition Stratified Sampling",
            "node_type": "mutator",
            "keywords": [
                "Sampling",
                "Stratification",
                "Coverage"
            ],
            "ports": {
                "requires": [
                    "Flag:HighVariance",
                    "Flag:TargetEntity",
                    "Flag:TargetMetric",
                    "Flag:BothQuartersZero",
                    "Flag:TargetBusiness",
                    "Flag:TargetCountry",
                    "Dimension:Division",
                    "Dimension:SubDivision",
                    "Metric:SampleSize"
                ],
                "provides": [
                    "Flag:IsSampled"
                ]
            },
            "semantics": {
                "intents": [
                    "Perform sampling logic to select exactly '{sample_size}' rows, ensuring each selected row meets at least one boolean flag condition.",
                    "The final sample must provide full coverage across all flag conditions, all '{div_col}' values, and all '{sub_div_col}' values, marking selected rows as '{output_col}'."
                ]
            },
            "data_params": {
                "sample_size": "calculated_sample_size",
                "div_col": "division",
                "sub_div_col": "sub_division",
                "output_col": "is_sampled"
            }
        }
    ]

    print("杈撳叆锛欰gent 3 鎶借薄鍚庣殑鑽夌鏁版嵁")
    print("-" * 50)

    processed_nodes = run_agent_4_matcher(mock_agent_3_output)

    print("\n鏈€缁堣緭鍑虹殑 JSON 鐘舵€侊細")
    print(json.dumps(processed_nodes, ensure_ascii=False, indent=2))
