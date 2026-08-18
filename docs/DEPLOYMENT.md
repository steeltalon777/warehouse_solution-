# Deployment Rules — Warehouse Solution

> Загружается только при деплое. Не засоряет контекст разработки.

## Branch Roles

| Ветка | Назначение | Кто меняет |
|---|---|---|
| `dev` | Разработка, все изменения агентов и пользователя | Агенты + пользователь |
| `main` | Релизное состояние (историческое) | Только при деплое |
| `prod` | Deploy source прода: production checkout/build на VPS | Только при деплое/горячем фиксе |

**Почему (hotfix #23):** production checkout application-репозиториев на VPS (`~/SyncServer`, `~/Warehouse_web`) работает из ветки `prod`. Перед каждым деплоем фиксируется предыдущий prod SHA — это rollback point. В `prod` попадает только утверждённый проверенный набор коммитов (fast-forward), без merge незавершённых dev-изменений.

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

### 6. Angular Build Freshness (pre-deploy gate)

Убедиться, что Angular-билд в `Warehouse_web/angular_static/` **актуальный** и соответствует dev-стенду:

```bash
# На dev-стенде
stat -c '%Y' Warehouse_frontend/dist/warehouse-frontend/browser/index.html
# Должен быть сегодняшней датой

# В Warehouse_web (должен совпадать)
stat -c '%Y' Warehouse_web/angular_static/index.html
```

Если даты не совпадают или билд старый — повторить `npm run build` и скопировать заново.

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

**Проверить перед push:**
```bash
# Убедиться, что билд свежий (дата сегодняшняя)
ls -la angular_static/index.html
# Сравнить с dev-стендом — НЕ должно быть старого билда с прошлого деплоя
stat -c '%Y' angular_static/index.html
```

**⚠️ Критично:** Без этого шага на проде останется старый Angular-билд, даже если Django-код новый.
Дефолтный `FRONTEND_BUILD_DIR=/app/angular_static` в образе — без volume-маунтов на VPS.

### Шаг 3: Зафиксировать rollback point на VPS

Перед обновлением ветки `prod` записать текущие SHA и образы application-сервисов
(см. журнал в `docs/TZ-HOTFIX_PROD_DIAGNOSTICS.md` и preflight-процедуру):

```bash
git -C ~/SyncServer rev-parse prod && git -C ~/Warehouse_web rev-parse prod
docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | grep -E "syncserver|warehouse_web"
```

### Шаг 4: Обновить ветку prod на VPS (fast-forward до проверенного коммита)

```bash
cd ~/SyncServer
git fetch origin
git checkout prod
git merge --ff-only <verified_sha>   # или git pull --ff-only origin prod

cd ~/Warehouse_web
git fetch origin
git checkout prod
git merge --ff-only <verified_sha>
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
# Вернуть код на предыдущий зафиксированный prod SHA (rollback point)
cd ~/SyncServer
git checkout prod
git reset --hard <previous_prod_sha>
docker compose up -d --build

cd ~/Warehouse_web
git checkout prod
git reset --hard <previous_prod_sha>
docker compose up -d --build

# Восстановить БД если миграции повредили данные (только по отдельному решению)
docker exec -i pg-main psql -U appuser -d syncserver_main < ~/backups/syncserver_main_*_predeploy.sql
```

После отката — доработка на dev-стенде, затем повторный деплой.

---

### Admin Hardening Gate (v3.1F)

Starting from v3.1F, all Django Admin management routes require active superuser + POST + CSRF.

**Deployment order:**

1. Build and tag new SyncServer + Warehouse_web images. Do NOT switch traffic.
2. Run `python manage.py audit_admin_security --mode pre-scrub` with new Warehouse_web image against current schema. Save redacted inventory (IDs/key paths/counts only) as deployment evidence.
3. Create encrypted PostgreSQL backup. Document owner, retention, deletion date.
4. Deploy SyncServer additive changes (ensure endpoint, root-only policy).
5. Run `python manage.py migrate` (applies 0012_scrub_sync_payload_secrets and 0013_align_site_mirror_contract).
6. Run `python manage.py audit_admin_security --fail-on-findings`. Any blocker = NO-GO.
7. Only on exit code 0: switch Warehouse_web traffic to new image.
8. Perform stand smoke and Playwright admin scenarios.

**Rollback rules:**
- Return to pre-hardening Warehouse_web without external `/admin/` block is forbidden.
- Scrub migration 0012 is irreversible — payload secrets are intentionally not restored.
- Additive SyncServer endpoints may remain after Django rollback.
- Root-only mutation policy must not be relaxed during rollback.

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
