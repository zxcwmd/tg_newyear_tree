"""FastAPI сервер для Mini App: отдаёт статику, API, кликер, командные ёлки, магазин и донат."""
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
from config import (
    BOT_TOKEN,
    DONATE_PACKS,
    GRAM_WALLET_ADDRESS,
    LOOTBOX_PRICE,
    ORNAMENTS,
    TREE_THEMES,
    WEBAPP_URL,
)
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
    wish_text: str = ""
    init_data: str = ""
    user: UserInfoModel | None = None


class DailyClaimRequest(BaseModel):
    init_data: str = ""
    user: UserInfoModel | None = None


class LootboxRequest(BaseModel):
    init_data: str = ""
    user: UserInfoModel | None = None


class TreeStyleRequest(BaseModel):
    chat_id: int
    bg_theme: str = "midnight"
    garland_style: str = "multicolor"
    topper_type: str = "star"
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


class CreateTeamTreeRequest(BaseModel):
    title: str
    init_data: str = ""
    user: UserInfoModel | None = None


class JoinTeamTreeRequest(BaseModel):
    invite_code: str
    init_data: str = ""
    user: UserInfoModel | None = None


class SyncBackupRequest(BaseModel):
    chat_id: int
    coins: int | None = None
    coin_turnover: int | None = None
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


def normalize_chat_id(chat_id: int) -> int:
    """Групповые и командные ёлки имеют отрицательный ID (< 0). Одиночные положительные ID (> 1) объединяем в общую ёлку (1)."""
    return 1 if chat_id > 1 else chat_id


def is_inside_tree(x_pct: float, y_pct: float) -> bool:
    """Проверяет, попадает ли точка (0..100, 0..100) внутрь кроны одного из 3 ярусов ёлки."""
    sx = x_pct * 4.0  # 0..400
    sy = y_pct * 5.0  # 0..500
    tiers = [
        (60.0, 216.0, 8.0, 76.0),
        (146.0, 326.0, 14.0, 96.0),
        (236.0, 430.0, 18.0, 120.0),
    ]
    for y_top, y_bot, hw_top, hw_bot in tiers:
        if y_top <= sy <= y_bot:
            t = (sy - y_top) / (y_bot - y_top)
            max_hw = hw_top + t * (hw_bot - hw_top)
            if abs(sx - 200.0) <= max_hw:
                return True
    return False


def clamp_to_tree(x_pct: float, y_pct: float) -> tuple[float, float]:
    """Притягивает координаты внутрь кроны ёлки (для перетаскивания)."""
    sx = x_pct * 4.0
    sy = max(64.0, min(426.0, y_pct * 5.0))
    tiers = [
        (60.0, 216.0, 8.0, 74.0),
        (146.0, 326.0, 14.0, 94.0),
        (236.0, 430.0, 18.0, 118.0),
    ]
    allowed_hw = 20.0
    for y_top, y_bot, hw_top, hw_bot in tiers:
        if y_top <= sy <= y_bot:
            t = (sy - y_top) / (y_bot - y_top)
            hw = hw_top + t * (hw_bot - hw_top)
            if hw > allowed_hw:
                allowed_hw = hw
    clamped_sx = max(200.0 - allowed_hw, min(200.0 + allowed_hw, sx))
    return round(clamped_sx / 4.0, 1), round(sy / 5.0, 1)


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/ping")
async def ping():
    return {"status": "ok"}


@app.get("/api/ornaments")
async def get_ornaments():
    return ORNAMENTS


@app.get("/api/leaderboard")
async def get_leaderboard_endpoint(chat_id: int = Query(default=1)):
    cid = normalize_chat_id(chat_id)
    chat_stats = await db.get_stats(cid)
    global_lb = await db.get_global_leaderboard()
    return {
        "chat_stats": chat_stats,
        "by_toys": global_lb["by_toys"],
        "by_turnover": global_lb["by_turnover"],
        "by_coins": global_lb["by_turnover"],
        "team_trees": global_lb["team_trees"],
    }


@app.get("/api/tree/{chat_id}")
async def get_tree(
    chat_id: int,
    user_id: int = Query(default=1),
    username: str = Query(default=""),
    first_name: str = Query(default="Игрок"),
    invite_code: str = Query(default=""),
    referrer_id: int = Query(default=0),
):
    await db.upsert_user(user_id, username=username, first_name=first_name)

    referral_bonus_applied = False
    if referrer_id and referrer_id > 0:
        referral_bonus_applied = await db.apply_referral(user_id, referrer_id)

    # Если передан invite_code командной ёлки — присоединяем игрока и открываем эту командную ёлку
    if invite_code:
        if invite_code.startswith("ref_"):
            try:
                ref_uid = int(invite_code[4:])
                if await db.apply_referral(user_id, ref_uid):
                    referral_bonus_applied = True
            except Exception:
                pass
        else:
            invited_tree = await db.get_tree_by_invite_code(invite_code)
            if invited_tree:
                chat_id = invited_tree["chat_id"]
                if invited_tree.get("owner_id"):
                    if await db.apply_referral(user_id, int(invited_tree["owner_id"])):
                        referral_bonus_applied = True

    cid = normalize_chat_id(chat_id)
    tree = await db.get_tree(cid)
    if not tree:
        default_title = "Общая новогодняя ёлка" if cid == 1 else f"Командная ёлка #{abs(cid) % 10000}"
        tree = await db.get_or_create_tree(cid, default_title, is_team=1 if cid < 0 else 0)
    if cid < 0:
        await db.add_team_member(cid, user_id)

    profile = await db.get_user_profile(user_id)
    decorations = await db.get_decorations(cid)
    stats = await db.get_stats(cid)
    leaderboard = await db.get_global_leaderboard()
    bot_uname = await bot_module.get_bot_username()
    return {
        "tree": tree,
        "decorations": decorations,
        "stats": stats,
        "leaderboard": leaderboard,
        "ornaments": ORNAMENTS,
        "donate_packs": DONATE_PACKS,
        "gram_wallet": GRAM_WALLET_ADDRESS,
        "profile": profile,
        "bot_username": bot_uname,
        "webapp_url": WEBAPP_URL,
        "tree_themes": TREE_THEMES,
        "lootbox_price": LOOTBOX_PRICE,
        "advent_rewards": db.ADVENT_REWARDS,
        "referral_bonus_applied": referral_bonus_applied,
    }


@app.post("/api/team/create")
async def create_team_tree_endpoint(req: CreateTeamTreeRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    title = (req.title or "").strip()
    if len(title) < 2:
        raise HTTPException(400, "Введи название командной ёлки (минимум 2 символа)")
    team_tree = await db.create_team_tree(uid, title)
    profile = await db.get_user_profile(uid)
    bot_uname = await bot_module.get_bot_username()
    code = team_tree["invite_code"]
    bot_link = f"https://t.me/{bot_uname}?start={code}" if bot_uname else f"{WEBAPP_URL}/?invite={code}"
    web_link = f"{WEBAPP_URL}/?chat_id={team_tree['chat_id']}&invite={code}"
    return {
        "ok": True,
        "tree": team_tree,
        "invite_code": code,
        "bot_invite_url": bot_link,
        "web_invite_url": web_link,
        "profile": profile,
    }


@app.post("/api/team/join")
async def join_team_tree_endpoint(req: JoinTeamTreeRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    code = (req.invite_code or "").strip()
    # Извлекаем код, если вставили полную ссылку
    if "invite=" in code:
        code = code.split("invite=")[-1].split("&")[0]
    elif "start=" in code:
        code = code.split("start=")[-1].split("&")[0]
    team_tree = await db.get_tree_by_invite_code(code)
    if not team_tree:
        raise HTTPException(404, "Командная ёлка по этому коду/ссылке не найдена")
    await db.add_team_member(team_tree["chat_id"], uid)
    referral_bonus = False
    if team_tree.get("owner_id"):
        referral_bonus = await db.apply_referral(uid, int(team_tree["owner_id"]))
    profile = await db.get_user_profile(uid)
    return {
        "ok": True,
        "tree": team_tree,
        "profile": profile,
        "referral_bonus_applied": referral_bonus,
    }


@app.post("/api/daily-claim")
async def claim_daily_advent_endpoint(req: DailyClaimRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    ok, msg, reward, profile = await db.claim_daily_advent(uid)
    if not ok:
        raise HTTPException(400, msg)
    return {
        "ok": True,
        "message": msg,
        "reward": reward,
        "profile": profile,
    }


@app.post("/api/lootbox")
async def open_lootbox_endpoint(req: LootboxRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    ok, msg, prize, profile = await db.open_lootbox(uid)
    if not ok:
        raise HTTPException(400, msg)
    return {
        "ok": True,
        "message": msg,
        "prize": prize,
        "profile": profile,
    }


@app.post("/api/tree-style")
async def update_tree_style_endpoint(req: TreeStyleRequest):
    await _ensure_user_from_req(req.init_data, req.user)
    cid = normalize_chat_id(req.chat_id)
    bg = req.bg_theme if req.bg_theme in TREE_THEMES["backgrounds"] else "aurora"
    garland = req.garland_style if req.garland_style in TREE_THEMES["garlands"] else "classic"
    topper = req.topper_type if req.topper_type in TREE_THEMES["toppers"] else "star"
    tree = await db.update_tree_style(cid, bg_theme=bg, garland_style=garland, topper_type=topper)
    return {
        "ok": True,
        "tree": tree,
        "message": "Стиль ёлки обновлён! 🎨",
    }


@app.post("/api/sync")
async def sync_backup_endpoint(req: SyncBackupRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    cid = normalize_chat_id(req.chat_id)
    tree = await db.get_tree(cid)
    if not tree:
        default_title = "Общая новогодняя ёлка" if cid == 1 else f"Командная ёлка #{abs(cid) % 10000}"
        await db.get_or_create_tree(cid, default_title, is_team=1 if cid < 0 else 0)
    await db.sync_backup(
        chat_id=cid,
        user_id=uid,
        coins=req.coins,
        coin_turnover=req.coin_turnover,
        click_power=req.click_power,
        inventory=req.inventory,
        decorations=req.decorations,
    )
    profile = await db.get_user_profile(uid)
    decorations = await db.get_decorations(cid)
    stats = await db.get_stats(cid)
    leaderboard = await db.get_global_leaderboard()
    return {
        "ok": True,
        "profile": profile,
        "decorations": decorations,
        "stats": stats,
        "leaderboard": leaderboard,
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


@app.post("/api/donate/gram-order")
async def create_gram_order(req: DonateOrderRequest):
    """Создаёт заказ в GRAM для последующей автоматической выдачи сразу после оплаты."""
    uid = await _ensure_user_from_req(req.init_data, req.user)
    pack = DONATE_PACKS.get(req.pack_id)
    if not pack:
        raise HTTPException(404, "Набор не найден")
    order_id = await db.create_order(uid, req.pack_id, "GRAM", int(pack["gram_price"]))
    memo = f"NYTREE_{order_id}_{uid}"
    return {
        "ok": True,
        "order_id": order_id,
        "memo": memo,
        "gram_price": pack["gram_price"],
        "wallet": GRAM_WALLET_ADDRESS,
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
        "message": f"Набор «{pack['title']}» автоматически выдан! 🎉",
        "profile": profile,
    }


@app.post("/api/decorate")
async def decorate(req: DecorateRequest):
    cid = normalize_chat_id(req.chat_id)
    tree = await db.get_tree(cid)
    if not tree:
        default_title = "Общая новогодняя ёлка" if cid == 1 else f"Командная ёлка #{abs(cid) % 10000}"
        tree = await db.get_or_create_tree(cid, default_title, is_team=1 if cid < 0 else 0)
    if tree.get("is_finished"):
        raise HTTPException(400, "Ёлка уже подведена! Ивент завершён 🎉")
    if req.ornament_type not in ORNAMENTS:
        raise HTTPException(400, "Неизвестная игрушка")
    if req.color not in ORNAMENTS[req.ornament_type]["colors"]:
        raise HTTPException(400, "Неизвестный цвет")
    if not is_inside_tree(req.x, req.y):
        raise HTTPException(400, "Вешай игрушки прямо на веточки ёлки! 🎄")

    uid = await _ensure_user_from_req(req.init_data, req.user)
    has_item = await db.consume_inventory_item(uid, req.ornament_type)
    if not has_item:
        info = ORNAMENTS[req.ornament_type]
        raise HTTPException(
            400,
            f"В инвентаре нет «{info['emoji']} {info['name']}»! Купи в Магазине за {info['price']} 🪙",
        )
    dec_id = await db.add_decoration(
        cid, uid, req.ornament_type, req.color, req.x, req.y, wish_text=req.wish_text
    )
    profile = await db.get_user_profile(uid)
    return {"id": dec_id, "ok": True, "profile": profile, "wish_text": (req.wish_text or "").strip()[:140]}


@app.post("/api/move")
async def move_decoration(req: MoveRequest):
    cx, cy = clamp_to_tree(req.x, req.y)
    uid = await _ensure_user_from_req(req.init_data, req.user)
    ok = await db.move_decoration(req.decoration_id, uid, cx, cy)
    if not ok:
        raise HTTPException(403, "Можно перемещать только свои игрушки")
    return {"ok": True, "x": cx, "y": cy}


@app.post("/api/delete")
async def delete_decoration(req: DeleteRequest):
    uid = await _ensure_user_from_req(req.init_data, req.user)
    deleted = await db.delete_decoration(req.decoration_id, uid)
    if not deleted:
        raise HTTPException(403, "Можно снимать только свои игрушки")
    await db.return_inventory_item(uid, deleted["ornament_type"])
    profile = await db.get_user_profile(uid)
    return {"ok": True, "profile": profile}


@app.get("/api/final-image/{chat_id}")
async def final_image(chat_id: int):
    cid = normalize_chat_id(chat_id)
    tree = await db.get_tree(cid)
    if not tree:
        raise HTTPException(404, "Tree not found")
    decorations = await db.get_decorations(cid)
    png = generate_tree_image(decorations, title=f"Ёлка: {tree.get('chat_title') or cid}")
    return Response(content=png, media_type="image/png")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
