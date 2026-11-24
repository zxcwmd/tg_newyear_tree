"""Запуск Mini App + Telegram-бота одним процессом (в т.ч. для Alwaysdata User program)."""
import uvicorn

from config import WEBAPP_HOST, WEBAPP_PORT
from webapp.app import app


def main():
    print(f"✅ Запуск сервера на {WEBAPP_HOST}:{WEBAPP_PORT}")
    uvicorn.run(app, host=WEBAPP_HOST, port=WEBAPP_PORT, log_level="info")


if __name__ == "__main__":
    main()
