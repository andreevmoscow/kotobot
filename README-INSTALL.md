# Установщик Котобота

Папка самодостаточная: код бота + интерактивный `install.sh`.
Нужен только сервер с Ubuntu/Debian и доступ в интернет.

## Перенос на новый сервер

```bash
scp -r kotobot-installer root@NEW:/root/
ssh root@NEW 'bash /root/kotobot-installer/install.sh'
```

Или одним архивом, если он рядом (`kotobot-installer.tar.gz`):

```bash
scp kotobot-installer.tar.gz root@NEW:/root/
ssh root@NEW 'tar -xzf /root/kotobot-installer.tar.gz -C /root && bash /root/kotobot-installer/install.sh'
```

## Что спросит

1. Каталог установки (по умолчанию `/opt/kotobot`).
2. Токен бота от @BotFather — ввод скрытый, формат проверяется.
3. Проверка токена через Telegram (`getMe`) — покажет имя бота.
4. Ключ TheCatAPI (можно пропустить — будет демо-лимит).
5. ID группы (можно пропустить и вписать позже).
6. Пауза между котиками, inline-режим, подпись автора.
7. Часовой пояс.
8. Подтверждение — и установка.

## Что делает

- Ставит Docker и `docker compose`, если их нет.
- Раскладывает код в каталог установки.
- Пишет `.env` (токен) и `bot.env` (остальные настройки), права `600`.
- Создаёт `data` с владельцем `uid 10001`.
- Собирает образ и запускает контейнер с `restart: unless-stopped`.

## Проверка без установки

```bash
bash install.sh --dry-run
```

Спросит всё то же самое и разложит файлы, но не тронет Docker — удобно проверить конфиги.

## После установки

1. @BotFather → `/setprivacy` → бот → **Disable** (иначе `/cat` без упоминания не дойдёт).
2. @BotFather → `/setinline` → бот → подсказка (для inline-режима).
3. Добавить бота в группу, написать `/cat`.
4. Если ID группы не задавали: `docker compose logs | grep 'chat_id='`,
   затем вписать в `bot.env` → `ALLOWED_CHAT_IDS=...` и `docker compose up -d`.

## Требования

- Ubuntu/Debian, root (или sudo).
- 1 ГБ RAM достаточно.
- Токен и ключи — те же, что на старом сервере, либо новые.
- На старом сервере перед запуском нового: `docker compose down`,
  иначе два экземпляра конфликтуют за `getUpdates` (ошибка 409).
