"""Telegram-бот новогодней ёлки."""
import asyncio
import logging
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN, WEBAPP_URL, TIMEZONE, GREETINGS
import database as db
from tree_image import generate_tree_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

dp = Dispatcher()


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


@dp.message(CommandStart())
async def cmd_start(message: Message):
    chat = message.chat
    if chat.type == "private":
        await message.answer(
            "🎄 Привет! Я — бот новогодней ёлки!\n\n"
            "Добавь меня в групповой чат, и мы вместе нарядим ёлку до 1 января. "
            "1 января я пришлю в чат финальную ёлку с поздравлением и итогами 🎉\n\n"
            "Команды:\n"
            "/start — создать ёлку в чате\n"
            "/tree — показать текущую ёлку\n"
            "/stats — кто сколько повесил\n"
            "/help — помощь",
            reply_markup=webapp_button(chat.id, "🎄 Попробовать демо-ёлку"),
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
        "Нажимайте кнопку ниже, выбирайте игрушку и кликайте по ёлке 👇\n\n"
        "1 января я пришлю сюда финальную ёлку с поздравлением и итогами 🎉",
        reply_markup=webapp_button(chat.id),
    )


@dp.message(Command("tree"))
async def cmd_tree(message: Message):
    chat = message.chat
    if chat.type == "private":
        await message.answer("Эта команда работает в групповом чате 🙂 Добавь меня в чат!")
        return
    tree = await db.get_tree(chat.id)
    if not tree:
        await message.answer("Ёлка ещё не создана. Напиши /start 🎄")
        return
    decorations = await db.get_decorations(chat.id)
    png = generate_tree_image(decorations, title=f"Ёлка: {chat.title or ''}")
    photo = BufferedInputFile(png, filename="tree.png")
    await message.answer_photo(
        photo,
        caption=f"🎄 Ёлка чата «{chat.title}» — игрушек: <b>{len(decorations)}</b>",
        reply_markup=webapp_button(chat.id),
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    chat = message.chat
    if chat.type == "private":
        await message.answer("Команда для группового чата 🙂")
        return
    tree = await db.get_tree(chat.id)
    if not tree:
        await message.answer("Ёлка ещё не создана. Напиши /start 🎄")
        return
    stats = await db.get_stats(chat.id)
    decorations = await db.get_decorations(chat.id)
    await message.answer(
        f"📊 <b>Итоги по ёлке «{chat.title}»</b>\n\n"
        f"Всего игрушек: <b>{len(decorations)}</b>\n\n"
        f"{format_stats(stats)}",
        reply_markup=webapp_button(chat.id, "🎄 Украсить ещё"),
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🎄 <b>Как украсить ёлку?</b>\n\n"
        "1. Нажми кнопку «🎄 Украсить ёлку»\n"
        "2. Выбери игрушку и цвет внизу экрана\n"
        "3. Нажми на ёлку, чтобы повесить игрушку (свои игрушки можно перетаскивать)\n"
        "4. Чтобы снять свою игрушку — просто нажми на неё\n\n"
        "Команды:\n"
        "/start — создать/открыть ёлку\n"
        "/tree — показать текущую ёлку картинкой\n"
        "/stats — статистика участников\n"
        "/finish — подвести итоги досрочно (для теста)"
    )


@dp.message(Command("finish"))
async def cmd_finish(message: Message, bot: Bot):
    """Досрочный финал — для теста/ручного запуска."""
    chat = message.chat
    if chat.type == "private":
        await message.answer("Только в групповом чате 🙂")
        return
    tree = await db.get_tree(chat.id)
    if not tree:
        await message.answer("Ёлка ещё не создана. Напиши /start 🎄")
        return
    if tree.get("is_finished"):
        await message.answer("Итоги уже подведены 🎉")
        return
    await finish_tree(bot, chat.id, chat.title or "")


async def finish_tree(bot: Bot, chat_id: int, chat_title: str):
    """Генерирует финал и шлёт в чат."""
    await db.mark_tree_finished(chat_id)
    decorations = await db.get_decorations(chat_id)
    stats = await db.get_stats(chat_id)
    png = generate_tree_image(decorations, title=f"Ёлка: {chat_title}")
    greeting = random.choice(GREETINGS)
    caption = (
        f"{greeting}\n\n"
        f"🎄 Ёлка чата «{chat_title}» — всего игрушек: <b>{len(decorations)}</b>\n\n"
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
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    sched_task = asyncio.create_task(scheduler(bot))
    log.info("Bot started. WebApp URL: %s", WEBAPP_URL)
    try:
        await dp.start_polling(bot, handle_signals=handle_signals)
    finally:
        sched_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
