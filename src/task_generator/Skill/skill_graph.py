import collections
from typing import Dict, Tuple


class SafeDict(dict):
    """Format-map helper that leaves unknown placeholders unchanged."""

    def __missing__(self, key):
        return "{" + key + "}"


class SkillNode:
    """Dynamic legacy skill node backed by a JSON skill config."""

    def __init__(self, node_id: str, skill_config: dict = None):
        self.node_id = node_id
        self.input_bindings: Dict[str, dict] = {}
        self.output_names: Dict[str, Tuple[str, str]] = {}
        self.rendered_intents = []
        self.rendered_constraints = []
        self.rendered_rubrics = []

        self.skill_config = skill_config or {}
        self.name = self.skill_config.get("skill_name", "unnamed_skill")
        self.node_type = self.skill_config.get("node_type", "base")
        self.max_instances = self.skill_config.get("max_instances", 1)
        self.keywords = self.skill_config.get("keywords", [])

        ports = self.skill_config.get("ports", {})
        self.requires = ports.get("requires", [])
        self.provides = ports.get("provides", [])
        self.possible_successors = self.skill_config.get("possible_successors", [])

        semantics = self.skill_config.get("semantics", {})
        self.prompt_intents = semantics.get("intents", [])
        self.deliverable_constraints = semantics.get("constraints", [])
        self.hidden_rubrics = semantics.get("rubrics", [])
        self.expected_deliverables = semantics.get("deliverables", [])
        self.system_prompt = semantics.get("system_prompt", "You are a helpful task designer.")

        self.data_params = self.skill_config.get("data_params", {})
        self.suggested_row_counts = self.data_params.get("suggested_row_counts", {})

        if not self.expected_deliverables:
            possible_file = self.data_params.get("output_file") or self.data_params.get("deliverable_file")
            if possible_file:
                self.expected_deliverables = [possible_file]

    def resolve_input_port(self, in_port_name: str, graph) -> Tuple[str, str]:
        if in_port_name not in self.input_bindings:
            raise ValueError(f"Node {self.node_id} ({self.name}) has no binding for input port {in_port_name}.")

        binding = self.input_bindings[in_port_name]
        source_node = graph.nodes[binding["source"]]
        if binding["port"] not in source_node.output_names:
            raise ValueError(f"Source node {binding['source']} has not registered output port {binding['port']}.")

        return source_node.output_names[binding["port"]]

    def on_join_graph(self, graph):
        format_dict = self.data_params.copy()
        if self.expected_deliverables:
            format_dict["deliverables"] = " and ".join([f"'{item}'" for item in self.expected_deliverables])
        else:
            format_dict["deliverables"] = "'the required output files'"

        safe_format_dict = SafeDict(**format_dict)
        self.rendered_intents = [
            item.format_map(safe_format_dict) if "{" in item else item
            for item in self.prompt_intents
        ]
        self.rendered_constraints = [
            item.format_map(safe_format_dict) if "{" in item else item
            for item in self.deliverable_constraints
        ]
        self.rendered_rubrics = [
            item.format_map(safe_format_dict) if "{" in item else item
            for item in self.hidden_rubrics
        ]

    def register_data_operations(self, vfs, graph):
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
        print(f"--- connected: {from_id}[{out_port}] ---> {to_id}[{in_port}]")

    def topological_sort(self):
        queue = [node_id for node_id, degree in self.in_degree.items() if degree == 0]
        order = []
        in_degree = self.in_degree.copy()
        while queue:
            current = queue.pop(0)
            order.append(self.nodes[current])
            for neighbor in self.adjacency_list[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        return order

    def compile_semantics(self):
        result = {
            "System_Prompt": "",
            "Intents": [],
            "Constraints": [],
            "Rubrics": [],
            "Suggested_Rows": {},
            "Deliverables": [],
        }
        for node in self.topological_sort():
            if node.node_type == "base":
                result["System_Prompt"] = getattr(node, "system_prompt", "You are a helpful task designer.")
            if node.node_type != "trap":
                result["Intents"].extend(node.rendered_intents)
                result["Constraints"].extend(node.rendered_constraints)
            result["Rubrics"].extend(getattr(node, "rendered_rubrics", []))
            if hasattr(node, "suggested_row_counts"):
                result["Suggested_Rows"].update(node.suggested_row_counts)
            if hasattr(node, "expected_deliverables"):
                result["Deliverables"].extend(node.expected_deliverables)
        return result


def build_greedy_graph(base_skill_id: str) -> SkillGraph:
    """Build a dependency-satisfying graph starting from one base skill."""
    from task_generator.Skill.skill_bank import SKILL_REGISTRY

    graph = SkillGraph()
    pending_candidates = {}
    instantiated_counts = collections.defaultdict(int)
    queue = []

    base_skill_class = SKILL_REGISTRY[base_skill_id]
    instantiated_counts[base_skill_id] += 1
    base_inst_id = f"{base_skill_id}_inst_{instantiated_counts[base_skill_id]}"
    base_node = base_skill_class(node_id=base_inst_id)

    graph.add_node(base_node)
    base_node.on_join_graph(graph)
    queue.append(base_node)

    print(f"--- seeded base skill: {base_node.name} ({base_inst_id})")

    while queue:
        current_node = queue.pop(0)
        for successor in current_node.possible_successors:
            successor_id = successor["skill_id"]
            port_map = successor["port_map"]
            successor_skill_class = SKILL_REGISTRY[successor_id]

            if instantiated_counts[successor_id] >= successor_skill_class.max_instances:
                continue

            pending_candidates.setdefault(successor_id, {})
            for out_port, in_port in port_map.items():
                pending_candidates[successor_id][in_port] = (current_node.node_id, out_port)

            required_ports = set(successor_skill_class.requires)
            collected_ports = set(pending_candidates[successor_id].keys())
            if required_ports.issubset(collected_ports):
                instantiated_counts[successor_id] += 1
                new_inst_id = f"{successor_id}_inst_{instantiated_counts[successor_id]}"
                new_node = successor_skill_class(node_id=new_inst_id)

                graph.add_node(new_node)
                print(f"--- instantiated skill: {new_node.name} ({new_inst_id})")

                for in_port, (source_inst_id, source_out_port) in pending_candidates[successor_id].items():
                    if in_port in required_ports:
                        graph.connect_ports(source_inst_id, source_out_port, new_inst_id, in_port)

                new_node.on_join_graph(graph)
                queue.append(new_node)
                pending_candidates[successor_id] = {}
            else:
                missing = required_ports - collected_ports
                print(f"--- skill {successor_id} waiting for missing ports: {missing}")

    return graph


if __name__ == "__main__":
    import json

    auto_graph = build_greedy_graph("base_pnl_01")
    print(json.dumps(auto_graph.compile_semantics(), indent=4, ensure_ascii=False))
