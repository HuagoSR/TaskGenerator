import inspect
import json
import os

from task_generator.Skill import operators
from task_generator.Skill.skill_graph import SkillNode


OPERATOR_REGISTRY = {}
for name, obj in inspect.getmembers(operators):
    if inspect.isclass(obj) and issubclass(obj, SkillNode) and obj is not SkillNode:
        OPERATOR_REGISTRY[name] = obj


json_path = os.path.join(os.path.dirname(__file__), "skills_config.json")
with open(json_path, "r", encoding="utf-8") as f:
    SKILL_DATABASE = json.load(f)


class SkillFactoryProxy:
    """Callable wrapper that instantiates an operator class from JSON config."""

    def __init__(self, skill_id, config):
        self.skill_id = skill_id
        self.config = config
        self.max_instances = config.get("max_instances", 1)
        self.requires = config.get("ports", {}).get("requires", [])
        self.operator_class_name = config["operator_class"]

    def __call__(self, node_id: str):
        operator_class = OPERATOR_REGISTRY[self.operator_class_name]
        return operator_class(node_id=node_id, skill_config=self.config)


SKILL_REGISTRY = {
    skill_id: SkillFactoryProxy(skill_id, skill_config)
    for skill_id, skill_config in SKILL_DATABASE.items()
}
