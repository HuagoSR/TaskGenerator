import json
import os
import re
from typing import List, Dict, Optional
import inspect
from Skill import operators
import time

# 定义考点库的路径
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "skills_config.json")
# 定义端口字典的路径
PORTS_DICT_PATH = os.path.join(os.path.dirname(__file__), "ports_dict.json")

def _load_db() -> dict:
    """内部辅助函数：加载最新数据库"""
    if not os.path.exists(DATABASE_PATH):
        return {}
    with open(DATABASE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_db(db_data: dict) -> bool:
    """内部辅助函数：安全落盘"""
    with open(DATABASE_PATH, "w", encoding="utf-8") as f:
        json.dump(db_data, f, indent=4, ensure_ascii=False)
    return True

def _load_ports_db() -> dict:
    if not os.path.exists(PORTS_DICT_PATH):
        # 如果文件不存在，初始化一个基础字典
        initial_ports = {
            "Financial:AnyAmount": "Generic financial amount.",
            "Dimension:Generic": "Generic classification dimension."
        }
        _save_ports_db(initial_ports)
        return initial_ports
    with open(PORTS_DICT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_ports_db(db_data: dict) -> bool:
    with open(PORTS_DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(db_data, f, indent=4, ensure_ascii=False)
    return True


# 提取 operators.py 中所有的算子类
OPERATOR_REGISTRY = {
    name: cls for name, cls in inspect.getmembers(operators, inspect.isclass)
    if issubclass(cls, operators.SkillNode) and cls is not operators.SkillNode
}


def list_available_operators() -> str:
    """
    【工具功能】列出当前系统中所有受支持的底层 Python 数据算子。
    大模型在创建新考点前，可以通过此接口了解系统有哪些现成的“骨架”可用。

    返回:
        str: 包含算子名称及其简要说明（docstring）的列表。
    """
    results = []
    for name, cls in OPERATOR_REGISTRY.items():
        doc = inspect.getdoc(cls) or "无描述"
        # 提取第一行作为简要说明
        short_doc = doc.split('\n')[0]
        results.append(f"- {name}: {short_doc}")

    return "当前系统支持以下底层算子：\n" + "\n".join(results)


def get_operator_source_code(operator_name: str) -> str:
    """
    【工具功能】查看某个具体底层算子的 Python 源代码。
    大模型需要调用此接口来分析该算子的 register_data_operations 方法，
    从而弄清楚在创建考点时，需要在 data_params 中填入哪些具体的键值对（Key-Value）。

    参数:
        operator_name (str): 算子类名（如 "ForeignKeyDictionaryOperator"）。

    返回:
        str: 该算子的完整 Python 源代码。
    """
    if operator_name not in OPERATOR_REGISTRY:
        return f"Error: 找不到算子 '{operator_name}'。请先使用 list_available_operators 检查拼写。"

    cls = OPERATOR_REGISTRY[operator_name]
    try:
        # inspect 模块直接把类的源代码提取成字符串
        source_code = inspect.getsource(cls)
        return f"以下是 {operator_name} 的源代码，请仔细分析它如何使用 self.data_params：\n```python\n{source_code}\n```"
    except Exception as e:
        return f"Error: 无法获取源码。详细信息: {str(e)}"


# ==========================================
# 供 LLM Agent 调用的工具 API
# ==========================================

def search_skills(keyword: str = "", needs_input_port: str = "", provides_output_port: str = "") -> str:
    """
    【工具功能】搜索现有的业务考点库。在你想要新建考点前，必须先调用此工具查找是否有可复用的考点，或者寻找可以连接的上游/下游节点。

    参数:
        keyword (str): 选填。业务关键词（如 "税", "缺失值", "汇率"）。
        needs_input_port (str): 选填。搜索【需要特定输入】的考点。如 "Financial:PreTax"。
        provides_output_port (str): 选填。搜索【能提供特定输出】的考点。如 "Dimension:Region"。

    返回:
        str: 包含匹配考点概要信息的文本字符串。如果未找到，将返回提示。
    """
    db = _load_db()
    results = []

    for s_id, config in db.items():
        match = True

        # 1. 关键词匹配 (搜索 ID, Name 或 keywords)
        if keyword:
            kw_lower = keyword.lower()
            keywords_list = [k.lower() for k in config.get("keywords", [])]
            if not (kw_lower in s_id.lower() or kw_lower in config.get("skill_name",
                                                                       "").lower() or kw_lower in keywords_list):
                match = False

        # 2. 端口匹配
        ports = config.get("ports", {})
        if needs_input_port and needs_input_port not in ports.get("requires", []):
            match = False
        if provides_output_port and provides_output_port not in ports.get("provides", []):
            match = False

        if match:
            # 组装返回给大模型的简报
            info = f"- ID: {s_id} | Name: {config.get('skill_name')} | Requires: {ports.get('requires', [])} | Provides: {ports.get('provides', [])}"
            results.append(info)

    if not results:
        return f"搜索完成。未找到匹配关键字 '{keyword}' 或端口要求的考点。建议考虑调用 create_skill 新建一个考点。"

    return "找到以下匹配的考点：\n" + "\n".join(results)


def get_skill_details(skill_id: str) -> str:
    """
    【工具功能】读取某个具体考点的全部详细配置（包含业务意图、判分点、执行参数等）。

    参数:
        skill_id (str): 考点的唯一标识符（如 "base_pnl_01"）。

    返回:
        str: 格式化后的 JSON 字符串。
    """
    db = _load_db()
    if skill_id not in db:
        return f"Error: 库中不存在 ID 为 '{skill_id}' 的考点，请先通过 search_skills 确认 ID。"

    return json.dumps(db[skill_id], indent=2, ensure_ascii=False)


def create_skill(
        skill_id: str,
        skill_name: str,
        node_type: str,
        operator_class: str,
        requires: List[str],
        provides: List[str],
        keywords: List[str],
        intents: List[str],
        rubrics: List[str],
        data_params: dict
) -> str:
    """
    【工具功能】向考点库中添加一个全新的业务考点。

    参数:
        skill_id (str): 考点唯一ID（需使用小写的英文和下划线，如 "mut_carbon_tax"）。
        skill_name (str): 考点业务名称（如 "碳排放税核算"）。
        node_type (str): 节点类型，必须是 "base", "mutator", "trap", "global" 之一。
        operator_class (str): 底层执行算子，目前仅支持 "BaseDataGeneratorOperator", "ForeignKeyDictionaryOperator", "CellPerturbationOperator", "GlobalRequirementOperator"。
        requires (List[str]): 依赖的输入语义端口列表，如 ["Financial:PreTax"]。
        provides (List[str]): 提供的输出语义端口列表。
        keywords (List[str]): 业务关键词，便于日后检索。
        intents (List[str]): 业务指令话术模板（可使用大括号包裹 data_params 里的键作占位符）。
        rubrics (List[str]): 隐藏的评分标准模板。
        data_params (dict): 传递给底层算子的具体执行参数字典。

    返回:
        str: 创建成功或失败的系统反馈。
    """
    db = _load_db()
    if skill_id in db:
        return f"Error: 考点 ID '{skill_id}' 已存在！请更换 ID 或使用现有考点。"
    if operator_class not in OPERATOR_REGISTRY:
        return f"Error: 不支持的算子 '{operator_class}'。请先调用 list_available_operators 查看当前系统可用的底层算子列表。"

    # 组装为标准 JSON 结构
    new_skill = {
        "skill_name": skill_name,
        "node_type": node_type,
        "operator_class": operator_class,
        "keywords": keywords,
        "ports": {
            "requires": requires,
            "provides": provides
        },
        "possible_successors": [],  # 新节点默认没有连线
        "semantics": {
            "intents": intents,
            "rubrics": rubrics
        },
        "data_params": data_params
    }

    db[skill_id] = new_skill
    _save_db(db)
    return f"Success: 全新考点 '{skill_name}' ({skill_id}) 已成功注册到题库！你可以继续调用 connect_skills 将它接入现有图谱。"


def connect_skills(source_skill_id: str, target_skill_id: str, port_mapping: Dict[str, str]) -> str:
    """
    【工具功能】在两个考点之间建立数据流动连线（将 source_skill_id 设为 target_skill_id 的前置节点）。

    参数:
        source_skill_id (str): 上游输出数据的考点 ID。
        target_skill_id (str): 下游接收数据的考点 ID。
        port_mapping (Dict[str, str]): 端口映射字典，格式为 {"上游的Provides端口": "下游的Requires端口"}。

    返回:
        str: 连线成功或失败的系统反馈。
    """
    db = _load_db()
    if source_skill_id not in db:
        return f"Error: 上游考点 '{source_skill_id}' 不存在。"
    if target_skill_id not in db:
        return f"Error: 下游考点 '{target_skill_id}' 不存在。"

    # 获取上下游的端口声明
    source_provides = db[source_skill_id].get("ports", {}).get("provides", [])
    target_requires = db[target_skill_id].get("ports", {}).get("requires", [])

    # 严格的语义类型校验
    for src_port, tgt_port in port_mapping.items():
        if src_port not in source_provides:
            return f"Error: 连线失败！上游节点 '{source_skill_id}' 并没有声明提供输出端口 '{src_port}'。它只提供 {source_provides}。"
        if tgt_port not in target_requires:
            return f"Error: 连线失败！下游节点 '{target_skill_id}' 并不需要输入端口 '{tgt_port}'。它需要 {target_requires}。"

    # 校验通过，写入图谱边关系
    new_connection = {
        "skill_id": target_skill_id,
        "port_map": port_mapping
    }

    # 防止重复连线
    existing_connections = db[source_skill_id].get("possible_successors", [])
    for conn in existing_connections:
        if conn["skill_id"] == target_skill_id and conn["port_map"] == port_mapping:
            return f"Notice: 连线已存在，无需重复添加。"

    db[source_skill_id].setdefault("possible_successors", []).append(new_connection)
    _save_db(db)

    return f"Success: 节点 '{source_skill_id}' 已成功连接到 '{target_skill_id}'！图谱拓扑已更新。"


def request_new_operator(intent_description: str, proposed_data_params: dict, required_pandas_logic: str) -> str:
    """
    【工具功能】当现有的底层算子（Operators）都无法满足复杂的财务/数据逻辑时，调用此接口向人类开发者提交开发请求。

    参数:
        intent_description (str): 详细描述这个新考点需要完成的具体业务逻辑（如：按 FIFO 结转库存）。
        proposed_data_params (dict): 你期望这个新算子将来能接收的参数结构示例。
        required_pandas_logic (str): 提供伪代码或 Pandas 操作思路，辅助人类开发者编写算子。

    返回:
        str: 提交成功的反馈。
    """
    request_ticket = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "PENDING_HUMAN_REVIEW",
        "intent": intent_description,
        "proposed_params": proposed_data_params,
        "suggested_logic": required_pandas_logic
    }

    request_file = "pending_operator_requests.json"

    # 将需求追加到本地的工单列表中
    requests = []
    if os.path.exists(request_file):
        with open(request_file, "r", encoding="utf-8") as f:
            requests = json.load(f)

    requests.append(request_ticket)

    with open(request_file, "w", encoding="utf-8") as f:
        json.dump(requests, f, indent=4, ensure_ascii=False)

    return "Success: 新算子开发请求已成功提交给人类架构师！此工单已记录。在人类完成开发并注册到系统前，请跳过此考点，继续处理其他可复用算子的任务。"


def get_port_dictionary() -> str:
    """
    【工具功能】获取系统中所有已注册的语义端口（Ports）列表及其详细定义。
    在进行推演连线（Port Inference）或创建新考点前，必须调用此工具对齐标准词汇！

    返回:
        str: 包含所有合法端口名和解释的文本。
    """
    ports_db = _load_ports_db()
    results = []
    for port_name, desc in ports_db.items():
        results.append(f"- [{port_name}]: {desc}")

    return "系统当前已注册的标准端口如下，请尽可能复用它们：\n" + "\n".join(results)


def register_new_port(port_name: str, description: str) -> str:
    """
    【工具功能】当现有的端口字典中绝对没有合适的端口时，调用此工具注册一个全新的语义端口。

    参数:
        port_name (str): 端口名。必须严格遵循 "类别:细节" 的驼峰命名法（如 "Financial:CarbonTax" 或 "Dimension:ProductLine"）。
        description (str): 对该端口代表的业务含义的英文详细解释。

    返回:
        str: 注册成功或失败的反馈。
    """
    # 1. 严格的命名规范防御 (必须是 Word:Word 格式)
    if not re.match(r"^[A-Z][a-zA-Z0-9]*:[A-Z][a-zA-Z0-9]*$", port_name):
        return f"Error: 端口命名不规范！'{port_name}' 不符合 'Category:Detail' 格式（例如 'Financial:PreTax'，首字母必须大写且不能有空格）。"

    ports_db = _load_ports_db()

    # 2. 防重检查
    if port_name in ports_db:
        return f"Notice: 端口 '{port_name}' 已经存在，无需重复注册，你可以直接使用它。"

    # 3. 注册落盘
    ports_db[port_name] = description
    _save_ports_db(ports_db)

    return f"Success: 新端口 '{port_name}' 已成功注册到全局数据字典！你现在可以在 create_skill 中使用它了。"

# ==========================================
# 供 人类 调用的工具 API
# ==========================================

def admin_delete_skill(skill_id_to_delete: str) -> str:
    """
    【人类管理员专用】安全删除图谱中的考点节点。
    它会自动遍历所有现有考点，解除任何指向被删除节点的连线依赖，然后彻底删除该考点。

    参数:
        skill_id_to_delete (str): 需要删除的考点 ID

    返回:
        str: 操作结果日志
    """
    db = _load_db()

    if skill_id_to_delete not in db:
        return f"Admin Error: 题库中不存在 ID 为 '{skill_id_to_delete}' 的考点。"

    cleaned_edges_count = 0

    # 1. 第一步：清理悬空连边 (Dangling Edges)
    # 遍历所有存在的节点，检查它们的 possible_successors 是否包含了待删除的节点
    for s_id, config in db.items():
        if s_id == skill_id_to_delete:
            continue

        successors = config.get("possible_successors", [])
        original_len = len(successors)

        # 过滤掉所有指向待删除节点的连线
        config["possible_successors"] = [
            conn for conn in successors
            if conn.get("skill_id") != skill_id_to_delete
        ]

        if len(config["possible_successors"]) < original_len:
            cleaned_edges_count += (original_len - len(config["possible_successors"]))
            print(f"[*] Admin Log: 已解除 [{s_id}] 对 [{skill_id_to_delete}] 的后继依赖连线。")

    # 2. 第二步：物理删除节点本体
    del db[skill_id_to_delete]

    # 3. 安全落盘
    _save_db(db)

    return f"Admin Success: 考点 '{skill_id_to_delete}' 已被彻底删除。同步清理了 {cleaned_edges_count} 条失效连线。"

if __name__ == "__main__":
    print(admin_delete_skill("mut_eu_digital_tax"))
'''
    print("=== 1. 测试查询可用算子 ===")
    print(list_available_operators())
    print("-" * 40)

    print("\n=== 2. 测试搜索现有考点 ===")
    print(search_skills(keyword="税"))
    print("-" * 40)

    print("\n=== 3. 模拟 Agent 创建新考点 ===")
    create_res = create_skill(
        skill_id="mut_eu_digital_tax",
        skill_name="欧洲数字服务税",
        node_type="mutator",
        operator_class="ForeignKeyDictionaryOperator",
        requires=["Financial:PreTax", "Dimension:Region"],
        provides=["Financial:PostTax"],
        keywords=["数字税", "欧洲", "合规"],
        intents=["根据 '{dict_table_name}' 扣除欧洲数字服务税，输出到 '{out_result_col}'。"],
        rubrics=["检查是否正确应用了数字税率。"],
        data_params={
            "dict_table_name": "EU_Tax.csv",
            "out_result_col": "Net_After_EU_Tax",
            "dict_join_key": "Region",
            "dict_columns": {"Region": ["France", "Germany"], "Rate": [0.03, 0.03]}
        }
    )
    print(create_res)
    print("-" * 40)

    print("\n=== 4. 模拟 Agent 进行连线 ===")
    connect_res = connect_skills(
        source_skill_id="base_pnl_01",
        target_skill_id="mut_eu_digital_tax",
        port_mapping={"Financial:PreTax": "Financial:PreTax", "Dimension:Region": "Dimension:Region"}
    )
    print(connect_res)
'''
