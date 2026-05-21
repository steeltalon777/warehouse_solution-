#!/usr/bin/env bash
# ======================================================================
# Warehouse Solution — Quickstart
# ======================================================================
# Скрипт проверяет зависимости и запускает весь девстенд одной командой.
#
# Использование:
#   ./quickstart.sh          — первый запуск (сборка + миграции)
#   ./quickstart.sh up       — быстрый запуск (без пересборки)
#   ./quickstart.sh reset    — перезапуск с очисткой БД
#
# После запуска:
#   SyncServer    → http://localhost:8000  (Swagger: http://localhost:8000/api/docs)
#   Warehouse_web → http://localhost:8001
#   Angular       → http://localhost:4200
#   Postgres      → localhost:5432
# ======================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log()     { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
fail()    { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ------------------------------------------------
# Проверка зависимостей
# ------------------------------------------------
check_deps() {
    echo ""
    echo "═══════════════════════════════════════════"
    echo "  Проверка зависимостей"
    echo "═══════════════════════════════════════════"

    if command -v docker &>/dev/null; then
        log "Docker: $(docker --version 2>&1)"
    else
        fail "Docker не найден. Установите: https://docs.docker.com/engine/install/"
    fi

    if docker compose version &>/dev/null; then
        log "Docker Compose: $(docker compose version 2>&1)"
    else
        fail "Docker Compose не найден (docker compose plugin)"
    fi

    if command -v make &>/dev/null; then
        log "Make: $(make --version 2>&1 | head -1)"
    else
        warn "make не найден — устанавливаю..."
        if command -v apt-get &>/dev/null; then
            sudo apt-get update -qq && sudo apt-get install -y -qq make
            log "make установлен"
        else
            fail "make не найден. Установите вручную: sudo apt-get install make"
        fi
    fi

    # Проверка портов
    local PORTS=(5432 8000 8001 4200)
    local PORT_NAMES=("Postgres" "SyncServer" "Warehouse_web" "Angular")
    local PORT_CONFLICT=false

    for i in "${!PORTS[@]}"; do
        port=${PORTS[$i]}
        name=${PORT_NAMES[$i]}
        if command -v ss &>/dev/null; then
            if ss -tlnp "sport = :$port" 2>/dev/null | grep -q LISTEN; then
                warn "Порт $port ($name) уже занят"
                PORT_CONFLICT=true
            fi
        elif command -v lsof &>/dev/null; then
            if lsof -i :$port &>/dev/null; then
                warn "Порт $port ($name) уже занят"
                PORT_CONFLICT=true
            fi
        fi
    done

    if [ "$PORT_CONFLICT" = true ]; then
        echo ""
        warn "Некоторые порты заняты. Убедитесь, что другие сервисы не мешают."
        echo ""
    fi

    # Проверка .env
    if [ ! -f ".env" ]; then
        warn ".env не найден, создаю из шаблона..."
        cat > .env << 'ENVEOF'
POSTGRES_DB=warehouse
POSTGRES_USER=warehouse_user
POSTGRES_PASSWORD=warehouse_pass
DATABASE_URL=postgresql://warehouse_user:warehouse_pass@postgres:5432/warehouse
APP_ENV=dev
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:4200,http://localhost:8001
DJANGO_ENV=development
SECRET_KEY=django-insecure-dev-only
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost,warehouse_web
CSRF_TRUSTED_ORIGINS=http://localhost:8001
SYNC_SERVER_URL=http://syncserver:8000/api/v1
FRONTEND_MODE=dev
FRONTEND_DEV_SERVER_URL=http://angular:4200
ENVEOF
        log ".env создан с дефолтными значениями"
    fi

    echo ""
}

# ------------------------------------------------
# Основные команды
# ------------------------------------------------
cmd_up() {
    make up
    make migrate
    echo ""
    echo "═══════════════════════════════════════════"
    echo "  Стенд запущен!"
    echo "═══════════════════════════════════════════"
    echo "  SyncServer    → http://localhost:8000"
    echo "  Warehouse_web → http://localhost:8001"
    echo "  Angular       → http://localhost:4200"
    echo "═══════════════════════════════════════════"
}

cmd_init() {
    make init
}

cmd_dev() {
    make dev
}

cmd_reset() {
    echo ""
    warn "Остановка и очистка..."
    make down
    docker compose down -v 2>/dev/null || true
    log "Чисто. Запускаю заново..."
    make init
}

cmd_logs() {
    make logs
}

cmd_help() {
    echo ""
    echo "Warehouse Solution Quickstart"
    echo ""
    echo "  ./quickstart.sh          — первый запуск (init)"
    echo "  ./quickstart.sh up       — быстрый запуск"
    echo "  ./quickstart.sh dev      — запуск + логи"
    echo "  ./quickstart.sh reset    — перезапуск с очисткой БД"
    echo "  ./quickstart.sh logs     — смотреть логи"
    echo "  ./quickstart.sh help     — эта справка"
    echo ""
}

# ------------------------------------------------
# Точка входа
# ------------------------------------------------
case "${1:-init}" in
    up)
        check_deps
        cmd_up
        ;;
    init|start)
        check_deps
        cmd_init
        ;;
    dev)
        check_deps
        cmd_dev
        ;;
    reset)
        cmd_reset
        ;;
    logs)
        cmd_logs
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        cmd_help
        ;;
esac