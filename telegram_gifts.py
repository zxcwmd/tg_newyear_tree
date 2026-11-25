"""Telegram-подарки игрока (regular и unique/NFT) через Bot API.

Зачем: игрок должен прикрепить к ёлке СВОЙ подарок из Telegram, а не только
внутриигровой предмет. Bot API (9.3+) умеет `getUserGifts`, поэтому бот может
получить список подарков пользователя — и regular, и unique (NFT из TON).

Документация: https://core.telegram.org/bots/api#getusergifts
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from config import (
    BOT_TOKEN,
    GIFT_EMOJI,
    TELEGRAM_API_BASE,
    TELEGRAM_GIFTS_ENABLED,
    TELEGRAM_GIFTS_LIMIT,
)

log = logging.getLogger(__name__)


class TelegramGiftsUnavailable(Exception):
    """Bot API недоступен (нет токена, сеть, ошибка Telegram)."""


def _emoji_for(slug: str, is_unique: bool, sticker_emoji: str = "") -> str:
    base = (slug or "").lower()
    for key, emoji in GIFT_EMOJI.items():
        if key in base:
            return emoji
    if sticker_emoji:
        return sticker_emoji
    return "💎" if is_unique else "🎁"


def normalize_gift(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Приводит OwnedGift (regular/unique) к плоскому виду для UI и открытки."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type")
    if kind not in ("regular", "unique"):
        return None
    gift = raw.get("gift") or {}
    if not isinstance(gift, dict):
        return None

    is_unique = kind == "unique"
    if is_unique:
        # UniqueGift: name, number, model.name, symbol.name, backdrop...
        name = gift.get("name") or ""
        slug = gift.get("base_name") or name or "unique gift"
        number = gift.get("number")
        model = (gift.get("model") or {}).get("name") or ""
        title = name or (f"{slug} #{number}" if number else slug)
        subtitle = f"№{number} · NFT" if number else "Telegram NFT"
        if model and model.lower() not in title.lower():
            subtitle = f"{subtitle} · {model}"
    else:
        slug = gift.get("id") or "gift"
        title = slug.replace("_", " ").title()
        subtitle = "Telegram-подарок"
        number = raw.get("unique_gift_number")

    sender = raw.get("sender_user") or {}
    sender_id = sender.get("id") if isinstance(sender, dict) else None

    # Ключ подарка. Telegram отдаёт owned_gift_id только бизнес-аккаунтам,
    # поэтому для обычных игроков собираем стабильный ключ:
    #   unique  → имя NFT (глобально уникально, оно же в ссылке t.me/nft/<name>)
    #   regular → gift.id + дата отправки + отправитель
    owned_gift_id = str(raw.get("owned_gift_id") or "")
    if not owned_gift_id:
        if is_unique and gift.get("name"):
            owned_gift_id = f"nft:{gift['name']}"
        else:
            owned_gift_id = f"reg:{gift.get('id') or 'gift'}:{raw.get('send_date') or 0}:{sender_id or 0}"
    if len(owned_gift_id) > 128:
        owned_gift_id = owned_gift_id[:128]

    return {
        "owned_gift_id": owned_gift_id,
        "slug": str(slug)[:64],
        "kind": kind,
        "is_unique": is_unique,
        "is_nft": is_unique,  # unique = настоящий NFT в TON
        "title": str(title)[:64],
        "subtitle": str(subtitle)[:64],
        "emoji": _emoji_for(
            str(slug), is_unique, str((gift.get("sticker") or {}).get("emoji") or "")
        ),
        "number": number,
        "gift_id": str(gift.get("id") or ""),
        "model": str((gift.get("model") or {}).get("name") or ""),
        "symbol": str((gift.get("symbol") or {}).get("name") or ""),
        "backdrop": str((gift.get("backdrop") or {}).get("name") or ""),
        "is_burned": bool(gift.get("is_burned")),
        "is_from_blockchain": bool(gift.get("is_from_blockchain")),
        "from_stars": bool(gift.get("is_premium")),
        "can_be_upgraded": bool(raw.get("can_be_upgraded")),
        "was_refunded": bool(raw.get("was_refunded")),
        "send_date": raw.get("send_date") or 0,
        "text": str(raw.get("text") or "")[:120],
        "sender_name": (
            sender.get("first_name") or sender.get("username") or "Telegram"
        ) if isinstance(sender, dict) else "Telegram",
        "sticker_emoji": ((gift.get("sticker") or {}).get("emoji") or "") if isinstance(gift, dict) else "",
    }


async def _call_bot_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not BOT_TOKEN:
        raise TelegramGiftsUnavailable("BOT_TOKEN не задан")
    url = f"{TELEGRAM_API_BASE}/bot{BOT_TOKEN}/{method}"
    timeout = aiohttp.ClientTimeout(total=12)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json(content_type=None)
    except Exception as e:  # сеть, DNS, таймауты
        raise TelegramGiftsUnavailable(f"Telegram API недоступен: {e}") from e

    if not isinstance(data, dict) or not data.get("ok"):
        desc = (data or {}).get("description") if isinstance(data, dict) else None
        raise TelegramGiftsUnavailable(desc or "Telegram API вернул ошибку")
    return data.get("result") or {}


async def fetch_user_gifts(user_id: int, limit: int | None = None) -> list[dict[str, Any]]:
    """Список подарков пользователя (включая unique/NFT), нормализованный.

    Бросает TelegramGiftsUnavailable, если Bot API недоступен.
    """
    if not TELEGRAM_GIFTS_ENABLED:
        raise TelegramGiftsUnavailable("Прикрепление Telegram-подарков выключено")
    if not user_id or int(user_id) <= 0:
        raise TelegramGiftsUnavailable("Некорректный user_id")

    lim = max(1, min(100, int(limit or TELEGRAM_GIFTS_LIMIT)))
    result = await _call_bot_api("getUserGifts", {"user_id": int(user_id), "limit": lim})
    raw_gifts = result.get("gifts") if isinstance(result, dict) else None
    if not isinstance(raw_gifts, list):
        return []

    out: list[dict[str, Any]] = []
    for raw in raw_gifts:
        norm = normalize_gift(raw)
        if norm and not norm["was_refunded"] and not norm["is_burned"]:
            out.append(norm)
    return out


async def fetch_user_gift(user_id: int, owned_gift_id: str) -> dict[str, Any] | None:
    """Ищет конкретный подарок игрока по owned_gift_id (проверка владения)."""
    gifts = await fetch_user_gifts(user_id, limit=100)
    for gift in gifts:
        if gift["owned_gift_id"] == str(owned_gift_id):
            return gift
    return None
