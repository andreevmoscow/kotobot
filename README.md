# 🐱 Котобот

[![ci](https://github.com/andreevmoscow/kotobot/actions/workflows/ci.yml/badge.svg)](https://github.com/andreevmoscow/kotobot/actions/workflows/ci.yml)

Телеграм-бот для группы: по команде `/cat` присылает случайного котика из интернета.
Основной источник — [TheCatAPI](https://thecatapi.com), резервный — [Cataas](https://cataas.com).

В примерах ниже `@your_bot` — юзернейм вашего бота.

## Быстрый старт

```bash
git clone https://github.com/<ваш-логин>/kotobot.git
cd kotobot
sudo bash install.sh
```

Установщик пошагово спросит токен, ключ TheCatAPI и id группы, поставит Docker
и запустит контейнер. Подробности — в [README-INSTALL.md](README-INSTALL.md).

## Что умеет

- `/cat` — случайное фото котика (в группе работает и `/cat@your_bot`).
- Кнопка **«🐱 Ещё котика»** под каждым фото.
- Видно, кто заказал: бот отвечает на сообщение с `/cat` и подписывает фото «🐱 для Имя».
- `/help` — справка, `/start` — приветствие.
- Inline-режим: `@your_bot` в поле ввода любого чата → выбрать котика и отправить.
- Антифлуд: не чаще одного котика в `COOLDOWN_SECONDS` секунд на чат.
- Белый список чатов: бот работает только в разрешённых группах.
- Кэш `file_id` с TTL: повторно та же картинка не скачивается, старое само чистится.
- Логи с суточной ротацией (7 файлов).
- Если TheCatAPI недоступен — автоматически переключается на Cataas.

## Структура

```
bot.py                 точка входа, polling, суточная чистка кэша
config.py              конфигурация из .env / bot.env
app/cats.py            источники котиков + скачивание
app/handlers.py        команды, кнопка, inline, обработка ошибок
app/middlewares.py     белый список чатов, антифлуд
app/cache.py           кэш file_id с TTL (data/file_ids.json)
deploy/deploy.sh       разворачивание на новом сервере
deploy/backup.sh       ежедневный бэкап в backups/
deploy/cleanup.sh      ежедневная уборка логов и docker-мусора
deploy/run.sh          запуск без Docker (резерв)
deploy/watchdog.sh     сторож для cron (резерв)
Dockerfile             образ
docker-compose.yml     запуск в контейнере
```

## Настройки

`.env` — токен (права `600`):

```
token=123456:ABC...        # имя переменной именно такое
```

`bot.env` — остальные настройки, читаются поверх `.env`:

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `ALLOWED_CHAT_IDS` | пусто | id групп через запятую; пусто = разрешено везде |
| `THE_CAT_API_KEY` | пусто | ключ TheCatAPI (без него демо-лимит) |
| `COOLDOWN_SECONDS` | `3` | пауза между котиками в чате |
| `INLINE_ENABLED` | `1` | `0` — выключить inline-режим |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` |
| `DATA_DIR` | `data` | куда писать кэш и логи |
| `CACHE_TTL_DAYS` | `30` | сколько дней хранить записи кэша |
| `REQUESTER_MODE` | `name` | подпись автора: `off` / `name` / `mention` |
| `OWNER_IDS` | пусто | Telegram id владельца: кому доступны `/allow`, `/deny`, `/chats` |

## Запуск (Docker, основной вариант)

```bash
cd /opt/kotobot
docker compose up -d --build     # первый запуск / обновление
docker compose ps
docker compose logs -f
```

Контейнер: `kotobot`, политика `restart: unless-stopped`, часовой пояс `Europe/Moscow`,
логи docker ограничены 10 МБ × 3. После ребута сервера поднимается сам
(`docker.service` enabled + restart policy).

## Логи и кэш

- Логи пишутся в **два места**: `docker compose logs` (stdout) и файл
  `data/logs/bot.log` с суточной ротацией в полночь, хранится 7 файлов.
- Кэш `data/file_ids.json` чистится сам: записи старше `CACHE_TTL_DAYS`
  удаляются при старте и раз в сутки в 04:00.
- Дополнительно cron раз в сутки (04:10) запускает `deploy/cleanup.sh`:
  удаляет ротированные логи старше 7 дней, чистит неиспользуемые docker-образы
  и кэш сборки старше недели.

## Бэкап и перенос на другой сервер

Ежедневно в 03:30 cron делает архив `backups/kotobot-YYYY-MM-DD.tar.gz`
(код + конфиги + токен, без кэша), хранит 14 дней.

Развернуть на новом сервере:

```bash
scp /opt/kotobot/backups/kotobot-2026-11-06.tar.gz root@NEW:/root/
ssh root@NEW 'mkdir -p /opt/kotobot && tar -xzf /root/kotobot-*.tar.gz -C /opt/kotobot && bash /opt/kotobot/deploy/deploy.sh'
```

`deploy.sh` сам поставит Docker (если его нет на Ubuntu), соберёт образ и запустит контейнер.

Есть и второй путь — папка `kotobot-installer/` (рядом с архивами): код + интерактивный
`install.sh`, который пошагово спрашивает токен, ключ TheCatAPI, id группы и сам всё поднимает.
Подробности — в `README-INSTALL.md` внутри неё.

Перед запуском на новом сервере **остановите бота на старом**:

```bash
cd /opt/kotobot && docker compose down
```

Иначе два экземпляра будут конфликтовать за `getUpdates` (ошибка 409).

Архив содержит токен и API-ключ — хранить только в защищённом месте (`600`),
при передаче по открытым каналам лучше зашифровать: `gpg -c kotobot-*.tar.gz`.

## Настройка в @BotFather

1. `/setprivacy` → **ваш бот** → **Disable**.
   Без этого бот в группе видит только `/cat@your_bot`, а не просто `/cat`.
   После смены privacy бота нужно **удалить из группы и добавить заново**.
   Альтернатива: выдать боту админку в группе.
2. `/setinline` → **ваш бот** → подсказка (например, `котик`).
3. Команды бот ставит сам при старте; вручную — `/setcommands`:
   ```
   cat - Прислать котика
   help - Что умеет бот
   ```

## Как узнать id группы

```bash
docker compose logs | grep 'chat_id=' | tail
```

Вписать в `bot.env`:

```
ALLOWED_CHAT_IDS=-1001234567890
```

и перезапустить: `docker compose up -d`.

## Управление группами

Владелец (id указан в `OWNER_IDS`) может добавлять и убирать группы прямо из чата:

| Команда | Что делает |
|---|---|
| `/allow` | добавить текущую группу в белый список |
| `/deny` | убрать текущую группу из списка |
| `/chats` | показать все разрешённые id |
| `/whoami` | показать свой id и id чата |

Динамический список хранится в `data/allowed_chats.json` и переживает перезапуск.
Группы, прописанные в `ALLOWED_CHAT_IDS`, убираются только через `bot.env` —
`/deny` про это предупредит.

## Частые проблемы

| Симптом | Причина / решение |
|---|---|
| В группе молчит на `/cat`, в личке отвечает | privacy mode: `/setprivacy` → Disable, переадд бота |
| `Котики сегодня прячутся` | оба источника недоступны — смотреть логи |
| `Conflict: terminated by other getUpdates` | два экземпляра: на старом сервере `docker compose down` |
| Бот отвечает в чужих группах | не заполнен `ALLOWED_CHAT_IDS` |
| `permission denied` при старте контейнера | `chown -R 10001:10001 /opt/kotobot/data` |

## Обслуживание

```bash
docker compose logs -f --tail 100
docker compose restart
docker compose up -d --build      # после обновления кода
du -sh /opt/kotobot/data          # кэш и логи
ls -lh /opt/kotobot/backups       # архивы
```

## Безопасность

- `.env` — `600`, каталог `/opt/kotobot` — `750`; токен не коммитить.
- Архивы бэкапа содержат секреты — тоже `600`.
- Пароль `kotobot` стоит сменить; для администрирования хватает `sudo`.
- Токен можно перевыпустить в BotFather (`/revoke`) и обновить `.env`.
