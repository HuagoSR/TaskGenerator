import os
import json
import logging
from datetime import datetime
from task_generator.Skill import skill_api_tools
# ==========================================
# 閰嶇疆鏃ュ織绯荤粺
# ==========================================
LOG_DIR = os.path.join(os.path.dirname(__file__), "agent_logs")
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(LOG_DIR, f"agent7_router_deterministic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(filename=log_filename, level=logging.INFO, format='%(asctime)s - [Agent 7] - %(message)s')


def run_agent_7_deterministic_router(new_skill_ids: list):
    """
    绾补鍩轰簬 Python 闆嗗悎浜ら泦 (Set Intersection) 鐨勬瀬閫熺鍙ｅ尮閰嶈矾鐢卞櫒銆?
    鏃犻渶璋冪敤澶фā鍨嬶紝鏃堕棿澶嶆潅搴?O(N * M)锛屾绉掔骇瀹屾垚杩炵嚎銆?
    """
    print(f"鈿?Agent 7 鍚姩 (绾唬鐮佹瀬閫熻矾鐢? | 澶勭悊鏂拌妭鐐? {new_skill_ids}")
    print("-" * 50)

    # 1. 鍔犺浇鏈€鏂扮殑瀹屾暣鍥捐氨鏁版嵁搴?
    db = skill_api_tools._load_db()
    connected_count = 0

    # 2. 閬嶅巻姣忎竴涓柊鍏ュ簱鐨勮妭鐐?
    for new_id in new_skill_ids:
        if new_id not in db:
            logging.warning(f"鑺傜偣 {new_id} 涓嶅湪鏁版嵁搴撲腑锛岃烦杩囥€?)
            continue

        new_node = db[new_id]
        # 鎻愬彇鏂拌妭鐐圭殑绔彛闆嗗悎锛堜娇鐢?set 鏂逛究姹備氦闆嗭級
        new_requires = set(new_node.get("ports", {}).get("requires", []))
        new_provides = set(new_node.get("ports", {}).get("provides", []))

        # 3. 涓庡叏搴撴墍鏈夎妭鐐硅繘琛屼袱涓ょ鍙ｆ瘮瀵?
        for target_id, target_node in db.items():
            # 閬垮厤鑷繁杩炶嚜宸?
            if new_id == target_id:
                continue

            target_requires = set(target_node.get("ports", {}).get("requires", []))
            target_provides = set(target_node.get("ports", {}).get("provides", []))

            # --- 妫€鏌ユ柟鍚?1: New Node (浜у嚭) -> Target Node (闇€姹? ---
            intersect_forward = new_provides.intersection(target_requires)
            if intersect_forward:
                # 鏋勯€犵鍙ｆ槧灏勫瓧鍏?e.g., {"Financial:PreTax": "Financial:PreTax"}
                port_map = {port: port for port in intersect_forward}

                # 璋冪敤搴曞眰鐨勫畨鍏ㄨ繛绾垮伐鍏凤紙鑷甫闃查噸澶嶆鏌ワ級
                res = skill_api_tools.connect_skills(new_id, target_id, port_map)
                print(f"杩炵嚎: [{new_id}] -> [{target_id}] | 绔彛: {list(intersect_forward)}")
                logging.info(res)
                connected_count += 1

            # --- 妫€鏌ユ柟鍚?2: Target Node (浜у嚭) -> New Node (闇€姹? ---
            intersect_backward = target_provides.intersection(new_requires)
            if intersect_backward:
                port_map = {port: port for port in intersect_backward}

                res = skill_api_tools.connect_skills(target_id, new_id, port_map)
                print(f"杩炵嚎: [{target_id}] -> [{new_id}] | 绔彛: {list(intersect_backward)}")
                logging.info(res)
                connected_count += 1

    print("-" * 50)
    print(f"Agent 7 鏋侀€熻矾鐢卞畬姣曪紒鍏辫Е鍙?{connected_count} 娆℃嫇鎵戣繛鎺ュ皾璇曪紙閲嶅杩炵嚎宸茶搴曞眰灞忚斀锛夈€?)


# ==========================================
# 杩愯娴嬭瘯
# ==========================================

def delete_new_skills(new_skill_ids: list):
    from task_generator.Skill import skill_api_tools
    for skill_id in test_new_ids:
        skill_api_tools.admin_delete_skill(f"{skill_id}")

if __name__ == "__main__":
    # 浼犲叆浣犲垰鍒氬叆搴撶殑閭?4 涓妭鐐?
    test_new_ids = [
        "load_festival_transaction_data",
        "handle_null_revenue_records",
        "filter_host_country",
        "calculate_compliant_revenue"
    ]

    #run_agent_7_deterministic_router(test_new_ids)
    delete_new_skills(new_skill_ids=test_new_ids)

