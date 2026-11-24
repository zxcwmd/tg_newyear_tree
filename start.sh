#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

find_working_python() {
  for py in \
    $(find /opt/render /home /root -name "python3*" -type f -executable 2>/dev/null) \
    "$(command -v python3 2>/dev/null)" \
    "$(command -v python 2>/dev/null)"; do
    if [ -n "$py" ] && [ -x "$py" ]; then
      if "$py" -c "import uvicorn, fastapi, aiogram" 2>/dev/null; then
        echo "$py"
        return 0
      fi
    fi
  done
  return 1
}

echo "==> Searching for Python environment with installed packages..."
if PY_BIN=$(find_working_python); then
  echo "==> Starting with ready Python: $PY_BIN"
  exec "$PY_BIN" run.py
fi

# Пробуем найти site-packages внутри /opt/render и добавить в PYTHONPATH
SITE_PKG=$(find /opt/render /home /root -path "*/site-packages/uvicorn" -type d 2>/dev/null | head -n 1 | xargs -r dirname)
if [ -n "$SITE_PKG" ]; then
  echo "==> Found site-packages at: $SITE_PKG"
  export PYTHONPATH="$SITE_PKG:${PYTHONPATH:-}"
  if PY_BIN=$(find_working_python); then
    echo "==> Starting with Python ($PY_BIN) + PYTHONPATH ($SITE_PKG)"
    exec "$PY_BIN" run.py
  fi
fi

# Если в runtime-контейнере Render пакеты не сохранились из build-шага, запускаем pip install
echo "==> Packages not found in runtime container, running pip install -r requirements.txt..."
pip install -r requirements.txt

# Повторяем поиск после установки
SITE_PKG=$(find /opt/render /home /root -path "*/site-packages/uvicorn" -type d 2>/dev/null | head -n 1 | xargs -r dirname)
if [ -n "$SITE_PKG" ]; then
  export PYTHONPATH="$SITE_PKG:${PYTHONPATH:-}"
fi

if PY_BIN=$(find_working_python); then
  echo "==> Starting with Python: $PY_BIN"
  exec "$PY_BIN" run.py
fi

echo "❌ Could not find Python with installed packages"
exit 1
