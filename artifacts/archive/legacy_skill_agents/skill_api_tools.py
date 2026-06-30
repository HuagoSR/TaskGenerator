import json
import os
import re
from typing import List, Dict, Optional
import inspect
from task_generator.Skill import operators
import time

# 瀹氫箟鑰冪偣搴撶殑璺緞
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "skills_config.json")
# 瀹氫箟绔彛瀛楀吀鐨勮矾寰?
PORTS_DICT_PATH = os.path.join(os.path.dirname(__file__), "ports_dict.json")

def _load_db() -> dict:
    """鍐呴儴杈呭姪鍑芥暟锛氬姞杞芥渶鏂版暟鎹簱锛堝甫绌烘枃浠堕槻寮归槻绾匡級"""
    if not os.path.exists(DATABASE_PATH):
        return {}
    try:
        with open(DATABASE_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}  # 濡傛灉鏂囦欢涓虹┖(0瀛楄妭)锛岀洿鎺ヨ繑鍥炵┖瀛楀吀
            return json.loads(content)
    except json.JSONDecodeError:
        print("[璀﹀憡] 鏁版嵁搴撴枃浠跺凡鎹熷潖鎴栦负绌猴紝宸查噸缃负绌洪搴撱€?)
        return {}


def _save_db(db_data: dict) -> bool:
    """鍐呴儴杈呭姪鍑芥暟锛氬畨鍏ㄨ惤鐩?""
    with open(DATABASE_PATH, "w", encoding="utf-8") as f:
        json.dump(db_data, f, indent=4, ensure_ascii=False)
    return True

def _load_ports_db() -> dict:
    if not os.path.exists(PORTS_DICT_PATH):
        # 濡傛灉鏂囦欢涓嶅瓨鍦紝鍒濆鍖栦竴涓熀纭€瀛楀吀
        initial_ports = {
            "Financial:AnyAmount": "Generic financial amount.",
            "Dimension:Generic": "Generic classification dimension."
        }
        _save_ports_db(initial_ports)
        return initial_ports
    with open(PORTS_DICT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_ports_db(db_data: dict) -> bool:
    with open(PORTS_DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(db_data, f, indent=4, ensure_ascii=False)
    return True


# 鎻愬彇 operators.py 涓墍鏈夌殑绠楀瓙绫?
OPERATOR_REGISTRY = {
    name: cls for name, cls in inspect.getmembers(operators, inspect.isclass)
    if issubclass(cls, operators.SkillNode) and cls is not operators.SkillNode
}


def list_available_operators() -> str:
    """
    銆愬伐鍏峰姛鑳姐€戝垪鍑哄綋鍓嶇郴缁熶腑鎵€鏈夊彈鏀寔鐨勫簳灞?Python 鏁版嵁绠楀瓙銆?
    澶фā鍨嬪湪鍒涘缓鏂拌€冪偣鍓嶏紝鍙互閫氳繃姝ゆ帴鍙ｄ簡瑙ｇ郴缁熸湁鍝簺鐜版垚鐨勨€滈鏋垛€濆彲鐢ㄣ€?

    杩斿洖:
        str: 鍖呭惈绠楀瓙鍚嶇О鍙婂叾绠€瑕佽鏄庯紙docstring锛夌殑鍒楄〃銆?
    """
    results = []
    for name, cls in OPERATOR_REGISTRY.items():
        doc = inspect.getdoc(cls) or "鏃犳弿杩?
        # 鎻愬彇绗竴琛屼綔涓虹畝瑕佽鏄?
        short_doc = doc.split('\n')[0]
        results.append(f"- {name}: {short_doc}")

    return "褰撳墠绯荤粺鏀寔浠ヤ笅搴曞眰绠楀瓙锛歕n" + "\n".join(results)


def get_operator_source_code(operator_name: str) -> str:
    """
    銆愬伐鍏峰姛鑳姐€戞煡鐪嬫煇涓叿浣撳簳灞傜畻瀛愮殑 Python 婧愪唬鐮併€?
    澶фā鍨嬮渶瑕佽皟鐢ㄦ鎺ュ彛鏉ュ垎鏋愯绠楀瓙鐨?register_data_operations 鏂规硶锛?
    浠庤€屽紕娓呮鍦ㄥ垱寤鸿€冪偣鏃讹紝闇€瑕佸湪 data_params 涓～鍏ュ摢浜涘叿浣撶殑閿€煎锛圞ey-Value锛夈€?

    鍙傛暟:
        operator_name (str): 绠楀瓙绫诲悕锛堝 "ForeignKeyDictionaryOperator"锛夈€?

    杩斿洖:
        str: 璇ョ畻瀛愮殑瀹屾暣 Python 婧愪唬鐮併€?
    """
    if operator_name not in OPERATOR_REGISTRY:
        return f"Error: 鎵句笉鍒扮畻瀛?'{operator_name}'銆傝鍏堜娇鐢?list_available_operators 妫€鏌ユ嫾鍐欍€?

    cls = OPERATOR_REGISTRY[operator_name]
    try:
        # inspect 妯″潡鐩存帴鎶婄被鐨勬簮浠ｇ爜鎻愬彇鎴愬瓧绗︿覆
        source_code = inspect.getsource(cls)
        return f"浠ヤ笅鏄?{operator_name} 鐨勬簮浠ｇ爜锛岃浠旂粏鍒嗘瀽瀹冨浣曚娇鐢?self.data_params锛歕n```python\n{source_code}\n```"
    except Exception as e:
        return f"Error: 鏃犳硶鑾峰彇婧愮爜銆傝缁嗕俊鎭? {str(e)}"


# ==========================================
# 渚?LLM Agent 璋冪敤鐨勫伐鍏?API
# ==========================================

def search_skills(keyword: str = "", skill_id: str = "", needs_input_port: str = "", provides_output_port: str = "") -> str:
    """
    銆愬伐鍏峰姛鑳姐€戞悳绱㈢幇鏈夌殑涓氬姟鑰冪偣搴撱€傚湪浣犳兂瑕佹柊寤鸿€冪偣鎴栬繛绾垮墠锛岃皟鐢ㄦ宸ュ叿鏌ユ壘鑺傜偣銆?

    鍙傛暟:
        keyword (str): 閫夊～銆備笟鍔″叧閿瘝锛堝 "绋?, "缂哄け鍊?, "姹囩巼"锛夈€?
        skill_id (str): 閫夊～銆傞€氳繃鍞竴鐨勮€冪偣 ID 杩涜绮剧‘鏌ユ壘銆?
        needs_input_port (str): 閫夊～銆傛悳绱€愰渶瑕佺壒瀹氳緭鍏ャ€戠殑鑰冪偣銆傚 "Financial:PreTax"銆?
        provides_output_port (str): 閫夊～銆傛悳绱€愯兘鎻愪緵鐗瑰畾杈撳嚭銆戠殑鑰冪偣銆傚 "Dimension:Region"銆?

    杩斿洖:
        str: 鍖呭惈鍖归厤鑰冪偣姒傝淇℃伅鐨勬枃鏈瓧绗︿覆銆?
    """
    db = _load_db()
    results = []

    for s_id, config in db.items():
        match = True

        # 1. 绮剧‘ ID 鍖归厤
        if skill_id and skill_id.lower() != s_id.lower():
            match = False

        # 2. 鍏抽敭璇嶆ā绯婂尮閰?
        if keyword:
            kw_lower = keyword.lower()
            keywords_list = [k.lower() for k in config.get("keywords", [])]
            if not (kw_lower in s_id.lower() or kw_lower in config.get("skill_name", "").lower() or kw_lower in keywords_list):
                match = False

        # 3. 绔彛鍖归厤
        ports = config.get("ports", {})
        if needs_input_port and needs_input_port not in ports.get("requires", []):
            match = False
        if provides_output_port and provides_output_port not in ports.get("provides", []):
            match = False

        if match:
            # 缁勮杩斿洖缁欏ぇ妯″瀷鐨勭畝鎶?
            info = f"- ID: {s_id} | Name: {config.get('skill_name')} | Requires: {ports.get('requires', [])} | Provides: {ports.get('provides', [])}"
            results.append(info)

    if not results:
        return f"鎼滅储瀹屾垚銆傛湭鎵惧埌鍖归厤鐨勮€冪偣銆?

    return "鎵惧埌浠ヤ笅鍖归厤鐨勮€冪偣锛歕n" + "\n".join(results)


def get_skill_details(skill_id: str) -> str:
    """
    銆愬伐鍏峰姛鑳姐€戣鍙栨煇涓叿浣撹€冪偣鐨勫叏閮ㄨ缁嗛厤缃紙鍖呭惈涓氬姟鎰忓浘銆佸垽鍒嗙偣銆佹墽琛屽弬鏁扮瓑锛夈€?

    鍙傛暟:
        skill_id (str): 鑰冪偣鐨勫敮涓€鏍囪瘑绗︼紙濡?"base_pnl_01"锛夈€?

    杩斿洖:
        str: 鏍煎紡鍖栧悗鐨?JSON 瀛楃涓层€?
    """
    db = _load_db()
    if skill_id not in db:
        return f"Error: 搴撲腑涓嶅瓨鍦?ID 涓?'{skill_id}' 鐨勮€冪偣锛岃鍏堥€氳繃 search_skills 纭 ID銆?

    return json.dumps(db[skill_id], indent=2, ensure_ascii=False)


def create_skill(
    skill_id: str,
    skill_name: str,
    node_type: str,
    sandbox_role: str = "Solver",  # 缁欎釜榛樿鍊煎厹搴?
    keywords: list = None,
    semantics: dict = None,
    data_profile: dict = None,
    possible_successors: list = None,
    **kwargs
) -> str:
    """
    Agent 6 (Registrar) 涓撶敤鎺ュ彛锛氬皢鑰冪偣鍐欏叆鏈湴 JSON 鏁版嵁搴擄紙鑷甫鏂拌€佺増鏈弬鏁板吋瀹癸級
    """
    db = _load_db()

    # 1. 绔彛鍏煎鎬х粍瑁咃細濡傛灉涓婃父鎷嗘暎浼犱簡 requires 鍜?provides锛岃繖閲岄噸鏂版墦鍖呭洖 ports
    actual_ports = kwargs.get("ports", {})
    if "requires" in kwargs:
        actual_ports["requires"] = kwargs["requires"]
    if "provides" in kwargs:
        actual_ports["provides"] = kwargs["provides"]

    # 2. 鏁版嵁鐢诲儚鍏煎锛氶槻姝㈡煇浜涘湴鏂硅繕鍦ㄤ紶鑰佺増鐨?data_params
    actual_data_profile = data_profile
    if not actual_data_profile and "data_params" in kwargs:
        actual_data_profile = kwargs["data_params"]

    # 3. 缁勮绗﹀悎澹版槑寮忔矙鐩掓爣鍑嗙殑鏂扮増鑺傜偣
    new_node = {
        "skill_name": skill_name,
        "node_type": node_type,
        "sandbox_role": sandbox_role,
        "keywords": keywords or [],
        "ports": actual_ports,
        "semantics": semantics or {},
        "data_profile": actual_data_profile or {},
        "possible_successors": possible_successors or []
    }

    # 4. 瑕嗙洊鎴栨柊寤猴紝骞惰惤鐩?
    db[skill_id] = new_node
    _save_db(db)

    return f"Success: 鑰冪偣 [{skill_id}] 宸叉垚鍔熷瓨鍏ユ暟鎹簱銆係chema 瀹屾暣鏃犳崯銆?

def connect_skills(source_skill_id: str, target_skill_id: str, port_mapping: Dict[str, str]) -> str:
    """
    銆愬伐鍏峰姛鑳姐€戝湪涓や釜鑰冪偣涔嬮棿寤虹珛鏁版嵁娴佸姩杩炵嚎锛堝皢 source_skill_id 璁句负 target_skill_id 鐨勫墠缃妭鐐癸級銆?

    鍙傛暟:
        source_skill_id (str): 涓婃父杈撳嚭鏁版嵁鐨勮€冪偣 ID銆?
        target_skill_id (str): 涓嬫父鎺ユ敹鏁版嵁鐨勮€冪偣 ID銆?
        port_mapping (Dict[str, str]): 绔彛鏄犲皠瀛楀吀锛屾牸寮忎负 {"涓婃父鐨凱rovides绔彛": "涓嬫父鐨凴equires绔彛"}銆?

    杩斿洖:
        str: 杩炵嚎鎴愬姛鎴栧け璐ョ殑绯荤粺鍙嶉銆?
    """
    db = _load_db()
    if source_skill_id not in db:
        return f"Error: 涓婃父鑰冪偣 '{source_skill_id}' 涓嶅瓨鍦ㄣ€?
    if target_skill_id not in db:
        return f"Error: 涓嬫父鑰冪偣 '{target_skill_id}' 涓嶅瓨鍦ㄣ€?

    # 鑾峰彇涓婁笅娓哥殑绔彛澹版槑
    source_provides = db[source_skill_id].get("ports", {}).get("provides", [])
    target_requires = db[target_skill_id].get("ports", {}).get("requires", [])

    # 涓ユ牸鐨勮涔夌被鍨嬫牎楠?
    for src_port, tgt_port in port_mapping.items():
        if src_port not in source_provides:
            return f"Error: 杩炵嚎澶辫触锛佷笂娓歌妭鐐?'{source_skill_id}' 骞舵病鏈夊０鏄庢彁渚涜緭鍑虹鍙?'{src_port}'銆傚畠鍙彁渚?{source_provides}銆?
        if tgt_port not in target_requires:
            return f"Error: 杩炵嚎澶辫触锛佷笅娓歌妭鐐?'{target_skill_id}' 骞朵笉闇€瑕佽緭鍏ョ鍙?'{tgt_port}'銆傚畠闇€瑕?{target_requires}銆?

    # 鏍￠獙閫氳繃锛屽啓鍏ュ浘璋辫竟鍏崇郴
    new_connection = {
        "skill_id": target_skill_id,
        "port_map": port_mapping
    }

    # 闃叉閲嶅杩炵嚎
    existing_connections = db[source_skill_id].get("possible_successors", [])
    for conn in existing_connections:
        if conn["skill_id"] == target_skill_id and conn["port_map"] == port_mapping:
            return f"Notice: 杩炵嚎宸插瓨鍦紝鏃犻渶閲嶅娣诲姞銆?

    db[source_skill_id].setdefault("possible_successors", []).append(new_connection)
    _save_db(db)

    return f"Success: 鑺傜偣 '{source_skill_id}' 宸叉垚鍔熻繛鎺ュ埌 '{target_skill_id}'锛佸浘璋辨嫇鎵戝凡鏇存柊銆?


def request_new_operator(intent_description: str, proposed_data_params: dict, required_pandas_logic: str) -> str:
    """
    銆愬伐鍏峰姛鑳姐€戝綋鐜版湁绠楀瓙鏃犳硶婊¤冻闇€姹傛椂锛屽悜浜虹被宸ョ▼甯堟彁浜ゅ紑鍙戝伐鍗曘€?
    """
    request_ticket = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "PENDING_HUMAN_REVIEW",
        "intent": intent_description,
        "proposed_params": proposed_data_params,
        "suggested_logic": required_pandas_logic
    }

    request_file = os.path.join(os.path.dirname(__file__), "pending_operator_requests.json")

    requests = []
    if os.path.exists(request_file):
        with open(request_file, "r", encoding="utf-8") as f:
            try:
                requests = json.load(f)
            except json.JSONDecodeError:
                pass

    requests.append(request_ticket)

    with open(request_file, "w", encoding="utf-8") as f:
        json.dump(requests, f, indent=4, ensure_ascii=False)

    return "Success: 宸ュ崟宸叉彁浜ょ粰浜虹被锛佽鍦ㄥ綋鍓嶈妭鐐圭殑 operator_class 涓～鍏?'PENDING_HUMAN_REVIEW'銆?


def get_port_dictionary() -> str:
    """
    銆愬伐鍏峰姛鑳姐€戣幏鍙栫郴缁熶腑鎵€鏈夊凡娉ㄥ唽鐨勮涔夌鍙ｏ紙Ports锛夊垪琛ㄥ強鍏惰缁嗗畾涔夈€?
    鍦ㄨ繘琛屾帹婕旇繛绾匡紙Port Inference锛夋垨鍒涘缓鏂拌€冪偣鍓嶏紝蹇呴』璋冪敤姝ゅ伐鍏峰榻愭爣鍑嗚瘝姹囷紒

    杩斿洖:
        str: 鍖呭惈鎵€鏈夊悎娉曠鍙ｅ悕鍜岃В閲婄殑鏂囨湰銆?
    """
    ports_db = _load_ports_db()
    results = []
    for port_name, desc in ports_db.items():
        results.append(f"- [{port_name}]: {desc}")

    return "绯荤粺褰撳墠宸叉敞鍐岀殑鏍囧噯绔彛濡備笅锛岃灏藉彲鑳藉鐢ㄥ畠浠細\n" + "\n".join(results)


def register_new_port(port_name: str, description: str) -> str:
    """
    銆愬伐鍏峰姛鑳姐€戝綋鐜版湁鐨勭鍙ｅ瓧鍏镐腑缁濆娌℃湁鍚堥€傜殑绔彛鏃讹紝璋冪敤姝ゅ伐鍏锋敞鍐屼竴涓叏鏂扮殑璇箟绔彛銆?

    鍙傛暟:
        port_name (str): 绔彛鍚嶃€傚繀椤讳弗鏍奸伒寰?"绫诲埆:缁嗚妭" 鐨勯┘宄板懡鍚嶆硶锛堝 "Financial:CarbonTax" 鎴?"Dimension:ProductLine"锛夈€?
        description (str): 瀵硅绔彛浠ｈ〃鐨勪笟鍔″惈涔夌殑鑻辨枃璇︾粏瑙ｉ噴銆?

    杩斿洖:
        str: 娉ㄥ唽鎴愬姛鎴栧け璐ョ殑鍙嶉銆?
    """
    # 1. 涓ユ牸鐨勫懡鍚嶈鑼冮槻寰?(蹇呴』鏄?Word:Word 鏍煎紡)
    if not re.match(r"^[A-Z][a-zA-Z0-9]*:[A-Z][a-zA-Z0-9]*$", port_name):
        return f"Error: 绔彛鍛藉悕涓嶈鑼冿紒'{port_name}' 涓嶇鍚?'Category:Detail' 鏍煎紡锛堜緥濡?'Financial:PreTax'锛岄瀛楁瘝蹇呴』澶у啓涓斾笉鑳芥湁绌烘牸锛夈€?

    ports_db = _load_ports_db()

    # 2. 闃查噸妫€鏌?
    if port_name in ports_db:
        return f"Notice: 绔彛 '{port_name}' 宸茬粡瀛樺湪锛屾棤闇€閲嶅娉ㄥ唽锛屼綘鍙互鐩存帴浣跨敤瀹冦€?

    # 3. 娉ㄥ唽钀界洏
    ports_db[port_name] = description
    _save_ports_db(ports_db)

    return f"Success: 鏂扮鍙?'{port_name}' 宸叉垚鍔熸敞鍐屽埌鍏ㄥ眬鏁版嵁瀛楀吀锛佷綘鐜板湪鍙互鍦?create_skill 涓娇鐢ㄥ畠浜嗐€?


def create_operator(operator_name: str, source_code: str) -> str:
    """
    銆愬伐鍏峰姛鑳姐€戝綋鐜版湁鐨勭畻瀛愮粷瀵规棤娉曟弧瓒充笟鍔￠€昏緫鏃讹紝鐢?LLM 鐩存帴缂栧啓鍏ㄦ柊鐨?Python 绠楀瓙绫讳唬鐮侊紝骞剁墿鐞嗘敞鍏ュ埌搴曞眰鏂囦欢涓€?

    鍙傛暟:
        operator_name (str): 鏂扮畻瀛愮殑绫诲悕锛堝 FilterOperator锛夈€?
        source_code (str): 瀹屾暣鐨?Python 绫绘簮浠ｇ爜銆傚繀椤诲寘鍚?def on_join_graph 鎴?register_data_operations 绛夋柟娉曘€?
    """
    # 鍋囪浣犵殑 operators.py 鍦ㄤ笂绾х洰褰曠殑 Skill 鏂囦欢澶逛笅锛屾牴鎹綘鐨勫疄闄呰矾寰勮皟鏁?
    operators_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Skill", "operators.py")

    # 绠€鍗曠殑鏍煎紡闃茬垎妫€鏌?
    if f"class {operator_name}" not in source_code:
        return f"Error: 浠ｇ爜鏍￠獙澶辫触锛佹湭鍦ㄦ簮浠ｇ爜涓壘鍒?'class {operator_name}' 鐨勫畾涔夈€?

    try:
        # 浠ヨ拷鍔犳ā寮?(Append) 鎵撳紑鏂囦欢锛屾妸澶фā鍨嬪啓鐨勪唬鐮佹帴鍦ㄦ渶鍚庨潰
        with open(operators_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n# ==========================================\n")
            f.write(f"# Auto-Generated by Agent 3: {operator_name}\n")
            f.write(f"# ==========================================\n")
            f.write(source_code)
            f.write("\n")

        return f"Success: 鍏ㄦ柊搴曞眰绠楀瓙 '{operator_name}' 宸叉垚鍔熺墿鐞嗘敞鍏ュ埌 operators.py 涓紒浣犲彲浠ョ户缁皟鐢?create_skill 鏉ヤ娇鐢ㄥ畠浜嗐€?
    except Exception as e:
        return f"Error: 娉ㄥ叆 Python 浠ｇ爜澶辫触: {e}"

# ==========================================
# 渚?浜虹被 璋冪敤鐨勫伐鍏?API
# ==========================================

def admin_delete_skill(skill_id_to_delete: str) -> str:
    """
    銆愪汉绫荤鐞嗗憳涓撶敤銆戝畨鍏ㄥ垹闄ゅ浘璋变腑鐨勮€冪偣鑺傜偣銆?
    瀹冧細鑷姩閬嶅巻鎵€鏈夌幇鏈夎€冪偣锛岃В闄や换浣曟寚鍚戣鍒犻櫎鑺傜偣鐨勮繛绾夸緷璧栵紝鐒跺悗褰诲簳鍒犻櫎璇ヨ€冪偣銆?

    鍙傛暟:
        skill_id_to_delete (str): 闇€瑕佸垹闄ょ殑鑰冪偣 ID

    杩斿洖:
        str: 鎿嶄綔缁撴灉鏃ュ織
    """
    db = _load_db()

    if skill_id_to_delete not in db:
        return f"Admin Error: 棰樺簱涓笉瀛樺湪 ID 涓?'{skill_id_to_delete}' 鐨勮€冪偣銆?

    cleaned_edges_count = 0

    # 1. 绗竴姝ワ細娓呯悊鎮┖杩炶竟 (Dangling Edges)
    # 閬嶅巻鎵€鏈夊瓨鍦ㄧ殑鑺傜偣锛屾鏌ュ畠浠殑 possible_successors 鏄惁鍖呭惈浜嗗緟鍒犻櫎鐨勮妭鐐?
    for s_id, config in db.items():
        if s_id == skill_id_to_delete:
            continue

        successors = config.get("possible_successors", [])
        original_len = len(successors)

        # 杩囨护鎺夋墍鏈夋寚鍚戝緟鍒犻櫎鑺傜偣鐨勮繛绾?
        config["possible_successors"] = [
            conn for conn in successors
            if conn.get("skill_id") != skill_id_to_delete
        ]

        if len(config["possible_successors"]) < original_len:
            cleaned_edges_count += (original_len - len(config["possible_successors"]))
            print(f"[*] Admin Log: 宸茶В闄?[{s_id}] 瀵?[{skill_id_to_delete}] 鐨勫悗缁т緷璧栬繛绾裤€?)

    # 2. 绗簩姝ワ細鐗╃悊鍒犻櫎鑺傜偣鏈綋
    del db[skill_id_to_delete]

    # 3. 瀹夊叏钀界洏
    _save_db(db)

    return f"Admin Success: 鑰冪偣 '{skill_id_to_delete}' 宸茶褰诲簳鍒犻櫎銆傚悓姝ユ竻鐞嗕簡 {cleaned_edges_count} 鏉″け鏁堣繛绾裤€?

if __name__ == "__main__":
    print(list_available_operators())
'''
    print("=== 1. 娴嬭瘯鏌ヨ鍙敤绠楀瓙 ===")
    print(list_available_operators())
    print("-" * 40)

    print("\n=== 2. 娴嬭瘯鎼滅储鐜版湁鑰冪偣 ===")
    print(search_skills(keyword="绋?))
    print("-" * 40)

    print("\n=== 3. 妯℃嫙 Agent 鍒涘缓鏂拌€冪偣 ===")
    create_res = create_skill(
        skill_id="mut_eu_digital_tax",
        skill_name="娆ф床鏁板瓧鏈嶅姟绋?,
        node_type="mutator",
        operator_class="ForeignKeyDictionaryOperator",
        requires=["Financial:PreTax", "Dimension:Region"],
        provides=["Financial:PostTax"],
        keywords=["鏁板瓧绋?, "娆ф床", "鍚堣"],
        intents=["鏍规嵁 '{dict_table_name}' 鎵ｉ櫎娆ф床鏁板瓧鏈嶅姟绋庯紝杈撳嚭鍒?'{out_result_col}'銆?],
        rubrics=["妫€鏌ユ槸鍚︽纭簲鐢ㄤ簡鏁板瓧绋庣巼銆?],
        data_params={
            "dict_table_name": "EU_Tax.csv",
            "out_result_col": "Net_After_EU_Tax",
            "dict_join_key": "Region",
            "dict_columns": {"Region": ["France", "Germany"], "Rate": [0.03, 0.03]}
        }
    )
    print(create_res)
    print("-" * 40)

    print("\n=== 4. 妯℃嫙 Agent 杩涜杩炵嚎 ===")
    connect_res = connect_skills(
        source_skill_id="base_pnl_01",
        target_skill_id="mut_eu_digital_tax",
        port_mapping={"Financial:PreTax": "Financial:PreTax", "Dimension:Region": "Dimension:Region"}
    )
    print(connect_res)
'''

