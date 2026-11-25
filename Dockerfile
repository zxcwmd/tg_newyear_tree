FROM python:3.11-slim

WORKDIR /app

# Системные шрифты для генерации открытки (Pillow):
# DejaVu — текст, Noto Color Emoji — цветные эмодзи в медальонах игрушек
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python3", "run.py"]
