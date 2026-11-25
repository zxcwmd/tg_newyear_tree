"""Конфигурация приложения."""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()


def _detect_webapp_url() -> str:
    explicit = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
    if explicit and explicit != "https://your-domain.example.com":
        return explicit
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if render_url:
        return render_url
    koyeb_domain = os.getenv("KOYEB_PUBLIC_DOMAIN", "").strip().rstrip("/")
    if koyeb_domain:
        return f"https://{koyeb_domain}"
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip().rstrip("/")
    if railway_domain:
        return f"https://{railway_domain}"
    return "http://localhost:8000"


WEBAPP_URL = _detect_webapp_url()

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

# --- Идентификаторы ёлок -------------------------------------------------
# Личная ёлка игрока: chat_id = -(PERSONAL_TREE_BASE + user_id).
# Диапазон не пересекается ни с групповыми чатами (~ -1e12), ни с командами (~ -9e8),
# и остаётся безопасным целым для JavaScript (|id| < 2^53).
PERSONAL_TREE_BASE = 4_000_000_000_000_000
# Номер «общей» ёлки из старых версий — теперь это «моя личная ёлка»
LEGACY_SHARED_TREE_ID = 1


def personal_tree_id(user_id: int) -> int:
    """Возвращает chat_id личной ёлки игрока."""
    return -(PERSONAL_TREE_BASE + int(user_id))


def is_personal_tree_id(chat_id: int) -> bool:
    return int(chat_id) <= -PERSONAL_TREE_BASE


def personal_tree_owner(chat_id: int) -> int:
    """Восстанавливает user_id владельца по id личной ёлки."""
    return abs(int(chat_id)) - PERSONAL_TREE_BASE

# Типы игрушек, их цвета и цена в монетах
ORNAMENTS = {
    "ball": {
        "name": "Шар",
        "emoji": "🔴",
        "price": 700,
        "colors": {
            "red": "#e63946",
            "gold": "#f4a261",
            "blue": "#4361ee",
            "green": "#2a9d8f",
            "pink": "#ff6b9d",
            "silver": "#adb5bd",
        },
    },
    "candy": {
        "name": "Конфета",
        "emoji": "🍬",
        "price": 950,
        "colors": {
            "red": "#e63946",
            "pink": "#ff6b9d",
        },
    },
    "snowflake": {
        "name": "Снежинка",
        "emoji": "❄️",
        "price": 1300,
        "colors": {
            "white": "#ffffff",
            "blue": "#a8dadc",
        },
    },
    "bell": {
        "name": "Колокольчик",
        "emoji": "🔔",
        "price": 1800,
        "colors": {
            "gold": "#ffd60a",
        },
    },
    "gift": {
        "name": "Подарок",
        "emoji": "🎁",
        "price": 2500,
        "colors": {
            "red": "#e63946",
            "blue": "#4361ee",
            "green": "#2a9d8f",
            "purple": "#9d4edd",
        },
    },
    "star": {
        "name": "Звезда",
        "emoji": "⭐",
        "price": 4000,
        "colors": {
            "gold": "#ffd60a",
            "silver": "#e9ecef",
        },
    },
    "angel": {
        "name": "Ангелочек",
        "emoji": "👼",
        "price": 6500,
        "colors": {
            "gold": "#fde047",
            "white": "#ffffff",
            "pink": "#f472b6",
        },
    },
    "crystal": {
        "name": "Кристалл",
        "emoji": "💎",
        "price": 9000,
        "colors": {
            "cyan": "#38bdf8",
            "purple": "#c084fc",
            "gold": "#facc15",
        },
    },
}

# Темы оформления ёлки (фон, гирлянда, макушка)
TREE_THEMES = {
    "backgrounds": {
        "aurora": {"name": "🌌 Северное сияние", "top": "#050b1a", "mid": "#0d1b3a", "bot": "#172a4f"},
        "fireplace": {"name": "🔥 Уютный камин", "top": "#2a0a0a", "mid": "#451a03", "bot": "#7c2d12"},
        "forest": {"name": "🌲 Изумрудный лес", "top": "#022c22", "mid": "#064e3b", "bot": "#0f766e"},
        "cyber": {"name": "🔮 Неоновая ночь", "top": "#1e1b4b", "mid": "#3b0764", "bot": "#701a75"},
    },
    "garlands": {
        "classic": {"name": "🌈 Разноцветная", "colors": ["#fde047", "#f43f5e", "#38bdf8", "#34d399", "#c084fc"]},
        "gold": {"name": "✨ Тёплое золото", "colors": ["#fef08a", "#fde047", "#f59e0b", "#fffbeb"]},
        "ice": {"name": "❄️ Ледяной неон", "colors": ["#e0f2fe", "#38bdf8", "#818cf8", "#22d3ee"]},
        "ruby": {"name": "❤️ Рубин и изумруд", "colors": ["#f43f5e", "#10b981", "#fde047", "#fb7185"]},
    },
    "toppers": {
        "star": {"name": "⭐ Вифлеемская звезда", "emoji": "⭐"},
        "crown": {"name": "👑 Золотая корона", "emoji": "👑"},
        "angel": {"name": "👼 Рождественский ангел", "emoji": "👼"},
        "snowflake": {"name": "❄️ Хрустальная снежинка", "emoji": "❄️"},
    },
}

# Сюрприз-бокс: фиксированная цена и публичный набор призов (показываем в слотах)
LOOTBOX_PRICE = 100
LOOTBOX_POOL = [
    {"item": "gift", "coins": 40, "weight": 26, "label": "🎁 Подарок + 40 🪙"},
    {"item": "star", "coins": 50, "weight": 24, "label": "⭐ Звезда + 50 🪙"},
    {"item": "angel", "coins": 75, "weight": 20, "label": "👼 Ангелочек + 75 🪙"},
    {"item": "crystal", "coins": 100, "weight": 15, "label": "💎 Кристалл + 100 🪙"},
    {"item": "bell", "coins": 300, "weight": 15, "label": "🔔 Джекпот: Колокольчик + 300 🪙"},
]

# Донат-наборы за Telegram Stars (XTR). Оплата в GRAM отключена.
DONATE_PACKS = {
    "coins_small": {
        "id": "coins_small",
        "title": "Горсть монет",
        "emoji": "🪙",
        "description": "+500 новогодних монет для покупки игрушек",
        "stars_price": 15,
        "rewards": {
            "coins": 500,
            "items": {},
            "click_power_bonus": 0,
        },
    },
    "coins_medium": {
        "id": "coins_medium",
        "title": "Мешок монет",
        "emoji": "💰",
        "description": "+2 500 новогодних монет и +1 к силе клика",
        "stars_price": 50,
        "rewards": {
            "coins": 2500,
            "items": {},
            "click_power_bonus": 1,
        },
    },
    "coins_mega": {
        "id": "coins_mega",
        "title": "Сундук Деда Мороза",
        "emoji": "💎",
        "description": "+10 000 монет и +3 к силе клика",
        "stars_price": 150,
        "rewards": {
            "coins": 10000,
            "items": {},
            "click_power_bonus": 3,
        },
    },
    "toys_pack": {
        "id": "toys_pack",
        "title": "Праздничный набор игрушек",
        "emoji": "🎁",
        "description": "3 Шара, 2 Конфеты, 2 Снежинки, 2 Подарка и 1 Звезда",
        "stars_price": 35,
        "rewards": {
            "coins": 100,
            "items": {
                "ball": 3,
                "candy": 2,
                "snowflake": 2,
                "gift": 2,
                "star": 1,
            },
            "click_power_bonus": 0,
        },
    },
    "royal_pack": {
        "id": "royal_pack",
        "title": "Королевский набор",
        "emoji": "👑",
        "description": "По 5 игрушек каждого вида + 3 000 монет + Сила клика +2",
        "stars_price": 100,
        "rewards": {
            "coins": 3000,
            "items": {
                "ball": 5,
                "candy": 5,
                "snowflake": 5,
                "bell": 5,
                "gift": 5,
                "star": 5,
            },
            "click_power_bonus": 2,
        },
    },
}

# --- NFT-подарки -------------------------------------------------------------
# Локальный реестр уже работает. Чтобы включить настоящий минт (TON/Telegram-подарки),
# заполните параметры ниже и реализуйте mint_gift() в database/webapp (см. NFT_INTEGRATION.md).
NFT_MINT_ENABLED = os.getenv("NFT_MINT_ENABLED", "0").strip() in ("1", "true", "yes")
NFT_COLLECTION_ADDRESS = os.getenv("NFT_COLLECTION_ADDRESS", "").strip()
TON_API_KEY = os.getenv("TON_API_KEY", "").strip()

# Прикрепление собственных Telegram-подарков (regular + unique/NFT) через Bot API getUserGifts.
TELEGRAM_GIFTS_ENABLED = os.getenv("TELEGRAM_GIFTS_ENABLED", "1").strip() in ("1", "true", "yes")
# Сколько последних подарков игрока запрашивать и показывать
TELEGRAM_GIFTS_LIMIT = int(os.getenv("TELEGRAM_GIFTS_LIMIT", "24"))
# Публичный адрес Telegram Bot API (для тестов/прокси)
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")

# Эмодзи для популярных подарков Telegram (slug -> эмодзи).
GIFT_EMOJI = {
    "heart": "❤️", "bear": "🐻", "rose": "🌹", "cake": "🎂", "bouquet": "💐",
    "rocket": "🚀", "trophy": "🏆", "ring": "💍", "diamond": "💎", "star": "⭐",
    "chocolate": "🍫", "teddy": "🧸", "snowman": "⛄", "santa": "🎅", "newyear": "🎄",
    "cup": "🏆", "medal": "🥇", "crown": "👑", "gem": "💎", "gift": "🎁",
    "snow": "❄️", "ball": "🎾", "candle": "🕯️", "fireworks": "🎆", "champagne": "🍾",
    "delicious": "🍰", "homemade": "🧁", "ice": "🧊", "moon": "🌙", "sun": "☀️",
}

# Поздравления для финала
GREETINGS = [
    "🎉 С Новым годом! Ваша ёлка наряжена — посмотрите, какая красота получилась!",
    "🎄 С праздником! Друзья вместе создали настоящую новогоднюю сказку!",
    "✨ С Новым годом! Пусть эта ёлка принесёт в ваш чат тепло, смех и удачу!",
    "🎊 Ура! Ёлка готова! Желаем вам в новом году ярких моментов и хороших друзей!",
]
