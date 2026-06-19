# Scope: Интеграция Playwright E2E-тестов в пайплайн

**Date:** 2026-06-19
**Decision Makers:** Architect + Пользователь

## Problem

В проекте есть 7 документов пользовательских сценариев (`docs/user_scenario/`) и 12 spec-файлов Playwright в `Warehouse_frontend/e2e/`. Но:

- Playwright запускается **только локально** через `npm run test:e2e` — нет интеграции в CI/CD
- Нет Docker-сервиса Playwright — тесты гоняются на хосте
- Нет GitHub Actions workflow
- Нет Makefile-цели для e2e
- Сценарии описывают новые экраны (Balances, Issue Repository, Unaccepted Repository), для которых тестов ещё нет
- Test data strategy не формализована

Пользователь хочет: «написать и встроить в пайплайн playwright тесты» — end-to-end через все сервисы (Angular → Django → SyncServer → PostgreSQL), запуск перед деплоем и важными изменениями.

## In Scope

1. **Инфраструктура запуска Playwright в Docker**
   - Docker-сервис Playwright в `docker-compose.yml`
   - Playwright Docker образ с Chromium
   - Сеть Docker для связи между сервисами
   - Health-check ожидание всех сервисов перед тестами

2. **Makefile-интеграция**
   - `make test-e2e` — запуск Playwright-тестов
   - `make test-e2e-report` — открыть HTML-отчёт
   - `make test-e2e-headed` — headed-режим для отладки

3. **Стратегия тестовых данных**
   - Fresh DB per run: миграции + seed через API
   - Test fixture пользователей для каждой роли (root, chief, storekeeper, observer)
   - Атомарные тесты: каждый spec создаёт нужные данные сам
   - Очистка после прогона (опционально)

4. **Организация тестов по сценариям**
   - Маппинг существующих spec ↔ разделы сценариев
   - Новые spec для Balances, Issue Repository, Unaccepted Repository
   - Стандартизация `data-testid` из сценариев

5. **GitHub Actions workflow (исследование/настройка)**
   - Проверить доступность GitHub Actions для репозитория
   - При доступности: workflow `e2e-tests.yml`
   - При недоступности: документация по ручному запуску

6. **Отчётность**
   - Playwright HTML reporter (уже настроен)
   - Trace и video retention on failure
   - Артефакты для CI-логов

## Out Of Scope

- Покрытие 100% сценариев в первой итерации
- Интеграция с Jenkins/GitLab CI/другими CI-системами (только GitHub Actions)
- Нагрузочное тестирование
- Тестирование мобильной версии
- Visual regression testing
- Интеграция Playwright с pre-commit hooks (оставляем на будущее)

## Success Criteria

1. `make test-e2e` запускает все Playwright-тесты в Docker и возвращает код выхода
2. Существующие 12 spec-файлов проходят успешно в Docker-окружении
3. Появляется минимум 3 новых spec-файла для новых экранов (Balances, Issue Repo, Unaccepted Repo)
4. HTML-отчёт генерируется и доступен локально
5. Если GitHub Actions доступен: workflow проходит в CI
6. Документация по запуску обновлена в `AGENTS.md` и/или `README.md`

## Assumptions

| Assumption | Status | Validation |
|---|---|---|
| Playwright Docker-образ (`mcr.microsoft.com/playwright:v1.60.0-jammy`) совместим с окружением | Reasonable | Проверить при первом запуске |
| Docker-сеть `warehouse-solution_default` доступна Playwright-контейнеру | Reasonable | Проверить `docker compose` networking |
| Стенд может быть поднят с нуля за <2 минут (миграции + seed) | Reasonable | Замерить время `make up && make migrate` |
| GitHub Actions доступен для private репозитория (с лимитами) | Dangerous | Проверить вкладку Actions на GitHub |
| Существующие spec используют `data-testid` из сценариев | Reasonable | Сверить spec-файлы с testid в сценариях |
| База данных может быть пересоздана для тестов (dev-стенд) | Validated | Уже делается в `make clean` |

## Alternatives Considered

| Approach | Verdict | Reason |
|---|---|---|
| **Do nothing** (оставить только локальный `npm run test:e2e`) | ❌ | Не решает задачу пользователя — нужен пайплайн |
| **Playwright on host** (гонять тесты локально, без Docker) | ❌ | Не воспроизводимо в CI, не соответствует пожеланию пользователя |
| **Playwright как Docker-сервис** (в docker-compose) | ✅ **Выбрано** | Воспроизводимо локально и в CI, изолированно, естественно для dev-стенда |
| **Playwright в GitHub Actions без Docker-стенда** (мокировать API) | ❌ | Противоречит требованию «end-to-end все сервисы» |
| **Отдельный docker-compose для тестов** (разделение dev и test) | ❌ | Избыточно для MVP, дублирует конфигурацию |

## Selected Approach

**Playwright как Docker-сервис в существующем `docker-compose.yml`.**

- Добавляется сервис `playwright` с образом `mcr.microsoft.com/playwright:v1.60.0-jammy`
- Playwright контейнер монтирует `./Warehouse_frontend` и запускает `npx playwright test`
- Playwright обращается к `warehouse_web:8001` (Docker internal network), а не `localhost:8001`
- `baseURL` в конфиге переопределяется через `E2E_BASE_URL` env var
- Makefile цель `make test-e2e` оркестрирует: поднять стенд → дождаться health → запустить playwright → собрать отчёт
- Test data: перед прогоном применяются миграции, затем тесты создают данные через BFF API (seed helpers)

## First Slice

**Инфраструктура + верификация существующих тестов.**

1. Добавить Playwright-сервис в `docker-compose.yml`
2. Добавить `make test-e2e` и `make test-e2e-report` в Makefile
3. Настроить `playwright.config.ts` для работы через Docker (E2E_BASE_URL=http://warehouse_web:8001)
4. Запустить существующие 12 spec в Docker — убедиться что проходят
5. Создать GitHub Actions workflow (если доступен)
6. Документировать процесс запуска

Намеренно исключено из первого слайса:
- Новые spec для Balances / Issue Repo / Unaccepted Repo (второй слайс)
- Второй слайс = покрытие новых экранов тестами

## Next Step

Создать **TZ в архитектурном режиме** (Architect mode) с детальным планом реализации первого слайса.
