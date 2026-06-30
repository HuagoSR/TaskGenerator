import random
from collections import defaultdict, deque
from typing import Any, Callable, Dict, List

import numpy as np
import pandas as pd


class DataGenerator:
    """Base strategy for generating one column of tabular data."""

    def generate(self, num_rows: int, vfs: "VirtualFileSystem" = None) -> list:
        raise NotImplementedError


class ProceduralGenerator(DataGenerator):
    """Generate simple synthetic data from a named procedural method."""

    def __init__(self, method: str, **kwargs):
        self.method = method
        self.kwargs = kwargs

    def generate(self, num_rows: int, vfs: "VirtualFileSystem" = None) -> list:
        method = self.method.lower()

        if method in ["uniform", "random_float", "float"]:
            min_val = self.kwargs.get("min", 0.0)
            max_val = self.kwargs.get("max", 1000.0)
            return np.random.uniform(min_val, max_val, num_rows).tolist()

        if method in ["categorical", "category", "random_category", "constant_list", "choice", "random_choice", "list"]:
            categories = (
                self.kwargs.get("categories")
                or self.kwargs.get("choices")
                or self.kwargs.get("options")
                or self.kwargs.get("values")
                or self.kwargs.get("list")
                or ["Default"]
            )
            return np.random.choice(categories or ["Default"], num_rows).tolist()

        if method in ["normal", "gaussian"]:
            mean = self.kwargs.get("mean", 0.0)
            std = self.kwargs.get("std", 1.0)
            return np.random.normal(mean, std, num_rows).tolist()

        if method in ["integer", "randint", "random_int"]:
            min_val = self.kwargs.get("min", 0)
            max_val = self.kwargs.get("max", 100)
            return np.random.randint(min_val, max_val, num_rows).tolist()

        if method in ["id", "uuid", "index"]:
            return [f"ID_{i:05d}" for i in range(1, num_rows + 1)]

        raise ValueError(
            f"Unsupported data generator method '{self.method}'. "
            "Use uniform, normal, categorical, integer, id, or ForeignKeyGenerator."
        )


class ForeignKeyGenerator(DataGenerator):
    """Generate foreign-key values from an already generated source table."""

    def __init__(self, source_table: str, source_col: str):
        self.source_table = source_table
        self.source_col = source_col

    def generate(self, num_rows: int, vfs: "VirtualFileSystem" = None) -> list:
        if not vfs or self.source_table not in vfs.collapsed_data:
            raise ValueError(f"Foreign-key source table not found: {self.source_table}")

        source_df = vfs.collapsed_data[self.source_table]
        if self.source_col not in source_df.columns:
            raise ValueError(f"Foreign-key source column not found: {self.source_table}.{self.source_col}")

        valid_options = source_df[self.source_col].dropna().unique()
        if len(valid_options) == 0:
            raise ValueError(f"Foreign-key source column has no non-null values: {self.source_table}.{self.source_col}")
        return np.random.choice(valid_options, num_rows).tolist()


class TabularBlueprint:
    """Declarative table blueprint that can collapse into a DataFrame."""

    def __init__(self, table_name: str):
        self.table_name = table_name
        self.schema: Dict[str, DataGenerator] = {}
        self.operation_queue: List[Dict[str, Any]] = []
        self.ground_truth: Dict[str, Any] = {"trap_rows": {}}

    def add_column(self, col_name: str, generator: DataGenerator):
        self.schema[col_name] = generator
        print(f"[{self.table_name}] registered column: {col_name}")

    def inject_trap(self, trap_name: str, handler: Callable[[pd.DataFrame, List[int]], None], count: int = 1):
        self.operation_queue.append(
            {
                "action": "trap",
                "name": trap_name,
                "handler": handler,
                "count": count,
            }
        )
        print(f"[{self.table_name}] queued trap: {trap_name}")

    def collapse(self, num_rows: int, vfs: "VirtualFileSystem") -> pd.DataFrame:
        print(f"\nCollapsing blueprint [{self.table_name}] with {num_rows} rows...")
        data = {
            col_name: generator.generate(num_rows, vfs=vfs)
            for col_name, generator in self.schema.items()
        }
        df = pd.DataFrame(data)

        for op in self.operation_queue:
            if op["action"] == "trap":
                self._apply_trap(df, op, num_rows)

        print(f"[{self.table_name}] collapse complete.")
        return df

    def _apply_trap(self, df: pd.DataFrame, op: Dict[str, Any], total_rows: int):
        count = op["count"]
        trap_name = op["name"]
        victim_indices = random.sample(range(total_rows), min(count, total_rows))
        self.ground_truth["trap_rows"][trap_name] = victim_indices
        op["handler"](df, victim_indices)


class VirtualFileSystem:
    """Registry and collapse controller for generated table blueprints."""

    def __init__(self):
        self.blueprints: Dict[str, TabularBlueprint] = {}
        self.collapsed_data: Dict[str, pd.DataFrame] = {}
        self.global_ground_truth: Dict[str, Any] = {}

    def create_tabular_blueprint(self, table_name: str) -> TabularBlueprint:
        if table_name in self.blueprints:
            raise ValueError(f"Blueprint already exists: {table_name}")
        blueprint = TabularBlueprint(table_name)
        self.blueprints[table_name] = blueprint
        return blueprint

    def get_blueprint(self, table_name: str) -> TabularBlueprint:
        return self.blueprints[table_name]

    def collapse_all(self, execution_order: List[str], row_counts: Dict[str, int]):
        print("\n=== Starting VFS collapse ===")
        for table_name in execution_order:
            if table_name not in self.blueprints:
                continue
            blueprint = self.blueprints[table_name]
            rows = row_counts.get(table_name, 100)
            df = blueprint.collapse(rows, vfs=self)
            self.collapsed_data[table_name] = df
            self.global_ground_truth[table_name] = blueprint.ground_truth

    def get_auto_collapse_order(self) -> List[str]:
        adj = defaultdict(list)
        in_degree = {table_name: 0 for table_name in self.blueprints.keys()}

        for table_name, blueprint in self.blueprints.items():
            for generator in blueprint.schema.values():
                if hasattr(generator, "source_table"):
                    ref_table = generator.source_table
                    if ref_table in self.blueprints:
                        adj[ref_table].append(table_name)
                        in_degree[table_name] += 1

        queue = deque([table_name for table_name, degree in in_degree.items() if degree == 0])
        order = []
        while queue:
            table_name = queue.popleft()
            order.append(table_name)
            for dependent in adj[table_name]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(order) < len(self.blueprints):
            raise RuntimeError("Detected a cyclic foreign-key dependency between blueprints.")

        return order
