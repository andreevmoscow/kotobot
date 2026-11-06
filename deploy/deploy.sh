#!/bin/bash
# Разворачивание Котобота на новом сервере.
#
#   scp kotobot-YYYY-MM-DD.tar.gz root@NEW:/root/
#   ssh root@NEW 'mkdir -p /opt/kotobot && tar -xzf /root/kotobot-*.tar.gz -C /opt/kotobot && bash /opt/kotobot/deploy/deploy.sh'
#
# Скрипт идемпотентен: повторный запуск просто пересобирает и перезапускает контейнер.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Котобот: разворачивание в $ROOT =="

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker не найден — устанавливаю (нужен root)..."
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io docker-compose-v2
    systemctl enable --now docker
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "ОШИБКА: плагин 'docker compose' недоступен" >&2
    exit 1
fi

if [ ! -f .env ] || [ ! -f bot.env ]; then
    echo "ОШИБКА: рядом с docker-compose.yml нет .env или bot.env" >&2
    exit 1
fi

mkdir -p data logs
chown -R 10001:10001 data
chmod 600 .env 2>/dev/null || true

echo "== сборка и запуск =="
docker compose up -d --build
sleep 6
docker compose ps

echo
echo "Готово. Логи: docker compose logs -f"
echo "ВАЖНО: на старом сервере сначала выполните 'docker compose down',"
echo "иначе два экземпляра будут конфликтовать за getUpdates (ошибка 409)."
