FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Moscow

WORKDIR /app

# tzdata нужен, чтобы TZ=Europe/Moscow и ротация логов в полночь работали по Москве
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py bot.py ./
COPY app ./app

RUN useradd --create-home --uid 10001 bot \
    && mkdir -p /app/data \
    && chown -R bot:bot /app

USER bot

CMD ["python", "bot.py"]
