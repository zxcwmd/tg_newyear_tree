#!/usr/bin/env bash
set -e

echo "==> Searching for Python environment with installed dependencies..."

# 1. Ищем python3 внутри /opt/render (виртуальное окружение Render/Poetry/pyenv), где уже установлен uvicorn
if [ -d "/opt/render" ]; then
  while IFS= read -r py; do
    if [ -n "$py" ] && "$py" -c "import uvicorn, aiogram, fastapi" >/dev/null 2>&1; then
      echo "==> Starting with Render Python: $py"
      exec "$py" run.py
    fi
  done < <(find /opt/render -name "python3" -type f -executable 2>/dev/null)
fi

# 2. Проверяем системный python3 / python
for py in "$(command -v python3 2>/dev/null)" "$(command -v python 2>/dev/null)"; do
  if [ -n "$py" ] && [ -x "$py" ] && "$py" -c "import uvicorn, aiogram, fastapi" >/dev/null 2>&1; then
    echo "==> Starting with system Python: $py"
    exec "$py" run.py
  fi
done

# 3. Если пакеты были установлены в site-packages внутри /opt/render, подключаем их через PYTHONPATH
if [ -d "/opt/render" ]; then
  SITE_PKG=$(find /opt/render -type d -name "uvicorn" 2>/dev/null | head -n 1 | xargs -r dirname)
  if [ -n "$SITE_PKG" ]; then
    echo "==> Found site-packages at: $SITE_PKG"
    export PYTHONPATH="${SITE_PKG}:${PYTHONPATH}"
    if python3 -c "import uvicorn, aiogram, fastapi" >/dev/null 2>&1; then
      echo "==> Starting with python3 + PYTHONPATH"
      exec python3 run.py
    fi
  fi
fi

# 4. Фолбэк: если сервис на Render запущен в Ruby-контейнере, создаём локальный .venv и ставим зависимости
echo "==> Installing dependencies into local .venv..."
SYS_PY=$(command -v python3 || command -v python)
"$SYS_PY" -m venv .venv || true
if [ -x ".venv/bin/python" ]; then
  .venv/bin/pip install --no-cache-dir -r requirements.txt
  echo "==> Starting with .venv/bin/python"
  exec .venv/bin/python run.py
else
  "$SYS_PY" -m pip install --user --no-cache-dir -r requirements.txt || "$SYS_PY" -m pip install --break-system-packages --no-cache-dir -r requirements.txt
  exec "$SYS_PY" run.py
fi
