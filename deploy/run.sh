#!/bin/bash
# Запуск бота (используется cron'ом).
cd /opt/kotobot || exit 1
exec .venv/bin/python -u bot.py >> logs/bot.log 2>&1
