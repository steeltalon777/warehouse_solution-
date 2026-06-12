# TZ: Деплой Warehouse 3.0 на прод (horizonstorage.ru)

## Execution Checklist

- [x] 0. Преддеплойная верификация на dev (D1-D6 решены) — повторно подтверждено 2026-06-12, см. Evidence ниже
- [ ] 0a. Release freeze: закоммитить и запушить все deploy-owned изменения из `dev`, исключить локальные артефакты/секреты
- [ ] 1. Бэкап продовой БД
- [ ] 2. Git pull dev → main на проде
- [ ] 3. Пересборка Docker-образов
- [ ] 4. Применение миграций Alembic
- [ ] 5. Запуск сервисов
- [ ] 5a. Конвертация временных ТМЦ → постоянные
- [ ] 6. Health-check и верификация
- [ ] 7. Обновление Angular-статики
- [ ] 8. Очистка Docker build cache
- [ ] 9. Постдеплойная верификация

## Check Rules

- Executor: пользователь (makc) — только ручной деплой.
- Агенты не выполняют запись на прод.
- Перед каждым шагом — подтверждение пользователя.
- При ошибке миграций — откат к бэкапу.

---

## 0a. Release freeze перед ручным деплоем

**Статус на 2026-06-12:** dev-стенд проходит финальные проверки, но деплой разрешён только после фиксации release-кандидата в git.

Перед шагом 1 пользователь вручную подтверждает, что:

- root workspace находится на ветке `dev`;
- `SyncServer`, `Warehouse_web`, `Warehouse_frontend` находятся на ветке `dev`;
- deploy-owned изменения закоммичены и запушены в `dev` во всех вложенных репозиториях;
- на проде `git pull origin dev` подтянет именно проверенный release-кандидат;
- не попадают в коммит/деплой локальные секреты и артефакты:
  - `.env`;
  - `Warehouse_web/media/documents/pdf/*.pdf`;
  - локальные Playwright/smoke snapshots вроде `*-snapshot.md`, `*-smoke*.png`, `login-form.md`, `search-electronics.md`.

Рекомендуемая локальная проверка перед push:

```bash
git status --short
git -C SyncServer status --short
git -C Warehouse_web status --short
git -C Warehouse_frontend status --short
git -C SyncServer log --oneline -3
git -C Warehouse_web log --oneline -3
git -C Warehouse_frontend log --oneline -3
```

**Нельзя начинать прод-деплой**, если нужные изменения есть только локально на dev-стенде и не доступны прод-серверу через `git pull origin dev`.

---

## 0. Преддеплойная верификация (dev-стенд)

Убедиться, что на dev-стенде:
- [x] 4 failing Django-теста починены — `docker compose exec -T warehouse_web python manage.py test`, 296 tests OK, 2026-06-12
- [x] SyncServer test suite проходит — `docker compose exec -T syncserver python -m pytest`, 386 passed / 2 skipped / 5 deselected / 7 xfailed, 2026-06-12
- [x] Ошибки балансов исправлены — регрессия покрыта полным SyncServer suite и stand smoke, 2026-06-12
- [x] Functional and WorkLogik.md актуализирован — проверены разделы II, IV, VI, VII, VIII; текущие операции/каталог соответствуют целевым правилам
- [x] PostgreSQL совместимость dev-стенда проверена — текущий стенд `postgres:15-alpine`, `alembic current` = `8e9a044a0fcf (head)`; для прода PostgreSQL 16 оставить отдельный ручной контроль после бэкапа
- [x] Dev-образы/стенд smoke пройдены — `make status`, health endpoints, HTTP smoke и Playwright smoke, 2026-06-12

### Evidence 2026-06-12

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Git branch gate | `git branch --show-current`; nested `git -C ... branch --show-current` | pass with notes | root, `SyncServer`, `Warehouse_web`, `Warehouse_frontend`, `Warehouse_client_core` on `dev`; `WarehouseAIWorkstation` on `main` but paused/out of deploy scope |
| Dirty tree gate | `git status --short`; nested statuses | blocked until release commit | local dirty/untracked files exist; deploy must wait until intended changes are committed/pushed and local `.env`/artifacts excluded |
| SyncServer tests | `docker compose exec -T syncserver python -m pytest` | pass | 386 passed, 2 skipped, 5 deselected, 7 xfailed, 8 warnings in 221.73s |
| Django tests | `docker compose exec -T warehouse_web python manage.py test` | pass | 296 tests OK |
| Angular build | `CI=true NG_CLI_ANALYTICS=false npm run build` | pass with warnings | bundle generated; only existing style budget warnings on several component SCSS files |
| Alembic head | `docker compose exec -T syncserver python -m alembic current` | pass | `8e9a044a0fcf (head) (mergepoint)` |
| Stand status | `make status`; `docker compose ps` | pass | postgres healthy; syncserver/web/angular up; SyncServer HTTP 200, detailed 200, Angular 200; web `/healthz/` OK |
| HTTP smoke | `curl -fsS -L` for `/operations/`, `/nomenclature/`, `/issued-assets/`, `/admin/login/?next=/admin/` | pass | pages returned successfully on dev stand |
| UI smoke | Playwright login `admin/admin123`, open `/operations/` | pass | operations table rendered in Django shell; BFF request observed: `/bff/api/v1/operations?page=1&page_size=20&exclude_adjustments=true` => 200 |
| Recent logs | `docker compose logs --tail=120 warehouse_web syncserver | rg -i "traceback|exception|syncserver request failed|error"` | pass | no matching recent errors |

### Current release notes / late fixes included in dev verification

- `SyncServer`: operations list supports `exclude_adjustments`, while explicit `type=ADJUSTMENT` still works.
- `Warehouse_web`: BFF forwards `exclude_adjustments` to SyncServer.
- `Warehouse_frontend`: operations table hides service adjustments by default unless a type filter is selected; comment rendering falls back from `comment` to `notes`; table has internal scroll wrapper and tightened comment/date columns.
- Catalog readonly Angular alias work is present in dev history (`Warehouse_web`/`Warehouse_frontend`) and smoke-tested through navigation/sidebar availability.

### Release blocker before production

На момент проверки есть незакоммиченные изменения:

- root: `.env` modified; `docs/TZ-PROD_DEPLOY_WAREHOUSE_3.0.md` modified; untracked local smoke snapshots/artifacts; untracked `docs/TZ-CATALOG_READONLY_ANGULAR_ALIAS.md`;
- `SyncServer`: `app/repos/operations_repo.py`, `tests/test_operations_acceptance_and_issue_api.py`;
- `Warehouse_web`: `apps/bff_api/operations_views.py`, `apps/bff_api/tests.py`, untracked generated PDFs under `media/documents/pdf/`;
- `Warehouse_frontend`: operations model/service/filter/table files.

**Действие:** до прод-деплоя закоммитить только intended release changes в соответствующих репозиториях и не коммитить `.env`, PDF и локальные smoke artifacts.

---

## 1. Бэкап продовой БД

```bash
ssh makc@147.45.102.135

mkdir -p ~/backups
docker exec pg-main pg_dump -U appuser -d syncserver_main \
  > ~/backups/syncserver_main_before_deploy_$(date +%Y-%m-%d_%H-%M).sql

ls -lh ~/backups/
```

Убедиться, что файл > 1 MB.

---

## 2. Git pull dev → main на проде

```bash
cd ~/SyncServer
git checkout main
git status --short
git pull origin dev
# Ожидается fast-forward

cd ~/Warehouse_web
git checkout main
git status --short
git pull origin dev

# Если Angular живёт отдельным репозиторием/директорией на проде:
cd ~/Warehouse_frontend
git checkout main
git status --short
git pull origin dev
```

Перед pull убедиться, что на проде нет локальных незакоммиченных изменений. Если `git status --short` не пустой — остановить деплой и разобрать вручную.

---

## 3. Пересборка Docker-образов

```bash
cd ~/SyncServer
docker compose build --no-cache

cd ~/Warehouse_web
docker compose build --no-cache

# Если Angular деплоится отдельным сервисом/образом:
cd ~/Warehouse_frontend
docker compose build --no-cache
```

Если продовая конфигурация собирает Angular внутри `Warehouse_web`, отдельный build `Warehouse_frontend` не нужен; достаточно убедиться, что свежий bundle попал в Django staticfiles на шаге 7.

---

## 4. Применение миграций Alembic

```bash
cd ~/SyncServer

# Остановить syncserver (но не БД!)
docker compose down syncserver

# Запустить миграции
docker compose run --rm migrate

# Ожидаемый вывод: применение миграций от 0010 до 8e9a044a0fcf
# 7538376fd139 → 0010_add_item_review_fields → 0011_catalog_audit_fields
# → 0012_issue_objects → 0013_issue_object_categories
# → 0014_category_unique_indexes → 0015_make_category_id_not_null
# → 0016_add_merge_fields → 8e9a044a0fcf (merge)

# Проверить
docker compose run --rm migrate python -m alembic current
# Должен показать: 8e9a044a0fcf (head)
```

**Если миграции упали:**
```bash
docker compose down syncserver
# Восстановить БД из бэкапа
docker exec -i pg-main psql -U appuser -d syncserver_main < ~/backups/...
# Откатить код
cd ~/SyncServer && git checkout <старый_коммит>
cd ~/SyncServer && docker compose up -d
```

---

## 5. Запуск сервисов

```bash
cd ~/SyncServer
docker compose up -d

cd ~/Warehouse_web
docker compose up -d

# Подождать 10 секунд
sleep 10
```

---

## 5a. Конвертация временных ТМЦ в постоянные

Все старые временные ТМЦ кладовщика преобразуются в постоянные ТМЦ
(категория «Без категории», ед. изм. «шт»).

```bash
# Dry-run: посмотреть сколько будет сконвертировано
cd ~/SyncServer
docker compose exec syncserver python scripts/batch_convert_temporary_items.py --dry-run

# Применить
docker compose exec syncserver python scripts/batch_convert_temporary_items.py
```

Ожидаемый результат: `Done: N converted, 0 failed`.

---

## 6. Health-check

```bash
curl -sk https://horizonstorage.ru/healthz/
# {"status":"ok","service":"warehouse_web"}

curl -sk https://horizonstorage.ru/api/v1/health
# {"status":"ok"}

docker ps
# Все 5 контейнеров up

# Проверить отсутствие явных ошибок после старта
docker logs warehouse_web --tail 120 | grep -Ei "traceback|exception|SyncServer request failed|error" || true
docker logs syncserver --tail 120 | grep -Ei "traceback|exception|error" || true
```

---

## 7. Обновление Angular-статики

Статика должна обновиться автоматически при пересборке Warehouse_web образа (если `npm run build` и `collectstatic` в Dockerfile).

Проверить:
```bash
docker exec warehouse_web ls /app/staticfiles/js/ | grep operations
# Должен быть свежий файл с новым хешем
```

---

## 8. Очистка Docker build cache

```bash
docker builder prune -a -f
# ~12 GB reclaimable
```

---

## 9. Постдеплойная верификация

```bash
# 1. Alembic
docker exec syncserver python -m alembic current
# → 8e9a044a0fcf (head)

# 2. Новые колонки в БД
docker exec pg-main psql -U appuser -d syncserver_main -c "
SELECT column_name FROM information_schema.columns
WHERE table_name='items'
AND column_name IN ('requires_review','created_by_user_id','merged_into_id');
"
# → 3 rows

# 3. Новые таблицы
docker exec pg-main psql -U appuser -d syncserver_main -c "
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('issue_objects','issue_object_categories');
"
# → 2 rows

# 4. Ошибки в логах
docker logs warehouse_web --tail 20 | grep -c "SyncServer request failed"
# → должно быть 0 или близко к 0

# 5. Smoke через браузер
# https://horizonstorage.ru/operations/
# https://horizonstorage.ru/nomenclature/
# https://horizonstorage.ru/catalog/
# https://horizonstorage.ru/issued-assets/
# https://horizonstorage.ru/admin/

# 6. Operations BFF default filter после late fix
# В браузерной Network-вкладке для /operations/ должен быть запрос:
# /bff/api/v1/operations?...&exclude_adjustments=true -> 200
```

## Rollback

При критическом сбое:
```bash
cd ~/SyncServer
docker compose down
git checkout <старый_коммит_main>
docker compose up -d

cd ~/Warehouse_web
docker compose down
git checkout <старый_коммит_main>
docker compose up -d

# Восстановить БД
docker exec -i pg-main psql -U appuser -d syncserver_main < ~/backups/syncserver_main_before_deploy_*.sql
```
