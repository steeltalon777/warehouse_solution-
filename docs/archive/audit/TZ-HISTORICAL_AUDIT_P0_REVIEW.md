# TZ: Ревью 12 P0-рисков исторической целостности (docs/audit/)

## Execution Checklist

- [x] 0. Контекст, источники и acceptance criteria подтверждены
- [x] 1. R-01: `effective_at` back-date на submitted — верифицирован
- [x] 2. R-02: `merge_items` переписывает `operation_lines.item_id` — верифицирован
- [x] 3. R-03: `restore_operation` без audit_event — верифицирован
- [x] 4. R-04: `soft_delete_item/category/unit` без audit_event — верифицирован
- [x] 5. R-05: разрыв `created_at` vs `effective_at` — верифицирован
- [x] 6. R-06: late acceptance переоценивает баланс «на дату submit» — верифицирован
- [x] 7. R-07: нет файлов source-documents — верифицирован
- [x] 8. R-11: нет integrity check `balance == sum(audit_item_effects)` — верифицирован
- [x] 9. R-12: `restore_operation` без audit ломает cycle — верифицирован
- [x] 10. R-20: merge без per-line resource — верифицирован
- [x] 11. R-26: нет scheduled integrity check — верифицирован
- [x] 12. R-36: отчёт чувствителен к back-date — верифицирован
- [x] 13. Сводный отчёт: приоритизация, оценка, зависимости, решение по срокам
- [x] 14. Stand/регрес-проверка (если потребуется воспроизведение)
- [x] 15. Final acceptance review (QA verifier) — принят пользователем 2026-08-07, отчёт `docs/audit/P0_REVIEW_2026-08-07.md`, ТЗ архивировано

## Check Rules

- Задача — **research/review, read-only**: анализ кода и данных, БЕЗ правок production-кода, БЕЗ миграций, БЕЗ коммитов в SyncServer/Warehouse_web.
- Executor отмечает пункты 1–12 только после фактической верификации в коде (grep/Read по указанным file:line + подтверждение/опровержение).
- Каждый риск закрывается вердиктом: **confirmed / refuted / partial** + evidence (file:line, фрагмент кода, команда проверки).
- Для подтверждённых рисков — предлагаемый фикс (подход, файлы, размер оценки S/M/L, зависимости).
- Пропущенная проверка остаётся `[ ]` с причиной.
- Пункт 13 — итоговый отчёт-решение: какие P0 входят в ближайший релиз, какие переносятся, какие требуют ADR.
- Пункт 14 — только если для подтверждения риска нужен живой стенд/воспроизведение.
- Пункт 15 — ставит QA verifier после проверки Evidence.

## Metadata

| Поле | Значение |
|---|---|
| Target | Ревью перед закрытием сезона / следующим релизом |
| Status | Ready for execution |
| Date | 2026-08-07 |
| Source | `docs/audit/HISTORICAL_RISK_REGISTER.md`, `docs/audit/HISTORICAL_INTEGRITY_AUDIT.md`, `docs/audit/HISTORICAL_DATA_FLOW.md`, `docs/audit/HISTORICAL_INTEGRITY_ROADMAP.md`, `docs/audit/SEASON_REPORT_READINESS.md` |
| Type | Research / review |
| Runtime scope | `SyncServer/` (чтение), при необходимости `Warehouse_web/` (чтение BFF-слоя) |
| Sensitive areas | `operations_service.py`, `operations_policy.py`, `catalog_admin_service.py`, `uow.py` — **только чтение** |

## 0. Контекст

Аудит `docs/audit/` (2026-07-31) выявил 40 рисков: 12 P0, 16 P1, 11 P2, 1 P3. Все P0 относятся к отсутствию/неконсистентности дат (`effective_at` vs `created_at`), потерям истории при merge/restore/soft-delete и отсутствию integrity-проверок. Часть P0 может ударить сезонную отчётность.

Задача: отдельной сессией разобрать каждый P0 — подтвердить/опровергнуть в коде, оценить фикс и предложить решение по срокам. Исполнитель НЕ реализует фиксы — он готовит решение.

## 1. Что разбираем (12 P0)

| ID | Область | Формулировка из риск-реестра | Указанные file:line |
|---|---|---|---|
| R-01 | III/Балансы | `effective_at` изменён у submitted операции без compensation effects | `operations_service.py:1336-1382`; `routes_operations.py:261-290`; `operations_workflow_policy.py:15-20` |
| R-02 | IV/Merge | `merge_items` физически переписывает `operation_lines.item_id` без per-line resource и без original_item_id | `catalog_admin_service.py:678-684` |
| R-03 | VII/Audit | `restore_operation` не пишет audit_event | `operations_service.py:2778-2793` |
| R-04 | V/Master | `soft_delete_item/category/unit` не пишет audit_event | `catalog_admin_service.py:421-459` |
| R-05 | III/Балансы | `audit_item_effects.created_at` ≠ `operations.effective_at`; отчёты используют `effective_at` | модель `audit_item_effects`; JOIN в отчётах |
| R-06 | III/Балансы | Late acceptance (после смены сезона) переоценивает баланс «на дату submit» | `accept_operation_lines` (routes/services) |
| R-07 | VI/Documents | Нет файлов source-documents, hash, OCR engine version; `source_ref` — единственный идентификатор | модели source-document-входа (0029/0030) |
| R-11 | III/Балансы | Нет integrity check `balance == sum(audit_item_effects)` | репозитории балансов/эффектов |
| R-12 | VII/Audit | restore + cancel + restore + new-submit без audit_event создаёт «потерянный» cycle | `operations_service.py` restore/cancel |
| R-20 | II/Lines | `merge_balance_transfer` audit_event_resources ссылается на operation, но не на строки | merge-код в `catalog_admin_service.py` |
| R-26 | III/Балансы | Нет автоматического scheduled integrity check (нет cron, нет scheduled repo) | инфраструктура SyncServer |
| R-36 | VIII/Reports | `reports_repo.list_item_movement` использует только `operations.effective_at`; backdated → отчёт неконсистентен | `reports_repo` (найти файл) |

## 2. Что делаем с каждым риском

Для каждого из 12:

1. **Верификация в коде**: найти место по указанным file:line (или найти фактическое), выписать фрагмент, понять текущее поведение.
2. **Вердикт**: `confirmed` (риск существует в текущем коде), `refuted` (уже исправлен/защищён), `partial` (частично закрыт).
3. **Evidence**: file:line, фрагмент кода, команда проверки (grep/read/pytest при необходимости).
4. Для confirmed/partial — **предлагаемый фикс**:
   - подход (service-level guard / DB constraint / новая модель / CLI-скрипт / отчётный JOIN),
   - файлы, которые придётся трогать,
   - оценка размера (S/M/L),
   - зависимости между рисками (например R-36 зависит от R-01; R-26 — инфраструктурное продолжение R-11),
   - нужно ли ADR.
5. Отдельно: **влияние на сезонную отчётность** — может ли риск исказить уже сформированные данные (требует ли backfill-миграции) или влияет только на будущее.

## 3. Out of scope (НЕ делаем)

- Реализация фиксов (отдельные TZ после ревью).
- P1/P2/P3-риски (только упомянуть, если всплыли в ходе разбора).
- Миграции данных, backfill, скрипты восстановления.
- Правки `Functional and WorkLogik.md`, ADR-документов (только рекомендация о необходимости ADR).
- Docker/CI/cron-инфраструктура (только описание предложения).

## 4. Acceptance criteria

- Пункты 1–12: для каждого — вердикт + evidence + (для confirmed) предлагаемый фикс с оценкой и зависимостями.
- Пункт 13: итоговый отчёт — таблица «риск → вердикт → размер → в ближайший релиз/перенос/нужен ADR», явная рекомендация, что блокирует закрытие сезона.
- Пункт 14 (опционально): если подтверждение требует живого стенда — следовать Stand Availability Protocol; иначе N/A с причиной.
- Пункт 15: QA verifier проверяет evidence и только затем ставит `[x]`.

## 5. Требования к отчёту исполнителя

```markdown
## Вердикты (сводка)
| Риск | Вердикт | Размер фикса | В релиз? | Зависит от |

## Детализация (по каждому риску)
### R-XX — <краткое имя>
- Вердикт: confirmed/refuted/partial
- Evidence: file:line + фрагмент + команда проверки
- Предлагаемый фикс: подход, файлы, оценка, ADR?
- Влияние на сезонную отчётность: да/нет, требуется backfill?

## Рекомендации
- Блокеры сезона (обязательны к фиксу)
- Желательно
- Перенос/деприоритизация
```

## 6. Тест-лестница

| Уровень | Применимо | Комментарий |
|---|---|---|
| 1. Static/grep-проверки | ✅ обязателен | grep/Read по каждому file:line |
| 2. Unit-тесты | ⚠️ по необходимости | только для подтверждения/опровержения существующего поведения, read-only запуск |
| 3. Component-тесты | ⚠️ по необходимости | BFF-слой при разборе R-06/R-36 |
| 4. Integration | ⚠️ по необходимости | если риск в поведении при реальной БД |
| 5. Stand smoke | ⚠️ опционально | только при потребности воспроизведения |
| 6. UI automation | — | N/A (research) |
| 7. User scenarios | — | N/A (research) |
| 8. Regression | ⚠️ при запуске тестов | полный `python -m pytest` перед завершением, если тесты запускались |
| 9. Acceptance review | ✅ | QA verifier по Evidence |

## 7. Git-правила

- Рабочая ветка — `dev`.
- Задача read-only: правки в `SyncServer/` и `Warehouse_web/` ЗАПРЕЩЕНЫ.
- Разрешён только новый файл отчёта (по согласованию): например `docs/audit/P0_REVIEW_2026-08-07.md` или комментарии в TZ.
- Коммит отчёта — только по явной команде пользователя.
