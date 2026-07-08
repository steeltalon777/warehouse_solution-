# TZ: Фикс брендинга — клиентская идентичность «ООО АС Горизонт»

**Date:** 2026-07-08
**Status:** Ready

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** Три независимых work units: (A) Angular favicon, (B) Django логотип + favicon + .env, (C) Django шаблоны — замена Quartermaster → клиент. Файлы не пересекаются, можно делать параллельно.

---

## Execution Checklist

- [ ] 0. Context verified — три бага подтверждены, корни найдены
- [ ] 1. Unit A: Angular — убрать дефолтный favicon, отдать управление Django
- [ ] 2. Unit B: Django — заменить плейсхолдеры логотипа и favicon на клиентские
- [ ] 3. Unit B: Django — обновить `.env.example` (дефолты → клиентские значения)
- [ ] 4. Unit C: Django — заменить `APP_PRODUCT_NAME` → `ORGANIZATION_SHORT_NAME` в шаблонах
- [ ] 5. Unit C: Django — `brand.html`, `base.html`, `login.html`, `sidebar.html` (footer)
- [ ] 6. Static checks: `npm run build` (Angular) + `python manage.py check` (Django)
- [ ] 7. Stand smoke: фавикон в браузере — клиентский (не ангуляровский)
- [ ] 8. Stand smoke: логотип в сайдбаре — клиентский (не «Q»)
- [ ] 9. Stand smoke: название везде — «ООО АС Горизонт» (не «Quartermaster»)
- [ ] 10. Stand smoke: страница входа, футер, title страницы, сайдбар
- [ ] 11. Final acceptance review

---

## Диагноз

### 1. Фавикон — ангуляровский (🔴)

Angular `src/index.html:8` содержит:
```html
<link rel="icon" type="image/x-icon" href="favicon.ico">
```

При сборке Angular CLI кладёт свой дефолтный favicon (ангуляровский щит, 15KB) в `dist/.../favicon.ico`. Этот `<link>` находится в Angular-контенте, который вставляется внутрь Django `<body>`, и **переопределяет** Django-фавикон из `base.html:8`:
```html
<link rel="icon" href="{% static APP_BRAND_FAVICON %}" type="image/x-icon">
```

Браузер берёт последний `<link rel="icon">` в DOM → ангуляровский.

### 2. Логотип — плейсхолдер «Q» (🔴)

`Warehouse_web/static/img/logo.svg` — буква «Q» в синем квадрате (367 байт). Используется в `brand.html`:
```html
<img src="{% static APP_BRAND_LOGO %}" alt="{{ APP_PRODUCT_NAME }}">
```

Реальный логотип клиента (`logo.png`, 1MB) лежит рядом, но **не используется** — переменная `APP_BRAND_LOGO` указывает на `.svg`, а не на `.png`.

### 3. Название «Quartermaster» вместо «ООО АС Горизонт» (🔴)

В `context_processors.py` `shell_context()` передаёт в шаблоны:
```python
"organization_short_name": settings.ORGANIZATION_SHORT_NAME,  # 'ООО АС "Горизонт"'
"organization_full_name": settings.ORGANIZATION_FULL_NAME,
```

Но эти переменные **нигде не используются** в шаблонах. Вместо них везде `APP_PRODUCT_NAME` = "Quartermaster":

| Шаблон | Строка | Текущее значение |
|---|---|---|
| `brand.html:5` | `{{ APP_PRODUCT_NAME }}` | Quartermaster |
| `base.html:7` | `<title>{{ APP_PRODUCT_NAME }} — ...` | Quartermaster |
| `base.html:40` | `&copy; {{ APP_PRODUCT_NAME }}` | Quartermaster |
| `login.html:7` | `{{ APP_PRODUCT_NAME }}` | Quartermaster |

---

## Scope

### In scope (5 файлов Django + 1 файл Angular)

| # | Файл | Действие |
|---|---|---|
| A1 | `Warehouse_frontend/src/index.html` | Убрать `<link rel="icon">` |
| B1 | `Warehouse_web/static/img/logo.svg` | Заменить на клиентский логотип |
| B2 | `Warehouse_web/static/img/favicon.ico` | Заменить на клиентский favicon |
| B3 | `Warehouse_web/.env.example` | Обновить дефолты `APP_PRODUCT_NAME` и `APP_BRAND_LOGO` |
| C1 | `Warehouse_web/templates/includes/brand.html` | `APP_PRODUCT_NAME` → `organization_short_name` |
| C2 | `Warehouse_web/templates/base.html` | `APP_PRODUCT_NAME` → `organization_short_name` (title + footer) |
| C3 | `Warehouse_web/templates/registration/login.html` | `APP_PRODUCT_NAME` → `organization_short_name` |

### Out of scope

- Замена `APP_PRODUCT_NAME` в `footer` и `base.html` — сам `APP_PRODUCT_NAME` остаётся как технический идентификатор продукта, но в пользовательских шаблонах заменяется на клиентское имя
- Angular shell (app.component.ts/html) — Angular не рисует глобальный заголовок (Django shell primary)
- SyncServer branding
- Переименование репозиториев, пакетов, docker-тегов
- Изменение `APP_BRAND_PRIMARY_COLOR`

---

## Unit A: Angular — убрать favicon, отдать Django

### A1. `Warehouse_frontend/src/index.html`

**Проблема:** строка 8 содержит `<link rel="icon">`, который при сборке создаёт ангуляровский favicon, переопределяющий Django.

**Решение:** убрать строку 8:

```diff
-  <link rel="icon" type="image/x-icon" href="favicon.ico">
```

**После сборки** нужно убедиться, что в `dist/warehouse-frontend/browser/index.html` нет `<link rel="icon">`. Если Angular CLI всё равно генерирует favicon — удалить файл `dist/.../favicon.ico` после сборки (или добавить в скрипт копирования в `angular_static/`).

### Acceptance criteria A

- [ ] `npm run build` — успешно
- [ ] В собранном `index.html` нет `<link rel="icon">`
- [ ] Фавикон в браузере — тот, что определён в Django `base.html` (клиентский)

---

## Unit B: Django — клиентские логотип и favicon

### B1. Заменить `logo.svg`

Текущий `Warehouse_web/static/img/logo.svg` — буква «Q». Нужен клиентский логотип. Есть два варианта:

**Вариант 1:** использовать существующий `logo.png` (1MB, уже в static). Тогда в `brand.html`:
```html
<img src="{% static 'img/logo.png' %}" ...>
```
И обновить `APP_BRAND_LOGO` в `.env.example`.

**Вариант 2:** заменить `logo.svg` на клиентский векторный логотип (если клиент предоставит).

**Рекомендация:** вариант 1 — самый быстрый. Потом можно заменить на `.svg`.

### B2. Заменить `favicon.ico`

Текущий `Warehouse_web/static/img/favicon.ico` (1118 байт, 16×16) — возможно тоже плейсхолдер. Нужен клиентский favicon (многоразмерный: 16×16, 32×32, 48×48).

### B3. Обновить `.env.example`

```diff
-# Product branding (Quartermaster, ADR-0015)
-APP_PRODUCT_NAME=Quartermaster
+APP_PRODUCT_NAME=ООО АС Горизонт
 APP_PRODUCT_VERSION=3.1
 APP_PRODUCT_TAGLINE=Система складского и имущественного учёта
-APP_BRAND_LOGO=img/logo.svg
+APP_BRAND_LOGO=img/logo.png
 APP_BRAND_FAVICON=img/favicon.ico
 APP_BRAND_PRIMARY_COLOR=#1a365d
```

### Acceptance criteria B

- [ ] `logo.png` (или `.svg`) — клиентский логотип
- [ ] `favicon.ico` — клиентский favicon
- [ ] `.env.example` отражает клиентские значения
- [ ] `python manage.py check` — без ошибок

---

## Unit C: Django шаблоны — Quartermaster → клиент

### C1. `brand.html` — сайдбар

Переменная `organization_short_name` уже передаётся в шаблоны через `shell_context`. Заменить:

```diff
-        <span class="brand-text">{{ APP_PRODUCT_NAME }}</span>
+        <span class="brand-text">{{ organization_short_name }}</span>
```

Логотип — если перешли на `logo.png`, обновить путь:
```diff
-    <img src="{% static APP_BRAND_LOGO %}" alt="{{ APP_PRODUCT_NAME }}" class="brand-logo">
+    <img src="{% static APP_BRAND_LOGO %}" alt="{{ organization_short_name }}" class="brand-logo">
```

### C2. `base.html` — `<title>` и футер

```diff
-    <title>{% block title %}{{ APP_PRODUCT_NAME }} — {{ APP_PRODUCT_TAGLINE }}{% endblock %}</title>
+    <title>{% block title %}{{ organization_short_name }} — {{ APP_PRODUCT_TAGLINE }}{% endblock %}</title>

-    <span class="app-footer__brand">&copy; {{ APP_PRODUCT_NAME }} {{ APP_PRODUCT_VERSION }}</span>
+    <span class="app-footer__brand">&copy; {{ organization_short_name }} {{ APP_PRODUCT_VERSION }}</span>
```

### C3. `login.html` — страница входа

```diff
-    <h1 class="login-product-name">{{ APP_PRODUCT_NAME }}</h1>
+    <h1 class="login-product-name">{{ organization_short_name }}</h1>
```

### C4. Проверить `sidebar.html` и `navbar.html`

Убедиться, что в них нет `APP_PRODUCT_NAME`, который виден пользователю.

### Acceptance criteria C

- [ ] Сайдбар показывает «ООО АС Горизонт» (не «Quartermaster»)
- [ ] `<title>` страницы — «ООО АС Горизонт — Система складского и имущественного учёта»
- [ ] Футер — «© ООО АС Горизонт 3.1»
- [ ] Страница входа — заголовок «ООО АС Горизонт»
- [ ] `APP_PRODUCT_NAME` сохранён в settings для обратной совместимости (env override)

---

## Test Strategy

| Level | Что проверяется | Команда |
|---|---|---|
| Static — Angular | `npm run build` без favicon | `cd Warehouse_frontend && npm run build` |
| Static — Django | `python manage.py check` | `cd Warehouse_web && python manage.py check` |
| Stand smoke | Фавикон в браузере — НЕ ангуляровский | Открыть `http://localhost:8001`, проверить вкладку браузера |
| Stand smoke | Логотип в сайдбаре — НЕ «Q» | Открыть `http://localhost:8001`, проверить сайдбар |
| Stand smoke | Название в сайдбаре — «ООО АС Горизонт» | Сайдбар верх |
| Stand smoke | Название на странице входа — «ООО АС Горизонт» | `http://localhost:8001/users/login/` |
| Stand smoke | Title страницы — «ООО АС Горизонт» | Вкладка браузера |
| Stand smoke | Футер — «© ООО АС Горизонт» | Низ страницы |
| Regression | Django shell, sidebar, навигация не сломаны | Пройтись по `/operations/`, `/nomenclature/`, `/catalog/` |

---

## Stand Requirements

- Docker dev-стенд: `make up`
- После изменений Angular: `npm run build`, затем скопировать в `angular_static/` или `make build-angular`
- После изменений Django: `make build-web` (пересборка образа) или `make restart`

---

## Architecture Review

**Date:** 2026-07-08 | **Reviewer:** Architect | **Verdict:** ✅ Approved — no blockers

| Category | Result |
|---|---|
| Complexity | ✅ 6 файлов, по 1-5 строк изменений. Каждая правка атомарна и обратима. |
| Coupling | ✅ Angular/Django граница не нарушается. Favicon ownership однозначно → Django shell. |
| Data & State | ✅ Без миграций. `organization_short_name` уже в `shell_context`, просто не используется. |
| Failure | ✅ Ошибка шаблона → `python manage.py check`. Нет favicon → стандартная иконка браузера. |
| Security | ✅ Без пользовательского ввода, без инжекций, без секретов. |
| Scalability | ✅ Статические ассеты, не влияет на нагрузку. |
| Observability | ✅ Ошибки шаблонов видны при старте/check. |
| Operability | ✅ Zero-downtime (статика). Откат: revert 6 строк. |

**🔴 Blockers:** 0  
**🟡 Warnings:**
1. **Angular CLI favicon regeneration** — даже без `<link rel="icon">` Angular CLI может положить `favicon.ico` в `dist/`. Проверить после сборки.
2. **`logo.png` (1MB)** — может быть великоват для сайдбара. Рекомендуется ресайз или конвертация в SVG.

**🔵 Notes:**
1. `APP_PRODUCT_NAME` остаётся в settings для обратной совместимости (env override).
2. `ORGANIZATION_SHORT_NAME` / `ORGANIZATION_FULL_NAME` уже в `shell_context` — готовы к использованию.

---

## Риски

| Риск | Вероятность | Митигация |
|---|---|---|
| Angular CLI генерирует favicon автоматически, даже без `<link>` в `index.html` | Средняя | Проверить после `npm run build` — если `favicon.ico` создан, удалить его скриптом копирования |
| Клиентский логотип не влезает в сайдбар по размеру | Низкая | CSS-класс `.brand-logo` уже задаёт размеры |
| `organization_short_name` не передан в контекст для SPA-страниц | Низкая | `shell_context` в `context_processors` применяется ко всем view |
| `.env.example` изменён, но на проде свои значения через env | Низкая | `APP_PRODUCT_NAME` и `ORGANIZATION_SHORT_NAME` переопределяются через env |

---

## Definition of Done

- [ ] Ангуляровский фавикон заменён на клиентский во всех браузерах
- [ ] Сайдбар показывает клиентский логотип (не «Q»)
- [ ] Сайдбар показывает «ООО АС Горизонт» (не «Quartermaster»)
- [ ] `<title>` — «ООО АС Горизонт ...»
- [ ] Страница входа — «ООО АС Горизонт»
- [ ] Футер — «© ООО АС Горизонт»
- [ ] `npm run build` и `python manage.py check` проходят
