#!/usr/bin/env bash
# =============================================================================
# Warehouse Solution — Ubuntu Desktop Setup Script
# =============================================================================
# Запуск: bash setup_ubuntu.sh
# Делает всё: системные пакеты → Python/Node/Rust → клонирование → БД → .env → миграции.
# Идемпотентен: повторный запуск безопасен, пропускает уже сделанное.
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[OK]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*"; exit 1; }

WS_ROOT="$HOME/projects/warehouse_solution"

# ---------------------------------------------------------------------------
# 0. Проверка: Ubuntu?
# ---------------------------------------------------------------------------
if ! grep -qi ubuntu /etc/os-release 2>/dev/null; then
    warn "Не Ubuntu. Продолжаем, но может не сработать."
fi

# ---------------------------------------------------------------------------
# 1. Системные пакеты
# ---------------------------------------------------------------------------
log "Установка системных пакетов..."
sudo apt update
sudo apt install -y \
    build-essential curl git \
    libpq-dev libsqlite3-dev pkg-config libssl-dev \
    libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
    libffi-dev libgirepository-2.0-0 \
    python3-dev python3-pip python3-venv \
    postgresql postgresql-client \
    libncurses-dev libreadline-dev libbz2-dev \
    liblzma-dev tk-dev

# ---------------------------------------------------------------------------
# 2. Pyenv
# ---------------------------------------------------------------------------
if [ ! -d "$HOME/.pyenv" ]; then
    log "Установка pyenv..."
    curl https://pyenv.run | bash
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
else
    log "pyenv уже установлен"
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
fi

for ver in 3.12.0 3.13.0; do
    if pyenv versions --bare | grep -q "^${ver}$"; then
        log "Python $ver уже установлен"
    else
        log "Установка Python $ver..."
        pyenv install "$ver"
    fi
done

# ---------------------------------------------------------------------------
# 3. NVM + Node 20
# ---------------------------------------------------------------------------
export NVM_DIR="$HOME/.nvm"
if [ ! -d "$NVM_DIR" ]; then
    log "Установка nvm..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi

[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

if nvm ls 20 --no-colors 2>/dev/null | grep -q 'v20\.'; then
    log "Node 20 уже установлен"
else
    log "Установка Node 20..."
    nvm install 20
fi
nvm use 20
log "Node: $(node --version) / npm: $(npm --version)"

# ---------------------------------------------------------------------------
# 4. Rust
# ---------------------------------------------------------------------------
if [ -f "$HOME/.cargo/bin/rustc" ]; then
    log "Rust уже установлен: $($HOME/.cargo/bin/rustc --version)"
else
    log "Установка Rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
fi
source "$HOME/.cargo/env"

# ---------------------------------------------------------------------------
# 5. Клонирование репозиториев
# ---------------------------------------------------------------------------
mkdir -p "$WS_ROOT"

clone_if_missing() {
    local dir="$1" url="$2"
    if [ -d "$dir/.git" ]; then
        log "Репозиторий $dir уже существует"
    else
        log "Клонирование $url → $dir"
        git clone "$url" "$dir"
    fi
}

# Корень
clone_if_missing "$WS_ROOT" \
    "https://github.com/steeltalon777/warehouse_solution-.git"

cd "$WS_ROOT"

# Вложенные
clone_if_missing "$WS_ROOT/SyncServer" \
    "git@github.com:steeltalon777/SyncServer.git"
clone_if_missing "$WS_ROOT/Warehouse_web" \
    "git@github.com:steeltalon777/Warehouse_web.git"
clone_if_missing "$WS_ROOT/Warehouse_frontend" \
    "https://github.com/steeltalon777/Warehouse_frontend.git"
clone_if_missing "$WS_ROOT/Warehouse_client_core" \
    "https://github.com/steeltalon777/Warehouse_core.git"

# Проверка веток (все должны быть dev)
for proj in SyncServer Warehouse_web Warehouse_frontend Warehouse_client_core; do
    branch=$(git -C "$WS_ROOT/$proj" branch --show-current 2>/dev/null || echo "?")
    if [ "$branch" != "dev" ]; then
        warn "$proj: ветка '$branch' (ожидалась 'dev')"
    else
        log "$proj: ветка dev OK"
    fi
done

# ---------------------------------------------------------------------------
# 6. Python venv + pip install
# ---------------------------------------------------------------------------
setup_python_project() {
    local dir="$1" py_ver="$2" label="$3"
    log "Настройка $label (Python $py_ver)..."
    cd "$dir"
    pyenv local "$py_ver"
    if [ ! -d ".venv" ]; then
        python -m venv .venv
    fi
    source .venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt
    log "$label: зависимости установлены"
}

setup_python_project "$WS_ROOT/SyncServer"    "3.13.0" "SyncServer"
setup_python_project "$WS_ROOT/Warehouse_web" "3.12.0" "Warehouse_web"

# ---------------------------------------------------------------------------
# 7. Angular: npm install
# ---------------------------------------------------------------------------
log "Настройка Warehouse_frontend (Angular)..."
cd "$WS_ROOT/Warehouse_frontend"
nvm use 20
npm install -g npm@11.12.1 --silent 2>/dev/null || true
npm install
log "Warehouse_frontend: npm install завершён"

# ---------------------------------------------------------------------------
# 8. Rust: cargo build
# ---------------------------------------------------------------------------
log "Настройка Warehouse_client_core (Rust)..."
cd "$WS_ROOT/Warehouse_client_core"
cargo fetch
cargo build --workspace 2>&1 | tail -5
log "Warehouse_client_core: cargo build завершён"

# ---------------------------------------------------------------------------
# 9. PostgreSQL
# ---------------------------------------------------------------------------
log "Настройка PostgreSQL..."
sudo systemctl enable postgresql 2>/dev/null || true
sudo systemctl start postgresql 2>/dev/null || true

# Создание пользователей и БД (идемпотентно через DO-block)
sudo -u postgres psql <<'SQL' 2>/dev/null && log "PostgreSQL: БД созданы" || warn "PostgreSQL: БД уже существуют или ошибка (проверь вручную)"
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'sync_user') THEN
        CREATE USER sync_user WITH PASSWORD 'sync_password';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'django_user') THEN
        CREATE USER django_user WITH PASSWORD 'django_password';
    END IF;
END
$$;

SELECT 'CREATE DATABASE sync_db OWNER sync_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sync_db')\gexec

SELECT 'CREATE DATABASE warehouse_web_db OWNER django_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'warehouse_web_db')\gexec

GRANT ALL PRIVILEGES ON DATABASE sync_db TO sync_user;
GRANT ALL PRIVILEGES ON DATABASE warehouse_web_db TO django_user;
\c sync_db
GRANT ALL ON SCHEMA public TO sync_user;
\c warehouse_web_db
GRANT ALL ON SCHEMA public TO django_user;
SQL

# ---------------------------------------------------------------------------
# 10. .env файлы (из шаблонов)
# ---------------------------------------------------------------------------
log "Создание .env файлов..."

# SyncServer
if [ ! -f "$WS_ROOT/SyncServer/.env" ]; then
    cp "$WS_ROOT/SyncServer/.env.example" "$WS_ROOT/SyncServer/.env"
    # Поправить БД URL на локальный PostgreSQL
    sed -i 's|DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://sync_user:sync_password@127.0.0.1:5432/sync_db|' \
        "$WS_ROOT/SyncServer/.env"
    sed -i 's|DATABASE_URL_TEST=.*|DATABASE_URL_TEST=postgresql+asyncpg://sync_user:sync_password@127.0.0.1:5432/sync_db|' \
        "$WS_ROOT/SyncServer/.env"
    log "SyncServer: .env создан"
else
    log "SyncServer: .env уже существует"
fi

# Warehouse_web
if [ ! -f "$WS_ROOT/Warehouse_web/.env" ]; then
    cp "$WS_ROOT/Warehouse_web/.env.example" "$WS_ROOT/Warehouse_web/.env"
    # SyncServer URL — локально
    sed -i 's|SYNC_SERVER_URL=.*|SYNC_SERVER_URL=http://127.0.0.1:8000/api/v1|' \
        "$WS_ROOT/Warehouse_web/.env"
    # По умолчанию SQLite для разработки
    sed -i 's|^DB_ENGINE=.*|DB_ENGINE=django.db.backends.sqlite3|' \
        "$WS_ROOT/Warehouse_web/.env"
    sed -i 's|^DB_NAME=.*|DB_NAME=db.sqlite3|' \
        "$WS_ROOT/Warehouse_web/.env"
    log "Warehouse_web: .env создан (SQLite для разработки)"
else
    log "Warehouse_web: .env уже существует"
fi

# ---------------------------------------------------------------------------
# 11. Миграции
# ---------------------------------------------------------------------------
log "Запуск миграций..."

# SyncServer (Alembic)
cd "$WS_ROOT/SyncServer"
source .venv/bin/activate
python -m alembic upgrade head
log "SyncServer: миграции применены"

# Warehouse_web (Django)
cd "$WS_ROOT/Warehouse_web"
source .venv/bin/activate
python manage.py migrate
log "Warehouse_web: миграции применены"

# ---------------------------------------------------------------------------
# 12. Итог
# ---------------------------------------------------------------------------
echo ""
echo "=============================================================================="
echo -e "${GREEN}Установка завершена!${NC}"
echo ""
echo "Для запуска стенда (в трёх терминалах):"
echo ""
echo "  Терминал 1 — SyncServer (:8000):"
echo "    cd ~/projects/warehouse_solution/SyncServer"
echo "    source .venv/bin/activate"
echo "    uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "  Терминал 2 — Django (:8001):"
echo "    cd ~/projects/warehouse_solution/Warehouse_web"
echo "    source .venv/bin/activate"
echo "    python manage.py runserver 0.0.0.0:8001"
echo ""
echo "  Терминал 3 — Angular dev server (:4200):"
echo "    cd ~/projects/warehouse_solution/Warehouse_frontend"
echo "    nvm use 20"
echo "    npm start"
echo ""
echo "Проверка здоровья:"
echo "  curl http://localhost:8000/api/v1/health"
echo "  curl http://localhost:8001/healthz/"
echo ""
echo "ВАЖНО: после перезагрузки терминала добавь в ~/.bashrc:"
echo '  export PYENV_ROOT="$HOME/.pyenv"'
echo '  [[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"'
echo '  eval "$(pyenv init -)"'
echo '  export NVM_DIR="$HOME/.nvm"'
echo '  [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"'
echo '  source "$HOME/.cargo/env"'
echo "=============================================================================="
