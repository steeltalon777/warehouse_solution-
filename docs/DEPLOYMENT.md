# Deployment Rules — Warehouse Solution

> Загружается только при деплое. Не засоряет контекст разработки.

## Branch Roles

| Ветка | Назначение | Кто меняет |
|---|---|---|
| `dev` | Разработка, все изменения агентов и пользователя | Агенты + пользователь |
| `main` | Релизное состояние — код, идентичный запущенному на проде | Только при деплое |
| `prod` | Аварийный фолбек — предыдущий `main` | Только при деплое |

**Почему:** `main` = код на проде. Если на проде `git pull` случайно дёрнет `dev` — ничего не сломается. Если нужно откатиться — `prod` содержит последнюю стабильную версию.

## Decision Authority

- **Деплой — только по команде пользователя.** Агент никогда не начинает деплой сам.
- Агент может сделать **pre-deploy review** по запросу пользователя или когда видит, что работы по активным TZ завершены.
- Пользователь может в любой момент сказать «стоп» или «откат».

---

## Pre-Deploy Review

Выполняется агентом перед тем, как пользователь даст команду на деплой.

### 1. TZ Checklist

- Все активные TZ в `docs/` закрыты (checklist полностью checked).
- Либо пользователь явно указал: «игнорировать TZ-X», «закрыть через силу».

### 2. Git State

Все деплоимые репозитории на `dev`, `git status --short` пуст (или содержит только осознанно исключённые артефакты):

```
git -C SyncServer status --short
git -C Warehouse_web status --short
git -C Warehouse_frontend status --short
```

### 3. Tests

| Репозиторий | Команда | Критерий |
|---|---|---|
| `SyncServer/` | `python -m pytest` | 0 failed |
| `Warehouse_web/` | `python manage.py test` | 0 failed |
| `Warehouse_frontend/` | `npm run build` | Успешный билд (style warnings допустимы) |

### 4. Migration Dry-Run

Проверить, какие миграции ждут применения:

```bash
# SyncServer
docker compose exec syncserver python -m alembic current
docker compose exec syncserver python -m alembic upgrade head --sql | head -50

# Warehouse_web
docker compose exec warehouse_web python manage.py showmigrations --plan | grep '\[ \]'
```

### 5. Dev Stand Health

```bash
make status
# Все эндпоинты отвечают, Postgres healthy
```

---

## Production Deploy Workflow

**Только по команде пользователя.** Порядок строгий.

### Шаг 1: Backup БД

На VPS, до любых изменений:

```bash
mkdir -p ~/backups
docker exec pg-main pg_dump -U appuser syncserver_main > ~/backups/syncserver_main_$(date +%Y%m%d_%H%M%S)_predeploy.sql
docker exec pg-main pg_dump -U appuser warehouse_web_db > ~/backups/warehouse_web_db_$(date +%Y%m%d_%H%M%S)_predeploy.sql
ls -lh ~/backups/
```

### Шаг 2: Angular Build → Warehouse_web

На dev-стенде:

```bash
cd Warehouse_frontend && npm run build
rm -rf ../Warehouse_web/angular_static/*
cp -r dist/warehouse-frontend/browser/* ../Warehouse_web/angular_static/
cd ../Warehouse_web
git add angular_static/
git commit -m "chore(deploy): update Angular static build for production"
```

Пользователь пушит коммит в `origin/dev`.

### Шаг 3: Сохранить фолбек на VPS

```bash
cd ~/SyncServer && git branch -f prod main
cd ~/Warehouse_web && git branch -f prod main
```

### Шаг 4: Git pull dev → main на VPS

```bash
cd ~/SyncServer
git checkout main
git pull origin dev   # или git reset --hard origin/dev если истории разошлись

cd ~/Warehouse_web
git checkout main
git pull origin dev
```

### Шаг 5: Пересборка контейнеров

```bash
cd ~/SyncServer && docker compose up -d --build
cd ~/Warehouse_web && docker compose up -d --build
```

### Шаг 6: Миграции

```bash
cd ~/SyncServer
docker compose exec syncserver python -m alembic upgrade head

cd ~/Warehouse_web
docker compose exec web python manage.py migrate --noinput
```

### Шаг 7: Конвертация временных ТМЦ (если применимо)

```bash
cd ~/SyncServer
docker compose exec syncserver python scripts/batch_convert_temporary_items.py --dry-run
docker compose exec syncserver python scripts/batch_convert_temporary_items.py
```

### Шаг 8: Health-Check

```bash
curl -sk https://horizonstorage.ru/api/v1/health
# → {"status":"ok"}

curl -sk -o /dev/null -w "%{http_code}" https://horizonstorage.ru/healthz/
# → 200

docker ps
# Все контейнеры up: syncserver, warehouse_web, nginx_gateway, nextcloud, pg-main
```

### Шаг 9: Очистка

```bash
docker builder prune -a -f
```

---

## Angular Strategy

**Option C — bake into Django image.** Никаких volume-маунтов, никакого Node.js на проде.

- Ангуляр билдится **на dev-стенде** (шаг 2 деплоя).
- Результат коммитится в `Warehouse_web/angular_static/`.
- `Warehouse_web/Dockerfile` содержит `COPY . .` — статика попадает в образ.
- На VPS в `.env`: `FRONTEND_BUILD_DIR=/app/angular_static`, `FRONTEND_MODE=build`.
- В `.gitignore` `angular_static/` **не игнорируется** — это отслеживаемые файлы.

---

## Rollback

При критическом сбое:

```bash
# Вернуть код на prod (предыдущий стабильный)
cd ~/SyncServer
git checkout prod
docker compose up -d --build

cd ~/Warehouse_web
git checkout prod
docker compose up -d --build

# Восстановить БД если миграции повредили данные
docker exec -i pg-main psql -U appuser -d syncserver_main < ~/backups/syncserver_main_*_predeploy.sql
```

После отката — доработка на dev-стенде, затем повторный деплой.

---

## SSH Access

- Агент **не хранит** SSH-ключи, пароли, IP-адреса, пути к ключам в правилах или коде.
- Если агенту нужен доступ к VPS — **запрашивает у пользователя**.
- Пользователь предоставляет доступ: путь к ключу, jump-host, или временный туннель.

---

## VPS Environment Variables

Имена переменных (значения — только у пользователя, агент не читает/не хранит):

- `DATABASE_URL`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`
- `FRONTEND_BUILD_DIR`
- `FRONTEND_MODE`

---

## VPS Architecture (справочно)

| Сервис | Контейнер | Доступ |
|---|---|---|
| SyncServer API | `syncserver` | `http://syncserver:8000` внутри backend-сети |
| Django | `warehouse_web` | `http://warehouse_web:8000` (gunicorn, 3 workers) |
| Nginx | `nginx_gateway` | `:80/:443` → проксирует `/api/` на syncserver, `/` на Django |
| PostgreSQL | `pg-main` | `127.0.0.1:5432`, БД: `syncserver_main`, `warehouse_web_db`, `nextcloud` |

**Сети:** все сервисы в общей Docker-сети `backend` (external). Nginx резолвит имена контейнеров через встроенный Docker DNS (`resolver 127.0.0.11`).

**Расположение:** все репозитории в `~/` пользователя на VPS. Каждый сервис имеет свой `docker-compose.yml`.
