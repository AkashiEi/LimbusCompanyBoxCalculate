import os
import json
import pymysql
from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import secrets
import dotenv

dotenv.load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Session secret for token generation
SESSION_SECRET = secrets.token_hex(32)

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('DB_PORT')),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_DATABASE'),
    'charset': os.getenv('DB_CHARSET'),
    'autocommit': True,
    'cursorclass': pymysql.cursors.DictCursor,
}

CHARACTERS = ['李箱', '浮士德', '堂吉诃德', '良秀', '默尔索', '鸿璐', '希斯克里夫', '以实玛丽', '罗佳', '辛克莱', '奥提斯', '格里高尔']


def get_db():
    return pymysql.connect(**DB_CONFIG)


def init_db():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            type VARCHAR(20) NOT NULL DEFAULT '人格',
            identity_name VARCHAR(100) NOT NULL DEFAULT '',
            season VARCHAR(20) NOT NULL DEFAULT '常驻',
            character_name VARCHAR(20) NOT NULL DEFAULT '',
            rarity INT NOT NULL DEFAULT 3,
            fragments_needed INT NOT NULL DEFAULT 400,
            boxes_needed INT NOT NULL DEFAULT 200,
            owned TINYINT NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            setting_key VARCHAR(50) PRIMARY KEY,
            setting_value VARCHAR(200) NOT NULL DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # 用户表
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password_hash VARCHAR(64) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'user',
            settings JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # 数据库迁移：为旧数据库添加缺失的列
        try:
            cur.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user' AFTER password_hash")
        except:
            pass  # 列已存在
        try:
            cur.execute("ALTER TABLE users ADD COLUMN settings JSON AFTER role")
        except:
            pass  # 列已存在
        # 用户物品持有表（只存储owned=1的物品ID，JSON格式）
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL UNIQUE,
            owned_ids JSON,
            wish_ids JSON,
            character_fragments JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # 用户设置表（JSON格式存储，和user_items类似）
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL UNIQUE,
            settings JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # 常量表（存储CHARS/TYPES/SEASONS）
        cur.execute("""
        CREATE TABLE IF NOT EXISTS constants (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category VARCHAR(20) NOT NULL,
            name VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_category_name (category, name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # 初始化默认常量
        default_constants = []
        for category, name in default_constants:
            cur.execute("INSERT IGNORE INTO constants (category, name) VALUES (%s, %s)", (category, name))
        
        for key, val in [('type_filter', 'ALL'), ('season_filter', 'ALL'), ('time_weeks', '10'), ('weekly_mirror_count', '10'), ('current_boxes', '195'), ('has_pass', 'true')]:
            cur.execute("INSERT IGNORE INTO settings (setting_key, setting_value) VALUES (%s, %s)", (key, val))
        conn.commit()
        print("[DB] Tables initialized OK")
    finally:
        conn.close()


def migrate_json_to_mysql():
    data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')
    if not os.path.exists(data_file):
        print("[MIGRATE] No data.json found, skipping")
        return
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = data.get('items', [])
    if not items:
        print("[MIGRATE] No items in data.json, skipping")
        return
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM items")
        existing = cur.fetchone()['cnt']
        if existing > 0:
            print(f"[MIGRATE] MySQL already has {existing} items, skipping migration")
            return
        for it in items:
            cur.execute(
                "INSERT INTO items (id, type, identity_name, season, character_name, rarity, fragments_needed, boxes_needed, owned) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (it.get('id'), it.get('type', '人格'), it.get('identity_name', ''), it.get('season', '常驻'),
                 it.get('character', ''), it.get('rarity', 3), it.get('fragments_needed', 400), it.get('boxes_needed', 200), it.get('owned', 0))
            )
        conn.commit()
        print(f"[MIGRATE] Migrated {len(items)} items")
    finally:
        conn.close()


def get_fragments_needed(rarity):
    return 400 if rarity == 3 else 150 if rarity == 2 else 0


def get_boxes_needed(rarity):
    return get_fragments_needed(rarity) / 2


def calc_weekly_boxes(weekly_mirror_count, has_pass=True):
    """计算每周可获得的箱子数量"""
    # 每日任务：3个/天
    daily_boxes = 10/10*3
    if not has_pass:
        daily_boxes = daily_boxes / 3
    weekly_boxes = daily_boxes * 7
    
    # 每周任务：10个*3周 = 30
    weekly_mission_boxes = 20/10*3
    if not has_pass:
        weekly_mission_boxes = weekly_mission_boxes / 3
    
    # 困难镜像：67.5
    hard_mirror_boxes = 225/10*3
    if not has_pass:
        hard_mirror_boxes = hard_mirror_boxes / 3
    
    # 普通镜像：9个/次
    weekly_regular_boxes = weekly_mirror_count * 30/10*3
    if not has_pass:
        weekly_regular_boxes = weekly_regular_boxes / 3
    
    weekly_total = weekly_boxes + weekly_mission_boxes + hard_mirror_boxes + weekly_regular_boxes
    
    return {
        'daily_mission': weekly_boxes,
        'weekly_mission': weekly_mission_boxes,
        'hard_mirror': hard_mirror_boxes,
        'regular_mirror': weekly_regular_boxes,
        'grand_total_weekly': int(weekly_total),
    }


@app.route('/api/constants', methods=['GET'])
def get_constants():
    """获取所有常量（角色、类型、赛季）"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT category, name FROM constants ORDER BY category, id")
        rows = cur.fetchall()
        result = {'characters': [], 'types': [], 'seasons': []}
        for r in rows:
            if r['category'] == 'character':
                result['characters'].append(r['name'])
            elif r['category'] == 'type':
                result['types'].append(r['name'])
            elif r['category'] == 'season':
                result['seasons'].append(r['name'])
        return jsonify(result)
    finally:
        conn.close()


@app.route('/api/items', methods=['GET'])
def get_items():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, type, identity_name, season, `character_name` as `character`, rarity, fragments_needed, boxes_needed, owned FROM items ORDER BY id")
        items = cur.fetchall()
        for it in items:
            for k in it:
                if hasattr(it[k], '__int__'):
                    it[k] = int(it[k])
        return jsonify(items)
    finally:
        conn.close()


@app.route('/api/items', methods=['POST'])
def add_item():
    item = request.json
    rarity = item.get('rarity', 3)
    item['fragments_needed'] = get_fragments_needed(rarity)
    item['boxes_needed'] = get_boxes_needed(rarity)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO items (type, identity_name, season, character_name, rarity, fragments_needed, boxes_needed, owned) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (item.get('type', '人格'), item.get('identity_name', ''), item.get('season', '常驻'),
             item.get('character', ''), rarity, item['fragments_needed'], item['boxes_needed'], item.get('owned', 0))
        )
        conn.commit()
        item['id'] = cur.lastrowid
        return jsonify(item), 201
    finally:
        conn.close()


@app.route('/api/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    item = request.json
    rarity = item.get('rarity', 3)
    fragments = get_fragments_needed(rarity)
    boxes = get_boxes_needed(rarity)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE items SET type=%s, identity_name=%s, season=%s, character_name=%s, rarity=%s, fragments_needed=%s, boxes_needed=%s, owned=%s WHERE id=%s",
            (item.get('type', '人格'), item.get('identity_name', ''), item.get('season', '常驻'),
             item.get('character', ''), rarity, fragments, boxes, item.get('owned', 0), item_id)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'not found'}), 404
        conn.commit()
        item['id'] = item_id
        item['fragments_needed'] = fragments
        item['boxes_needed'] = boxes
        return jsonify(item)
    finally:
        conn.close()


@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM items WHERE id=%s", (item_id,))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()


@app.route('/api/items/batch-owned', methods=['PUT'])
def batch_update_owned():
    data = request.json
    ids = data.get('ids', [])
    owned = data.get('owned', 1)
    if not ids:
        return jsonify({'ok': True, 'updated': 0})
    conn = get_db()
    try:
        cur = conn.cursor()
        placeholders = ','.join(['%s'] * len(ids))
        cur.execute(f"UPDATE items SET owned=%s WHERE id IN ({placeholders})", [owned] + ids)
        conn.commit()
        return jsonify({'ok': True, 'updated': cur.rowcount})
    finally:
        conn.close()


@app.route('/api/calculate', methods=['POST'])
def calculate():
    params = request.json or {}
    type_filter = params.get('type_filter', 'ALL')
    season_filter = params.get('season_filter', 'ALL')
    character_filter = params.get('character_filter', 'ALL')
    time_weeks = params.get('time_weeks', 10)
    weekly_mirror_count = params.get('weekly_mirror_count', 10)
    current_boxes = params.get('current_boxes', 0)
    has_pass = params.get('has_pass', True)
    owned_frags = params.get('character_fragments') or {}
    # 接收前端传来的 owned_ids（格式: { "1": true, "5": true } 或 [1, 5]）
    owned_input = params.get('owned_ids', {})
    wish_input = params.get('wish_ids', {})

    # 转换为集合
    owned_ids = set()
    if isinstance(owned_input, dict):
        owned_ids = {int(k) for k, v in owned_input.items() if v}
    elif isinstance(owned_input, list):
        owned_ids = set(int(x) for x in owned_input)

    wish_ids = set()
    if isinstance(wish_input, dict):
        wish_ids = {int(k) for k, v in wish_input.items() if v}
    elif isinstance(wish_input, list):
        wish_ids = set(int(x) for x in wish_input)

    # Normalize to list
    def to_list(val):
        if val is None or val == 'ALL':
            return []
        if isinstance(val, list):
            return [v for v in val if v and v != 'ALL']
        return [val]

    type_list = to_list(type_filter)
    season_list = to_list(season_filter)
    char_list = to_list(character_filter)

    conn = get_db()
    try:
        cur = conn.cursor()
        # 获取所有物品
        cur.execute("SELECT id, character_name, type, season, fragments_needed FROM items")
        all_items = cur.fetchall()

        # 决定要计算哪些物品
        items_to_calc = []
        if wish_ids:
            # 只计算 wish_ids 中的物品（且未拥有的）
            for item in all_items:
                item_id = item['id']
                if item_id in wish_ids and item_id not in owned_ids:
                    items_to_calc.append(item)
        else:
            # 计算所有未拥有的物品
            for item in all_items:
                item_id = item['id']
                if item_id not in owned_ids:
                    items_to_calc.append(item)

        # 应用过滤器并计算碎片
        char_fragments = {}
        for item in items_to_calc:
            if type_list and item['type'] not in type_list:
                continue
            if season_list and item['season'] not in season_list:
                continue
            ch = item['character_name']
            if char_list and ch not in char_list:
                continue
            char_fragments[ch] = char_fragments.get(ch, 0) + int(item['fragments_needed'])
    finally:
        conn.close()

    char_results = []
    for ch in CHARACTERS:
        target = char_fragments.get(ch, 0)
        owned = owned_frags.get(ch, 0) if isinstance(owned_frags.get(ch), int) else 0
        gap = max(target - owned, 0)
        char_results.append({
            'character': ch,
            'target_fragments': target,
            'owned_fragments': owned,
            'fragment_gap': gap,
            'box_gap': -(-gap // 2) if gap > 0 else 0,
        })

    # 计算每周箱子来源
    weekly_sources = calc_weekly_boxes(weekly_mirror_count, has_pass)
    weekly_total = weekly_sources['grand_total_weekly']

    total_box_gap = sum(r['box_gap'] for r in char_results)
    remaining = max(total_box_gap - current_boxes, 0)

    # 计算基于时间范围的每周需要普牢次数
    non_mirror_boxes = weekly_sources['daily_mission'] + weekly_sources['weekly_mission'] + weekly_sources['hard_mirror']
    mirror_needed_boxes = max(0, remaining - non_mirror_boxes * time_weeks)
    mirror_per_run = 9
    weekly_mirror_needed = -(-mirror_needed_boxes // (mirror_per_run * time_weeks)) if time_weeks > 0 else 0

    # 所需周数（基于输入的每周普牢次数）- 使用总周收益计算
    weeks_needed = -(-remaining // weekly_total) if weekly_total > 0 else 0

    result = {
        'type_filter': type_filter,
        'season_filter': season_filter,
        'current_boxes': current_boxes,
        'weekly_mirror_count': weekly_mirror_count,
        'time_weeks': time_weeks,
        'has_pass': has_pass,
        'characters': char_results,
        'total_box_gap': total_box_gap,
        'remaining_gap': int(remaining),
        'weekly_sources': weekly_sources,
        'weekly_mirror_needed': int(weekly_mirror_needed),
        'weeks_needed': int(weeks_needed),
    }
    return jsonify(result)


@app.route('/api/settings', methods=['GET'])
def get_settings():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT setting_key, setting_value FROM settings")
        rows = cur.fetchall()
        settings = {}
        for r in rows:
            k, v = r['setting_key'], r['setting_value']
            if k in ('time_weeks', 'weekly_mirror_count', 'current_boxes'):
                settings[k] = int(v)
            else:
                settings[k] = v
        return jsonify(settings)
    finally:
        conn.close()


@app.route('/api/settings', methods=['POST'])
def save_settings():
    conn = get_db()
    try:
        cur = conn.cursor()
        for k, v in request.json.items():
            cur.execute("INSERT INTO settings (setting_key, setting_value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE setting_value=%s", (k, str(v), str(v)))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()


# ========== 用户相关 API ==========

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token(user_id):
    """简单的token生成：user_id + 随机字符串"""
    return f"u{user_id}_{secrets.token_hex(16)}"

def extract_user_id(token):
    """从token提取用户ID"""
    if not token or not token.startswith('u'):
        return None
    try:
        return int(token.split('_')[0][1:])
    except:
        return None

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')

    print(f"[REGISTER] 收到注册请求: username={username}")
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    if len(username) < 2 or len(username) > 50:
        return jsonify({'error': '用户名长度需在2-50个字符之间'}), 400
    if len(password) < 4:
        return jsonify({'error': '密码长度至少4个字符'}), 400

    password_hash = hash_password(password)

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            return jsonify({'error': '用户名已存在'}), 409

        print(f"[REGISTER] 插入用户: {username}")
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'user')",
            (username, password_hash)
        )
        user_id = cur.lastrowid
        conn.commit()
        print(f"[REGISTER] 用户创建成功: id={user_id}, role=user")

        # 初始化用户物品记录（owned_ids为空JSON）
        cur.execute("INSERT INTO user_items (user_id, owned_ids) VALUES (%s, %s)", (user_id, '{}'))
        
        # 初始化用户设置记录（settings为空JSON）
        cur.execute("INSERT INTO user_settings (user_id, settings) VALUES (%s, %s)", (user_id, '{}'))
        
        conn.commit()

        # 只在items表为空时创建示例数据（不初始化user_items）
        cur.execute("SELECT COUNT(*) as cnt FROM items")
        if cur.fetchone()['cnt'] == 0:
            print("[REGISTER] items表为空，创建示例数据")
            sample_items = [
                ('人格', '李箱', '常驻', '李箱', 3, 400, 200)
            ]
            for item_type, name, season, char, rarity, frags, boxes in sample_items:
                cur.execute(
                    "INSERT INTO items (type, identity_name, season, character_name, rarity, fragments_needed, boxes_needed) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (item_type, name, season, char, rarity, frags, boxes)
                )
            conn.commit()

        token = generate_token(user_id)
        print(f"[REGISTER] 注册完成: user_id={user_id}, token={token[:20]}...")
        return jsonify({'ok': True, 'token': token, 'user_id': user_id, 'username': username}), 201
    except Exception as e:
        import traceback
        print(f"[REGISTER] 错误: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')

    print(f"[LOGIN] 收到登录请求: username={username}")
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    password_hash = hash_password(password)
    print(f"[LOGIN] 密码哈希: {password_hash[:16]}...")

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, username, role FROM users WHERE username = %s AND password_hash = %s", (username, password_hash))
        user = cur.fetchone()
        print(f"[LOGIN] 查询结果: {user}")
        
        if not user:
            return jsonify({'error': '用户名或密码错误'}), 401

        token = generate_token(user['id'])
        print(f"[LOGIN] 登录成功: user_id={user['id']}, role={user['role']}")
        return jsonify({'ok': True, 'token': token, 'user_id': user['id'], 'username': user['username'], 'role': user['role']})
    except Exception as e:
        import traceback
        print(f"[LOGIN] 错误: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


def get_user_from_token(token):
    """从token获取用户ID（简单实现，生产环境应用JWT）"""
    if not token:
        return None
    conn = get_db()
    try:
        cur = conn.cursor()
        # 简单查找（实际应验证token）
        cur.execute("SELECT id FROM users WHERE id = %s", (extract_user_id(token) if token else 0,))
        user = cur.fetchone()
        return user['id'] if user else None
    finally:
        conn.close()


@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': '未登录'}), 401

    conn = get_db()
    try:
        cur = conn.cursor()
        # 简单验证：token前缀匹配用户ID
        try:
            user_id = extract_user_id(token)
        except:
            return jsonify({'error': '无效token'}), 401

        cur.execute("SELECT id, username, role FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            return jsonify({'error': '用户不存在'}), 404

        return jsonify({'user_id': user['id'], 'username': user['username'], 'role': user['role']})
    finally:
        conn.close()


# ========== 用户物品相关 API ==========

def ensure_user_items(user_id):
    """确保user_items表中有该用户的记录，若没有则创建"""
    conn = get_db()
    try:
        cur = conn.cursor()
        # 检查字段是否存在，不存在则添加
        try:
            cur.execute("ALTER TABLE user_items ADD COLUMN character_fragments JSON AFTER wish_ids")
        except:
            pass  # 列已存在
        cur.execute("SELECT id FROM user_items WHERE user_id = %s", (user_id,))
        if not cur.fetchone():
            cur.execute("INSERT INTO user_items (user_id, owned_ids, wish_ids, character_fragments) VALUES (%s, %s, %s, %s)", (user_id, '{}', '{}', '{}'))
            conn.commit()
            print(f"[USER_ITEMS] 为用户 {user_id} 创建了空的user_items记录")
    finally:
        conn.close()


@app.route('/api/user/items', methods=['GET'])
def get_user_items():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    print(f"[USER_ITEMS] 收到token: {token}")
    if not token:
        return jsonify({'error': '未登录'}), 401

    user_id = extract_user_id(token)
    print(f"[USER_ITEMS] 解析user_id: {user_id}")
    if not user_id:
        return jsonify({'error': '无效token'}), 401

    conn = get_db()
    try:
        cur = conn.cursor()
        # 检查用户是否存在
        cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cur.fetchone():
            return jsonify({'error': '用户不存在'}), 404

        # 确保user_items记录存在
        ensure_user_items(user_id)

        # 获取用户物品状态
        cur.execute("SELECT owned_ids, wish_ids FROM user_items WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        owned_ids = row['owned_ids'] if row and row['owned_ids'] else {}
        wish_ids = row['wish_ids'] if row and row['wish_ids'] else {}
        
        # 如果是字符串，解析为JSON
        if isinstance(owned_ids, str):
            owned_ids = json.loads(owned_ids)
        if isinstance(wish_ids, str):
            wish_ids = json.loads(wish_ids)
        
        # 获取所有物品
        cur.execute("""
            SELECT i.id, i.type, i.identity_name, i.season, i.character_name as `character`,
                   i.rarity, i.fragments_needed, i.boxes_needed
            FROM items i
            ORDER BY i.id
        """)
        items = cur.fetchall()
        for it in items:
            for k in it:
                if hasattr(it[k], '__int__'):
                    it[k] = int(it[k])
            it['owned'] = 1 if str(it['id']) in owned_ids or it['id'] in owned_ids else 0
            it['wish'] = 1 if str(it['id']) in wish_ids or it['id'] in wish_ids else 0
        return jsonify(items)
    finally:
        conn.close()


@app.route('/api/user/items/<int:item_id>', methods=['PUT'])
def update_user_item(item_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': '未登录'}), 401

    user_id = extract_user_id(token)
    if not user_id:
        return jsonify({'error': '无效token'}), 401

    data = request.json
    owned = data.get('owned')
    wish = data.get('wish')

    conn = get_db()
    try:
        cur = conn.cursor()
        # 确保user_items记录存在
        ensure_user_items(user_id)

        # 获取当前owned_ids和wish_ids
        cur.execute("SELECT owned_ids, wish_ids FROM user_items WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        owned_ids = row['owned_ids'] if row and row['owned_ids'] else {}
        wish_ids = row['wish_ids'] if row and row['wish_ids'] else {}
        if isinstance(owned_ids, str):
            owned_ids = json.loads(owned_ids)
        if isinstance(wish_ids, str):
            wish_ids = json.loads(wish_ids)
        
        # 更新owned_ids（只有传入owned参数时才更新）
        if owned is not None:
            if owned:
                owned_ids[str(item_id)] = True
            else:
                owned_ids.pop(str(item_id), None)
                owned_ids.pop(item_id, None)
        
        # 更新wish_ids（只有传入wish参数时才更新）
        if wish is not None:
            if wish:
                wish_ids[str(item_id)] = True
            else:
                wish_ids.pop(str(item_id), None)
                wish_ids.pop(item_id, None)
        
        # 保存回数据库
        cur.execute("UPDATE user_items SET owned_ids = %s, wish_ids = %s WHERE user_id = %s", 
                    (json.dumps(owned_ids), json.dumps(wish_ids), user_id))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()


@app.route('/api/user/items/batch-owned', methods=['PUT'])
def batch_update_user_owned():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': '未登录'}), 401

    user_id = extract_user_id(token)
    if not user_id:
        return jsonify({'error': '无效token'}), 401

    data = request.json
    ids = data.get('ids', [])
    owned = data.get('owned')
    wish = data.get('wish')

    conn = get_db()
    try:
        cur = conn.cursor()
        # 确保user_items记录存在
        ensure_user_items(user_id)

        # 获取当前owned_ids和wish_ids
        cur.execute("SELECT owned_ids, wish_ids FROM user_items WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        owned_ids = row['owned_ids'] if row and row['owned_ids'] else {}
        wish_ids = row['wish_ids'] if row and row['wish_ids'] else {}
        if isinstance(owned_ids, str):
            owned_ids = json.loads(owned_ids)
        if isinstance(wish_ids, str):
            wish_ids = json.loads(wish_ids)
        
        if owned is not None:
            if owned:
                for item_id in ids:
                    owned_ids[str(item_id)] = True
            else:
                for item_id in ids:
                    owned_ids.pop(str(item_id), None)
                    owned_ids.pop(item_id, None)
        
        if wish is not None:
            if wish:
                for item_id in ids:
                    wish_ids[str(item_id)] = True
            else:
                for item_id in ids:
                    wish_ids.pop(str(item_id), None)
                    wish_ids.pop(item_id, None)
        
        # 保存回数据库
        cur.execute("UPDATE user_items SET owned_ids = %s, wish_ids = %s WHERE user_id = %s",
                    (json.dumps(owned_ids), json.dumps(wish_ids), user_id))

        conn.commit()
        return jsonify({'ok': True, 'updated': len(ids)})
    finally:
        conn.close()


# ========== 用户碎片持有 API ==========

@app.route('/api/user/fragments', methods=['GET'])
def get_user_fragments():
    """获取用户各角色的碎片持有情况"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': '未登录'}), 401

    user_id = extract_user_id(token)
    if not user_id:
        return jsonify({'error': '无效token'}), 401

    conn = get_db()
    try:
        ensure_user_items(user_id)
        cur = conn.cursor()
        cur.execute("SELECT character_fragments FROM user_items WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        char_frags = row['character_fragments'] if row and row['character_fragments'] else {}
        if isinstance(char_frags, str):
            char_frags = json.loads(char_frags)
        return jsonify(char_frags)
    finally:
        conn.close()


@app.route('/api/user/fragments', methods=['PUT'])
def update_user_fragments():
    """更新用户各角色的碎片持有情况"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': '未登录'}), 401

    user_id = extract_user_id(token)
    if not user_id:
        return jsonify({'error': '无效token'}), 401

    char_fragments = request.json or {}

    conn = get_db()
    try:
        ensure_user_items(user_id)
        cur = conn.cursor()
        cur.execute("UPDATE user_items SET character_fragments = %s WHERE user_id = %s",
                    (json.dumps(char_fragments), user_id))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()


# ========== 用户设置相关 API ==========

def ensure_user_settings(user_id):
    """确保user_settings表中有该用户的记录，若没有则创建"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM user_settings WHERE user_id = %s", (user_id,))
        if not cur.fetchone():
            cur.execute("INSERT INTO user_settings (user_id, settings) VALUES (%s, %s)", (user_id, '{}'))
            conn.commit()
            print(f"[USER_SETTINGS] 为用户 {user_id} 创建了空的user_settings记录")
    finally:
        conn.close()


@app.route('/api/user/settings', methods=['GET'])
def get_user_settings():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': '未登录'}), 401

    user_id = extract_user_id(token)
    if not user_id:
        return jsonify({'error': '无效token'}), 401

    conn = get_db()
    try:
        cur = conn.cursor()
        # 确保user_settings记录存在
        ensure_user_settings(user_id)
        
        cur.execute("SELECT settings FROM user_settings WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        # 即使没有settings也返回空对象，让前端使用默认值
        settings = {}
        if row and row['settings']:
            db_settings = row['settings']
            # 如果是字符串，解析为JSON
            if isinstance(db_settings, str):
                db_settings = json.loads(db_settings)
            # 确保数值类型正确
            for k in ('time_weeks', 'weekly_mirror_count', 'current_boxes'):
                if k in db_settings and db_settings[k]:
                    settings[k] = int(db_settings[k])
            return jsonify(settings)
        return jsonify({})
    finally:
        conn.close()


@app.route('/api/user/settings', methods=['POST'])
def save_user_settings():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': '未登录'}), 401

    user_id = extract_user_id(token)
    if not user_id:
        return jsonify({'error': '无效token'}), 401

    conn = get_db()
    try:
        cur = conn.cursor()
        # 确保user_settings记录存在
        ensure_user_settings(user_id)
        
        # 保存设置到user_settings表
        settings_json = json.dumps(request.json)
        cur.execute("UPDATE user_settings SET settings = %s WHERE user_id = %s", (settings_json, user_id))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()


@app.route('/api/user/calculate', methods=['POST'])
def calculate_user():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': '未登录'}), 401

    user_id = extract_user_id(token)
    if not user_id:
        return jsonify({'error': '无效token'}), 401

    params = request.json or {}
    type_filter = params.get('type_filter', 'ALL')
    season_filter = params.get('season_filter', 'ALL')
    character_filter = params.get('character_filter', 'ALL')
    time_weeks = params.get('time_weeks', 10)
    weekly_mirror_count = params.get('weekly_mirror_count', 10)
    current_boxes = params.get('current_boxes', 0)
    has_pass = params.get('has_pass', True)

    def to_list(val):
        if val is None or val == 'ALL':
            return []
        if isinstance(val, list):
            return [v for v in val if v and v != 'ALL']
        return [val]

    type_list = to_list(type_filter)
    season_list = to_list(season_filter)
    char_list = to_list(character_filter)

    conn = get_db()
    try:
        cur = conn.cursor()
        # 确保user_items记录存在
        ensure_user_items(user_id)

        # 获取用户的owned_ids、wish_ids和character_fragments
        cur.execute("SELECT owned_ids, wish_ids, character_fragments FROM user_items WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        owned_ids = row['owned_ids'] if row and row['owned_ids'] else {}
        wish_ids = row['wish_ids'] if row and row['wish_ids'] else {}
        owned_frags = row['character_fragments'] if row and row['character_fragments'] else {}
        if isinstance(owned_ids, str):
            owned_ids = json.loads(owned_ids)
        if isinstance(wish_ids, str):
            wish_ids = json.loads(wish_ids)
        if isinstance(owned_frags, str):
            owned_frags = json.loads(owned_frags)

        # 获取所有物品
        cur.execute("SELECT id, character_name, type, season, fragments_needed FROM items")
        all_items = cur.fetchall()

        # 计算未拥有的角色需要的碎片（目标碎片）
        target_frags = {}
        
        # 决定要计算哪些物品：如果有wish_ids，则只计算想要的；否则计算所有未拥有的
        items_to_calc = []
        if wish_ids:
            # 只计算wish_ids中的物品（且未拥有的）
            for item in all_items:
                item_id = item['id']
                if str(item_id) in wish_ids or item_id in wish_ids:
                    if str(item_id) not in owned_ids and item_id not in owned_ids:
                        items_to_calc.append(item)
        else:
            # 计算所有未拥有的物品
            for item in all_items:
                item_id = item['id']
                if str(item_id) not in owned_ids and item_id not in owned_ids:
                    items_to_calc.append(item)
        
        # 应用过滤器并计算碎片
        for item in items_to_calc:
            if type_list and item['type'] not in type_list:
                continue
            if season_list and item['season'] not in season_list:
                continue
            ch = item['character_name']
            if char_list and ch not in char_list:
                continue
            target_frags[ch] = target_frags.get(ch, 0) + int(item['fragments_needed'])
    finally:
        conn.close()

    char_results = []
    for ch in CHARACTERS:
        target = target_frags.get(ch, 0)
        owned = owned_frags.get(ch, 0) if isinstance(owned_frags.get(ch), int) else 0
        gap = max(target - owned, 0)
        char_results.append({
            'character': ch,
            'target_fragments': target,
            'owned_fragments': owned,
            'fragment_gap': gap,
            'box_gap': -(-gap // 2) if gap > 0 else 0,
        })

    # 计算每周箱子来源
    weekly_sources = calc_weekly_boxes(weekly_mirror_count, has_pass)
    weekly_total = weekly_sources['grand_total_weekly']

    total_box_gap = sum(r['box_gap'] for r in char_results)
    remaining = max(total_box_gap - current_boxes, 0)

    # 计算基于时间范围的每周需要普牢次数
    # 非普牢来源箱子 = 每日任务 + 每周任务 + 困难镜像（每周）
    non_mirror_boxes = weekly_sources['daily_mission'] + weekly_sources['weekly_mission'] + weekly_sources['hard_mirror']
    # 需要普牢提供的箱子 = 剩余箱子 - 时间范围内的非普牢来源箱子
    mirror_needed_boxes = max(0, remaining - non_mirror_boxes * time_weeks)
    # 每次普牢获得9个箱子
    mirror_per_run = 9
    # 每周需要普牢次数（基于时间范围）
    weekly_mirror_needed = -(-mirror_needed_boxes // (mirror_per_run * time_weeks)) if time_weeks > 0 else 0

    # 所需周数（基于输入的每周普牢次数）- 使用总周收益计算
    weeks_needed = -(-remaining // weekly_total) if weekly_total > 0 else 0

    result = {
        'type_filter': type_filter,
        'season_filter': season_filter,
        'current_boxes': current_boxes,
        'weekly_mirror_count': weekly_mirror_count,
        'time_weeks': time_weeks,
        'has_pass': has_pass,
        'characters': char_results,
        'total_box_gap': total_box_gap,
        'remaining_gap': int(remaining),
        'weekly_sources': weekly_sources,
        'weekly_mirror_needed': int(weekly_mirror_needed),
        'weeks_needed': int(weeks_needed),
    }
    return jsonify(result)


# ========== 游客计算 API（不存储到数据库） ==========

@app.route('/api/guest/calculate', methods=['POST'])
def calculate_guest():
    """游客计算API：前端传入owned_ids JSON，后端直接计算返回结果"""
    params = request.json or {}

    # 前端传入owned_ids格式: { "1": true, "5": true, "10": true } 或 [1, 5, 10]
    owned_input = params.get('owned_ids', {})
    wish_input = params.get('wish_ids', {})
    # 游客持有的角色碎片
    owned_frags = params.get('character_fragments') or {}
    
    # 转换为统一的owned_ids集合
    owned_ids = set()
    if isinstance(owned_input, dict):
        owned_ids = {int(k) for k, v in owned_input.items() if v}
    elif isinstance(owned_input, list):
        owned_ids = set(int(x) for x in owned_input)
    
    # 转换为wish_ids集合
    wish_ids = set()
    if isinstance(wish_input, dict):
        wish_ids = {int(k) for k, v in wish_input.items() if v}
    elif isinstance(wish_input, list):
        wish_ids = set(int(x) for x in wish_input)
    
    type_filter = params.get('type_filter', 'ALL')
    season_filter = params.get('season_filter', 'ALL')
    character_filter = params.get('character_filter', 'ALL')
    time_weeks = params.get('time_weeks', 10)
    weekly_mirror_count = params.get('weekly_mirror_count', 10)
    current_boxes = params.get('current_boxes', 0)
    has_pass = params.get('has_pass', True)

    def to_list(val):
        if val is None or val == 'ALL':
            return []
        if isinstance(val, list):
            return [v for v in val if v and v != 'ALL']
        return [val]

    type_list = to_list(type_filter)
    season_list = to_list(season_filter)
    char_list = to_list(character_filter)

    conn = get_db()
    try:
        cur = conn.cursor()
        # 获取所有物品
        cur.execute("SELECT id, character_name, type, season, fragments_needed FROM items")
        all_items = cur.fetchall()
        
        # 决定要计算哪些物品：如果有wish_ids，则只计算想要的；否则计算所有未拥有的
        items_to_calc = []
        if wish_ids:
            # 只计算wish_ids中的物品（且未拥有的）
            for item in all_items:
                item_id = item['id']
                if item_id in wish_ids and item_id not in owned_ids:
                    items_to_calc.append(item)
        else:
            # 计算所有未拥有的物品
            for item in all_items:
                item_id = item['id']
                if item_id not in owned_ids:
                    items_to_calc.append(item)
        
        # 应用过滤器并计算碎片
        target_frags = {}
        for item in items_to_calc:
            if type_list and item['type'] not in type_list:
                continue
            if season_list and item['season'] not in season_list:
                continue
            ch = item['character_name']
            if char_list and ch not in char_list:
                continue
            target_frags[ch] = target_frags.get(ch, 0) + int(item['fragments_needed'])
    finally:
        conn.close()

    char_results = []
    for ch in CHARACTERS:
        target = target_frags.get(ch, 0)
        owned = owned_frags.get(ch, 0) if isinstance(owned_frags.get(ch), int) else 0
        gap = max(target - owned, 0)
        char_results.append({
            'character': ch,
            'target_fragments': target,
            'owned_fragments': owned,
            'fragment_gap': gap,
            'box_gap': -(-gap // 2) if gap > 0 else 0,
        })

    # 计算每周箱子来源
    weekly_sources = calc_weekly_boxes(weekly_mirror_count, has_pass)
    weekly_total = weekly_sources['grand_total_weekly']

    total_box_gap = sum(r['box_gap'] for r in char_results)
    remaining = max(total_box_gap - current_boxes, 0)

    # 计算基于时间范围的每周需要普牢次数
    # 非普牢来源箱子 = 每日任务 + 每周任务 + 困难镜像（每周）
    non_mirror_boxes = weekly_sources['daily_mission'] + weekly_sources['weekly_mission'] + weekly_sources['hard_mirror']
    # 需要普牢提供的箱子 = 剩余箱子 - 时间范围内的非普牢来源箱子
    mirror_needed_boxes = max(0, remaining - non_mirror_boxes * time_weeks)
    # 每次普牢获得9个箱子
    mirror_per_run = 9
    # 每周需要普牢次数（基于时间范围）
    weekly_mirror_needed = -(-mirror_needed_boxes // (mirror_per_run * time_weeks)) if time_weeks > 0 else 0

    # 所需周数（基于输入的每周普牢次数）- 使用总周收益计算
    weeks_needed = -(-remaining // weekly_total) if weekly_total > 0 else 0

    result = {
        'type_filter': type_filter,
        'season_filter': season_filter,
        'current_boxes': current_boxes,
        'weekly_mirror_count': weekly_mirror_count,
        'time_weeks': time_weeks,
        'has_pass': has_pass,
        'characters': char_results,
        'total_box_gap': total_box_gap,
        'remaining_gap': int(remaining),
        'weekly_sources': weekly_sources,
        'weekly_mirror_needed': int(weekly_mirror_needed),
        'weeks_needed': int(weeks_needed),
    }
    return jsonify(result)


if __name__ == '__main__':
    import logging
    # 配置日志输出到文件和控制台
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('server_error.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    # 将Flask日志也写入文件
    logging.getLogger('werkzeug').setLevel(logging.INFO)
    init_db()
    migrate_json_to_mysql()
    print("启动边狱巴士箱子缺口计算器 API: http://localhost:5000")
    app.run(debug=True, port=5000)
