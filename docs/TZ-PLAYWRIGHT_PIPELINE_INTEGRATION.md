# TZ: Интеграция Playwright E2E-тестов в пайплайн

## TZ

- `/home/makc/AI_sandbox/warehouse_solution/docs/TZ-PLAYWRIGHT_PIPELINE_INTEGRATION.md`

## Execution Strategy

- [ ] 🟢 Parallel execution recommended
- **Reason:** Три независимых рабочих потока: (A) Docker-инфраструктура Playwright, (B) Makefile + конфиг, (C) GitHub Actions. Единственная точка синхронизации — интеграционный прогон после сборки всех трёх компонентов. Потоки A и B можно делать параллельно, C зависит от A+B.

### Стадии

| Стадия | Потоки | Что делается | Владелец |
|---|---|---|---|
| **1. Инфраструктура** | A ∥ B | A: docker-compose playwright-сервис. B: Makefile + playwright.config.ts | Архитектор / executor |
| **2. Интеграция** | — | Прогон 12 существующих spec в Docker, фикс ошибок | Executor |
| **3. CI/CD** | C | GitHub Actions workflow | Executor |
| **4. Документация** | — | AGENTS.md, README | Executor |

---

## Execution Checklist

- [ ] 0. Context verified
- [ ] 1. Architecture boundaries confirmed
- [ ] 2. Стадия 1A: Playwright Docker-сервис в docker-compose.yml
- [ ] 3. Стадия 1B: Makefile-цели + playwright.config.ts для Docker
- [ ] 4. Стадия 2: Интеграционный прогон 12 spec в Docker, фикс ошибок
- [ ] 5. Стадия 3: GitHub Actions workflow
- [ ] 6. Стадия 4: Документация обновлена
- [ ] 7. Static checks (docker compose config, npm run build)
- [ ] 8. Stand smoke tests (make test-e2e в Docker)
- [ ] 9. UI automation tests (Playwright report)
- [ ] 10. Final acceptance review

---

## 1. Контекст и границы

### Текущее состояние

| Компонент | Статус |
|---|---|
| Playwright-тесты | 12 spec-файлов в `Warehouse_frontend/e2e/` |
| Запуск тестов | Только локально: `npm run test:e2e` |
| Docker-сервис Playwright | Отсутствует |
| Makefile-цели e2e | Отсутствуют |
| GitHub Actions | Отсутствуют |
| Покрытие сценариев | ~24% (30 из ~123 scenario ID) |
| Ролевые тесты | Пропущены (`SKIP_ROLE_TESTS = true` — нет пользователей в dev DB) |

### Целевое состояние

- `make test-e2e` запускает все Playwright-тесты в Docker против полного стека (Angular → Django → SyncServer → PostgreSQL)
- Playwright выполняется в изолированном Docker-контейнере, а не на хосте
- HTML-отчёт доступен локально
- GitHub Actions workflow запускает те же тесты в CI при push в `dev` и `main`
- Существующие 12 spec проходят без ошибок в Docker-окружении

### In Scope

1. Playwright как Docker-сервис в `docker-compose.yml`
2. Makefile-цели: `test-e2e`, `test-e2e-report`, `test-e2e-headed`
3. Адаптация `playwright.config.ts` для Docker networking
4. Исправление spec, которые падают из-за отличий Docker-окружения
5. GitHub Actions workflow `.github/workflows/e2e-tests.yml`
6. Документация в `AGENTS.md` и `Warehouse_frontend/AGENTS.md`

### Out Of Scope

- Новые spec для Balances, Issue Repository, Unaccepted Repository (второй слайс)
- Новые spec для Nomenclature CRUD, Catalog search (второй слайс)
- Создание тестовых пользователей storekeeper/chief/observer в dev-стенде (отдельная TZ)
- Раскомментирование ролевых тестов (отдельная TZ после создания пользователей)
- Pre-commit hooks
- Visual regression testing
- Параллельный запуск spec-файлов (sharding)

---

## 2. Стадия 1A: Playwright Docker-сервис

### Файлы

- `/home/makc/AI_sandbox/warehouse_solution/docker-compose.yml` — добавить сервис `playwright`
- `/home/makc/AI_sandbox/warehouse_solution/Warehouse_web/Dockerfile` — добавить `curl` (для healthcheck)
- `/home/makc/AI_sandbox/warehouse_solution/Warehouse_frontend/e2e/playwright.config.ts` — адаптировать (см. стадию 1B)

### Требования к Docker-сервису

```yaml
playwright:
  image: mcr.microsoft.com/playwright:v1.60.0-jammy
  container_name: warehouse_playwright
  working_dir: /app
  volumes:
    - ./Warehouse_frontend:/app
    - /app/node_modules          # не затирать node_modules образа
    - playwright_report:/app/playwright-report
    - playwright_test_results:/app/test-results
  environment:
    - CI=${CI:-true}
    - E2E_BASE_URL=http://warehouse_web:8001
    - E2E_SYNC_HEALTH_URL=http://syncserver:8000/api/v1/health
    # Ролевые учётные данные — передаются из .env или defaults из helpers/login.ts
    - E2E_USERNAME_ROOT=${E2E_USERNAME_ROOT:-admin}
    - E2E_PASSWORD_ROOT=${E2E_PASSWORD_ROOT:-admin123}
    - E2E_USERNAME_SPA=${E2E_USERNAME_SPA:-test_spa_user}
    - E2E_PASSWORD_SPA=${E2E_PASSWORD_SPA:-test_spa_password}
  depends_on:
    warehouse_web:
      condition: service_healthy
    syncserver:
      condition: service_started
  # command по умолчанию — заглушка. Тесты запускаются через:
  #   make test-e2e          → docker compose run --rm playwright npx playwright test ...
  #   docker compose up       → НЕ запускает тесты (контейнер сразу выходит)
  command: echo "Playwright image ready. Use 'make test-e2e' to run tests."
  networks:
    - default
```

**Дизайн-решения:**
- Образ `mcr.microsoft.com/playwright:v1.60.0-jammy` — официальный образ Microsoft с Node.js, Chromium и Playwright 1.60 (соответствует `@playwright/test: ^1.60.0` в package.json)
- `command` включает health-check ожидание Django (до 30 секунд), затем запуск тестов
- `depends_on` с `service_healthy` для warehouse_web — гарантирует что Django принял запросы
- `volumes`: монтируется `./Warehouse_frontend` для доступа к spec-файлам, `/app/node_modules` — анонимный volume чтобы не затирать node_modules из образа
- `E2E_BASE_URL=http://warehouse_web:8001` — ключевое отличие от локального `localhost:8001`
- CI=true по умолчанию — включает retries (2) в Playwright

### Top-level volumes

Необходимо добавить именованные тома в секцию `volumes:` docker-compose.yml:

```yaml
volumes:
  postgres_data:
  playwright_report:
  playwright_test_results:
```

Без этого `docker compose up` упадёт с ошибкой «undefined volume».

### Docker-сеть

Все сервисы в `docker-compose.yml` уже в сети `default` (мост `warehouse-solution_default`). Playwright-контейнер будет в той же сети и сможет обращаться к `warehouse_web:8001` и `syncserver:8000`.

### Предварительное требование: curl в Warehouse_web

Образ `python:3.11-slim` **не содержит curl**. Для healthcheck нужно:

**Вариант А (рекомендуемый):** добавить `curl` в `Warehouse_web/Dockerfile`:
```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        fontconfig \
        ...
```

**Вариант Б (без изменения Dockerfile):** использовать Python healthcheck:
```yaml
healthcheck:
  test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz/')\""]
```

### Health-check для warehouse_web

Текущий docker-compose **не определяет** `healthcheck` для `warehouse_web`. Нужно добавить:

```yaml
warehouse_web:
  # ... существующие поля ...
  healthcheck:
    test: ["CMD-SHELL", "curl -f --max-time 5 http://localhost:8001/healthz/ || exit 1"]
    interval: 10s
    timeout: 5s
    retries: 6
    start_period: 15s
```

### Acceptance Criteria для стадии 1A

- [ ] `docker compose up -d` поднимает все 5 сервисов (postgres, syncserver, warehouse_web, angular, playwright)
- [ ] `docker compose ps` показывает `warehouse_playwright` с кодом выхода 0 (или running при `command` который держит контейнер)
- [ ] `docker compose logs playwright` содержит вывод Playwright (pass/fail)
- [ ] Playwright-отчёт доступен через volume `playwright_report`

---

## 3. Стадия 1B: Makefile + playwright.config.ts

### Файлы

- `/home/makc/AI_sandbox/warehouse_solution/Makefile` — добавить цели e2e
- `/home/makc/AI_sandbox/warehouse_solution/Warehouse_frontend/e2e/playwright.config.ts` — адаптировать

### Makefile-цели

```makefile
# ----- E2E тесты -----

test-e2e: ## Запустить Playwright E2E-тесты в Docker
	@echo "$(YELLOW)🧪 Запуск Playwright E2E-тестов...$(NC)"
	@echo "$(YELLOW)⏳ Ожидание готовности стенда...$(NC)"
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		curl -s --max-time 5 http://localhost:8001/healthz/ > /dev/null 2>&1 && break; \
		echo "  Waiting for Warehouse_web..."; \
		sleep 3; \
	done
	@for i in 1 2 3 4 5; do \
		curl -s --max-time 5 http://localhost:8000/api/v1/health > /dev/null 2>&1 && break; \
		echo "  Waiting for SyncServer..."; \
		sleep 3; \
	done
	@echo "$(GREEN)✅ Стенд готов, запуск тестов...$(NC)"
	@docker compose run --rm \
		-e CI=true \
		-e E2E_BASE_URL=http://warehouse_web:8001 \
		-e E2E_SYNC_HEALTH_URL=http://syncserver:8000/api/v1/health \
		playwright \
		npx playwright test --config=e2e/playwright.config.ts
	@echo "$(GREEN)✅ E2E тесты завершены$(NC)"

test-e2e-report: ## Открыть HTML-отчёт Playwright
	@echo "$(YELLOW)📊 Открытие Playwright отчёта...$(NC)"
	@xdg-open Warehouse_frontend/playwright-report/index.html 2>/dev/null || \
		echo "Отчёт: Warehouse_frontend/playwright-report/index.html"

test-e2e-headed: ## Запустить Playwright в headed-режиме (только локально)
	@echo "$(YELLOW)🧪 Запуск Playwright в headed-режиме...$(NC)"
	@cd Warehouse_frontend && E2E_BASE_URL=http://localhost:8001 npx playwright test --config=e2e/playwright.config.ts --headed

test-e2e-ui: ## Запустить Playwright UI mode (только локально)
	@cd Warehouse_frontend && E2E_BASE_URL=http://localhost:8001 npx playwright test --config=e2e/playwright.config.ts --ui
```

**Дизайн-решения:**
- `make test-e2e` использует `docker compose run --rm` (а не `up`) — контейнер создаётся и удаляется после прогона
- Перед запуском — быстрый health-check через `curl` чтобы не ждать зря
- `make test-e2e-headed` и `make test-e2e-ui` — для локальной отладки, используют `localhost:8001`
- CI всегда `true` в Docker, retries включены

### playwright.config.ts — адаптация

Текущий конфиг уже хорош. Нужны минимальные изменения:

```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  timeout: 30000,
  retries: process.env.CI ? 2 : 0,
  globalSetup: require.resolve('./global-setup'),
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:8001',
    headless: true,
    viewport: { width: 1280, height: 720 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
  ],
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
  // Добавить: директории для артефактов
  outputDir: './test-results',
});
```

**Изменения:**
- Добавить `outputDir: './test-results'` — стандартизирует путь для Docker volumes
- Всё остальное уже корректно: `E2E_BASE_URL` env var используется, `globalSetup` делает health-пробу

### Accept Criteria для стадии 1B

- [ ] `make test-e2e` выполняет health-check и запускает тесты
- [ ] `docker compose run --rm playwright ...` возвращает код выхода 0 при успехе, ненулевой при падении
- [ ] `make test-e2e-report` показывает путь к отчёту
- [ ] Локальный `make test-e2e-headed` работает через `localhost:8001`
- [ ] Конфиг Playwright не сломан — `npx playwright test --config=e2e/playwright.config.ts --list` показывает все spec

---

## 4. Стадия 2: Интеграционный прогон и фикс

### Задача

Прогнать все 12 spec-файлов через `make test-e2e` в Docker и исправить все упавшие тесты.

### Предварительная инвентаризация spec

| Spec | Ожидаемые проблемы в Docker |
|---|---|
| `catalog-readonly.spec.ts` | Хардкод `ADMIN_CREDENTIALS`, `page.goto('/login/')` вместо `/users/login/`. Нет env var fallback. |
| `temporary-items.spec.ts` | Хардкод `CHIEF_CREDENTIALS`, `OBSERVER_CREDENTIALS`, `page.goto('/login/')` вместо `/users/login/`. Нет env var fallback. |
| `logging-smoke.spec.ts` | Использует `E2E_USERNAME_ROOT`/`E2E_PASSWORD_ROOT` env vars — OK. Путь `/users/login/` — OK. |
| `acceptance/acceptance-journal.spec.ts` | Использует `loginAsRole` из helpers — OK. Seed через BFF API — OK. |
| `acceptance/acceptance-detail.spec.ts` | Использует `loginAsRole` из helpers — OK. Ролевые тесты могут скипаться если нет chief/observer. |
| `operations/operations-journal.spec.ts` | Использует `loginAsRole(page, 'spa_user')` — OK. |
| `operations/operations-create-modal.spec.ts` | Использует `loginAsRole(page, 'spa_user')` — OK. |
| `operations/operations-submit.spec.ts` | `SKIP_ROLE_TESTS = true` — только root-тест. |
| `operations/operations-list-filters.spec.ts` | Использует `loginAsRole(page, 'spa_user')` — OK. |
| `operations/operations-draft.spec.ts` | Использует `loginAsRole(page, 'spa_user')` — OK. |
| `operations/create-operation-total-header.spec.ts` | Использует `loginAsRole(page, 'spa_user')` — OK. |
| `operations/create-operation-line-numbers.spec.ts` | Использует `loginAsRole(page, 'spa_user')` — OK. |

### Критические расхождения для исправления

#### 4.1 catalog-readonly.spec.ts

**Проблемы:**
1. `page.goto('/login/')` — путь без `/users/`. В Django может не работать.
2. `ADMIN_CREDENTIALS` — хардкод `{ username: 'admin', password: 'admin123' }`, нет env var.

**Исправления:**
- Заменить `page.goto('/login/')` на `page.goto('/users/login/')`
- Заменить `ADMIN_CREDENTIALS` на использование `ROLE_CREDENTIALS.root` из helpers (как loginAsRole)
- Или: минимально — оставить хардкод но перейти на `/users/login/`

#### 4.2 temporary-items.spec.ts

**Проблемы:**
1. `page.goto('/login/')` — та же проблема
2. `CHIEF_CREDENTIALS`, `OBSERVER_CREDENTIALS` — хардкод

**Исправления:**
- `page.goto('/login/')` → `page.goto('/users/login/')`
- Хардкод credentials заменить на `ROLE_CREDENTIALS.chief` / `ROLE_CREDENTIALS.observer` из helpers

#### 4.3 global-setup.ts — health-check в Docker

В Docker `E2E_BASE_URL` будет `http://warehouse_web:8001`, но `globalSetup` запускается в контексте Playwright (внутри контейнера). Адрес `warehouse_web:8001` должен разрешаться через Docker DNS.

**Проверить:** что `globalSetup` корректно отрабатывает health-пробы через Docker DNS. Если нет — добавить fallback на `localhost` когда DNS не резолвится.

### Процесс исправления

1. Запустить `make test-e2e`
2. Собрать все упавшие тесты из вывода
3. Для каждого упавшего spec:
   - Если проблема в URL `/login/` vs `/users/login/` → исправить
   - Если проблема в хардкоде credentials → мигрировать на helpers
   - Если проблема в Docker networking → адаптировать baseURL/health-check
   - Если проблема в seed данных → добавить skip-guard с понятным сообщением
4. Повторять до полного прохождения (или стабильного skip по уважительной причине)

### Acceptance Criteria для стадии 2

- [ ] `make test-e2e` завершается без неожиданных падений
- [ ] Все spec, которые не зависят от отсутствующих ролевых пользователей, проходят
- [ ] Ролевые spec (chief/observer/storekeeper) либо проходят, либо честно скипаются с `test.skip()` и сообщением
- [ ] Playwright HTML report генерируется без ошибок
- [ ] Ни один spec не падает с ошибкой подключения (ECONNREFUSED)

---

## 5. Стадия 3: GitHub Actions workflow

### Предварительное условие

Репозиторий **публичный** → GitHub Actions доступен **безлимитно и бесплатно**.

### Файл

Создать `/home/makc/AI_sandbox/warehouse_solution/.github/workflows/e2e-tests.yml`

### Workflow

```yaml
name: E2E Tests

on:
  push:
    branches: [dev, main]
  pull_request:
    branches: [dev, main]
  workflow_dispatch:  # ручной запуск из GitHub UI

jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Docker Compose
        run: docker compose version

      - name: Create .env file
        run: |
          cat > .env << 'ENVEOF'
          POSTGRES_DB=warehouse
          POSTGRES_USER=warehouse_user
          POSTGRES_PASSWORD=warehouse_pass
          DJANGO_ENV=development
          DJANGO_SETTINGS_MODULE=config.settings
          SECRET_KEY=ci-test-secret-key-not-for-production
          DEBUG=True
          ALLOWED_HOSTS=127.0.0.1,localhost,warehouse_web
          DB_ENGINE=django.db.backends.postgresql
          DB_NAME=warehouse
          DB_USER=warehouse_user
          DB_PASSWORD=warehouse_pass
          DB_HOST=postgres
          DB_PORT=5432
          SYNC_SERVER_URL=http://syncserver:8000/api/v1
          FRONTEND_MODE=dev
          FRONTEND_DEV_SERVER_URL=http://angular:4200
          LOG_LEVEL=INFO
          LOG_FORMAT=console
          DATABASE_URL=postgresql://warehouse_user:warehouse_pass@postgres:5432/warehouse
          SYNC_ROOT_USER_TOKEN=ci-root-token-placeholder
          SYNC_DEVICE_TOKEN=ci-device-token-placeholder
          E2E_USERNAME_ROOT=admin
          E2E_PASSWORD_ROOT=admin123
          E2E_USERNAME_SPA=test_spa_user
          E2E_PASSWORD_SPA=test_spa_password
          ENVEOF

      - name: Build and start services
        run: |
          docker compose up -d --build postgres syncserver warehouse_web angular
          echo "Waiting for services to be healthy..."
          for i in $(seq 1 30); do
            if curl -s --max-time 3 http://localhost:8001/healthz/ > /dev/null 2>&1; then
              echo "Warehouse_web healthy"
              break
            fi
            echo "Waiting... ($i/30)"
            sleep 3
          done

      - name: Run migrations
        run: |
          docker compose exec -T syncserver python -m alembic upgrade head
          docker compose exec -T warehouse_web python manage.py migrate
          docker compose exec -T warehouse_web python manage.py create_initial_superuser || true
          docker compose exec -T syncserver python scripts/bootstrap_root.py || true

      - name: Run Playwright tests
        run: |
          docker compose run --rm \
            -e CI=true \
            -e E2E_BASE_URL=http://warehouse_web:8001 \
            -e E2E_SYNC_HEALTH_URL=http://syncserver:8000/api/v1/health \
            -e E2E_USERNAME_ROOT=admin \
            -e E2E_PASSWORD_ROOT=admin123 \
            -e E2E_USERNAME_SPA=test_spa_user \
            -e E2E_PASSWORD_SPA=test_spa_password \
            playwright \
            npx playwright test --config=e2e/playwright.config.ts

      - name: Upload Playwright report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: Warehouse_frontend/playwright-report/
          retention-days: 7

      - name: Upload test results
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-test-results
          path: Warehouse_frontend/test-results/
          retention-days: 7

      - name: Docker logs on failure
        if: failure()
        run: |
          docker compose logs syncserver --tail=50
          docker compose logs warehouse_web --tail=50
```

**Дизайн-решения:**
- `runs-on: ubuntu-latest` — GitHub-hosted раннер с Docker
- `.env` создаётся из секретов/плейсхолдеров. **Важно:** `SYNC_ROOT_USER_TOKEN` и `SYNC_DEVICE_TOKEN` — плейсхолдеры, для CI нужны реальные или bootstrap должен их генерировать
- `workflow_dispatch` — ручной запуск для тестирования без push
- `timeout-minutes: 20` — достаточный запас для сборки и тестов
- Артефакты отчёта сохраняются всегда (`if: always()`), трейсы — только при падении (`if: failure()`)
- Логи SyncServer и Django при падении для отладки

### Примечание по токенам

В dev-стенде bootstrap_root.py генерирует root-токен и сохраняет в БД. Django-клиент использует этот токен через `SYNC_ROOT_USER_TOKEN`. В CI нужно:
- Либо иметь `.env` с валидными токенами (через GitHub Secrets)
- Либо выполнять bootstrap и затем читать токен из вывода

**Рекомендация для первой итерации:** добавить в workflow шаг `bootstrap_root.py`, который выводит токен, и передавать его через environment.

### Acceptance Criteria для стадии 3

- [ ] `.github/workflows/e2e-tests.yml` существует
- [ ] Workflow проходит валидацию GitHub Actions schema
- [ ] При push в `dev` workflow запускается автоматически
- [ ] Workflow можно запустить вручную через `workflow_dispatch`
- [ ] Артефакты отчёта прикрепляются к workflow run

---

## 6. Стадия 4: Документация

### Файлы

- `/home/makc/AI_sandbox/warehouse_solution/AGENTS.md` — добавить секцию про e2e
- `/home/makc/AI_sandbox/warehouse_solution/Warehouse_frontend/AGENTS.md` — обновить секцию Dev-стенд и тестирование

### Что добавить

В корневой `AGENTS.md` (после секции `make` команд):

```markdown
| `make test-e2e` | Запустить Playwright E2E-тесты в Docker |
| `make test-e2e-report` | Открыть HTML-отчёт последнего прогона |
| `make test-e2e-headed` | Запустить тесты в headed-режиме (локально) |
```

В `Warehouse_frontend/AGENTS.md`:

```markdown
## E2E тестирование (Playwright)

Все acceptance-тесты описаны в `docs/user_scenario/` и реализованы в `Warehouse_frontend/e2e/`.

### Запуск

- `make test-e2e` — полный прогон в Docker (CI-окружение)
- `make test-e2e-headed` — headed-режим для отладки
- `make test-e2e-report` — открыть отчёт

### Структура

- `e2e/helpers/` — утилиты: логин (`loginAsRole`), seed-данные, network-guard
- `e2e/operations/` — тесты экрана «Операции»
- `e2e/acceptance/` — тесты экрана «Приёмка»
- `e2e/regression/` — регрессионные тесты (пока пусто)

### Добавление новых тестов

1. Найти scenario ID в `docs/user_scenario/`
2. Использовать `data-testid` из соответствующего раздела сценария
3. Для логина — `loginAsRole(page, 'root')` из helpers
4. Для seed-данных — функции из `helpers/seed.ts`
```

### Acceptance Criteria для стадии 4

- [ ] `AGENTS.md` упоминает `make test-e2e` в таблице команд
- [ ] `Warehouse_frontend/AGENTS.md` содержит секцию E2E тестирования
- [ ] Пути и команды в документации актуальны

---

## 7. Тестовая стратегия

### Test Ladder

| Level | Что проверяется | Команда |
|---|---|---|
| **Static checks** | `docker compose config` — валидация YAML | `docker compose config --quiet` |
| **Static checks** | TypeScript компиляция spec-файлов | `npx playwright test --list` |
| **Stand smoke** | Health-check всех сервисов | `make status` |
| **Stand smoke** | Playwright запускается и подключается | `make test-e2e` (хотя бы первые 3 spec) |
| **UI automation** | Полный прогон 12 spec | `make test-e2e` |
| **CI verification** | Workflow проходит в GitHub Actions | Push в `dev` |

### Неприменимые уровни (с обоснованием)

| Level | Почему не применяется |
|---|---|
| Unit tests | Неприменимо — это инфраструктурная TZ, а не бизнес-логика |
| Component tests | Неприменимо — нет компонентов для тестирования |
| DB integration (отдельно) | Покрывается stand smoke (тесты сами используют БД) |

### Stand requirements

- **База данных:** PostgreSQL в Docker, миграции Alembic + Django
- **Seed данные:** тесты создают данные через BFF API (seed helpers)
- **Сервисы:** postgres, syncserver, warehouse_web, angular — все через `docker compose`
- **Health checks:** `/api/v1/health` (SyncServer), `/healthz/` (Django)
- **Переменные окружения:** `E2E_BASE_URL`, `CI`, `E2E_USERNAME_*`, `E2E_PASSWORD_*`
- **Очистка:** `docker compose down` останавливает стенд. База сохраняется в volume.

---

## 8. Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
| Playwright-образ несовместим с node_modules из volume | Средняя | Высокое | Использовать анонимный volume для `/app/node_modules` |
| Хардкод `page.goto('/login/')` в catalog-readonly и temporary-items ломает тесты в Docker | Высокая | Среднее | Исправить пути и credentials в стадии 2 |
| `SYNC_ROOT_USER_TOKEN` не валиден в CI | Высокая | Высокое | Генерировать токен через `bootstrap_root.py` или GitHub Secrets |
| Angular dev server не успевает собраться в CI | Средняя | Среднее | Увеличить `start_period` и timeout ожидания |
| GitHub Actions раннер не поддерживает Docker Compose v2 | Низкая | Среднее | Использовать `docker compose` (без дефиса), ubuntu-latest имеет его |
| Ролевые пользователи (chief/storekeeper/observer) не существуют в БД | Высокая | Низкое | Тесты уже скипаются с `SKIP_ROLE_TESTS=true` |

---

## 9. Критерии приёмки (общие)

- [ ] `docker compose up -d` поднимает 5 сервисов, включая playwright
- [ ] `make test-e2e` выполняет полный прогон 12 spec-файлов
- [ ] Playwright HTML-отчёт генерируется в `Warehouse_frontend/playwright-report/`
- [ ] `make test-e2e-headed` работает локально
- [ ] GitHub Actions workflow существует и валиден
- [ ] Документация обновлена
- [ ] Ни один spec не падает с ошибкой подключения
- [ ] Хардкод credentials заменён на helpers где возможно

---

## 10. Порядок выполнения стадий

```
Стадия 1A (docker-compose)  ←→  Стадия 1B (Makefile + config)
                ↘            ↙
              Стадия 2 (интеграционный прогон + фикс)
                    ↓
              Стадия 3 (GitHub Actions)
                    ↓
              Стадия 4 (документация)
```

Стадии 1A и 1B можно делать параллельно — они не конфликтуют по файлам:
- 1A трогает `docker-compose.yml`
- 1B трогает `Makefile` и `playwright.config.ts`

---

## Check Rules

- Architect создаёт checklist и acceptance criteria.
- Executor agents проверяют implementation и test items только после запуска верификации.
- QA verifier проверяет final acceptance только после review evidence.
- Если проверка пропущена — остаётся незакрытой с причиной.
