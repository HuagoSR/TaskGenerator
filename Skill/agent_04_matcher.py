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
你是一位资深的“数据分析考题出题专家 (Exam Setter)”。
你收到了一份已经拆解好的考点大纲（JSON 格式）。你的唯一任务是为每个考点分配底层的 Python 算子（operator_class）。

# 核心认知法则（你是出题人，不是考生！）
在处理每一个节点时，你必须先在脑海中问自己一个问题：
“为了考学生这个知识点，作为出题人的我，是否需要提前在数据库里【凭空捏造新数据】或者【故意破坏原始数据】？”

# 决策与执行管线 (Decision Workflow)

当你遍历输入的所有节点时，请严格根据上述问题进行判断，并执行相应的分支：

分支 A：【纯考生动作】(不需要出题人造数据)
- 判定标准：该步骤是常规的数据处理逻辑（例如：条件筛选、分组聚合、按公式计算方差、列之间的加减乘除等）。这些都是【考生】应该写的代码。出题人不需要提前把“方差”或“筛选结果”算好放在数据表里。
- 执行动作：
  1. [强制禁止] 绝对禁止调用 `list_available_operators` 或 `request_new_operator`。
  2. [直接分配] 直接将该节点的 `"operator_class"` 赋值为 `"PhantomTaskOperator"`。
  3. 处理下一个节点。

分支 B：【出题人动作】(必须出题人准备数据/挖坑)
- 判定标准：该步骤要求必须有物理数据的变化才能进行考试。通常包括：
  1. 需要拉取或生成一张基础的数据表 (通常是 base 节点)。
  2. 需要为复杂的变异考点提供“外部数据字典”（例如：要求考生跨表匹配汇率，出题人就必须先造一张“汇率表”出来）。
  3. 需要故意注入脏数据作为考试陷阱（例如：故意把 5 个正常数值变成空值或负数）。
- 执行动作：
  1. 你必须调用 `list_available_operators` 查找底层算子。
  2. 调用 `get_operator_source_code` 对齐参数名，写入 `data_params`。
  3. 只有当现有算子无法实现这个“造数据/破坏数据”的动作时，才能调用 `request_new_operator` 提交工单。

# 最终输出要求：
输出一个包含所有已处理节点的 JSON 数组。必须确保每一个节点的 `operator_class` 都已明确赋值（PhantomTaskOperator 或真实的 Python 类名）。
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

    print("输入：Agent 3 抽象后的草稿数据")
    print("-" * 50)

    processed_nodes = run_agent_4_matcher(mock_agent_3_output)

    print("\n最终输出的 JSON 状态：")
    print(json.dumps(processed_nodes, ensure_ascii=False, indent=2))