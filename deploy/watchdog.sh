#!/bin/bash
# Сторож: поднимает бота, если он не запущен. Вызывается cron'ом раз в минуту.
set -u
cd /opt/kotobot || exit 1
mkdir -p logs

# один сторож за раз
exec 9>.watchdog.lock
flock -n 9 || exit 0

# ротация лога, чтобы не рос бесконечно
if [ -f logs/bot.log ] && [ "$(stat -c%s logs/bot.log 2>/dev/null || echo 0)" -gt 5242880 ]; then
    cp -f logs/bot.log logs/bot.log.1
    : > logs/bot.log
fi

if ! pgrep -f "[.]venv/bin/python -u bot.py" >/dev/null 2>&1; then
    echo "$(date -Is) watchdog: бот не запущен, стартую" >> logs/watchdog.log
    setsid nohup .venv/bin/python -u bot.py >> logs/bot.log 2>&1 < /dev/null &
fi
