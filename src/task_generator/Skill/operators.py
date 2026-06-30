from collections import defaultdict

import pandas as pd

from task_generator.FileGenerator.blueprint_core import ForeignKeyGenerator, ProceduralGenerator
from task_generator.Skill.skill_graph import SkillNode


class BaseDataGeneratorOperator(SkillNode):
    """Create a base table from procedural column generators."""

    def on_join_graph(self, graph):
        self.table_name = self.data_params["table_name"]
        for index, port_name in enumerate(self.provides):
            physical_col = self.data_params["output_columns"][index]["name"]
            self.output_names[port_name] = (self.table_name, physical_col)
        self.data_params["out_table"] = self.table_name
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        blueprint = vfs.create_tabular_blueprint(self.table_name)
        for col_info in self.data_params["output_columns"]:
            generator_type = col_info["generator_type"]
            kwargs = col_info.get("kwargs", {})
            blueprint.add_column(col_info["name"], ProceduralGenerator(generator_type, **kwargs))


class ForeignKeyDictionaryOperator(SkillNode):
    """Create a dictionary table and attach a foreign-key column to a target table."""

    def on_join_graph(self, graph):
        self.target_table, self.amount_col = self.resolve_input_port(self.requires[0], graph)
        _, self.fk_col = self.resolve_input_port(self.requires[1], graph)

        self.dict_table = self.data_params["dict_table_name"]
        self.out_col = self.data_params["out_result_col"]
        self.output_names[self.provides[0]] = (self.target_table, self.out_col)

        self.data_params.update(
            {
                "in_target_table": self.target_table,
                "in_amount_col": self.amount_col,
                "in_fk_col": self.fk_col,
            }
        )
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        dict_blueprint = vfs.create_tabular_blueprint(self.dict_table)
        for col_name, values in self.data_params["dict_columns"].items():
            dict_blueprint.add_column(col_name, ProceduralGenerator("constant_list", values=values))
        target_blueprint = vfs.get_blueprint(self.target_table)
        target_blueprint.add_column(self.fk_col, ForeignKeyGenerator(self.dict_table, self.data_params["dict_join_key"]))


class CellPerturbationOperator(SkillNode):
    """Apply a single-column trap to generated data."""

    def on_join_graph(self, graph):
        self.target_table, self.target_col = self.resolve_input_port(self.requires[0], graph)
        if self.provides:
            self.output_names[self.provides[0]] = (self.target_table, self.target_col)
        self.data_params.update(
            {
                "in_target_table": self.target_table,
                "in_target_col": self.target_col,
            }
        )
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        target_blueprint = vfs.get_blueprint(self.target_table)
        count = self.data_params.get("trap_count", 1)
        target_blueprint.inject_trap(trap_name=self.node_id, handler=self.apply_trap, count=count)

    def apply_trap(self, df, victim_indices):
        mode = self.data_params["perturbation_mode"]
        for idx in victim_indices:
            val = df.loc[idx, self.target_col]
            if pd.isna(val) and mode != "to_null":
                continue
            try:
                if mode == "to_negative":
                    df.loc[idx, self.target_col] = -abs(float(val))
                elif mode == "to_null":
                    df.loc[idx, self.target_col] = None
            except ValueError:
                continue


class GlobalRequirementOperator(SkillNode):
    """Semantic-only operator that does not modify generated data."""

    def register_data_operations(self, vfs, graph):
        pass


class TabularDataLoaderOperator(SkillNode):
    """Register columns for a source table described by data_params."""

    def on_join_graph(self, graph):
        self.target_table = self.data_params["source_file"]
        output_cols = self.data_params.get("output_columns", [])
        for index, port_name in enumerate(self.provides):
            if index < len(output_cols):
                col_name = output_cols[index]["name"]
            else:
                col_name = port_name.split(":")[-1].lower()
            self.output_names[port_name] = (self.target_table, col_name)
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        if self.target_table in vfs.blueprints:
            blueprint = vfs.get_blueprint(self.target_table)
        else:
            blueprint = vfs.create_tabular_blueprint(self.target_table)
        for col_info in self.data_params.get("output_columns", []):
            blueprint.add_column(col_info["name"], ProceduralGenerator(col_info["generator_type"], **col_info.get("kwargs", {})))


class ColumnMultiplierOperator(SkillNode):
    """Declare a derived output column without generating it in VFS."""

    def on_join_graph(self, graph):
        self.target_table, _ = self.resolve_input_port(self.requires[0], graph)
        out_col = self.data_params.get("output_col") or self.data_params.get("output_column") or self.data_params.get("new_col")
        if not out_col:
            raise KeyError(f"Node {self.node_id} is missing output_col, output_column, or new_col.")
        self.output_names[self.provides[0]] = (self.target_table, out_col)
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        pass


class PhantomTaskOperator(SkillNode):
    """Semantic placeholder for mutator-like skills without physical data generation."""

    def on_join_graph(self, graph):
        if self.provides:
            self.target_table, _ = self.resolve_input_port(self.requires[0], graph)
            for port_name in self.provides:
                out_col = self.data_params.get("output_col") or self.data_params.get("new_col")
                if not out_col or len(self.provides) > 1:
                    out_col = port_name.split(":")[-1]
                self.output_names[port_name] = (self.target_table, out_col)
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        pass


class PhantomTrapOperator(SkillNode):
    """Semantic placeholder for trap-handling skills without physical data corruption."""

    def on_join_graph(self, graph):
        if self.provides:
            self.target_table, _ = self.resolve_input_port(self.requires[0], graph)
            for port_name in self.provides:
                out_col = self.data_params.get("output_col") or self.data_params.get("new_col") or port_name.split(":")[-1]
                self.output_names[port_name] = (self.target_table, out_col)
        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        pass


class MultiColumnPerturbationOperator(SkillNode):
    """Apply one trap across multiple resolved physical columns."""

    def on_join_graph(self, graph):
        self.target_columns_info = []
        if not self.requires:
            print(f"[Trap Operator] Node {self.node_id} has no required ports; skipping physical perturbation.")
            return

        for in_port in self.requires:
            table_name, col_name = self.resolve_input_port(in_port, graph)
            self.target_columns_info.append((table_name, col_name))

        for index, port_name in enumerate(self.provides):
            table_name, col_name = (
                self.target_columns_info[index]
                if index < len(self.target_columns_info)
                else self.target_columns_info[0]
            )
            self.output_names[port_name] = (table_name, col_name)

        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        if not getattr(self, "target_columns_info", None):
            return

        table_to_cols = defaultdict(list)
        for table_name, col_name in self.target_columns_info:
            table_to_cols[table_name].append(col_name)

        count = self.data_params.get("trap_count", 5)
        for table_name, cols in table_to_cols.items():
            blueprint = vfs.get_blueprint(table_name)
            blueprint.inject_trap(
                trap_name=f"{self.node_id}_{table_name}",
                handler=lambda df, idxs, target_cols=cols: self._apply_trap_logic(df, idxs, target_cols),
                count=count,
            )

    def _apply_trap_logic(self, df, victim_indices, target_cols):
        mode = self.data_params.get("perturbation_mode", "to_null")
        for idx in victim_indices:
            if idx not in df.index:
                continue
            for col_name in target_cols:
                if col_name not in df.columns:
                    continue
                val = df.loc[idx, col_name]
                if pd.isna(val) and mode != "to_null":
                    continue
                try:
                    if mode == "to_negative":
                        df.loc[idx, col_name] = -abs(float(val))
                    elif mode == "to_null":
                        df.loc[idx, col_name] = None
                except ValueError:
                    continue


class MultiTableBaseOperator(SkillNode):
    """Create multiple base tables from schemas in data_params."""

    def on_join_graph(self, graph):
        self.target_tables = list(getattr(self, "suggested_row_counts", {}).keys())
        if not self.target_tables:
            self.target_tables = ["primary_data.xlsx", "reference_data.xlsx"]

        for index, port_name in enumerate(self.provides):
            table_index = min(index, len(self.target_tables) - 1)
            table_name = self.target_tables[table_index]
            col_name = port_name.split(":")[-1]

            port_mapping = self.data_params.get("port_to_column_mapping", {})
            if port_name in port_mapping:
                table_name = port_mapping[port_name].get("table", table_name)
                col_name = port_mapping[port_name].get("column", col_name)

            self.output_names[port_name] = (table_name, col_name)

        super().on_join_graph(graph)

    def register_data_operations(self, vfs, graph):
        schemas = self.data_params.get("schemas", {})
        for table_name in self.target_tables:
            blueprint = vfs.create_tabular_blueprint(table_name)
            if table_name in schemas:
                for col_info in schemas[table_name]:
                    generator_type = col_info.get("generator_type", "random_float")
                    kwargs = col_info.get("kwargs", {})
                    blueprint.add_column(col_info["name"], ProceduralGenerator(generator_type, **kwargs))
            else:
                print(f"[Warning] Node {self.node_id} is missing schema for {table_name}; generating port columns only.")
                for _, (mapped_table, col_name) in self.output_names.items():
                    if mapped_table == table_name:
                        blueprint.add_column(col_name, ProceduralGenerator("random_float", min=100.0, max=5000.0))
