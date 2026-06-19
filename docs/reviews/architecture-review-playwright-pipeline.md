# Architecture Review — Playwright Pipeline Integration

**Date:** 2026-06-19
**Reviewer:** Architect

## Verdict
🔴 **Revisions required** — 2 блокера должны быть исправлены в TZ перед реализацией.

---

## 🔴 Blockers

### 1. Healthcheck warehouse_web: curl не установлен в образе

- **Checklist item:** Operability — health-check для Docker
- **Issue:** TZ (строка 150) определяет healthcheck для warehouse_web:
  ```yaml
  test: ["CMD-SHELL", "curl -f --max-time 5 http://localhost:8001/healthz/ || exit 1"]
  ```
  Но `Warehouse_web/Dockerfile` (строка 1) базируется на `python:3.11-slim`, в котором **нет curl**. Healthcheck всегда будет падать с `curl: not found`, и `depends_on: service_healthy` для playwright никогда не выполнится.
- **Impact:** Playwright-сервис не запустится — `docker compose up` зависнет в ожидании healthcheck.
- **Recommendation:** Добавить `curl` в `apt-get install` в `Warehouse_web/Dockerfile`:
  ```dockerfile
  RUN apt-get update \
      && apt-get install -y --no-install-recommends \
          curl \
          fontconfig \
          ...
  ```
  **Альтернатива:** использовать Python-based healthcheck:
  ```yaml
  test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz/')\""]
  ```

### 2. Docker volumes не объявлены в top-level секции

- **Checklist item:** Operability — docker compose config должен быть валидным
- **Issue:** TZ (строки 99-100) ссылается на named volumes `playwright_report` и `playwright_test_results` в сервисе playwright, но они не добавлены в top-level `volumes:` секцию docker-compose.yml. Текущий `volumes:` содержит только `postgres_data:`.
- **Impact:** `docker compose config` вернёт ошибку, `docker compose up` упадёт.
- **Recommendation:** Добавить в top-level `volumes:` секцию docker-compose.yml:
  ```yaml
  volumes:
    postgres_data:
    playwright_report:
    playwright_test_results:
  ```

---

## 🟡 Warnings

### 3. Хардкод credentials в GitHub Actions workflow

- **Checklist item:** Security — secrets management
- **Issue:** GitHub Actions workflow (TZ строки 400-403) содержит plain-text пароли `admin123`, `test_spa_password` в шаге `Create .env file`. Для **публичного репозитория** это означает что любой читатель видит тестовые учётные данные.
- **Impact:** Низкий — это dev-credentials, такие же defaults как в `helpers/login.ts` и `make reset-django-admin`. Но best practice — использовать GitHub Secrets.
- **Recommendation:** Заменить на `${{ secrets.E2E_PASSWORD_ROOT }}` с fallback-значениями. В первой итерации допустимо оставить как есть (для скорости), но добавить TODO-комментарий.

### 4. Playwright-сервис: конфликт command и docker compose run

- **Checklist item:** Complexity — ясность ответственности
- **Issue:** В TZ playwright-сервис имеет `command` который запускает тесты (строки 115-125), но Makefile использует `docker compose run --rm playwright npx playwright test...` (строка 197) — переопределяет command. Два пути запуска тестов могут запутать.
- **Impact:** Низкий — `docker compose run` всегда переопределяет command. Но разработчик может случайно запустить `docker compose up playwright` и получить неожиданный результат.
- **Recommendation:** Убрать `command` из сервиса, заменив на `command: ["echo", "Playwright service ready. Use 'make test-e2e' or 'docker compose run --rm playwright npx playwright test...'"]`. Или явно документировать что `docker compose up` НЕ запускает тесты.

### 5. global-setup.ts: разное поведение health-check в Docker

- **Checklist item:** Failure Modes — graceful degradation
- **Issue:** `global-setup.ts` делает HTTP-запросы к `E2E_BASE_URL` и `E2E_SYNC_HEALTH_URL`. В Docker эти URL резолвятся через Docker DNS (`warehouse_web:8001` вместо `localhost:8001`). Если DNS не резолвится (редкий случай), globalSetup выдаст warning и продолжит, но сами тесты упадут.
- **Impact:** Низкий — Docker DNS надёжен в compose-сетях.
- **Recommendation:** Не требует немедленного действия. Добавить в TZ примечание что `global-setup.ts` уже обрабатывает ошибки и не прерывает тесты.

---

## 🔵 Notes

### 6. Отсутствие параллельного sharding

- **Checklist item:** Scalability
- **Note:** 12 spec-файлов выполняются последовательно в одном Chromium worker. При росте количества тестов время прогона может стать проблемой. Playwright поддерживает sharding (`--shard=1/3`), Docker Compose позволяет запустить несколько контейнеров.
- **Recommendation:** Не блокирует — отложить до момента когда прогон занимает >5 минут.

### 7. Нет CI-уведомлений о падении тестов

- **Checklist item:** Observability
- **Note:** GitHub Actions workflow не содержит шага уведомлений (Slack, email) при падении. Без этого разработчик узнает о проблеме только зайдя в GitHub.
- **Recommendation:** В первой итерации не критично. Добавить `if: failure()` шаг с GitHub Issue creation или Slack webhook во втором слайсе.

### 8. Не указан playwright.config.ts для CI

- **Checklist item:** Operability
- **Note:** TZ упоминает `playwright.config.ts` адаптацию (добавить `outputDir`), но не указывает что для CI может понадобиться отдельный проект (например, `CI=true` включает retries — это уже есть). Разницы между dev и CI конфигурацией нет.
- **Recommendation:** Ок, текущий дизайн покрывает оба случая через `process.env.CI`.

---

## Резюме

| Класс | Количество | Действие |
|---|---|---|
| 🔴 Blocker | 2 | Исправить в TZ перед реализацией |
| 🟡 Warning | 3 | Принять к сведению, добавить TODO |
| 🔵 Note | 3 | Документировать, не блокирует |

**Необходимые правки TZ:**
1. Добавить `curl` в `Warehouse_web/Dockerfile` (или Python-healthcheck)
2. Добавить `playwright_report:` и `playwright_test_results:` в top-level `volumes:`
3. (Опционально) Заменить `command` в playwright-сервисе на заглушку
