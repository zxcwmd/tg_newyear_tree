"""Запуск бота + Mini App одним процессом."""
import asyncio
import logging
import uvicorn

from config import BOT_TOKEN, WEBAPP_PORT
import database as db
import bot as bot_module
from webapp.app import app

log = logging.getLogger(__name__)


async def run_bot_safely():
    try:
        await bot_module.main()
    except Exception as e:
        log.warning(
            "Telegram Bot polling не удалось запустить в текущем окружении (%s). "
            "Mini App веб-сервер продолжает работу.",
            e,
        )


async def main():
    await db.init_db()

    config = uvicorn.Config(app, host="0.0.0.0", port=WEBAPP_PORT, log_level="info")
    server = uvicorn.Server(config)
    web_task = asyncio.create_task(server.serve())

    print(f"✅ Mini App сервер запущен: http://0.0.0.0:{WEBAPP_PORT}")

    if BOT_TOKEN:
        bot_task = asyncio.create_task(run_bot_safely())
        print("✅ Telegram Bot токен загружен, запуск polling...")
        await asyncio.gather(web_task, bot_task)
    else:
        print("ℹ️  BOT_TOKEN не задан в .env — запущен только Mini App веб-сервер (режим превью).")
        await web_task


if __name__ == "__main__":
    asyncio.run(main())
