# 🎄 Новогодняя ёлка — Telegram Mini App

Бот, в котором друзья в групповом чате вместе украшают ёлку до 1 января.
1 января бот присылает в чат финальную ёлку картинкой + поздравление + итоги по участникам.

## Как это работает

1. Добавляешь бота в групповой чат → `/start` → ёлка создана
2. Все нажимают «🎄 Украсить ёлку» → открывается Mini App
3. Выбираешь игрушку (шар, звезда, снежинка, подарок, колокольчик, конфета) и цвет → кликаешь по ёлке
4. Игрушка сохраняется в базу и видна всем в чате
5. 1 января в 00:00 (по `TIMEZONE`) бот сам шлёт финал: картинка ёлки + поздравление + топ участников

## Быстрый старт

```bash
pip install -r requirements.txt
cp .env.example .env
# заполни BOT_TOKEN и WEBAPP_URL
python run.py
```

### Получить BOT_TOKEN
1. Открой [@BotFather](https://t.me/BotFather) → `/newbot` → скопируй токен
2. `/setprivacy` → выбери бота → **Disable** (чтобы видел сообщения в группе)
3. Добавь бота в групповой чат как администратора (или просто участником)

### WEBAPP_URL
Telegram требует **HTTPS** для Mini App. Для локальной разработки:
```bash
# терминал 2 (после запуска run.py)
ngrok http 8000
# скопируй https-адрес в .env как WEBAPP_URL
```
Для продакшна — свой домен с HTTPS (VPS + nginx + certbot, или Render/Fly.io).

## Команды бота

| Команда | Что делает |
|---|---|
| `/start` | Создать ёлку в чате + кнопка Mini App |
| `/tree` | Показать текущую ёлку картинкой |
| `/stats` | Топ участников по числу игрушек |
| `/help` | Помощь |
| `/finish` | Подвести итоги досрочно (для теста) |

## Структура

```
bot.py              — обработчики команд, планировщик финала 1 января
webapp/app.py       — FastAPI: API + раздача Mini App
webapp/static/      — фронтенд Mini App (HTML/CSS/JS)
database.py         — SQLite: ёлки, юзеры, игрушки
tree_image.py       — генерация финальной картинки ёлки (Pillow)
config.py           — токен, URL, типы игрушек, поздравления
run.py              — запуск бота + Mini App одним процессом
```

## База данных

SQLite (`data.db`), таблицы:
- `trees` — одна ёлка на чат (`chat_id`)
- `users` — участники
- `decorations` — игрушки с координатами (x, y в % от размера ёлки)

## Деплой на Alwaysdata (бесплатно, с постоянной БД и HTTPS)

1. Зарегистрируйся на [alwaysdata.com](https://www.alwaysdata.com/) (тариф Free — 100 МБ).
2. В панели управления включи SSH: **Remote access → SSH** (задай пароль для своего SSH-пользователя или используй **Web SSH** прямо в браузере).
3. Подключись по SSH и выполни:
   ```bash
   git clone https://github.com/zxcwmd/tg_newyear_tree.git
   cd tg_newyear_tree
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   cp .env.example .env
   nano .env
   ```
   В `.env` укажи:
   ```env
   BOT_TOKEN=твой_токен_от_BotFather
   WEBAPP_URL=https://ИМЯ_АККАУНТА.alwaysdata.net
   TIMEZONE=Europe/Moscow
   ```
4. В панели Alwaysdata открой **Web → Sites** и нажми редактировать (⚙️) у своего сайта `ИМЯ_АККАУНТА.alwaysdata.net`:
   - **Type:** `Python ASGI` (или `User program`)
   - Если выбрал **Python ASGI**:
     - **Python version:** `3.11` (или новее)
     - **Application path:** `tg_newyear_tree/webapp/app.py` (callable `application`)
     - **Working directory:** `tg_newyear_tree`
     - **Virtualenv directory:** `tg_newyear_tree/venv`
   - Если выбрал **User program**:
     - **Command:** `/home/ИМЯ_АККАУНТА/tg_newyear_tree/venv/bin/python /home/ИМЯ_АККАУНТА/tg_newyear_tree/run.py`
     - **Working directory:** `tg_newyear_tree`
   - На вкладке **SSL** включи **Force HTTPS**.
5. Чтобы бесплатный сайт не засыпал от простоя, открой **Advanced → Scheduled tasks → Add a scheduled task**:
   - **Type:** `HTTP request`
   - **URL:** `https://ИМЯ_АККАУНТА.alwaysdata.net/ping`
   - **Frequency:** каждые 15 минут (`*/15 * * * *`)

## Деплой на VPS

1. VPS (Ubuntu) + Python 3.11+
2. `git clone`, `pip install -r requirements.txt`, создать `.env`
3. Запустить через `systemd` или `pm2`/`nohup`: `python run.py`
4. Поставить nginx reverse-proxy на порт 8000 с HTTPS (Let's Encrypt)

## Что можно доработать дальше

- Гирлянды (линия между точками)
- Анимация снега и мерцания в Mini App
- Напоминания в чат за неделю/день до финала
- Экспорт финальной ёлки в стикер
