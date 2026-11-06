#!/bin/bash
# Ежедневный бэкап проекта: архив, из которого разворачивается бот на другом сервере.
set -euo pipefail

cd /opt/kotobot || exit 1

STAMP="$(date +%F)"
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p backups
OUT="backups/kotobot-${STAMP}.tar.gz"

FILES=(
    bot.py config.py requirements.txt Dockerfile docker-compose.yml
    .dockerignore .gitignore bot.env .env README.md README-INSTALL.md install.sh
    deploy app
)

EXISTING=()
for item in "${FILES[@]}"; do
    if [ -e "$item" ]; then
        EXISTING+=("$item")
    fi
done

if [ ${#EXISTING[@]} -eq 0 ]; then
    echo "backup: нечего архивировать" >&2
    exit 1
fi

tar -czf "${OUT}.part" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='data' \
    --exclude='logs' \
    --exclude='backups' \
    "${EXISTING[@]}"

mv "${OUT}.part" "$OUT"
chmod 600 "$OUT"
find backups -maxdepth 1 -name 'kotobot-*.tar.gz*' -mtime +"${KEEP_DAYS}" -delete

echo "$(date -Is) backup ok: ${OUT} ($(du -h "$OUT" | cut -f1))"
