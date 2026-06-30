# ADR-0017: WPF Migration via Rust Core

## Status
Accepted

## Date
2026-06-19

## Context

`WarehouseWorkstation` — зрелый WPF-клиент (117 тестов, .NET 8, MVVM, AI-воркстейшн). Он имеет собственную SQLite, прямые HTTP-клиенты к SyncServer, и собственные DTO — архитектурно дублируя `Warehouse_client_core` (Rust).

Анализ миграции (`WarehouseWorkstation/docs/MIGRATION_AIWORKSTATION_TO_CORE_ANALYSIS.md`) показал:
- 4 из 41 ViewModels затронуто (10%)
- 7 из 49 сервисов затронуто (14%)
- 29 файлов удалить, 7 адаптировать, 2-3 создать
- AI-сервисы не затронуты (0 транзитивных зависимостей от warehouse SQLite)
- Оценка: 12-20 дней на полную миграцию (против месяцев на переписывание с нуля)

Требуется принять решение: мигрировать WPF на Rust core или оставить независимым.

## Decision

**Мигрировать WPF на Rust core через FFI (P/Invoke). Фазировать: Layer 0 в v3.1, Layers 1-7 в v3.2.**

### Фазы

| Фаза | Релиз | Слой | Что |
|------|-------|------|-----|
| 0 | **v3.1** | FFI spike | C# `CoreHandle` SafeHandle wrapper, загрузка DLL, `core_version()/open()/close()`, smoke test. **НЕ продуктовые сценарии.** |
| 1 | v3.2 | Bootstrap/Auth | `BootstrapOrchestrationService`, `AuthContextRefreshService` → Core |
| 2 | v3.2 | Directory | `DirectoryWorkspaceService` + ViewModels → Core catalog facade |
| 3 | v3.2 | Balances | `BalanceService` → Core balances facade |
| 4 | v3.2 | Operations | `OperationService` → Core operations facade |
| 5 | v3.2 | Documents | `DocumentPrintService` → Core documents facade |
| 6 | v3.2 | Sync Engine | Удалить `RefreshOrchestrator`, `SyncStateService` — Core управляет sync |
| 7 | v3.2 | Cleanup | Удалить `Integrations.Sync`, старые SQLite-таблицы, старые репозитории |

### Архитектурная цель

```
WPF ViewModels (unchanged)
    ↓
Application Services (adapted)
    ↓
Core Facade Adapters (new)
    ↓
Rust Core FFI (warehouse_ffi.dll)
    ↓
Rust Core SQLite + SyncServer HTTP
```

### Почему не в v3.1

1. **v3.1 = offline readiness, не offline completion.** Полная миграция WPF — это 12-20 дней. Попытка втиснуть её в v3.1 превратит branding + sync_state + core gate в «WPF migration release» со смещением всех приоритетов.

2. **Гибридное состояние опасно.** Если в v3.1 начать Layers 1-2, WPF окажется в гибридном режиме: часть данных через старый C# HttpClient/SQLite, часть через Rust core. Это удваивает поверхность багов.

3. **Layer 0 доказывает feasibility без риска.** C# FFI wrapper + smoke test подтверждает, что P/Invoke работает, DLL загружается, память не течёт. Это снимает главный технический риск миграции.

### Hard rule

**При миграции Layers 1-7 (в v3.2): старый сервис/репозиторий/таблица удаляются в том же PR, где добавляется Core-адаптер.** Никакого сосуществования двух параллельных доменных слоёв.

## Consequences

- WPF получает единое хранилище и sync-движок Rust core (вместо дублирующей реализации).
- v3.1 подтверждает техническую возможность миграции без риска для продукта.
- v3.2 получает чистый миграционный план с доказанной FFI-основой.
- AI-функционал WPF не затрагивается миграцией (подтверждено анализом).
- `Integrations.Sync` проект будет удалён полностью (18 файлов).

## Confidence
**High** — анализ миграции выполнен, 4 из 5 decision gate пройдены. Последний gate (stand smoke Core ↔ SyncServer) закрывается в v3.1C.
