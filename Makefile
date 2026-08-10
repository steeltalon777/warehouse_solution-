# Makefile для управления dev-стендом Warehouse Solution
# Одна команда для старта:  make dev

.PHONY: help up down build logs ps shell clean migrate status dev init setup bootstrap-root bootstrap-root-migrate rotate-tokens rotate-tokens-root rotate-tokens-device test-e2e test-e2e-report test-e2e-headed test-e2e-ui integrity-check

# Цвета для вывода
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m

help: ## Показать помощь
	@echo "$(GREEN)Warehouse Solution Dev Environment$(NC)"
	@echo ""
	@echo "$(YELLOW)Команды:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-18s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Примеры:$(NC)"
	@echo "  make        — запустить всё одной командой"
	@echo "  make dev    — запустить и смотреть логи"
	@echo "  make up     — запустить в фоне"
	@echo "  make down   — остановить"

# ----- Запуск / остановка -----

up: ## Запустить девстенд (все сервисы в фоне)
	@echo "$(YELLOW)🚀 Запуск dev-стенда...$(NC)"
	docker compose up -d --build
	@echo "$(GREEN)✅ Стенд запущен!$(NC)"
	@echo "$(GREEN)📦 Postgres:      :5432$(NC)"
	@echo "$(GREEN)📦 SyncServer:    http://localhost:8000$(NC)"
	@echo "$(GREEN)📦 Warehouse_web: http://localhost:8001$(NC)"
	@echo "$(GREEN)📦 Angular:       http://localhost:4200$(NC)"

down: ## Остановить девстенд
	@echo "$(YELLOW)🛑 Остановка dev-стенда...$(NC)"
	docker compose down
	@echo "$(GREEN)✅ Стенд остановлен$(NC)"

restart: down up ## Перезапустить девстенд

# ----- Сборка -----

build: ## Пересобрать все образы с нуля
	@echo "$(YELLOW)🔨 Пересборка образов (без кэша)...$(NC)"
	docker compose build --no-cache
	@echo "$(GREEN)✅ Образы собраны$(NC)"

build-sync: ## Пересобрать только SyncServer
	docker compose build --no-cache syncserver

build-web: ## Пересобрать только Warehouse_web
	docker compose build --no-cache warehouse_web

build-angular: ## Пересобрать только Angular-фронтенд
	docker compose build --no-cache angular

# ----- Логи -----

logs: ## Показать логи всех сервисов (Ctrl+C для выхода)
	docker compose logs -f

logs-sync: ## Показать логи SyncServer
	docker compose logs -f syncserver

logs-web: ## Показать логи Warehouse_web
	docker compose logs -f warehouse_web

logs-angular: ## Показать логи Angular
	docker compose logs -f angular

# ----- Shell -----

ps: ## Статус контейнеров
	docker compose ps

shell-sync: ## Зайти в Shell SyncServer
	docker compose exec syncserver /bin/bash || docker compose exec syncserver /bin/sh

shell-web: ## Зайти в Shell Warehouse_web
	docker compose exec warehouse_web /bin/bash || docker compose exec warehouse_web /bin/sh

shell-angular: ## Зайти в Shell Angular
	docker compose exec angular /bin/sh

# ----- Миграции -----

migrate-sync: ## Применить миграции SyncServer (alembic)
	docker compose exec syncserver python -m alembic upgrade head

migrate-web: ## Применить миграции Warehouse_web (Django)
	docker compose exec warehouse_web python manage.py migrate

migrate: migrate-sync migrate-web ## Применить все миграции

migrate-sync-autogen: ## Сгенерировать авто-миграцию SyncServer
	docker compose exec syncserver python -m alembic autogenerate --autogenerate

migrate-web-makemigrations: ## Создать миграции Django
	docker compose exec warehouse_web python manage.py makemigrations

sync-catalog-cache: ## Полная сверка кэша каталога с SyncServer
	docker compose exec warehouse_web python manage.py sync_catalog_cache

# ----- SyncServer скрипты -----

bootstrap-root: ## Запустить bootstrap корневого пользователя и Django устройства (SyncServer)
	docker compose exec syncserver python scripts/bootstrap_root.py

bootstrap-root-migrate: ## Запустить миграции + bootstrap корневого пользователя
	docker compose exec syncserver python scripts/bootstrap_root.py --run-migrations

rotate-tokens: ## Ротировать токены root и Django устройства (оба)
	docker compose exec syncserver python scripts/rotate_tokens.py --root --django-device

rotate-tokens-root: ## Ротировать только токен root пользователя
	docker compose exec syncserver python scripts/rotate_tokens.py --root

rotate-tokens-device: ## Ротировать только токен Django устройства
	docker compose exec syncserver python scripts/rotate_tokens.py --django-device

convert-temp-items: ## Конвертировать активные временные ТМЦ в постоянные
	docker compose exec syncserver python scripts/batch_convert_temporary_items.py

convert-temp-items-dry: ## Dry-run конвертации временных ТМЦ
	docker compose exec syncserver python scripts/batch_convert_temporary_items.py --dry-run

integrity-check: ## Read-only integrity CLI для SyncServer (TZ A-7)
	docker compose exec -T syncserver python scripts/integrity_check.py $(ARGS)

# ----- Статус -----

status: ## Показать статус контейнеров и проверить эндпоинты
	@echo "$(YELLOW)Статус контейнеров:$(NC)"
	@docker compose ps
	@echo ""
	@echo "$(YELLOW)Проверка эндпоинтов:$(NC)"
	@echo -n "SyncServer (:8000):          "
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/api/v1/health || echo "Не доступен"
	@echo -n "SyncServer detailed (:8000): "
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/api/v1/health/detailed || echo "Не доступен"
	@echo -n "Warehouse_web (:8001):      "
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8001/ || echo "Не доступен"
	@echo -n "Angular (:4200):            "
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:4200/ || echo "Не доступен"
	@echo ""
	@echo -n "Postgres:                   "
	@docker compose exec postgres pg_isready -U warehouse_user 2>/dev/null || echo "Не доступен"

# ----- Очистка -----

clean: ## Очистить всё (контейнеры + volumes + образы)
	@echo "$(RED)⚠️  ВНИМАНИЕ! Это удалит все данные и образы!$(NC)"
	@read -p "Вы уверены? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		docker compose down -v --rmi all; \
		echo "$(GREEN)✅ Очистка выполнена$(NC)"; \
	else \
		echo "$(YELLOW)Отмена$(NC)"; \
	fi

clean-dangling: ## Удалить висящие образы/контейнеры Docker
	docker system prune -f

# ----- Основные флоу -----

dev: up migrate logs ## 🚀 Запустить стенд + применить миграции + показать логи

init: ## 🆕 Первоначальная инициализация (первый запуск проекта)
	@echo "$(YELLOW)📦 Первая инициализация проекта...$(NC)"
	@echo "$(YELLOW}🔍 Проверка Docker...$(NC)"
	@docker --version > /dev/null 2>&1 || { echo "$(RED)❌ Docker не найден. Установите Docker: https://docs.docker.com/engine/install/$(NC)"; exit 1; }
	@docker compose version > /dev/null 2>&1 || { echo "$(RED)❌ Docker Compose не найден.$(NC)"; exit 1; }
	@echo "$(GREEN)✅ Docker OK$(NC)"
	@echo ""
	@echo "$(YELLOW)🔨 Сборка образов...$(NC)"
	docker compose build
	@echo ""
	@echo "$(YELLOW)📦 Запуск PostgreSQL...$(NC)"
	docker compose up -d postgres
	@echo "$(YELLOW)⏳ Ожидание готовности PostgreSQL...$(NC)"
	@sleep 3
	@docker compose exec -T postgres pg_isready -U warehouse_user > /dev/null 2>&1 || { \
		echo "$(YELLOW)⏳ Ещё ждём PostgreSQL...$(NC)"; sleep 5; \
	}
	@echo "$(GREEN)✅ PostgreSQL готов$(NC)"
	@echo ""
	@echo "$(YELLOW)🚀 Запуск всех сервисов...$(NC)"
	docker compose up -d
	@echo "$(YELLOW)⏳ Ожидание готовности SyncServer...$(NC)"
	@sleep 5
	@echo "$(GREEN)✅ Запуск завершён$(NC)"
	@echo ""
	@$(MAKE) migrate
	@echo ""
	@$(MAKE) status
	@echo ""
	@echo "$(GREEN)🎉 Стенд готов!$(NC)"
	@echo "$(GREEN)📦 SyncServer:    http://localhost:8000  (Swagger: http://localhost:8000/api/docs)$(NC)"
	@echo "$(GREEN)📦 Warehouse_web: http://localhost:8001$(NC)"
	@echo "$(GREEN)📦 Angular:       http://localhost:4200$(NC)"
	@echo "$(GREEN)📦 Postgres:      :5432$(NC)"

setup: init ## Алиас для init (первоначальная настройка)

# ----- Резервное копирование -----

backup-db: ## Сделать дамп PostgreSQL
	@mkdir -p backups
	docker compose exec -T postgres pg_dump -U warehouse_user warehouse > backups/warehouse_$$(date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)✅ Дамп сохранён в backups/$(NC)"

restore-db: ## Восстановить PostgreSQL из дампа (make restore-db FILE=backups/warehouse_xxx.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)❌ Укажите FILE=backups/warehouse_xxx.sql$(NC)"; exit 1; \
	fi
	@cat $(FILE) | docker compose exec -T postgres psql -U warehouse_user warehouse
	@echo "$(GREEN)✅ База восстановлена из $(FILE)$(NC)"


# ----- Django Admin -----

reset-django-admin: ## Сбросить Django superuser до admin/admin123
	@docker compose exec warehouse_web python manage.py shell -c "from django.contrib.auth.models import User; u, _ = User.objects.get_or_create(username='admin'); u.set_password('admin123'); u.is_superuser = True; u.is_staff = True; u.is_active = True; u.email = 'admin@warehouse.local'; u.save(); print('Django superuser admin reset to default')"

# ----- E2E тесты (Playwright) -----

test-e2e: ## Запустить Playwright E2E-тесты в Docker
	@echo "$(YELLOW)🧪 Запуск Playwright E2E-тестов...$(NC)"
	@docker compose up -d postgres syncserver warehouse_web angular
	@echo "$(YELLOW)⏳ Ожидание готовности стенда...$(NC)"
	@ready=0; \
	for i in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -fsS --max-time 5 http://localhost:8001/healthz/ > /dev/null 2>&1; then \
			ready=1; \
			break; \
		fi; \
		echo "  Waiting for Warehouse_web..."; \
		sleep 3; \
	done; \
	if [ $$ready -ne 1 ]; then \
		echo "$(RED)❌ Warehouse_web did not become ready$(NC)"; \
		exit 1; \
	fi
	@ready=0; \
	for i in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -fsS --max-time 5 http://localhost:8000/api/v1/health > /dev/null 2>&1; then \
			ready=1; \
			break; \
		fi; \
		echo "  Waiting for SyncServer..."; \
		sleep 3; \
	done; \
	if [ $$ready -ne 1 ]; then \
		echo "$(RED)❌ SyncServer did not become ready$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)✅ Стенд готов, запуск тестов...$(NC)"
	@docker compose run --rm \
		-e CI=true \
		-e E2E_BASE_URL=http://warehouse-web:8001 \
		-e E2E_SYNC_HEALTH_URL=http://syncserver:8000/api/v1/health \
		playwright \
		npx playwright test --config=e2e/playwright.config.ts
	@echo "$(GREEN)✅ E2E тесты завершены$(NC)"

test-e2e-report: ## Открыть HTML-отчёт Playwright
	@echo "$(YELLOW)📊 Открытие Playwright отчёта...$(NC)"
	@if [ -f Warehouse_frontend/playwright-html-report/index.html ]; then \
		xdg-open Warehouse_frontend/playwright-html-report/index.html 2>/dev/null || \
			echo "Отчёт: Warehouse_frontend/playwright-html-report/index.html"; \
	else \
		echo "$(RED)❌ Отчёт не найден: Warehouse_frontend/playwright-html-report/index.html$(NC)"; \
		exit 1; \
	fi

test-e2e-headed: ## Запустить Playwright в headed-режиме (только локально)
	@echo "$(YELLOW)🧪 Запуск Playwright в headed-режиме...$(NC)"
	@cd Warehouse_frontend && E2E_BASE_URL=http://localhost:8001 npx playwright test --config=e2e/playwright.config.ts --headed

test-e2e-ui: ## Запустить Playwright UI mode (только локально)
	@cd Warehouse_frontend && E2E_BASE_URL=http://localhost:8001 npx playwright test --config=e2e/playwright.config.ts --ui
