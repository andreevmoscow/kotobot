#!/bin/bash
# Ежедневная уборка: старые ротированные логи приложения и docker-мусор.
set -u

cd /opt/kotobot || exit 1

# ротированные логи приложения старше 7 дней
find data/logs -maxdepth 1 -type f -name 'bot.log.*' -mtime +7 -delete 2>/dev/null || true

# не даём разрастаться логам cron-задач
for f in logs/backup.log logs/cleanup.log; do
    if [ -f "$f" ] && [ "$(stat -c%s "$f" 2>/dev/null || echo 0)" -gt 1048576 ]; then
        : > "$f"
    fi
done

# docker: неиспользуемые образы и кэш сборки старше недели
docker image prune -f --filter "until=168h" >/dev/null 2>&1 || true
docker builder prune -f --filter "until=168h" >/dev/null 2>&1 || true

echo "$(date -Is) cleanup ok: data=$(du -sh data 2>/dev/null | cut -f1)"
