"""FastAPI сервер для Mini App: отдаёт статику, API и запускает бота в фоне (ASGI lifespan)."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import logging
import os
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import bot as bot_module
from config import BOT_TOKEN, ORNAMENTS
import database as db
from tree_image import generate_tree_image

log = logging.getLogger(__name__)


async def _run_bot_background():
    try:
        await bot_module.main(handle_signals=False)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log.warning(
            "Telegram Bot polling не удалось запустить в текущем окружении (%s). "
            "Mini App веб-сервер продолжает работу.",
            e,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    bot_task = None
    if BOT_TOKEN:
        bot_task = asyncio.create_task(_run_bot_background())
    else:
        log.info("BOT_TOKEN не задан — запущен только Mini App веб-сервер.")
    try:
        yield
    finally:
        if bot_task and not bot_task.done():
            bot_task.cancel()
            try:
                await bot_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="New Year Tree Mini App", lifespan=lifespan)
# Алиас для Alwaysdata Python ASGI (по умолчанию ищет `application`)
application = app

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def validate_init_data(init_data: str) -> dict:
    """Проверяет подпись Telegram initData. Возвращает словарь полей."""
    if not init_data:
        return {}
    if not BOT_TOKEN:
        return dict(parse_qsl(init_data))
    try:
        data = dict(parse_qsl(init_data))
        hash_value = data.pop("hash", None)
        if not hash_value:
            return {}
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, hash_value):
            return {}
        return data
    except Exception:
        return {}


def parse_user(init_data: str) -> dict:
    fields = validate_init_data(init_data)
    raw_user = fields.get("user", "{}")
    try:
        user = json.loads(raw_user)
    except Exception:
        user = {}
    return user


class DecorateRequest(BaseModel):
    chat_id: int
    ornament_type: str
    color: str
    x: float
    y: float
    init_data: str = ""


class MoveRequest(BaseModel):
    decoration_id: int
    x: float
    y: float
    init_data: str = ""


class DeleteRequest(BaseModel):
    decoration_id: int
    init_data: str = ""


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/ping")
async def ping():
    return {"status": "ok"}


@app.get("/api/ornaments")
async def get_ornaments():
    return ORNAMENTS


@app.get("/api/tree/{chat_id}")
async def get_tree(chat_id: int):
    tree = await db.get_tree(chat_id)
    if not tree:
        default_title = "Демо-чат друзей" if chat_id == 1 else f"Чат #{chat_id}"
        tree = await db.get_or_create_tree(chat_id, default_title)
    decorations = await db.get_decorations(chat_id)
    stats = await db.get_stats(chat_id)
    return {
        "tree": tree,
        "decorations": decorations,
        "stats": stats,
        "ornaments": ORNAMENTS,
    }


@app.post("/api/decorate")
async def decorate(req: DecorateRequest):
    tree = await db.get_tree(req.chat_id)
    if not tree:
        default_title = "Демо-чат друзей" if req.chat_id == 1 else f"Чат #{req.chat_id}"
        tree = await db.get_or_create_tree(req.chat_id, default_title)
    if tree.get("is_finished"):
        raise HTTPException(400, "Ёлка уже подведена! Ивент завершён 🎉")
    if req.ornament_type not in ORNAMENTS:
        raise HTTPException(400, "Unknown ornament")
    if req.color not in ORNAMENTS[req.ornament_type]["colors"]:
        raise HTTPException(400, "Unknown color")
    if not (0 <= req.x <= 100 and 0 <= req.y <= 100):
        raise HTTPException(400, "Coordinates out of range")

    user = parse_user(req.init_data)
    user_id = int(user.get("id", 0)) if user.get("id") else 0
    await db.upsert_user(
        user_id,
        username=user.get("username", ""),
        first_name=user.get("first_name", "Участник"),
        last_name=user.get("last_name", ""),
    )
    dec_id = await db.add_decoration(req.chat_id, user_id, req.ornament_type, req.color, req.x, req.y)
    return {"id": dec_id, "ok": True}


@app.post("/api/move")
async def move_decoration(req: MoveRequest):
    if not (0 <= req.x <= 100 and 0 <= req.y <= 100):
        raise HTTPException(400, "Coordinates out of range")
    user = parse_user(req.init_data)
    user_id = int(user.get("id", 0)) if user.get("id") else 0
    ok = await db.move_decoration(req.decoration_id, user_id, req.x, req.y)
    if not ok:
        raise HTTPException(403, "Можно перемещать только свои игрушки")
    return {"ok": True}


@app.post("/api/delete")
async def delete_decoration(req: DeleteRequest):
    user = parse_user(req.init_data)
    user_id = int(user.get("id", 0)) if user.get("id") else 0
    ok = await db.delete_decoration(req.decoration_id, user_id)
    if not ok:
        raise HTTPException(403, "Можно удалять только свои игрушки")
    return {"ok": True}


@app.get("/api/final-image/{chat_id}")
async def final_image(chat_id: int):
    tree = await db.get_tree(chat_id)
    if not tree:
        raise HTTPException(404, "Tree not found")
    decorations = await db.get_decorations(chat_id)
    png = generate_tree_image(decorations, title=f"Ёлка чата: {tree.get('chat_title') or chat_id}")
    return Response(content=png, media_type="image/png")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
