from typing import List, Dict, Optional, Any, Tuple
import collections



class SkillNode:
    """三位一体的考点超级基类"""
    # === 类级别的元数据配置 ===
    node_type: str = "base"
    name: str = "未命名考点"
    max_instances: int = 1
    requires: List[str] = []
    provides: List[str] = []
    possible_successors: List[Dict] = []
    prompt_intents: List[str] = []
    deliverable_constraints: List[str] = []
    hidden_rubrics: List[str] = []
    expected_deliverables: List[str] = []

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.input_bindings: Dict[str, dict] = {}
        self.output_names: Dict[str, Tuple[str, str]] = {}  # 存储 (表名, 列名)
        self.rendered_intents = []
        self.rendered_constraints = []
        self.rendered_rubrics = []

    def resolve_input_port(self, in_port_name: str, graph) -> Tuple[str, str]:
        if in_port_name not in self.input_bindings:
            raise ValueError(f"节点 {self.node_id} 的输入端口 {in_port_name} 未连接！")

        binding = self.input_bindings[in_port_name]
        source_node = graph.nodes[binding["source"]]

        if binding["port"] not in source_node.output_names:
            raise ValueError(f"源头节点 {binding['source']} 尚未注册输出端口 {binding['port']} 的物理名称！")

        return source_node.output_names[binding["port"]]

    def on_join_graph(self, graph):
        """
        符号绑定与语义渲染。
        子类重写此方法，用于：
        1. 寻址并锁定上游的表名和列名。
        2. 给自己即将生成的数据起名字。
        3. 渲染 semantic_intents 模版。
        """
        pass

    def register_data_operations(self, vfs, graph):
        """纯粹的数据生成。子类必须重写这个方法"""
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