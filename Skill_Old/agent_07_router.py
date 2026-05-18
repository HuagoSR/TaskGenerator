import os
import json
import logging
from datetime import datetime
import skill_api_tools

# ==========================================
# 配置日志系统
# ==========================================
LOG_DIR = os.path.join(os.path.dirname(__file__), "agent_logs")
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(LOG_DIR, f"agent7_router_deterministic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(filename=log_filename, level=logging.INFO, format='%(asctime)s - [Agent 7] - %(message)s')


def run_agent_7_deterministic_router(new_skill_ids: list):
    """
    纯粹基于 Python 集合交集 (Set Intersection) 的极速端口匹配路由器。
    无需调用大模型，时间复杂度 O(N * M)，毫秒级完成连线。
    """
    print(f"⚡ Agent 7 启动 (纯代码极速路由) | 处理新节点: {new_skill_ids}")
    print("-" * 50)

    # 1. 加载最新的完整图谱数据库
    db = skill_api_tools._load_db()
    connected_count = 0

    # 2. 遍历每一个新入库的节点
    for new_id in new_skill_ids:
        if new_id not in db:
            logging.warning(f"节点 {new_id} 不在数据库中，跳过。")
            continue

        new_node = db[new_id]
        # 提取新节点的端口集合（使用 set 方便求交集）
        new_requires = set(new_node.get("ports", {}).get("requires", []))
        new_provides = set(new_node.get("ports", {}).get("provides", []))

        # 3. 与全库所有节点进行两两端口比对
        for target_id, target_node in db.items():
            # 避免自己连自己
            if new_id == target_id:
                continue

            target_requires = set(target_node.get("ports", {}).get("requires", []))
            target_provides = set(target_node.get("ports", {}).get("provides", []))

            # --- 检查方向 1: New Node (产出) -> Target Node (需求) ---
            intersect_forward = new_provides.intersection(target_requires)
            if intersect_forward:
                # 构造端口映射字典 e.g., {"Financial:PreTax": "Financial:PreTax"}
                port_map = {port: port for port in intersect_forward}

                # 调用底层的安全连线工具（自带防重复检查）
                res = skill_api_tools.connect_skills(new_id, target_id, port_map)
                print(f"连线: [{new_id}] -> [{target_id}] | 端口: {list(intersect_forward)}")
                logging.info(res)
                connected_count += 1

            # --- 检查方向 2: Target Node (产出) -> New Node (需求) ---
            intersect_backward = target_provides.intersection(new_requires)
            if intersect_backward:
                port_map = {port: port for port in intersect_backward}

                res = skill_api_tools.connect_skills(target_id, new_id, port_map)
                print(f"连线: [{target_id}] -> [{new_id}] | 端口: {list(intersect_backward)}")
                logging.info(res)
                connected_count += 1

    print("-" * 50)
    print(f"Agent 7 极速路由完毕！共触发 {connected_count} 次拓扑连接尝试（重复连线已被底层屏蔽）。")


# ==========================================
# 运行测试
# ==========================================

def delete_new_skills(new_skill_ids: list):
    import skill_api_tools
    for skill_id in test_new_ids:
        skill_api_tools.admin_delete_skill(f"{skill_id}")

if __name__ == "__main__":
    # 传入你刚刚入库的那 4 个节点
    test_new_ids = [
        "load_festival_transaction_data",
        "handle_null_revenue_records",
        "filter_host_country",
        "calculate_compliant_revenue"
    ]

    #run_agent_7_deterministic_router(test_new_ids)
    delete_new_skills(new_skill_ids=test_new_ids)
