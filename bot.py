"""Telegram-бот новогодней ёлки (поддержка Mini App, Telegram Stars и финала 1 января)."""
import asyncio
import logging
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN, DONATE_PACKS, GREETINGS, TIMEZONE, WEBAPP_URL
import database as db
from tree_image import generate_tree_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

dp = Dispatcher()
_active_bot: Bot | None = None


def get_bot_instance() -> Bot | None:
    global _active_bot
    if _active_bot is None and BOT_TOKEN:
        _active_bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    return _active_bot


async def create_stars_invoice_link(user_id: int, pack_id: str, order_id: int) -> str | None:
    """Создаёт ссылку на инвойс в Telegram Stars (XTR) для оплаты внутри Mini App."""
    pack = DONATE_PACKS.get(pack_id)
    bot = get_bot_instance()
    if not pack or not bot:
        return None
    payload = f"stars:{user_id}:{pack_id}:{order_id}"
    link = await bot.create_invoice_link(
        title=f"{pack['emoji']} {pack['title']}",
        description=pack["description"],
        payload=payload,
        provider_token="",  # Для Telegram Stars (XTR) provider_token всегда пустая строка
        currency="XTR",
        prices=[LabeledPrice(label=pack["title"], amount=int(pack["stars_price"]))],
    )
    return link


def webapp_button(chat_id: int, text: str = "🎄 Украсить ёлку") -> InlineKeyboardMarkup:
    url = f"{WEBAPP_URL}/?chat_id={chat_id}"
    kb = InlineKeyboardBuilder()
    kb.button(text=text, web_app=WebAppInfo(url=url))
    return kb.as_markup()


def format_stats(stats: list[dict]) -> str:
    if not stats:
        return "Пока никто не украшал ёлку 🎄"
    lines = []
    medals = ["🥇", "🥈", "🥉"]
    for i, s in enumerate(stats[:10]):
        name = f"@{s['username']}" if s.get("username") else (s.get("first_name") or "Участник")
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} {name} — <b>{s['count']}</b> игрушек")
    return "\n".join(lines)


@dp.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@dp.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload if payment else ""
    parts = payload.split(":")
    if len(parts) == 4 and parts[0] == "stars":
        _, uid_str, pack_id, order_id_str = parts
        uid = int(uid_str)
        order_id = int(order_id_str)
        await db.complete_order_or_pack(uid, pack_id, order_id)
        pack = DONATE_PACKS.get(pack_id, {})
        await message.answer(
            f"🎉 Оплата в ⭐️ Telegram Stars прошла успешно!\n"
            f"Набор <b>{pack.get('title', pack_id)}</b> зачислен на твой аккаунт!"
        )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    chat = message.chat
    if message.from_user:
        await db.upsert_user(
            message.from_user.id,
            username=message.from_user.username or "",
            first_name=message.from_user.first_name or "Участник",
            last_name=message.from_user.last_name or "",
        )
    if chat.type == "private":
        await db.get_or_create_tree(1, "Общая новогодняя ёлка")
        await message.answer(
            "🎄 Привет! Я — бот новогодней ёлки!\n\n"
            "• Фарми монеты в кликере 🪙\n"
            "• Покупай игрушки в магазине 🛍 или за ⭐️ Stars / 💎 GRAM\n"
            "• Украшай общую ёлку вместе с другими игроками и друзьями до 1 января!\n\n"
            "Добавь меня в групповой чат или открой общую ёлку кнопкой ниже 👇\n\n"
            "Команды:\n"
            "/start — открыть ёлку\n"
            "/tree — показать текущую ёлку картинкой\n"
            "/stats — рейтинг игроков\n"
            "/help — помощь",
            reply_markup=webapp_button(1, "🎄 Открыть Новогоднюю ёлку"),
        )
        return

    tree = await db.get_or_create_tree(chat.id, chat.title or "")
    if tree.get("is_finished"):
        await message.answer(
            "🎉 Ивент уже завершён! Ёлка подведена. С Новым годом!",
            reply_markup=webapp_button(chat.id, "🎄 Посмотреть ёлку"),
        )
        return

    await message.answer(
        f"🎄 <b>Новогодняя ёлка чата «{chat.title}» создана!</b>\n\n"
        "Украшайте её вместе с друзьями до 1 января! "
        "Фармите монеты в кликере 🪙, покупайте украшения и вешайте на ёлку 👇\n\n"
        "1 января я пришлю сюда финальную ёлку с поздравлением и итогами 🎉",
        reply_markup=webapp_button(chat.id),
    )


@dp.message(Command("tree"))
async def cmd_tree(message: Message):
    chat = message.chat
    target_id = 1 if chat.type == "private" else chat.id
    target_title = "Общая новогодняя ёлка" if chat.type == "private" else (chat.title or "Новогодняя ёлка")
    tree = await db.get_tree(target_id)
    if not tree:
        tree = await db.get_or_create_tree(target_id, target_title)
    decorations = await db.get_decorations(target_id)
    png = generate_tree_image(decorations, title=f"Ёлка: {target_title}")
    photo = BufferedInputFile(png, filename="tree.png")
    await message.answer_photo(
        photo,
        caption=f"🎄 {target_title} — игрушек на ёлке: <b>{len(decorations)}</b>",
        reply_markup=webapp_button(target_id),
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    chat = message.chat
    target_id = 1 if chat.type == "private" else chat.id
    target_title = "Общая новогодняя ёлка" if chat.type == "private" else (chat.title or "Чат")
    tree = await db.get_tree(target_id)
    if not tree:
        await message.answer("Ёлка ещё не создана. Напиши /start 🎄")
        return
    stats = await db.get_stats(target_id)
    decorations = await db.get_decorations(target_id)
    await message.answer(
        f"📊 <b>Итоги по ёлке «{target_title}»</b>\n\n"
        f"Всего игрушек: <b>{len(decorations)}</b>\n\n"
        f"{format_stats(stats)}",
        reply_markup=webapp_button(target_id, "🎄 Украсить ещё"),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🎄 <b>Как устроена игра?</b>\n\n"
        "1. Открой приложение кнопкой «🎄 Украсить ёлку»\n"
        "2. Во вкладке <b>«🪙 Кликер»</b> фарми монеты и прокачивай силу клика\n"
        "3. Во вкладке <b>«🛍 Магазин»</b> покупай игрушки за монеты (а в <b>«💎 Донат»</b> — наборы за ⭐️ Stars или 💎 GRAM)\n"
        "4. Во вкладке <b>«🎄 Ёлка»</b> выбери купленную игрушку и цвет, затем нажми на ёлку, чтобы повесить её!\n"
        "5. Свои игрушки можно перетаскивать по ёлке или снимать обратно в инвентарь.\n\n"
        "Команды:\n"
        "/start — открыть ёлку\n"
        "/tree — прислать картинку ёлки в чат\n"
        "/stats — рейтинг участников\n"
        "/finish — подвести итоги досрочно"
    )


@dp.message(Command("finish"))
async def cmd_finish(message: Message, bot: Bot):
    """Досрочный финал — для теста/ручного запуска."""
    chat = message.chat
    tree = await db.get_tree(chat.id)
    if not tree:
        await message.answer("Ёлка ещё не создана. Напиши /start 🎄")
        return
    if tree.get("is_finished"):
        await message.answer("Итоги уже подведены 🎉")
        return
    await finish_tree(bot, chat.id, chat.title or "Новогодняя ёлка")


async def finish_tree(bot: Bot, chat_id: int, chat_title: str):
    """Генерирует финал и шлёт в чат."""
    await db.mark_tree_finished(chat_id)
    decorations = await db.get_decorations(chat_id)
    stats = await db.get_stats(chat_id)
    png = generate_tree_image(decorations, title=f"Ёлка: {chat_title}")
    greeting = random.choice(GREETINGS)
    caption = (
        f"{greeting}\n\n"
        f"🎄 Ёлка «{chat_title}» — всего игрушек: <b>{len(decorations)}</b>\n\n"
        f"🏆 <b>Итоги:</b>\n{format_stats(stats)}\n\n"
        f"С Новым годом! 🎉"
    )
    photo = BufferedInputFile(png, filename="final_tree.png")
    await bot.send_photo(chat_id, photo, caption=caption)


async def scheduler(bot: Bot):
    """Проверяет каждую минуту: не наступило ли 1 января."""
    tz = ZoneInfo(TIMEZONE)
    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.now(tz)
            if now.month == 1 and now.day == 1:
                trees = await db.get_unfinished_trees()
                for t in trees:
                    log.info("Finishing tree for chat %s", t["chat_id"])
                    try:
                        await finish_tree(bot, t["chat_id"], t.get("chat_title") or "")
                    except Exception as e:
                        log.exception("Failed to finish tree %s: %s", t["chat_id"], e)
        except Exception as e:
            log.exception("Scheduler error: %s", e)


async def main(handle_signals: bool = True):
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN не задан! Создай .env по образцу .env.example")
    await db.init_db()
    bot = get_bot_instance()
    sched_task = asyncio.create_task(scheduler(bot))
    log.info("Bot started. WebApp URL: %s", WEBAPP_URL)
    try:
        await dp.start_polling(bot, handle_signals=handle_signals)
    finally:
        sched_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
