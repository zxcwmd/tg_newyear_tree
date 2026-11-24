"""Слой базы данных (SQLite + aiosqlite)."""
import secrets
import aiosqlite
from datetime import datetime, timezone
from config import DATABASE_PATH, DONATE_PACKS, ORNAMENTS

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
            "ALTER TABLE trees ADD COLUMN is_team INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE trees ADD COLUMN invite_code TEXT",
            "ALTER TABLE trees ADD COLUMN owner_id INTEGER",
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass
        await db.execute("UPDATE users SET coin_turnover = coins WHERE coin_turnover < coins")
        await db.execute(
            "INSERT OR IGNORE INTO trees (chat_id, chat_title, created_at, is_team) VALUES (1, 'Общая новогодняя ёлка', ?, 0)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        await db.execute("UPDATE decorations SET chat_id = 1 WHERE chat_id > 1")
        await db.commit()


async def get_or_create_tree(chat_id: int, chat_title: str = "", is_team: int = 0) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM trees WHERE chat_id = ?", (chat_id,))
        row = await cur.fetchone()
        if row:
            return dict(row)
        invite_code = f"team_{secrets.token_hex(4)}" if (is_team or chat_id < 0) else None
        await db.execute(
            "INSERT INTO trees (chat_id, chat_title, created_at, is_team, invite_code) VALUES (?, ?, ?, ?, ?)",
            (chat_id, chat_title, now, 1 if (is_team or chat_id < 0) else 0, invite_code),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM trees WHERE chat_id = ?", (chat_id,))
        return dict(await cur.fetchone())


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
    if chat_id == 1:
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
            inventory[r["ornament_type"]] = r["quantity"]
        user_dict["inventory"] = inventory
        user_dict["team_trees"] = await get_user_team_trees(user_id)
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


async def add_decoration(chat_id: int, user_id: int, ornament_type: str, color: str, x: float, y: float) -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if chat_id < 0:
            await db.execute(
                "INSERT OR IGNORE INTO team_members (chat_id, user_id, joined_at) VALUES (?, ?, ?)",
                (chat_id, user_id, now),
            )
        cur = await db.execute(
            """
            INSERT INTO decorations (chat_id, user_id, ornament_type, color, x, y, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, user_id, ornament_type, color, x, y, now),
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
                        await db.execute(
                            """
                            INSERT INTO decorations (chat_id, user_id, ornament_type, color, x, y, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (chat_id, user_id, otype, color, x, y, now),
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
            WHERE t.is_team = 1 OR t.chat_id < 0
            GROUP BY t.chat_id
            ORDER BY count DESC, members_count DESC, t.created_at ASC
            LIMIT 50
            """
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
