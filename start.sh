#!/usr/bin/env bash
set -e

for py in \
  /opt/render/project/python/Python-*/bin/python3 \
  /opt/render/project/.render/python-*/bin/python3 \
  "$(command -v python3 2>/dev/null)" \
  "$(command -v python 2>/dev/null)"; do
  if [ -n "$py" ] && [ -x "$py" ]; then
    echo "==> Starting with Python: $py"
    exec "$py" run.py
  fi
done

FOUND_PY=$(find /opt/render -name "python3" -type f -executable 2>/dev/null | head -n 1)
if [ -n "$FOUND_PY" ]; then
  echo "==> Starting with found Python: $FOUND_PY"
  exec "$FOUND_PY" run.py
fi

echo "❌ Python interpreter not found!"
exit 1
