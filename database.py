"""Слой базы данных (SQLite + aiosqlite)."""
import aiosqlite
from datetime import datetime, timezone
from config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS trees (
    chat_id INTEGER PRIMARY KEY,
    chat_title TEXT,
    created_at TEXT NOT NULL,
    is_finished INTEGER NOT NULL DEFAULT 0,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    updated_at TEXT NOT NULL
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

CREATE INDEX IF NOT EXISTS idx_decorations_chat ON decorations(chat_id);
CREATE INDEX IF NOT EXISTS idx_decorations_user ON decorations(user_id);
"""


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def get_or_create_tree(chat_id: int, chat_title: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM trees WHERE chat_id = ?", (chat_id,))
        row = await cur.fetchone()
        if row:
            return dict(row)
        await db.execute(
            "INSERT INTO trees (chat_id, chat_title, created_at) VALUES (?, ?, ?)",
            (chat_id, chat_title, now),
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


async def upsert_user(user_id: int, username: str = "", first_name: str = "", last_name: str = ""):
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                updated_at=excluded.updated_at
            """,
            (user_id, username or "", first_name or "", last_name or "", now),
        )
        await db.commit()


async def add_decoration(chat_id: int, user_id: int, ornament_type: str, color: str, x: float, y: float) -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
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


async def delete_decoration(decoration_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "DELETE FROM decorations WHERE id = ? AND user_id = ?",
            (decoration_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def move_decoration(decoration_id: int, user_id: int, x: float, y: float) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "UPDATE decorations SET x = ?, y = ? WHERE id = ? AND user_id = ?",
            (x, y, decoration_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_stats(chat_id: int) -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT u.user_id, u.username, u.first_name, COUNT(d.id) AS count
            FROM decorations d
            JOIN users u ON u.user_id = d.user_id
            WHERE d.chat_id = ?
            GROUP BY u.user_id
            ORDER BY count DESC
            """,
            (chat_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


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
