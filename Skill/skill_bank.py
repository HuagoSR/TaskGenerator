import sys
sys.path.append("..")
from Skill.skill_graph import SkillNode
from FileGenerator.blueprint_core import ProceduralGenerator, ForeignKeyGenerator
import random


# ==========================================
# 1. 基石考点
# ==========================================
class BasePnLSkill(SkillNode):
    node_type = "base"
    name = "跨国音乐巡演利润汇总"
    requires = []
    provides = ["out_revenue_col", "out_expense_col", "out_country_col"]
    suggested_row_counts = {"Tour_Data.xlsx": 25}
    expected_deliverables = ["Music_Tour_PnL_Result.xlsx"]
    # 指明可能的后继节点及端口映射
    possible_successors = [
        {"skill_id": "mut_tax_01", "port_map": {"out_revenue_col": "in_amount", "out_country_col": "in_country"}},
        {"skill_id": "trap_double_negative", "port_map": {"out_expense_col": "in_target"}},
        {"skill_id": "mut_currency_ex", "port_map": {"out_country_col": "in_country"}},
        {"skill_id": "trap_missing_value", "port_map": {"out_revenue_col": "in_target"}},
        {"skill_id": "trap_missing_value", "port_map": {"out_expense_col": "in_target"}}
    ]

    # 1. 业务步骤
    prompt_intents = [
        "Prepare a structured Excel profit and loss (P&L) report using the provided '{out_table}' file.",
        "Calculate Total Net Revenue, Total Expenses, and Net Income.",
        "Note: All initial financial figures provided are in USD."
    ]
    # 2. 给考生的死命令
    deliverable_constraints = [
        "The final deliverable MUST be an Excel file named 'Music_Tour_PnL_Result.xlsx'."
    ]
    # 3. 判分的答案
    hidden_rubrics = [
        "Check if Total Net Revenue and Total Expenses are accurately aggregated from '{out_table}'."
    ]

    system_prompt = """You are a Senior Audit Partner assigning a task to a Junior AI Auditor.
        1. Weave the 'Business Intents' into a professional, cohesive business narrative. The words wrapped in single quotes (like 'Tour_Data.xlsx') are literal files/columns; you MUST copy them exactly.
        2. Add a 'Requirements / Notes' section at the end and copy the 'Deliverable Constraints' EXACTLY as bullet points. Do not change a single word of the constraints."""

    def on_join_graph(self, graph):
        """【发车安检口】：决定表名列名，并渲染语义大纲"""
        # 1. 给自己生成的数据起名字
        self.table_name = "Tour_Data.xlsx"
        self.rev_col = "Gross_Revenue"
        self.exp_col = "Expenses"
        self.country_col = "Country"

        # 2. 注册自己的输出插槽坐标 (表名, 列名)
        self.output_names["out_revenue_col"] = (self.table_name, self.rev_col)
        self.output_names["out_expense_col"] = (self.table_name, self.exp_col)
        self.output_names["out_country_col"] = (self.table_name, self.country_col)

        # 3. 渲染语义
        format_dict = {"out_table": self.table_name}
        self.rendered_intents = [i.format(**format_dict) for i in self.prompt_intents]
        self.rendered_constraints = self.deliverable_constraints
        self.rendered_rubrics = [r.format(**format_dict) for r in self.hidden_rubrics]

    def register_data_operations(self, vfs, graph):
        """【执行期】：纯粹的数据生成，无需再查图"""
        bp = vfs.create_tabular_blueprint(self.table_name)
        bp.add_column(self.rev_col, ProceduralGenerator("normal", mean=10000, std=2000))
        bp.add_column(self.exp_col, ProceduralGenerator("normal", mean=4000, std=500))
        


# ==========================================
# 2. 变异考点
# ==========================================
class TaxMutatorSkill(SkillNode):
    node_type = "mutator"
    name = "跨国扣税率"
    requires = ["in_amount", "in_country"]
    provides = ["out_net_amount"]
    suggested_row_counts = {"Tax_Rates.csv": 4}    
    prompt_intents = [
        "Match the '{in_country_col}' column in the '{in_country_table}' table with the '{dict_table}' file to apply the correct tax withholding rates. Calculate the net revenue and store it in a new column named '{out_net_amount_col}'."
    ]
    deliverable_constraints = []
    
    hidden_rubrics = [
        "Verify that tax rates were correctly mapped from '{dict_table}' (e.g., UK should be calculated at 20%)."
    ]

    possible_successors = [        
        {"skill_id": "mut_currency_ex", "port_map": {"out_net_amount": "in_amount"}},
    ]

    def on_join_graph(self, graph):
        """【发车安检口】"""
        # 1. 确认已有 Slot (寻址上游真实物理名称)
        self.target_table, self.amount_col = self.resolve_input_port("in_amount", graph)
        _, self.country_col = self.resolve_input_port("in_country", graph)

        # 2. 补充未有 Slot (给自己起名)
        self.dict_table = "Tax_Rates.csv"
        self.net_amount_col = "Net_Revenue_After_Tax"
        self.output_names["out_net_amount"] = (self.target_table, self.net_amount_col)

        # 3. 渲染语义(Context Mapping 完成)
        format_dict = {
            "in_country_table": self.target_table,
            "in_country_col": self.country_col,
            "dict_table": self.dict_table,
            "out_net_amount_col": self.net_amount_col
        }
        self.rendered_intents = [intent.format(**format_dict) for intent in self.prompt_intents]
        self.rendered_constraints = self.deliverable_constraints
        self.rendered_rubrics = [r.format(**format_dict) for r in self.hidden_rubrics]

    def register_data_operations(self, vfs, graph):
        """【执行期】"""
        # 建字典表
        dict_bp = vfs.create_tabular_blueprint(self.dict_table)
        countries = ["UK", "France", "Spain", "Germany"]
        rates = [0.20, 0.15, 0.24, 0.15825]
        dict_bp.add_column("Country", ProceduralGenerator("constant_list", values=countries))
        dict_bp.add_column("Rate", ProceduralGenerator("constant_list", values=rates))

        # 去主表打外键约束
        target_bp = vfs.get_blueprint(self.target_table)
        target_bp.add_column(self.country_col, ForeignKeyGenerator(self.dict_table, "Country"))


class CurrencyExchangeSkill(SkillNode):
    node_type = "mutator"
    name = "多币种汇率换算"
    requires = ["in_amount", "in_country"]  # 需要金额和国家来匹配货币
    provides = ["out_local_amount"]
    suggested_row_counts = {"Currency_Rates_Base_RMB.xlsx": 4}
    prompt_intents = [
        "Refer to the newly provided '{exchange_table}' which contains RMB-based exchange rates (e.g., 1 RMB = X Foreign Currency).",
        "Your task: (1) Derive a USD-to-other-currencies conversion table. (2) Identify the local currency for each '{in_country_col}' (e.g., France -> EUR). (3) Convert the values in '{in_amount_col}' (currently in USD) to the local currency.",
        "Append the results to a new column named '{out_local_col}'. If a country's currency is not listed, use a 1:1 exchange rate."
    ]

    deliverable_constraints = [
        "The derived USD conversion table MUST be included as a separate sheet named 'Derived_USD_Rates' within the final deliverable."
    ]

    def on_join_graph(self, graph):
        self.rendered_constraints = self.deliverable_constraints

        # 1. 锁定物理位置
        self.target_table, self.amount_col = self.resolve_input_port("in_amount", graph)
        _, self.country_col = self.resolve_input_port("in_country", graph)

        # 2. 定义新文件和新列名
        self.exchange_table = "Currency_Rates_Base_RMB.xlsx"
        self.local_amount_col = "Local_Currency_Amount"
        self.output_names["out_local_amount"] = (self.target_table, self.local_amount_col)

        # 3. 渲染语义
        format_dict = {
            "exchange_table": self.exchange_table,
            "in_amount_col": self.amount_col,
            "in_country_col": self.country_col,
            "out_local_col": self.local_amount_col
        }
        self.rendered_intents = [i.format(**format_dict) for i in self.prompt_intents]
        self.rendered_rubrics = [
            f"Verify if {self.local_amount_col} correctly reflects USD to local currency conversion based on RMB rates."
        ]

    def register_data_operations(self, vfs, graph):
        # 创建 RMB 汇率基准表
        ex_bp = vfs.create_tabular_blueprint(self.exchange_table)
        # 这里数据：1 RMB 等于多少外币
        ex_bp.add_column("Currency", ProceduralGenerator("constant_list", values=["USD", "GBP", "EUR", "JPY"]))
        ex_bp.add_column("Rate_per_RMB", ProceduralGenerator("constant_list", values=[0.14, 0.11, 0.13, 21.0])) 
        target_bp = vfs.get_blueprint(self.target_table)
        

# ==========================================
# 3. 陷阱考点
# ==========================================
class DoubleNegativeTrapSkill(SkillNode):
    node_type = "trap"
    name = "双重负数陷阱"
    max_instances = 99
    requires = ["in_target"]
    provides = []

    prompt_intents = []
    deliverable_constraints = []
    
    hidden_rubrics = [
        "Ensure that negative entries (e.g., refunds) in the '{in_target_col}' column of '{in_target_table}' are handled correctly using absolute values and not double-deducted."
    ]

    def on_join_graph(self, graph):
        """【发车安检口】"""
        # 1. 锁定攻击目标
        self.target_table, self.target_col = self.resolve_input_port("in_target", graph)

        # 2. 渲染约束 (向判分 Agent 或考生明确指出该列)
        format_dict = {
            "in_target_table": self.target_table,
            "in_target_col": self.target_col
        }
        self.rendered_constraints = [c.format(**format_dict) for c in self.deliverable_constraints]
        self.rendered_rubrics = [r.format(**format_dict) for r in self.hidden_rubrics]

    def register_data_operations(self, vfs, graph):
        """【执行期】向主表投递破坏函数"""
        target_bp = vfs.get_blueprint(self.target_table)
        target_bp.inject_trap(trap_name=self.name, handler=self.apply_trap, count=1)

    def apply_trap(self, df, victim_indices):
        """【坍缩期】回调破坏函数"""
        for idx in victim_indices:
            val = df.loc[idx, self.target_col]
            df.loc[idx, self.target_col] = -abs(float(val))
            print(f"   ->  触发 [{self.name}] (行号: {idx}, 目标列: {self.target_col})")


class MissingValueTrapSkill(SkillNode):
    node_type = "trap"
    name = "通用缺失值陷阱"
    max_instances = 99
    requires = ["in_target"]
    provides = []

    def on_join_graph(self, graph):
        # 锁定被攻击的列
        self.target_table, self.target_col = self.resolve_input_port("in_target", graph)

        # 渲染后台判分标准 (题干里什么都不写，这就是陷阱)
        self.rendered_rubrics = [
            f"Check if the model identified and handled the missing value in '{self.target_col}' of '{self.target_table}'."
        ]

    def register_data_operations(self, vfs, graph):
        target_bp = vfs.get_blueprint(self.target_table)
        # 将自身的 apply_trap 逻辑注入蓝图
        target_bp.inject_trap(trap_name=f"{self.name}_{self.node_id}", handler=self.apply_trap, count=1)

    def apply_trap(self, df, victim_indices):
        """物理破坏：把选中行的数据变为空"""
        for idx in victim_indices:
            df.loc[idx, self.target_col] = None  # 或者 np.nan
            print(f"   ->  触发 [缺失值陷阱] (行号: {idx}, 目标列: {self.target_col})")


# ==========================================
# 4. 全局考点
# ==========================================

class GlobalRequirementSkill(SkillNode):
    node_type = "global"
    name = "全局交付与排版规范"
    # 作为一个“空降”考点，它不需要任何输入输出，也没有最大数量限制
    max_instances = 1
    requires = []
    provides = []
    expected_deliverables = ["task_summary.pdf"]

    #  1. 业务意图
    prompt_intents = [
        "In addition to the calculations, please draft a 'Task Completion Summary' as a separate PDF document.",
        "In this summary document, you must explicitly document any data anomalies, missing values, or accounting issues you encountered during your analysis and explain how you resolved them."
    ]

    #  2. 硬性约束
    deliverable_constraints = [
        "The final summary deliverable MUST be a PDF file named 'task_summary.pdf'.",
        "The overall formatting, style, and layout of all deliverables MUST be clean, professional, and business-ready."
    ]

    #  3. 打分点
    hidden_rubrics = [
        "Verify that a 'Task Completion Summary' is clearly included as a separate 'task_summary.pdf' file.",
        "Check if the PDF summary accurately identifies the embedded data anomalies (e.g. missing data) if they were present.",
        "Evaluate whether the overall formatting and style of the deliverables are highly professional and readable."
    ]

    def on_join_graph(self, graph):
        """【发车安检口】全局节点没有变量需要替换，直接原样赋值即可"""
        self.rendered_intents = self.prompt_intents
        self.rendered_constraints = self.deliverable_constraints
        self.rendered_rubrics = self.hidden_rubrics

    def register_data_operations(self, vfs, graph):
        """【数据坍缩期】全局节点不生产物理文件，直接放行"""
        pass

# ==========================================
# 5. 全局考点注册表 (供引擎实例化)
# ==========================================
SKILL_REGISTRY = {
    "base_pnl_01": BasePnLSkill,
    "mut_tax_01": TaxMutatorSkill,
    "trap_double_negative": DoubleNegativeTrapSkill,
    "mut_currency_ex": CurrencyExchangeSkill,
    "trap_missing_value": MissingValueTrapSkill,
    "global_req_01": GlobalRequirementSkill
}