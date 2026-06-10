# TZ: Деплой Warehouse 3.0 на прод (horizonstorage.ru)

## Execution Checklist

- [ ] 0. Преддеплойная верификация на dev (D1-D6 решены)
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

## 0. Преддеплойная верификация (dev-стенд)

Убедиться, что на dev-стенде:
- [ ] 4 failing Django-теста починены
- [ ] SyncServer test suite проходит
- [ ] Ошибки балансов исправлены
- [ ] Functional and WorkLogik.md актуализирован
- [ ] PostgreSQL 16 совместимость проверена
- [ ] Dev-образы пересобраны, smoke пройден

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
git pull origin dev
# Ожидается fast-forward

cd ~/Warehouse_web
git checkout main
git pull origin dev
```

---

## 3. Пересборка Docker-образов

```bash
cd ~/SyncServer
docker compose build --no-cache

cd ~/Warehouse_web
docker compose build --no-cache
```

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
# https://horizonstorage.ru/issued-assets/
# https://horizonstorage.ru/admin/
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
