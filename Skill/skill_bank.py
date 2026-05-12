import json
import os
import inspect
from Skill import operators
from Skill.skill_graph import SkillNode

# 1. 自动扫描并注册所有的底层算子
OPERATOR_REGISTRY = {}
for name, obj in inspect.getmembers(operators):
    # 如果它是一个类，且继承自 SkillNode，且不是 SkillNode 本身
    if inspect.isclass(obj) and issubclass(obj, SkillNode) and obj is not SkillNode:
        OPERATOR_REGISTRY[name] = obj

# 2. 读取 JSON 题库
json_path = os.path.join(os.path.dirname(__file__), "skills_config.json")
with open(json_path, "r", encoding="utf-8") as f:
    SKILL_DATABASE = json.load(f)


# 3. 动态包装类 (为了兼容你旧版 build_greedy_graph 的调用方式)
class SkillFactoryProxy:
    """这是一个伪装成 Python 类的代理对象，兼容贪婪算法里的逻辑"""

    def __init__(self, skill_id, config):
        self.skill_id = skill_id
        self.config = config

        # 伪装类属性供引擎检查
        self.max_instances = config.get("max_instances", 1)
        self.requires = config.get("ports", {}).get("requires", [])
        self.operator_class_name = config["operator_class"]

    def __call__(self, node_id: str):
        # 当图引擎尝试“实例化”它时，我们返回挂载了 JSON 灵魂的真实 Operator
        OperatorClass = OPERATOR_REGISTRY[self.operator_class_name]
        return OperatorClass(node_id=node_id, skill_config=self.config)


# 4. 组装出引擎期待的 SKILL_REGISTRY
SKILL_REGISTRY = {}
for s_id, s_config in SKILL_DATABASE.items():
    SKILL_REGISTRY[s_id] = SkillFactoryProxy(s_id, s_config)