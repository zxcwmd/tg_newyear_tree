"""Слой базы данных (SQLite + aiosqlite)."""
import random
import secrets
import aiosqlite
from datetime import datetime, timedelta, timezone
from config import (
    DATABASE_PATH,
    DONATE_PACKS,
    LEGACY_SHARED_TREE_ID,
    LOOTBOX_PRICE,
    ORNAMENTS,
    PERSONAL_TREE_BASE,
    TREE_THEMES,
    is_personal_tree_id,
    personal_tree_id,
    personal_tree_owner,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS trees (
    chat_id INTEGER PRIMARY KEY,
    chat_title TEXT,
    created_at TEXT NOT NULL,
    is_finished INTEGER NOT NULL DEFAULT 0,
    finished_at TEXT,
    is_team INTEGER NOT NULL DEFAULT 0,
    invite_code TEXT,
    owner_id INTEGER
);

CREATE TABLE IF NOT EXISTS team_members (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    coins INTEGER NOT NULL DEFAULT 50,
    coin_turnover INTEGER NOT NULL DEFAULT 50,
    click_power INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory (
    user_id INTEGER NOT NULL,
    ornament_type TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, ornament_type)
);

CREATE TABLE IF NOT EXISTS decorations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    ornament_type TEXT NOT NULL,
    color TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES trees(chat_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pack_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decorations_chat ON decorations(chat_id);
CREATE INDEX IF NOT EXISTS idx_decorations_user ON decorations(user_id);
"""


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(SCHEMA)
        for col_sql in [
            "ALTER TABLE users ADD COLUMN coins INTEGER NOT NULL DEFAULT 50",
            "ALTER TABLE users ADD COLUMN coin_turnover INTEGER NOT NULL DEFAULT 50",
            "ALTER TABLE users ADD COLUMN click_power INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE users ADD COLUMN last_daily_date TEXT DEFAULT ''",
            "ALTER TABLE users ADD COLUMN daily_streak INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN referrals_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE trees ADD COLUMN is_team INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE trees ADD COLUMN invite_code TEXT",
            "ALTER TABLE trees ADD COLUMN owner_id INTEGER",
            "ALTER TABLE trees ADD COLUMN bg_theme TEXT NOT NULL DEFAULT 'aurora'",
            "ALTER TABLE trees ADD COLUMN garland_style TEXT NOT NULL DEFAULT 'classic'",
            "ALTER TABLE trees ADD COLUMN topper_type TEXT NOT NULL DEFAULT 'star'",
            "ALTER TABLE decorations ADD COLUMN wish_text TEXT NOT NULL DEFAULT ''",
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass
        await db.execute("UPDATE users SET coin_turnover = coins WHERE coin_turnover < coins")
        # Миграция v8: старая «общая» ёлка (chat_id = 1) и все групповые ёлки
        # (chat_id > 1) больше не существуют — у каждого игрока своя ёлка.
        await db.execute(
            "UPDATE decorations SET chat_id = ? WHERE chat_id = ? OR chat_id > 1",
            (-PERSONAL_TREE_BASE - 1, LEGACY_SHARED_TREE_ID),
        )
        await db.execute("DELETE FROM decorations WHERE chat_id > 1")
        await db.execute("DELETE FROM trees WHERE chat_id = ? OR chat_id > 1", (LEGACY_SHARED_TREE_ID,))
        await db.commit()


async def get_or_create_tree(chat_id: int, chat_title: str = "", is_team: int = 0) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    chat_id = int(chat_id)
    personal = is_personal_tree_id(chat_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM trees WHERE chat_id = ?", (chat_id,))
        row = await cur.fetchone()
        if row:
            return dict(row)
        team_flag = 0 if personal else 1
        invite_code = None if personal else f"team_{secrets.token_hex(4)}"
        await db.execute(
            "INSERT INTO trees (chat_id, chat_title, created_at, is_team, invite_code) VALUES (?, ?, ?, ?, ?)",
            (chat_id, chat_title, now, team_flag, invite_code),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM trees WHERE chat_id = ?", (chat_id,))
        return dict(await cur.fetchone())


async def get_or_create_personal_tree(user_id: int, first_name: str = "") -> dict:
    """Личная ёлка игрока — отдельная от всех и недоступная по приглашению."""
    user = await upsert_user(user_id, first_name=first_name or "")
    name = (first_name or user.get("first_name") or "").strip()[:32]
    title = f"Ёлка {name}" if name and name != "Участник" else "Моя новогодняя ёлка"
    tree = await get_or_create_tree(personal_tree_id(user_id), title)
    if first_name and tree.get("chat_title") != title:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                "UPDATE trees SET chat_title = ? WHERE chat_id = ?", (title, personal_tree_id(user_id))
            )
            await db.commit()
        tree["chat_title"] = title
    return tree


async def get_tree(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM trees WHERE chat_id = ?", (chat_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_team_tree(owner_id: int, title: str) -> dict:
    """Создаёт новую командную ёлку и возвращает её данные вместе с invite_code."""
    now = datetime.now(timezone.utc).isoformat()
    clean_title = (title or "Командная ёлка друзей").strip()[:48]
    existing = await get_owned_team_tree(owner_id)
    if existing:
        # У игрока уже есть своя команда — второй раз ссылку не генерируем,
        # иначе друзья разбредутся по разным ёлкам.
        return existing
    invite_code = f"team_{secrets.token_hex(4)}"
    # Отрицательный ID для командной ёлки
    team_chat_id = -(900000000 + secrets.randbelow(90000000))
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            INSERT INTO trees (chat_id, chat_title, created_at, is_team, invite_code, owner_id)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (team_chat_id, clean_title, now, invite_code, owner_id),
        )
        await db.execute(
            "INSERT OR IGNORE INTO team_members (chat_id, user_id, joined_at) VALUES (?, ?, ?)",
            (team_chat_id, owner_id, now),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM trees WHERE chat_id = ?", (team_chat_id,))
        return dict(await cur.fetchone())


async def get_owned_team_tree(owner_id: int) -> dict | None:
    """Командная ёлка, созданная этим игроком (не более одной на игрока)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM trees WHERE owner_id = ? AND chat_id < 0 AND chat_id > ? ORDER BY created_at ASC LIMIT 1",
            (owner_id, -PERSONAL_TREE_BASE),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_tree_members(chat_id: int) -> list[dict]:
    """Участники командной ёлки (для человечков под ёлкой)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT tm.user_id,
                   COALESCE(u.first_name, 'Участник') AS first_name,
                   COALESCE(u.username, '') AS username,
                   tm.joined_at
            FROM team_members tm
            LEFT JOIN users u ON u.user_id = tm.user_id
            WHERE tm.chat_id = ?
            ORDER BY tm.joined_at ASC
            """,
            (chat_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_member_count(chat_id: int) -> int:
    """Сколько человек участвует в этой ёлке (личная = 1, группа/команда = участники)."""
    chat_id = int(chat_id)
    if is_personal_tree_id(chat_id):
        return 1
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) AS cnt FROM team_members WHERE chat_id = ?", (chat_id,)
        )
        row = await cur.fetchone()
        owner_cnt = int(row[0]) if row else 0
    if owner_cnt <= 0:
        tree = await get_tree(chat_id)
        owner_cnt = 1 if (tree and tree.get("owner_id")) else 0
    return max(0, owner_cnt)


async def get_tree_by_invite_code(invite_code: str) -> dict | None:
    code = (invite_code or "").strip()
    if not code:
        return None
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM trees WHERE invite_code = ?", (code,))
        row = await cur.fetchone()
        if row:
            return dict(row)
        # Если передан числовой ID вида team_-912345678
        if code.startswith("team_"):
            rest = code[5:]
            try:
                cid = int(rest)
                cur2 = await db.execute("SELECT * FROM trees WHERE chat_id = ?", (cid,))
                r2 = await cur2.fetchone()
                if r2:
                    return dict(r2)
            except Exception:
                pass
        return None


async def add_team_member(chat_id: int, user_id: int):
    # Личные ёлки не принимают участников — только командные и групповые.
    if is_personal_tree_id(chat_id) or int(chat_id) >= 0:
        return
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO team_members (chat_id, user_id, joined_at) VALUES (?, ?, ?)",
            (chat_id, user_id, now),
        )
        await db.commit()


async def get_user_team_trees(user_id: int) -> list[dict]:
    """Возвращает список всех командных ёлок, в которых состоит пользователь."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT DISTINCT t.chat_id, t.chat_title, t.invite_code, t.owner_id,
                   (SELECT COUNT(*) FROM decorations d WHERE d.chat_id = t.chat_id) AS toys_count,
                   (SELECT COUNT(*) FROM team_members tm WHERE tm.chat_id = t.chat_id) AS members_count
            FROM trees t
            LEFT JOIN team_members tm ON tm.chat_id = t.chat_id
            LEFT JOIN decorations d ON d.chat_id = t.chat_id
            WHERE (t.is_team = 1 OR t.chat_id < 0)
              AND (t.owner_id = ? OR tm.user_id = ? OR d.user_id = ?)
            ORDER BY t.created_at DESC
            """,
            (user_id, user_id, user_id),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def upsert_user(user_id: int, username: str = "", first_name: str = "", last_name: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        existing = await cur.fetchone()
        if not existing:
            await db.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name, coins, coin_turnover, click_power, updated_at)
                VALUES (?, ?, ?, ?, 50, 50, 1, ?)
                """,
                (user_id, username or "", first_name or "Участник", last_name or "", now),
            )
            await db.execute(
                "INSERT OR IGNORE INTO inventory (user_id, ornament_type, quantity) VALUES (?, 'ball', 2)",
                (user_id,),
            )
            await db.execute(
                "INSERT OR IGNORE INTO inventory (user_id, ornament_type, quantity) VALUES (?, 'snowflake', 1)",
                (user_id,),
            )
        else:
            await db.execute(
                """
                UPDATE users SET
                    username = CASE WHEN ? != '' THEN ? ELSE username END,
                    first_name = CASE WHEN ? != '' THEN ? ELSE first_name END,
                    last_name = CASE WHEN ? != '' THEN ? ELSE last_name END,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (username, username, first_name, first_name, last_name, last_name, now, user_id),
            )
        await db.commit()
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return dict(await cur.fetchone())


async def get_user_profile(user_id: int) -> dict:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = await cur.fetchone()
        if not user:
            user_dict = await upsert_user(user_id)
        else:
            user_dict = dict(user)
        cur_inv = await db.execute(
            "SELECT ornament_type, quantity FROM inventory WHERE user_id = ?",
            (user_id,),
        )
        inv_rows = await cur_inv.fetchall()
        inventory = {k: 0 for k in ORNAMENTS.keys()}
        for r in inv_rows:
            if r["ornament_type"] in inventory:
                inventory[r["ornament_type"]] = r["quantity"]
        user_dict["inventory"] = inventory
        user_dict["team_trees"] = await get_user_team_trees(user_id)
        # Адвент-календарь и рефералка: значения по умолчанию для старых строк
        user_dict.setdefault("daily_streak", 0)
        user_dict.setdefault("last_daily_date", "")
        user_dict.setdefault("referred_by", 0)
        user_dict.setdefault("referrals_count", 0)
        try:
            user_dict["daily_streak"] = int(user_dict.get("daily_streak") or 0)
        except Exception:
            user_dict["daily_streak"] = 0
        try:
            user_dict["referrals_count"] = int(user_dict.get("referrals_count") or 0)
        except Exception:
            user_dict["referrals_count"] = 0
        today_str = datetime.now(timezone.utc).date().isoformat()
        user_dict["can_claim_daily"] = str(user_dict.get("last_daily_date") or "") != today_str
        return user_dict


async def add_coins(user_id: int, amount: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins + ?, coin_turnover = coin_turnover + ? WHERE user_id = ?",
            (amount, max(0, amount), user_id),
        )
        await db.commit()
        cur = await db.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0


async def upgrade_click_power(user_id: int) -> tuple[bool, str, dict]:
    profile = await get_user_profile(user_id)
    current_power = int(profile.get("click_power", 1))
    cost = current_power * 100
    if profile["coins"] < cost:
        return False, f"Недостаточно монет (нужно {cost} 🪙)", profile
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins - ?, coin_turnover = coin_turnover + ?, click_power = click_power + 1 WHERE user_id = ?",
            (cost, cost, user_id),
        )
        await db.commit()
    updated = await get_user_profile(user_id)
    return True, f"Сила клика увеличена до +{updated['click_power']} 🪙!", updated


async def buy_ornament(user_id: int, ornament_type: str, count: int = 1) -> tuple[bool, str, dict]:
    if ornament_type not in ORNAMENTS:
        return False, "Неизвестная игрушка", await get_user_profile(user_id)
    price = int(ORNAMENTS[ornament_type].get("price", 25)) * count
    profile = await get_user_profile(user_id)
    if profile["coins"] < price:
        return False, f"Не хватает монет! Нужно {price} 🪙", profile
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins - ?, coin_turnover = coin_turnover + ? WHERE user_id = ?",
            (price, price, user_id),
        )
        await db.execute(
            """
            INSERT INTO inventory (user_id, ornament_type, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, ornament_type) DO UPDATE SET
                quantity = quantity + excluded.quantity
            """,
            (user_id, ornament_type, count),
        )
        await db.commit()
    updated = await get_user_profile(user_id)
    return True, f"Куплено: {ORNAMENTS[ornament_type]['emoji']} {ORNAMENTS[ornament_type]['name']}!", updated


async def consume_inventory_item(user_id: int, ornament_type: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT quantity FROM inventory WHERE user_id = ? AND ornament_type = ?",
            (user_id, ornament_type),
        )
        row = await cur.fetchone()
        if not row or row[0] <= 0:
            return False
        await db.execute(
            "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND ornament_type = ?",
            (user_id, ornament_type),
        )
        await db.commit()
        return True


async def return_inventory_item(user_id: int, ornament_type: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO inventory (user_id, ornament_type, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, ornament_type) DO UPDATE SET
                quantity = quantity + 1
            """,
            (user_id, ornament_type),
        )
        await db.commit()


async def create_order(user_id: int, pack_id: str, currency: str, amount: int) -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO orders (user_id, pack_id, currency, amount, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (user_id, pack_id, currency, amount, now),
        )
        await db.commit()
        return cur.lastrowid


async def get_order(order_id: int) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def complete_order_or_pack(user_id: int, pack_id: str, order_id: int = 0) -> dict:
    pack = DONATE_PACKS.get(pack_id)
    if not pack:
        return await get_user_profile(user_id)
    await upsert_user(user_id)
    rewards = pack["rewards"]
    coins_bonus = int(rewards.get("coins", 0))
    power_bonus = int(rewards.get("click_power_bonus", 0))
    items = rewards.get("items", {})

    async with aiosqlite.connect(DATABASE_PATH) as db:
        if order_id:
            cur = await db.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
            row = await cur.fetchone()
            if row and row[0] == "paid":
                return await get_user_profile(user_id)
            await db.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (order_id,))

        await db.execute(
            """
            UPDATE users SET
                coins = coins + ?,
                coin_turnover = coin_turnover + ?,
                click_power = click_power + ?
            WHERE user_id = ?
            """,
            (coins_bonus, coins_bonus, power_bonus, user_id),
        )
        for otype, qty in items.items():
            if qty > 0:
                await db.execute(
                    """
                    INSERT INTO inventory (user_id, ornament_type, quantity)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, ornament_type) DO UPDATE SET
                        quantity = quantity + excluded.quantity
                    """,
                    (user_id, otype, qty),
                )
        await db.commit()
    return await get_user_profile(user_id)


async def apply_referral(user_id: int, referrer_id: int) -> bool:
    """Начисляет бонус +300 монет и редкие игрушки и пригласившему, и приглашённому другу."""
    if not referrer_id or user_id == referrer_id:
        return False
    await upsert_user(user_id)
    await upsert_user(referrer_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row or (row["referred_by"] and int(row["referred_by"]) != 0):
            return False
        await db.execute(
            "UPDATE users SET referred_by = ?, coins = coins + 300, coin_turnover = coin_turnover + 300 WHERE user_id = ?",
            (referrer_id, user_id),
        )
        await db.execute(
            "UPDATE users SET referrals_count = COALESCE(referrals_count, 0) + 1, coins = coins + 300, coin_turnover = coin_turnover + 300 WHERE user_id = ?",
            (referrer_id,),
        )
        for uid in (user_id, referrer_id):
            for otype in ("gift", "star"):
                await db.execute(
                    """
                    INSERT INTO inventory (user_id, ornament_type, quantity)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, ornament_type) DO UPDATE SET
                        quantity = quantity + 1
                    """,
                    (uid, otype),
                )
        await db.commit()
        return True


ADVENT_REWARDS = [
    {"day": 1, "coins": 150, "item": "ball", "title": "День 1: +150 🪙 и 🔴 Шар"},
    {"day": 2, "coins": 250, "item": "candy", "title": "День 2: +250 🪙 и 🍬 Конфета"},
    {"day": 3, "coins": 350, "item": "snowflake", "title": "День 3: +350 🪙 и ❄️ Снежинка"},
    {"day": 4, "coins": 500, "item": "bell", "title": "День 4: +500 🪙 и 🔔 Колокольчик"},
    {"day": 5, "coins": 700, "item": "gift", "title": "День 5: +700 🪙 и 🎁 Подарок"},
    {"day": 6, "coins": 1000, "item": "star", "title": "День 6: +1000 🪙 и ⭐ Звезда"},
    {"day": 7, "coins": 1500, "item": "crystal", "title": "День 7+: +1500 🪙, 💎 Кристалл и +1 к силе клика!"},
]


async def claim_daily_advent(user_id: int) -> tuple[bool, str, dict, dict]:
    """Открытие ежедневного подарка Адвент-календаря под ёлкой."""
    today_dt = datetime.now(timezone.utc).date()
    today_str = today_dt.isoformat()
    yesterday_str = (today_dt - timedelta(days=1)).isoformat()

    profile = await get_user_profile(user_id)
    last_date = str(profile.get("last_daily_date") or "")
    if last_date == today_str:
        return False, "Ты уже открывал сегодняшний подарок! Приходи завтра 🎄", {}, profile

    prev_streak = int(profile.get("daily_streak") or 0)
    new_streak = (prev_streak + 1) if last_date == yesterday_str else 1
    reward_idx = min(new_streak, 7) - 1
    reward = ADVENT_REWARDS[reward_idx]
    coins_bonus = reward["coins"]
    item_type = reward["item"]
    power_bonus = 1 if new_streak >= 7 else 0

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE users SET
                coins = coins + ?,
                coin_turnover = coin_turnover + ?,
                click_power = click_power + ?,
                last_daily_date = ?,
                daily_streak = ?
            WHERE user_id = ?
            """,
            (coins_bonus, coins_bonus, power_bonus, today_str, new_streak, user_id),
        )
        await db.execute(
            """
            INSERT INTO inventory (user_id, ornament_type, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, ornament_type) DO UPDATE SET
                quantity = quantity + 1
            """,
            (user_id, item_type),
        )
        await db.commit()

    updated = await get_user_profile(user_id)
    return True, f"🎁 {reward['title']}!", reward, updated


async def open_lootbox(user_id: int) -> tuple[bool, str, dict, dict]:
    """Новогодний Сюрприз-бокс (Гача) за монеты."""
    profile = await get_user_profile(user_id)
    if profile["coins"] < LOOTBOX_PRICE:
        return False, f"Нужно {LOOTBOX_PRICE} 🪙 для открытия Сюрприз-бокса!", {}, profile

    pool = [
        {"weight": 26, "item": "gift", "coins": 40, "label": "🎁 Подарок + 40 🪙"},
        {"weight": 24, "item": "star", "coins": 50, "label": "⭐ Звезда + 50 🪙"},
        {"weight": 20, "item": "angel", "coins": 75, "label": "👼 Редкий Ангелочек + 75 🪙"},
        {"weight": 15, "item": "crystal", "coins": 100, "label": "💎 Легендарный Кристалл + 100 🪙"},
        {"weight": 15, "item": "bell", "coins": 300, "label": "🎰 ДЖЕКПОТ: 🔔 Колокольчик + 300 🪙!"},
    ]
    choices = [p for p in pool for _ in range(p["weight"])]
    won = random.choice(choices)
    net_coin_diff = won["coins"] - LOOTBOX_PRICE
    turnover_add = LOOTBOX_PRICE + won["coins"]

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE users SET
                coins = coins + ?,
                coin_turnover = coin_turnover + ?
            WHERE user_id = ?
            """,
            (net_coin_diff, turnover_add, user_id),
        )
        await db.execute(
            """
            INSERT INTO inventory (user_id, ornament_type, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, ornament_type) DO UPDATE SET
                quantity = quantity + 1
            """,
            (user_id, won["item"]),
        )
        await db.commit()

    updated = await get_user_profile(user_id)
    return True, f"Выпало из бокса: {won['label']}", won, updated


async def update_tree_style(chat_id: int, bg_theme: str, garland_style: str, topper_type: str) -> dict:
    bg = bg_theme if bg_theme in TREE_THEMES["backgrounds"] else "aurora"
    garland = garland_style if garland_style in TREE_THEMES["garlands"] else "classic"
    topper = topper_type if topper_type in TREE_THEMES["toppers"] else "star"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE trees SET bg_theme = ?, garland_style = ?, topper_type = ? WHERE chat_id = ?",
            (bg, garland, topper, chat_id),
        )
        await db.commit()
    return await get_tree(chat_id)


async def add_decoration(
    chat_id: int,
    user_id: int,
    ornament_type: str,
    color: str,
    x: float,
    y: float,
    wish_text: str = "",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    clean_wish = (wish_text or "").strip()[:120]
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if chat_id < 0 and not is_personal_tree_id(chat_id):
            await db.execute(
                "INSERT OR IGNORE INTO team_members (chat_id, user_id, joined_at) VALUES (?, ?, ?)",
                (chat_id, user_id, now),
            )
        cur = await db.execute(
            """
            INSERT INTO decorations (chat_id, user_id, ornament_type, color, x, y, wish_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, user_id, ornament_type, color, x, y, clean_wish, now),
        )
        await db.commit()
        return cur.lastrowid


async def get_decorations(chat_id: int) -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT d.*, u.username, u.first_name
            FROM decorations d
            LEFT JOIN users u ON u.user_id = d.user_id
            WHERE d.chat_id = ?
            ORDER BY d.created_at ASC
            """,
            (chat_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def delete_decoration(decoration_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM decorations WHERE id = ? AND user_id = ?",
            (decoration_id, user_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        dec = dict(row)
        await db.execute("DELETE FROM decorations WHERE id = ?", (decoration_id,))
        await db.commit()
        return dec


async def move_decoration(decoration_id: int, user_id: int, x: float, y: float) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "UPDATE decorations SET x = ?, y = ? WHERE id = ? AND user_id = ?",
            (x, y, decoration_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def sync_backup(
    chat_id: int,
    user_id: int,
    coins: int | None,
    coin_turnover: int | None,
    click_power: int | None,
    inventory: dict | None,
    decorations: list[dict] | None,
):
    """Восстанавливает прогресс из клиентского бэкапа, если БД на бесплатном хостинге перезапускалась."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if coins is not None or click_power is not None or coin_turnover is not None:
            cur = await db.execute(
                "SELECT coins, coin_turnover, click_power FROM users WHERE user_id = ?",
                (user_id,),
            )
            u = await cur.fetchone()
            if u:
                new_coins = max(int(u["coins"]), int(coins or 0))
                new_turnover = max(int(u["coin_turnover"]), int(coin_turnover or 0), new_coins)
                new_power = max(int(u["click_power"]), int(click_power or 1))
                await db.execute(
                    "UPDATE users SET coins = ?, coin_turnover = ?, click_power = ?, updated_at = ? WHERE user_id = ?",
                    (new_coins, new_turnover, new_power, now, user_id),
                )
        if inventory and isinstance(inventory, dict):
            for otype, qty in inventory.items():
                if otype in ORNAMENTS and isinstance(qty, int) and qty >= 0:
                    cur = await db.execute(
                        "SELECT quantity FROM inventory WHERE user_id = ? AND ornament_type = ?",
                        (user_id, otype),
                    )
                    row = await cur.fetchone()
                    cur_qty = row["quantity"] if row else 0
                    if qty > cur_qty:
                        await db.execute(
                            """
                            INSERT INTO inventory (user_id, ornament_type, quantity)
                            VALUES (?, ?, ?)
                            ON CONFLICT(user_id, ornament_type) DO UPDATE SET
                                quantity = MAX(quantity, excluded.quantity)
                            """,
                            (user_id, otype, qty),
                        )
        if decorations and isinstance(decorations, list):
            cur = await db.execute(
                "SELECT COUNT(*) AS cnt FROM decorations WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
            cnt_row = await cur.fetchone()
            if cnt_row and cnt_row["cnt"] == 0:
                for d in decorations[:100]:
                    otype = d.get("ornament_type", "ball")
                    color = d.get("color", "red")
                    x = float(d.get("x", 50))
                    y = float(d.get("y", 50))
                    d_uid = int(d.get("user_id", user_id))
                    if d_uid == user_id and otype in ORNAMENTS and 0 <= x <= 100 and 0 <= y <= 100:
                        wish = str(d.get("wish_text") or "").strip()[:120]
                        await db.execute(
                            """
                            INSERT INTO decorations (chat_id, user_id, ornament_type, color, x, y, wish_text, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (chat_id, user_id, otype, color, x, y, wish, now),
                        )
        await db.commit()


async def get_stats(chat_id: int) -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT d.user_id,
                   COALESCE(u.username, '') AS username,
                   COALESCE(u.first_name, 'Участник') AS first_name,
                   COALESCE(u.coins, 0) AS coins,
                   COALESCE(u.coin_turnover, COALESCE(u.coins, 0)) AS coin_turnover,
                   COUNT(d.id) AS count
            FROM decorations d
            LEFT JOIN users u ON u.user_id = d.user_id
            WHERE d.chat_id = ?
            GROUP BY d.user_id
            ORDER BY count DESC, coin_turnover DESC
            """,
            (chat_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_team_trees_leaderboard() -> list[dict]:
    """Возвращает рейтинг всех командных ёлок (где is_team = 1 или групповой чат chat_id < 0)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT t.chat_id,
                   COALESCE(t.chat_title, 'Командная ёлка') AS chat_title,
                   t.invite_code,
                   t.owner_id,
                   COUNT(DISTINCT d.id) AS count,
                   COUNT(DISTINCT COALESCE(tm.user_id, d.user_id)) AS members_count
            FROM trees t
            LEFT JOIN decorations d ON d.chat_id = t.chat_id
            LEFT JOIN team_members tm ON tm.chat_id = t.chat_id
            WHERE t.chat_id < 0 AND t.chat_id > ?
            GROUP BY t.chat_id
            ORDER BY count DESC, members_count DESC, t.created_at ASC
            LIMIT 50
            """,
            (-PERSONAL_TREE_BASE,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_global_leaderboard() -> dict:
    """Возвращает общий рейтинг всех игроков бота (по игрушкам, по обороту монет и командные ёлки)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur_toys = await db.execute(
            """
            SELECT u.user_id,
                   COALESCE(u.username, '') AS username,
                   COALESCE(u.first_name, 'Игрок') AS first_name,
                   COALESCE(u.coins, 0) AS coins,
                   COALESCE(u.coin_turnover, COALESCE(u.coins, 0)) AS coin_turnover,
                   COALESCE(u.click_power, 1) AS click_power,
                   COUNT(d.id) AS count
            FROM users u
            LEFT JOIN decorations d ON d.user_id = u.user_id
            GROUP BY u.user_id
            ORDER BY count DESC, coin_turnover DESC
            LIMIT 50
            """
        )
        by_toys = [dict(r) for r in await cur_toys.fetchall()]

        cur_turnover = await db.execute(
            """
            SELECT u.user_id,
                   COALESCE(u.username, '') AS username,
                   COALESCE(u.first_name, 'Игрок') AS first_name,
                   COALESCE(u.coins, 0) AS coins,
                   COALESCE(u.coin_turnover, COALESCE(u.coins, 0)) AS coin_turnover,
                   COALESCE(u.click_power, 1) AS click_power,
                   COUNT(d.id) AS count
            FROM users u
            LEFT JOIN decorations d ON d.user_id = u.user_id
            GROUP BY u.user_id
            ORDER BY coin_turnover DESC, count DESC
            LIMIT 50
            """
        )
        by_turnover = [dict(r) for r in await cur_turnover.fetchall()]

    team_trees = await get_team_trees_leaderboard()
    return {
        "by_toys": by_toys,
        "by_turnover": by_turnover,
        "by_coins": by_turnover,
        "team_trees": team_trees,
    }


async def get_unfinished_trees() -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM trees WHERE is_finished = 0")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def mark_tree_finished(chat_id: int):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE trees SET is_finished = 1, finished_at = ? WHERE chat_id = ?",
            (now, chat_id),
        )
        await db.commit()
