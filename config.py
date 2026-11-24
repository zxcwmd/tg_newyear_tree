"""Конфигурация приложения."""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://localhost:8000").strip().rstrip("/")

# Поддержка переменных окружения Alwaysdata (IP / PORT / ALWAYSDATA_HTTPD_*), Render и локального запуска
WEBAPP_HOST = os.getenv(
    "IP",
    os.getenv("ALWAYSDATA_HTTPD_IP", os.getenv("WEBAPP_HOST", "0.0.0.0")),
)
WEBAPP_PORT = int(
    os.getenv(
        "PORT",
        os.getenv("ALWAYSDATA_HTTPD_PORT", os.getenv("WEBAPP_PORT", "8000")),
    )
)

_raw_db_path = os.getenv("DATABASE_PATH", "data.db")
DATABASE_PATH = (
    _raw_db_path
    if os.path.isabs(_raw_db_path)
    else os.path.join(BASE_DIR, _raw_db_path)
)

TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

# Типы игрушек и их цвета
ORNAMENTS = {
    "ball": {
        "name": "Шар",
        "emoji": "🔴",
        "colors": {
            "red": "#e63946",
            "gold": "#f4a261",
            "blue": "#4361ee",
            "green": "#2a9d8f",
            "pink": "#ff6b9d",
            "silver": "#adb5bd",
        },
    },
    "star": {
        "name": "Звезда",
        "emoji": "⭐",
        "colors": {
            "gold": "#ffd60a",
            "silver": "#e9ecef",
        },
    },
    "snowflake": {
        "name": "Снежинка",
        "emoji": "❄️",
        "colors": {
            "white": "#ffffff",
            "blue": "#a8dadc",
        },
    },
    "gift": {
        "name": "Подарок",
        "emoji": "🎁",
        "colors": {
            "red": "#e63946",
            "blue": "#4361ee",
            "green": "#2a9d8f",
            "purple": "#9d4edd",
        },
    },
    "bell": {
        "name": "Колокольчик",
        "emoji": "🔔",
        "colors": {
            "gold": "#ffd60a",
        },
    },
    "candy": {
        "name": "Конфета",
        "emoji": "🍬",
        "colors": {
            "red": "#e63946",
            "pink": "#ff6b9d",
        },
    },
}

# Поздравления для финала
GREETINGS = [
    "🎉 С Новым годом! Ваша ёлка наряжена — посмотрите, какая красота получилась!",
    "🎄 С праздником! Друзья вместе создали настоящую новогоднюю сказку!",
    "✨ С Новым годом! Пусть эта ёлка принесёт в ваш чат тепло, смех и удачу!",
    "🎊 Ура! Ёлка готова! Желаем вам в новом году ярких моментов и хороших друзей!",
]
