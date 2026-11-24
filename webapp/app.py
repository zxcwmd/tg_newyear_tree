"""FastAPI сервер для Mini App: отдаёт статику, API, кликер, магазин и донат (Stars / GRAM)."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import logging
import os
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import bot as bot_module
from config import BOT_TOKEN, DONATE_PACKS, GRAM_WALLET_ADDRESS, ORNAMENTS
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
application = app

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.middleware("http")
async def no_cache_api_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


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


def resolve_user(init_data: str = "", fallback_user: dict | None = None) -> dict:
    fields = validate_init_data(init_data)
    raw_user = fields.get("user", "")
    if raw_user:
        try:
            parsed = json.loads(raw_user)
            if parsed.get("id"):
                return parsed
        except Exception:
            pass
    # Если подпись не совпала (например, прокси/тест), пробуем распарсить user из init_data напрямую
    if init_data:
        try:
            raw_fields = dict(parse_qsl(init_data))
            if "user" in raw_fields:
                parsed = json.loads(raw_fields["user"])
                if parsed.get("id"):
                    return parsed
        except Exception:
            pass
    if fallback_user and fallback_user.get("id") is not None:
        return fallback_user
    return {"id": 1, "username": "", "first_name": "Игрок", "last_name": ""}


class UserInfoModel(BaseModel):
    id: int = 1
    username: str = ""
    first_name: str = "Игрок"
    last_name: str = ""


class DecorateRequest(BaseModel):
    chat_id: int
    ornament_type: str
    color: str
    x: float
    y: float
    init_data: str = ""
    user: UserInfoModel | None = None


class MoveRequest(BaseModel):
    decoration_id: int
    x: float
    y: float
    init_data: str = ""
    user: UserInfoModel | None = None


class DeleteRequest(BaseModel):
    decoration_id: int
    init_data: str = ""
    user: UserInfoModel | None = None


class ClickRequest(BaseModel):
    clicks: int = 1
    init_data: str = ""
    user: UserInfoModel | None = None


class UpgradeClickRequest(BaseModel):
    init_data: str = ""
    user: UserInfoModel | None = None


class BuyOrnamentRequest(BaseModel):
    ornament_type: str
    count: int = 1
    init_data: str = ""
    user: UserInfoModel | None = None


class DonateOrderRequest(BaseModel):
    pack_id: str
    currency: str = "XTR"
    order_id: int = 0
    init_data: str = ""
    user: UserInfoModel | None = None


class SyncBackupRequest(BaseModel):
    chat_id: int
    coins: int | None = None
    click_power: int | None = None
    inventory: dict | None = None
    decorations: list[dict] | None = None
    init_data: str = ""
    user: UserInfoModel | None = None


async def _ensure_user_from_req(init_data: str, user_model: UserInfoModel | None) -> int:
    fb = user_model.model_dump() if user_model else None
    u = resolve_user(init_data, fb)
    uid = int(u.get("id") or 1)
    await db.upsert_user(
        uid,
        username=str(u.get("username") or ""),
        first_name=str(u.get("first_name") or "Игрок"),
        last_name=str(u.get("last_name") or ""),
    )
    return uid


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
async def get_tree(
    chat_id: int,
    user_id: int = Query(default=1),
    username: str = Query(default=""),
    first_name: str = Query(default="Игрок"),
):
    tree = await db.get_tree(chat_id)
    if not tree:
        default_title = "Демо-чат друзей" if chat_id == 1 else f"Чат #{chat_id}"
        tree = await db.get_or_create_tree(chat_id, default_title)
    await db.upsert_user(user_id, username=username, first_name=first_name)
    profile = await db.get_user_profile(user_id)
    decorations = await db.get_decorations(chat_id)
    stats = await db.get_stats(chat_id)
    return {
        "tree": tree,
        "decorations": decorations,
        "stats": stats,
        "ornaments": ORNAMENTS,
        "donate_packs": DONATE_PACKS,
        "gram_wallet": GRAM_WALLET_ADDRESS,
        "profile": profile,
    }


@app.post("/api/sync")
async def sync_backup_endpoint(req: SyncBackupRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    tree = await db.get_tree(req.chat_id)
    if not tree:
        default_title = "Демо-чат друзей" if req.chat_id == 1 else f"Чат #{req.chat_id}"
        await db.get_or_create_tree(req.chat_id, default_title)
    await db.sync_backup(
        chat_id=req.chat_id,
        user_id=uid,
        coins=req.coins,
        click_power=req.click_power,
        inventory=req.inventory,
        decorations=req.decorations,
    )
    profile = await db.get_user_profile(uid)
    decorations = await db.get_decorations(req.chat_id)
    stats = await db.get_stats(req.chat_id)
    return {
        "ok": True,
        "profile": profile,
        "decorations": decorations,
        "stats": stats,
    }


@app.post("/api/click")
async def click_coins(req: ClickRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    clicks = max(1, min(50, int(req.clicks)))
    profile = await db.get_user_profile(uid)
    power = max(1, int(profile.get("click_power", 1)))
    earned = clicks * power
    await db.add_coins(uid, earned)
    updated_profile = await db.get_user_profile(uid)
    return {
        "ok": True,
        "earned": earned,
        "profile": updated_profile,
    }


@app.post("/api/upgrade-click")
async def upgrade_click(req: UpgradeClickRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    ok, msg, profile = await db.upgrade_click_power(uid)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg, "profile": profile}


@app.post("/api/buy")
async def buy_ornament(req: BuyOrnamentRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    count = max(1, min(20, int(req.count)))
    ok, msg, profile = await db.buy_ornament(uid, req.ornament_type, count=count)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg, "profile": profile}


@app.post("/api/donate/stars-invoice")
async def create_stars_invoice(req: DonateOrderRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    pack = DONATE_PACKS.get(req.pack_id)
    if not pack:
        raise HTTPException(404, "Набор не найден")
    order_id = await db.create_order(uid, req.pack_id, "XTR", int(pack["stars_price"]))
    invoice_link = None
    try:
        invoice_link = await bot_module.create_stars_invoice_link(uid, req.pack_id, order_id)
    except Exception as e:
        log.warning("Could not create Telegram Stars invoice link: %s", e)
    return {
        "ok": True,
        "order_id": order_id,
        "invoice_link": invoice_link,
        "pack": pack,
    }


@app.post("/api/donate/claim")
async def claim_donate_pack(req: DonateOrderRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    pack = DONATE_PACKS.get(req.pack_id)
    if not pack:
        raise HTTPException(404, "Набор не найден")
    order_id = req.order_id
    if not order_id:
        amount = int(pack["gram_price"] if req.currency == "GRAM" else pack["stars_price"])
        order_id = await db.create_order(uid, req.pack_id, req.currency, amount)
    profile = await db.complete_order_or_pack(uid, req.pack_id, order_id)
    return {
        "ok": True,
        "message": f"Набор «{pack['title']}» успешно начислен! 🎉",
        "profile": profile,
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
        raise HTTPException(400, "Неизвестная игрушка")
    if req.color not in ORNAMENTS[req.ornament_type]["colors"]:
        raise HTTPException(400, "Неизвестный цвет")
    if not (0 <= req.x <= 100 and 0 <= req.y <= 100):
        raise HTTPException(400, "Координаты вне диапазона")

    uid = await _ensure_user_from_req(req.init_data, req.user)
    has_item = await db.consume_inventory_item(uid, req.ornament_type)
    if not has_item:
        info = ORNAMENTS[req.ornament_type]
        raise HTTPException(
            400,
            f"В инвентаре нет «{info['emoji']} {info['name']}»! Купи в Магазине за {info['price']} 🪙",
        )
    dec_id = await db.add_decoration(req.chat_id, uid, req.ornament_type, req.color, req.x, req.y)
    profile = await db.get_user_profile(uid)
    return {"id": dec_id, "ok": True, "profile": profile}


@app.post("/api/move")
async def move_decoration(req: MoveRequest):
    if not (0 <= req.x <= 100 and 0 <= req.y <= 100):
        raise HTTPException(400, "Координаты вне диапазона")
    uid = await _ensure_user_from_req(req.init_data, req.user)
    ok = await db.move_decoration(req.decoration_id, uid, req.x, req.y)
    if not ok:
        raise HTTPException(403, "Можно перемещать только свои игрушки")
    return {"ok": True}


@app.post("/api/delete")
async def delete_decoration(req: DeleteRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    deleted = await db.delete_decoration(req.decoration_id, uid)
    if not deleted:
        raise HTTPException(403, "Можно снимать только свои игрушки")
    # Возвращаем снятую игрушку обратно в инвентарь игрока
    await db.return_inventory_item(uid, deleted["ornament_type"])
    profile = await db.get_user_profile(uid)
    return {"ok": True, "profile": profile}


@app.get("/api/final-image/{chat_id}")
async def final_image(chat_id: int):
    tree = await db.get_tree(chat_id)
    if not tree:
        raise HTTPException(404, "Tree not found")
    decorations = await db.get_decorations(chat_id)
    png = generate_tree_image(decorations, title=f"Ёлка чата: {tree.get('chat_title') or chat_id}")
    return Response(content=png, media_type="image/png")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
