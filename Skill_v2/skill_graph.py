from typing import List, Dict, Optional, Any, Tuple
import collections


class SkillNode:
    """
    考点超级基类
    SkillNode 是一个动态容器，它的“灵魂”由传入的 JSON config 决定。
    """

    def __init__(self, node_id: str, skill_config: dict = None):
        self.node_id = node_id

        # 1. 物理连线状态 (运行时产生)
        self.input_bindings: Dict[str, dict] = {}
        self.output_names: Dict[str, Tuple[str, str]] = {}  # 存储 (表名, 列名)

        # 2. 运行时渲染状态
        self.rendered_intents = []
        self.rendered_constraints = []
        self.rendered_rubrics = []

        # ==========================================
        # 以下属性全部从 JSON 配置文件动态注入
        # ==========================================
        self.skill_config = skill_config or {}

        # 基础元数据
        self.name = self.skill_config.get("skill_name", "未命名考点")
        self.node_type = self.skill_config.get("node_type", "base")
        self.max_instances = self.skill_config.get("max_instances", 1)
        self.keywords = self.skill_config.get("keywords", [])


        # 拓扑与连线端口
        ports = self.skill_config.get("ports", {})
        self.requires = ports.get("requires", [])
        self.provides = ports.get("provides", [])
        self.possible_successors = self.skill_config.get("possible_successors", [])

        # 语义与文案
        semantics = self.skill_config.get("semantics", {})
        self.prompt_intents = semantics.get("intents", [])
        self.deliverable_constraints = semantics.get("constraints", [])
        self.hidden_rubrics = semantics.get("rubrics", [])
        self.expected_deliverables = semantics.get("deliverables", [])
        self.system_prompt = semantics.get("system_prompt", "You are a helpful task designer.")

        # 核心：执行期参数（供底层的具体 Python 操作类读取使用）
        # 例如：税率字典的文件名、需要相乘的常数、陷阱破坏的行数等
        self.data_params = self.skill_config.get("data_params", {})
        self.suggested_row_counts = self.data_params.get("suggested_row_counts", {})

    def resolve_input_port(self, in_port_name: str, graph) -> Tuple[str, str]:
        """顺藤摸瓜：根据逻辑端口名，向图谱上游索要真实的(物理表名, 物理列名)"""
        if in_port_name not in self.input_bindings:
            raise ValueError(f"节点 {self.node_id} ({self.name}) 的输入端口 {in_port_name} 未连接！")

        binding = self.input_bindings[in_port_name]
        source_node = graph.nodes[binding["source"]]

        if binding["port"] not in source_node.output_names:
            raise ValueError(f"源头节点 {binding['source']} 尚未注册输出端口 {binding['port']} 的物理名称！")

        return source_node.output_names[binding["port"]]

    def on_join_graph(self, graph):
        """
        【通用发车安检口】
        在V2架构下，因为我们有了统一的 self.data_params 字典，
        我们可以把渲染逻辑下沉到基类，这样未来的 Operator 子类甚至不用重写这个方法！
        """
        # 默认实现：如果有格式化字典，直接拿 data_params 里的物理名字去渲染
        format_dict = self.data_params.copy()

        # 如果子类在调用 super().on_join_graph() 前解析了 input_port，
        # 可以把上游的物理表名/列名也加进 format_dict 里。

        self.rendered_intents = [i.format(**format_dict) if '{' in i else i for i in self.prompt_intents]
        self.rendered_constraints = [c.format(**format_dict) if '{' in c else c for c in self.deliverable_constraints]
        self.rendered_rubrics = [r.format(**format_dict) if '{' in r else r for r in self.hidden_rubrics]

    def register_data_operations(self, vfs, graph):
        """纯粹的数据生成。由继承本类的“算子(Operator)”具体实现"""
        pass


class SkillGraph:
    def __init__(self):
        self.nodes = {}
        self.adjacency_list = {}
        self.in_degree = {}

    def add_node(self, node: SkillNode):
        self.nodes[node.node_id] = node
        self.adjacency_list[node.node_id] = []
        self.in_degree[node.node_id] = 0

    def connect_ports(self, from_id, out_port, to_id, in_port):
        self.nodes[to_id].input_bindings[in_port] = {"source": from_id, "port": out_port}
        self.adjacency_list[from_id].append(to_id)
        self.in_degree[to_id] += 1
        print(f"--- 连线成功: {from_id}[{out_port}] ---> {to_id}[{in_port}]")

    def topological_sort(self):
        queue = [nid for nid, deg in self.in_degree.items() if deg == 0]
        order = []
        in_deg_temp = self.in_degree.copy()
        while queue:
            curr = queue.pop(0)
            order.append(self.nodes[curr])
            for neighbor in self.adjacency_list[curr]:
                in_deg_temp[neighbor] -= 1
                if in_deg_temp[neighbor] == 0:
                    queue.append(neighbor)
        return order

    def compile_semantics(self):
        order = self.topological_sort()
        res = {
            "System_Prompt": "",
            "Intents": [],
            "Constraints": [],
            "Rubrics": [],
            "Suggested_Rows": {},
            "Deliverables": []
        }
        for n in order:
            if n.node_type == "base":
                res["System_Prompt"] = getattr(n, "system_prompt", "You are a helpful task designer.")

            res["Intents"].extend(n.rendered_intents)
            res["Constraints"].extend(n.rendered_constraints)
            res["Rubrics"].extend(getattr(n, "rendered_rubrics", []))
            if hasattr(n, 'suggested_row_counts'):
                res["Suggested_Rows"].update(n.suggested_row_counts)
            if hasattr(n, 'expected_deliverables'):
                res["Deliverables"].extend(n.expected_deliverables)

        return res


def build_greedy_graph(base_skill_id: str) -> SkillGraph:
    """
    贪婪生长图算法：给定一个基石考点，让图尽可能地长出所有满足依赖的分支。
    """
    from Skill.skill_bank import SKILL_REGISTRY

    graph = SkillGraph()
    pending_candidates = {}

    # 计数器
    instantiated_counts = collections.defaultdict(int)
    queue = []

    BaseSkillClass = SKILL_REGISTRY[base_skill_id]

    # 赋予带编号的唯一 Node ID
    instantiated_counts[base_skill_id] += 1
    base_inst_id = f"{base_skill_id}_inst_{instantiated_counts[base_skill_id]}"
    base_node = BaseSkillClass(node_id=base_inst_id)

    graph.add_node(base_node)
    base_node.on_join_graph(graph)
    queue.append(base_node)

    print(f"--- 种下基石节点: {base_node.name} ({base_inst_id})")

    while queue:
        current_node = queue.pop(0)

        for succ in current_node.possible_successors:
            succ_id = succ["skill_id"]
            port_map = succ["port_map"]
            SuccSkillClass = SKILL_REGISTRY[succ_id]

            # 检查该考点是否已经达到了最大繁殖上限
            if instantiated_counts[succ_id] >= SuccSkillClass.max_instances:
                continue

            if succ_id not in pending_candidates:
                pending_candidates[succ_id] = {}

            # 将上游的 (节点ID, 端口名) 放入候车室
            for out_port, in_port in port_map.items():
                pending_candidates[succ_id][in_port] = (current_node.node_id, out_port)

            required_ports = set(SuccSkillClass.requires)
            collected_ports = set(pending_candidates[succ_id].keys())

            if required_ports.issubset(collected_ports):
                # 依赖全部满足，孵化带编号的新节点！
                instantiated_counts[succ_id] += 1
                new_inst_id = f"{succ_id}_inst_{instantiated_counts[succ_id]}"
                new_node = SuccSkillClass(node_id=new_inst_id)

                graph.add_node(new_node)
                print(f"--- 成功孵化节点: {new_node.name} ({new_inst_id})")

                # 执行连线
                for in_p, (src_inst_id, src_out_p) in pending_candidates[succ_id].items():
                    if in_p in required_ports:
                        graph.connect_ports(src_inst_id, src_out_p, new_inst_id, in_p)

                # 触发发车安检，锁定物理名称
                new_node.on_join_graph(graph)
                queue.append(new_node)

                # 清空该考点的候车室，为它的下一次实例化腾出空间
                # 注意：这里不能用 del，否则下一个实例来的时候会报错
                pending_candidates[succ_id] = {}
            else:
                missing = required_ports - collected_ports
                print(f"--- 节点 {succ_id} 正在候车室等待，还缺: {missing}")

    return graph


if __name__ == "__main__":    
    auto_graph = build_greedy_graph("base_pnl_01")    
    result = auto_graph.compile_semantics()
    import json
    print(json.dumps(result, indent=4, ensure_ascii=False))