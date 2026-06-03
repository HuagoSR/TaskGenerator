import pandas as pd
import numpy as np
import random
from typing import Dict, List, Any, Callable


# ==========================================
# 1. 策略接口与基础实现 (Strategy Pattern)
# ==========================================
class DataGenerator:
    """数据生成策略的基类。"""

    # 增加 vfs 参数，让生成器在需要时可以查阅全局的其他表格
    def generate(self, num_rows: int, vfs: 'VirtualFileSystem' = None) -> list:
        raise NotImplementedError


class ProceduralGenerator(DataGenerator):
    """程序规则生成策略"""

    def __init__(self, method: str, **kwargs):
        self.method = method
        self.kwargs = kwargs

    def generate(self, num_rows, vfs=None):
        import numpy as np

        # 将 LLM 可能生成的五花八门的名称统一转小写，方便做同义词匹配
        method = self.method.lower()

        # 1. 兼容随机浮点数 (uniform / random_float / float)
        if method in ['uniform', 'random_float', 'float']:
            min_val = self.kwargs.get('min', 0.0)
            max_val = self.kwargs.get('max', 1000.0)
            return np.random.uniform(min_val, max_val, num_rows)

        # 2. 兼容分类变量
        elif method in ['categorical', 'category', 'random_category', 'constant_list','choice', 'random_choice', 'list']:
            categories = (
                    self.kwargs.get('categories') or
                    self.kwargs.get('choices') or
                    self.kwargs.get('options') or
                    self.kwargs.get('values') or
                    self.kwargs.get('list') or
                    ['Default']
            )
            # 确保哪怕拿到的是空列表，也有兜底
            if not categories:
                categories = ['Default']
            return np.random.choice(categories, num_rows)

        # 3. 兼容正态分布
        elif method in ['normal', 'gaussian']:
            mean = self.kwargs.get('mean', 0.0)
            std = self.kwargs.get('std', 1.0)
            return np.random.normal(mean, std, num_rows)

        # 4. 兼容随机整数
        elif method in ['integer', 'randint', 'random_int']:
            min_val = self.kwargs.get('min', 0)
            max_val = self.kwargs.get('max', 100)
            return np.random.randint(min_val, max_val, num_rows)

        # 5. 兼容 ID 生成器
        elif method in ['id', 'uuid', 'index']:
            return [f"ID_{i:05d}" for i in range(1, num_rows + 1)]

        # 6. 如果真遇到了完全没见过的名字，再报错
        else:
            raise ValueError(f"致命错误：VFS 引擎不支持数据生成器类型 '{self.method}'！请使用 uniform, normal, categorical 等标准类型。")


class ForeignKeyGenerator(DataGenerator):
    """外键生成策略：去另一张已经生成的表里捞取合法的数值"""

    def __init__(self, source_table: str, source_col: str):
        self.source_table = source_table
        self.source_col = source_col

    def generate(self, num_rows: int, vfs: 'VirtualFileSystem' = None) -> list:
        if not vfs or self.source_table not in vfs.collapsed_data:
            raise ValueError(f"外键生成失败：找不到依赖的表 {self.source_table}！请检查坍缩顺序。")

        # 从全局 VFS 中拿到源表的数据
        source_df = vfs.collapsed_data[self.source_table]
        if self.source_col not in source_df.columns:
            raise ValueError(f"外键生成失败：表 {self.source_table} 中没有 {self.source_col} 列！")

        # 获取所有合法的不重复选项，然后随机抽取填入当前列
        valid_options = source_df[self.source_col].dropna().unique()
        return np.random.choice(valid_options, num_rows).tolist()


# ==========================================
# 2. 核心表格蓝图类 (The Tabular Blueprint)
# ==========================================
class TabularBlueprint:
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.schema: Dict[str, DataGenerator] = {}
        self.operation_queue: List[Dict[str, Any]] = []
        self.ground_truth: Dict[str, List[int]] = {"trap_rows": {}}

    def add_column(self, col_name: str, generator: DataGenerator):
        self.schema[col_name] = generator
        print(f"[{self.table_name}] 注册列: {col_name}")

    def inject_trap(self, trap_name: str, handler: Callable[[pd.DataFrame, List[int]], None], count: int = 1):
        """向操作队列压入一个外部定义好的陷阱指令"""
        self.operation_queue.append({
            "action": "trap",
            "name": trap_name,
            "handler": handler, # 存入这个函数指针
            "count": count
        })
        print(f"[{self.table_name}] 压入陷阱指令: {trap_name}")

    # 重点修改：坍缩时接收 vfs
    def collapse(self, num_rows: int, vfs: 'VirtualFileSystem') -> pd.DataFrame:
        print(f"\n开始坍缩蓝图 [{self.table_name}] (行数: {num_rows})...")

        data = {}
        for col_name, generator in self.schema.items():
            data[col_name] = generator.generate(num_rows, vfs=vfs)

        df = pd.DataFrame(data)

        for op in self.operation_queue:
            if op["action"] == "trap":
                self._apply_trap(df, op, num_rows)

        print(f"[{self.table_name}] 坍缩完成！")
        return df

    def _apply_trap(self, df: pd.DataFrame, op: Dict[str, Any], total_rows: int):
        count = op["count"]
        trap_name = op["name"]

        # 挑选受害者
        victim_indices = random.sample(range(total_rows), min(count, total_rows))
        self.ground_truth["trap_rows"][trap_name] = victim_indices

        op["handler"](df, victim_indices)


# ==========================================
# 3. 虚拟文件系统 (VFS) 大管家
# ==========================================
class VirtualFileSystem:
    """全局文件登记与坍缩控制中心"""

    def __init__(self):
        self.blueprints: Dict[str, TabularBlueprint] = {}
        # 存放物理坍缩后的 Pandas DataFrame，供外键查询和最终导出
        self.collapsed_data: Dict[str, pd.DataFrame] = {}
        self.global_ground_truth = {}

    def create_tabular_blueprint(self, table_name: str) -> TabularBlueprint:
        if table_name in self.blueprints:
            raise ValueError(f"蓝图 {table_name} 已存在！")
        bp = TabularBlueprint(table_name)
        self.blueprints[table_name] = bp
        return bp

    def get_blueprint(self, table_name: str) -> TabularBlueprint:
        return self.blueprints[table_name]

    def collapse_all(self, execution_order: List[str], row_counts: Dict[str, int]):
        """
        按照考点拓扑设定的顺序，依次坍缩蓝图。
        顺序极度重要：被外键依赖的表（如税率字典）必须先坍缩！
        """
        print("\n=== 启动 VFS 全局坍缩 ===")
        for table_name in execution_order:
            if table_name in self.blueprints:
                bp = self.blueprints[table_name]
                rows = row_counts.get(table_name, 100)  # 默认 100 行
                df = bp.collapse(rows, vfs=self)
                self.collapsed_data[table_name] = df
                self.global_ground_truth[table_name] = bp.ground_truth

    def get_auto_collapse_order(self) -> List[str]:
        """自动分析蓝图中的外键依赖，返回正确的坍缩顺序"""
        from collections import defaultdict, deque

        adj = defaultdict(list)
        in_degree = {table_name: 0 for table_name in self.blueprints.keys()}

        # 1. 扫描所有蓝图，查找外键依赖
        for table_name, bp in self.blueprints.items():
            for col_name, gen in bp.schema.items():
                # 检查这个 generator 是不是有 ref_table 属性 (即 ForeignKeyGenerator)
                if hasattr(gen, 'source_table'):
                    ref_table = gen.source_table
                    if ref_table in self.blueprints:
                        adj[ref_table].append(table_name)
                        in_degree[table_name] += 1

        # 2. 拓扑排序 (Kahn算法)
        queue = deque([t for t in in_degree if in_degree[t] == 0])
        order = []
        while queue:
            u = queue.popleft()
            order.append(u)
            for v in adj[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(order) < len(self.blueprints):
            raise Exception("检测到表之间存在循环引用，无法坍缩！")

        return order