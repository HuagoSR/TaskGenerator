import sys

sys.path.append("..")
from Skill.skill_graph import SkillNode
from FileGenerator.blueprint_core import ProceduralGenerator, ForeignKeyGenerator


class BaseDataGeneratorOperator(SkillNode):
    """通用基石算子：凭空造表"""
    def on_join_graph(self, graph):
        self.table_name = self.data_params["table_name"]
        for i, port_name in enumerate(self.provides):
            physical_col = self.data_params["output_columns"][i]["name"]
            self.output_names[port_name] = (self.table_name, physical_col)
        self.data_params["out_table"] = self.table_name
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        bp = vfs.create_tabular_blueprint(self.table_name)
        for col_info in self.data_params["output_columns"]:
            gen_type = col_info["generator_type"]
            kwargs = col_info.get("kwargs", {})
            bp.add_column(col_info["name"], ProceduralGenerator(gen_type, **kwargs))

class ForeignKeyDictionaryOperator(SkillNode):
    """通用变异算子：造字典表并打外键（搞定扣税、汇率、提成等一切乘法映射）"""
    def on_join_graph(self, graph):
        self.target_table, self.amount_col = self.resolve_input_port(self.requires[0], graph)
        _, self.fk_col = self.resolve_input_port(self.requires[1], graph)

        self.dict_table = self.data_params["dict_table_name"]
        self.out_col = self.data_params["out_result_col"]
        self.output_names[self.provides[0]] = (self.target_table, self.out_col)

        self.data_params.update({
            "in_target_table": self.target_table,
            "in_amount_col": self.amount_col,
            "in_fk_col": self.fk_col
        })
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        dict_bp = vfs.create_tabular_blueprint(self.dict_table)
        for col_name, values in self.data_params["dict_columns"].items():
            dict_bp.add_column(col_name, ProceduralGenerator("constant_list", values=values))
        target_bp = vfs.get_blueprint(self.target_table)
        target_bp.add_column(self.fk_col, ForeignKeyGenerator(self.dict_table, self.data_params["dict_join_key"]))

class CellPerturbationOperator(SkillNode):
    """通用陷阱算子：对单元格进行物理破坏"""
    def on_join_graph(self, graph):
        self.target_table, self.target_col = self.resolve_input_port(self.requires[0], graph)
        self.data_params.update({
            "in_target_table": self.target_table,
            "in_target_col": self.target_col
        })
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        target_bp = vfs.get_blueprint(self.target_table)
        count = self.data_params.get("trap_count", 1)
        target_bp.inject_trap(trap_name=self.node_id, handler=self.apply_trap, count=count)

    def apply_trap(self, df, victim_indices):
        mode = self.data_params["perturbation_mode"]
        for idx in victim_indices:
            if mode == "to_negative":
                val = df.loc[idx, self.target_col]
                df.loc[idx, self.target_col] = -abs(float(val))
            elif mode == "to_null":
                df.loc[idx, self.target_col] = None

class GlobalRequirementOperator(SkillNode):
    """空降算子：纯文案，不碰数据"""
    def on_join_graph(self, graph):
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        pass