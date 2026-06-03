import sys
import pandas as pd
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
        # 解析输入端口
        self.target_table, self.target_col = self.resolve_input_port(self.requires[0], graph)

        # 如果该 Trap 节点定义了输出端口，必须注册物理映射
        if self.provides:
            self.output_names[self.provides[0]] = (self.target_table, self.target_col)

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
            val = df.loc[idx, self.target_col]

            # 如果这个单元格已经是空的了，就跳过它，不要再尝试做数学运算
            if pd.isna(val) and mode != "to_null":
                continue

            try:
                if mode == "to_negative":
                    df.loc[idx, self.target_col] = -abs(float(val))
                elif mode == "to_null":
                    df.loc[idx, self.target_col] = None
            except ValueError:
                # 防御性编程：万一里面是个字符串（比如 "Unknown"），转 float 会失败，直接跳过
                continue

class GlobalRequirementOperator(SkillNode):
    """空降算子：纯文案，不碰数据"""
    def on_join_graph(self, graph):
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        pass


class TabularDataLoaderOperator(SkillNode):
    def on_join_graph(self, graph):
        # 修正：直接用完整文件名建表更安全，防止 VFS 丢失后缀
        self.target_table = self.data_params["source_file"]
        output_cols = self.data_params.get("output_columns", [])
        for i, port_name in enumerate(self.provides):
            if i < len(output_cols):
                col_name = output_cols[i]["name"]
            else:
                col_name = port_name.split(":")[-1].lower()
            self.output_names[port_name] = (self.target_table, col_name)
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        bp = vfs.get_blueprint(self.target_table) if self.target_table in vfs.blueprints else vfs.create_tabular_blueprint(self.target_table)
        for col_info in self.data_params.get("output_columns", []):
            bp.add_column(col_info["name"], ProceduralGenerator(col_info["generator_type"], **col_info.get("kwargs", {})))



class ColumnMultiplierOperator(SkillNode):
    def on_join_graph(self, graph):
        self.target_table, _ = self.resolve_input_port(self.requires[0], graph)

        out_col = (
                self.data_params.get("output_col") or
                self.data_params.get("output_column") or
                self.data_params.get("new_col")
        )

        if not out_col:
            raise KeyError(f"节点 {self.node_id} 找不到输出列名！(尝试了 output_col, output_column, new_col 均失败)")

        self.output_names[self.provides[0]] = (self.target_table, out_col)
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        pass


class PhantomTaskOperator(SkillNode):
    """
    万能幽灵算子：专门处理所有 Mutator（变异）考点。
    修复版：支持多端口同时输出，并智能推断物理列名。
    """

    def on_join_graph(self, graph):
        if self.provides:  # 如果有输出端口
            # 幽灵算子默认继承第一个输入端口所在的表名
            self.target_table, _ = self.resolve_input_port(self.requires[0], graph)

            # 遍历大模型给出的所有输出端口
            for port_name in self.provides:
                # 尝试拿大模型显式指定的列名
                out_col = self.data_params.get("output_col") or self.data_params.get("new_col")

                # 如果没给，或者有多个端口共用，就用端口名拆分作为物理列名（例如 "Financial:CostData" -> "CostData"）
                if not out_col or len(self.provides) > 1:
                    out_col = port_name.split(":")[-1]

                    # 将每个端口都老老实实注册进大字典
                self.output_names[port_name] = (self.target_table, out_col)

        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        # 绝对的幽灵，VFS 造表时什么都不做
        pass


class PhantomTaskOperator(SkillNode):
    """
    万能幽灵算子：专门处理所有 Mutator（变异）考点。
    修复版：支持多端口同时输出，并智能推断物理列名。
    """

    def on_join_graph(self, graph):
        if self.provides:  # 如果有输出端口
            # 幽灵算子默认继承第一个输入端口所在的表名
            self.target_table, _ = self.resolve_input_port(self.requires[0], graph)

            # 遍历大模型给出的所有输出端口
            for port_name in self.provides:
                # 尝试拿大模型显式指定的列名
                out_col = self.data_params.get("output_col") or self.data_params.get("new_col")

                # 如果没给，或者有多个端口共用，就用端口名拆分作为物理列名
                if not out_col or len(self.provides) > 1:
                    out_col = port_name.split(":")[-1]

                self.output_names[port_name] = (self.target_table, out_col)

        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        # 绝对的幽灵，VFS 造表时什么都不做
        pass


class PhantomTrapOperator(SkillNode):
    """
    幽灵陷阱算子 (Semantic Trap Operator)
    用于那些“要求考生清洗/填补/处理异常”，但不需要底层引擎去发生物理破坏的考点。
    """

    def on_join_graph(self, graph):
        # 支持把清洗后的结果映射到 provides 端口，逻辑同 PhantomTaskOperator
        if self.provides:
            self.target_table, _ = self.resolve_input_port(self.requires[0], graph)
            for port_name in self.provides:
                out_col = self.data_params.get("output_col") or self.data_params.get("new_col") or port_name.split(":")[
                    -1]
                self.output_names[port_name] = (self.target_table, out_col)
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        # 核心：它是幽灵陷阱，不在系统初始数据生成阶段（VFS）挖任何坑
        pass

class MultiColumnPerturbationOperator(SkillNode):
    """
    终极防御版陷阱算子 (免疫大模型幻觉)
    严格依赖 DAG 图谱的物理连线，绝对不信任大模型在 data_params 里瞎编的列名。
    """

    def on_join_graph(self, graph):
        # 记录需要破坏的物理表和物理列：[(table1, col1), (table1, col2), ...]
        self.target_columns_info = []

        # 防御 1：如果大模型忘了给输入端口，直接跳过，不引发崩溃
        if not self.requires:
            print(f"[Trap Operator] 警告：节点 {self.node_id} 没有 requires 端口，跳过物理破坏。")
            return

        # 顺着网线找物理列，彻底无视 data_params 里的列名！
        for in_port in self.requires:
            tbl, col = self.resolve_input_port(in_port, graph)
            self.target_columns_info.append((tbl, col))

        # 透传输出端口（如果有的话）
        for i, port in enumerate(self.provides):
            tbl, col = self.target_columns_info[i] if i < len(self.target_columns_info) else self.target_columns_info[0]
            self.output_names[port] = (tbl, col)

        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        if not hasattr(self, 'target_columns_info') or not self.target_columns_info:
            return

        # 将物理列按表分组（因为 VFS 是按表来触发 Trap 的）
        from collections import defaultdict
        table_to_cols = defaultdict(list)
        for tbl, col in self.target_columns_info:
            table_to_cols[tbl].append(col)

        # 防御 2：安全获取破坏数量，找不到就默认 5 行
        count = self.data_params.get("trap_count", 5)

        for tbl, cols in table_to_cols.items():
            bp = vfs.get_blueprint(tbl)

            # 使用闭包将具体的物理列名传递给破坏函数
            bp.inject_trap(
                trap_name=f"{self.node_id}_{tbl}",
                handler=lambda df, idxs, target_cols=cols: self._apply_trap_logic(df, idxs, target_cols),
                count=count
            )

    def _apply_trap_logic(self, df, victim_indices, target_cols):
        import pandas as pd

        #防御 3：安全获取破坏模式，大模型没给就默认转空值
        mode = self.data_params.get("perturbation_mode", "to_null")

        for idx in victim_indices:
            # 万一 VFS 传来的索引越界，安全跳过
            if idx not in df.index:
                continue

            for col in target_cols:
                #终极防御：如果在表里还是找不到这列，直接跳过
                if col not in df.columns:
                    continue

                val = df.loc[idx, col]

                # 如果这个单元格已经是空的了，就不要再尝试做数学运算
                if pd.isna(val) and mode != "to_null":
                    continue

                try:
                    if mode == "to_negative":
                        df.loc[idx, col] = -abs(float(val))
                    elif mode == "to_null":
                        df.loc[idx, col] = None
                except ValueError:
                    # 如果单元格里是个字符串（比如 "Unknown"），转 float 会失败，直接跳过
                    continue


class MultiTableBaseOperator(SkillNode):
    """
    多表基石算子 (升级版)：支持读取完整的表结构 Schema，
    不仅生成用于图谱计算的端口列，还能生成用于增加业务真实性的“背景维度列”。
    """

    def on_join_graph(self, graph):
        # 1. 获取需要生成的所有表名
        self.target_tables = list(self.suggested_row_counts.keys())
        if not self.target_tables:
            # 兜底防御
            self.target_tables = ["primary_data.xlsx", "reference_data.xlsx"]

        # 2. 将 provides 端口映射到物理表和物理列
        for i, port_name in enumerate(self.provides):
            # 将端口尽量均匀地分配到各个表
            table_idx = min(i, len(self.target_tables) - 1)
            t_name = self.target_tables[table_idx]

            # 默认：用端口名的后缀作为被计算的物理列名（例如 "Finance:RawTourData" -> "RawTourData"）
            col_name = port_name.split(":")[-1]

            # 高阶支持：如果大模型在 data_params 中给出了精准的端口映射字典，则优先使用
            port_mapping = self.data_params.get("port_to_column_mapping", {})
            if port_name in port_mapping:
                t_name = port_mapping[port_name].get("table", t_name)
                col_name = port_mapping[port_name].get("column", col_name)

            self.output_names[port_name] = (t_name, col_name)

        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        # 3. 核心改造：尝试读取大模型设计好的完整数据表架构
        schemas = self.data_params.get("schemas", {})

        for t_name in self.target_tables:
            bp = vfs.create_tabular_blueprint(t_name)

            # 情况 A：如果 Agent 3 听话地写了这张表的 schemas，直接按照 schema 完整造表（含冗余列）
            if t_name in schemas:
                for col_info in schemas[t_name]:
                    gen_type = col_info.get("generator_type", "random_float")
                    kwargs = col_info.get("kwargs", {})
                    # 将列的生成器挂载到蓝图上
                    bp.add_column(col_info["name"], ProceduralGenerator(gen_type, **kwargs))

            # 情况 B：兜底防御，大模型忘了写 schemas，回退到老办法（只生成被端口用到的列）
            else:
                print(f"[警告] 基石节点 {self.node_id} 缺少表 '{t_name}' 的 schemas 定义，降级为仅生成计算端口列。")
                for port_name, (tbl, col) in self.output_names.items():
                    if tbl == t_name:
                        bp.add_column(col, ProceduralGenerator("random_float", min=100.0, max=5000.0))