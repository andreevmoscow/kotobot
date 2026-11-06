#!/bin/bash
# Интерактивная установка Котобота на чистый сервер (Ubuntu/Debian).
#
#   sudo bash install.sh            # обычная установка
#   bash install.sh --dry-run       # только спросить и разложить файлы, без Docker
#
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BOLD=$'\033[1m'
DIM=$'\033[2m'
GREEN=$'\033[32m'
RED=$'\033[31m'
YELLOW=$'\033[33m'
RESET=$'\033[0m'

DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help)
            sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Неизвестный аргумент: $arg" >&2
            exit 2
            ;;
    esac
done

header() { printf '\n%s== %s ==%s\n' "$BOLD" "$1" "$RESET"; }
info()   { printf '%s\n' "$*"; }
warn()   { printf '%s%s%s\n' "$YELLOW" "$*" "$RESET"; }
fail()   { printf '%s%s%s\n' "$RED" "$*" "$RESET" >&2; exit 1; }

ask() {
    local prompt="$1" default="${2:-}" answer=""
    if [ -n "$default" ]; then
        printf '%s [%s]: ' "$prompt" "$default" >&2
    else
        printf '%s: ' "$prompt" >&2
    fi
    read -r answer || true
    if [ -n "$default" ]; then
        printf '%s' "${answer:-$default}"
    else
        printf '%s' "$answer"
    fi
}

ask_secret() {
    local prompt="$1" answer=""
    printf '%s: ' "$prompt" >&2
    read -r -s answer || true
    printf '\n' >&2
    printf '%s' "$answer"
}

ask_yn() {
    local prompt="$1" default="${2:-y}" answer=""
    printf '%s [%s]: ' "$prompt" "$default" >&2
    read -r answer || true
    answer="${answer:-$default}"
    case "$answer" in
        [YyДд]*) return 0 ;;
        *) return 1 ;;
    esac
}

valid_token() { [[ "$1" =~ ^[0-9]{5,}:[A-Za-z0-9_-]{20,}$ ]]; }

fetch_bot_username() {
    local token="$1" resp=""
    command -v curl >/dev/null 2>&1 || return 2
    resp="$(curl -sS --max-time 10 "https://api.telegram.org/bot${token}/getMe" 2>/dev/null)" || return 2
    case "$resp" in
        *'"ok":true'*) printf '%s' "$resp" | sed -n 's/.*"username":"\([^"]*\)".*/\1/p' ;;
        *) return 1 ;;
    esac
}

# ------------------------------------------------------------------ приветствие
printf '%s\n' "${BOLD}🐱 Установка Котобота${RESET}"
printf '%s\n' "${DIM}Бот для группы: по /cat присылает случайного котика из интернета.${RESET}"
if [ "$DRY_RUN" -eq 1 ]; then
    printf '%s\n' "${YELLOW}Режим --dry-run: файлы разложим, Docker не трогаем.${RESET}"
fi

if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
    fail "Нужны права root. Запустите: sudo bash install.sh"
fi

# ---------------------------------------------------------------------- опрос
header "1/8. Куда ставить"
TARGET="$(ask "Каталог установки" "/opt/kotobot")"
[ -n "$TARGET" ] || fail "Каталог не задан"
case "$TARGET" in
    /) fail "Нельзя ставить в корень /" ;;
esac

header "2/8. Токен бота"
info "Взять у @BotFather: /mybots → ваш бот → API Token."
info "Формат: 123456789:AAExampleTokenFromBotFather (без пробелов)."
BOT_TOKEN=""
while true; do
    BOT_TOKEN="$(ask_secret "Токен")"
    [ -n "$BOT_TOKEN" ] || { warn "Пусто, попробуйте ещё раз."; continue; }
    valid_token "$BOT_TOKEN" && break
    warn "Не похоже на токен. Пример: 123456789:AAExampleTokenFromBotFather"
    ask_yn "Всё равно продолжить?" n || continue
    break
done

BOT_USERNAME=""
header "3/8. Проверка токена"
USERNAME_FILE="$(mktemp)"
set +e
fetch_bot_username "$BOT_TOKEN" >"$USERNAME_FILE" 2>/dev/null
CHECK_RC=$?
set -e
if [ "$CHECK_RC" -eq 0 ]; then
    BOT_USERNAME="$(cat "$USERNAME_FILE")"
    info "${GREEN}Токен рабочий.${RESET} Бот: @${BOT_USERNAME}"
elif [ "$CHECK_RC" -eq 2 ]; then
    warn "curl недоступен — проверку пропускаю."
    BOT_USERNAME="$(ask "Username бота без @ (для напоминаний, можно пусто)" "")"
else
    warn "Telegram не подтвердил токен (нет сети или токен неверный)."
    ask_yn "Продолжить всё равно?" n || fail "Установка отменена."
    BOT_USERNAME="$(ask "Username бота без @ (можно пусто)" "")"
fi
rm -f "$USERNAME_FILE"

header "4/8. TheCatAPI"
info "Бесплатный ключ: https://thecatapi.com/signup (10 000 запросов/мес)."
info "Можно оставить пустым — будет демо-лимит."
API_KEY="$(ask_secret "Ключ TheCatAPI (Enter — пропустить)")"
API_KEY="$(printf '%s' "$API_KEY" | tr -d '[:space:]')"

header "5/8. Группа"
info "ID группы, где боту разрешено работать. Пусто — бот ответит в любой группе,"
info "id потом можно узнать из логов и дописать в bot.env."
CHAT_IDS="$(ask "ALLOWED_CHAT_IDS (например -1001234567890, можно пусто)" "")"
CHAT_IDS="$(printf '%s' "$CHAT_IDS" | tr -d ' ')"
if [ -n "$CHAT_IDS" ] && ! [[ "$CHAT_IDS" =~ ^-?[0-9]+(,-?[0-9]+)*$ ]]; then
    warn "Это не похоже на список id, оставляю пустым."
    CHAT_IDS=""
fi

header "6/8. Поведение"
COOLDOWN="$(ask "Пауза между котиками в чате, сек" "3")"
[[ "$COOLDOWN" =~ ^[0-9]+([.][0-9]+)?$ ]] || COOLDOWN=3

INLINE="1"
if ! ask_yn "Включить inline-режим ( @бот в поле ввода любого чата )?" y; then
    INLINE="0"
fi

info "Подпись автора: 1) name — имя без уведомления, 2) mention — с уведомлением, 3) off — без имени"
MODE_CHOICE="$(ask "Выбор" "1")"
case "$MODE_CHOICE" in
    2) REQUESTER_MODE="mention" ;;
    3) REQUESTER_MODE="off" ;;
    *) REQUESTER_MODE="name" ;;
esac

header "7/8. Часовой пояс"
TZ_VALUE="$(ask "TZ (влияет на время в логах и ротацию)" "Europe/Moscow")"
[[ "$TZ_VALUE" =~ ^[A-Za-z]+/[A-Za-z_+-]+$ ]] || TZ_VALUE="Europe/Moscow"

header "8/8. Проверьте настройки"
BOT_LINE="не проверен"
[ -n "$BOT_USERNAME" ] && BOT_LINE="@${BOT_USERNAME}"
API_LINE="нет (демо-лимит)"
[ -n "$API_KEY" ] && API_LINE="ключ задан"
DOCKER_LINE="установим при необходимости"
[ "$DRY_RUN" -eq 1 ] && DOCKER_LINE="не трогаем (--dry-run)"
cat <<EOF
  Каталог:        ${TARGET}
  Бот:            ${BOT_LINE}
  TheCatAPI:      ${API_LINE}
  Группа:         ${CHAT_IDS:-любая (заполнить позже)}
  Пауза:          ${COOLDOWN} сек
  Inline:         ${INLINE}
  Автор:          ${REQUESTER_MODE}
  Часовой пояс:   ${TZ_VALUE}
  Docker:         ${DOCKER_LINE}
EOF

ask_yn "Всё верно, ставим?" y || fail "Отменено пользователем."

# ------------------------------------------------------------------ установка
header "Установка"

if [ "$DRY_RUN" -eq 0 ] && ! command -v docker >/dev/null 2>&1; then
    ask_yn "Docker не найден. Установить docker.io и docker-compose-v2?" y \
        || fail "Без Docker установка невозможна."
    info "apt-get update..."
    apt-get update -qq
    info "Устанавливаю Docker..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io docker-compose-v2
    systemctl enable --now docker
fi

if [ "$DRY_RUN" -eq 0 ] && ! docker compose version >/dev/null 2>&1; then
    fail "Плагин 'docker compose' недоступен. Поставьте docker-compose-v2 вручную."
fi

info "Каталог ${TARGET}"
mkdir -p "$TARGET"

if [ -f "$TARGET/.env" ]; then
    BACKUP_NAME=".env.bak.$(date +%s)"
    cp -a "$TARGET/.env" "$TARGET/${BACKUP_NAME}"
    warn "Старый .env сохранён как ${BACKUP_NAME}"
fi

ITEMS=(bot.py config.py requirements.txt Dockerfile docker-compose.yml .dockerignore .gitignore app)
for item in "${ITEMS[@]}"; do
    if [ ! -e "${SRC_DIR}/${item}" ]; then
        fail "В установщике отсутствует ${item} — архив неполный."
    fi
    rm -rf "${TARGET:?}/${item}"
    cp -a "${SRC_DIR}/${item}" "${TARGET}/"
done
info "Файлы проекта скопированы."

( umask 077
  cat > "$TARGET/.env" <<EOF
# Токен Telegram-бота (от @BotFather)
token=${BOT_TOKEN}
TZ=${TZ_VALUE}
EOF
  cat > "$TARGET/bot.env" <<EOF
ALLOWED_CHAT_IDS=${CHAT_IDS}
THE_CAT_API_KEY=${API_KEY}
COOLDOWN_SECONDS=${COOLDOWN}
INLINE_ENABLED=${INLINE}
LOG_LEVEL=INFO
DATA_DIR=data
CACHE_TTL_DAYS=30
REQUESTER_MODE=${REQUESTER_MODE}
EOF
)
chmod 600 "$TARGET/.env" "$TARGET/bot.env"
info "Конфиги записаны (.env и bot.env, права 600)."

mkdir -p "$TARGET/data"
chown -R 10001:10001 "$TARGET/data" 2>/dev/null || warn "Не смог выставить владельца data (uid 10001)."
chmod 750 "$TARGET" 2>/dev/null || true

if [ "$DRY_RUN" -eq 1 ]; then
    warn "--dry-run: Docker не запускаю. Проверьте ${TARGET} и запустите 'docker compose up -d --build'."
    exit 0
fi

header "Сборка и запуск"
cd "$TARGET"
docker compose up -d --build
sleep 6
docker compose ps
info ""
docker compose logs --tail 15 || true

# --------------------------------------------------------------- что дальше
header "Готово"
cat <<EOF
Бот установлен в ${TARGET}.

Что сделать в Telegram:
  1. @BotFather → /setprivacy → ваш бот → Disable
     (иначе в группе работает только /cat@${BOT_USERNAME:-bot}, но не /cat)
  2. @BotFather → /setinline → ваш бот → подсказка (например, "котик")
  3. Добавить бота в группу и написать /cat
  4. Если группа ещё не задана: посмотреть id в логах
        cd ${TARGET} && docker compose logs | grep 'chat_id='
     и вписать в bot.env строку ALLOWED_CHAT_IDS=..., затем
        docker compose up -d

Управление:
  cd ${TARGET}
  docker compose logs -f
  docker compose restart
  docker compose up -d --build
EOF
