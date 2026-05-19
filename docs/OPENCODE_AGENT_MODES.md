# OpenCode Agent Modes

## Current Shape

This repository defines one project-local primary agent and uses system modes for the rest.

| Mode | Source | Purpose |
|---|---|---|
| **Orchestrator** | project `.opencode/agents/orchestrator.md` | Primary agent — координирует параллельное выполнение до 5 субагентов. Анализирует ТЗ, разбивает на независимые юниты, верифицирует, агрегирует. |
| Build | native OpenCode | Direct implementation mode |
| Plan | native OpenCode | Read-only planning mode |
| Architect | global user config | Plan-like mode that may edit Markdown TZ/ADR/docs |

## Orchestrator Mode Details

### Назначение
Оркестратор — режим, аналогичный Build, но с массовым параллелизмом. Он получает ТЗ, спроектированное с учётом параллелизма, и:

1. Анализирует ТЗ на независимые юниты работы
2. Запускает до 5 субагентов одновременно (через `task` tool)
3. Верифицирует результаты каждого субагента
4. Интегрирует и агрегирует вывод
5. Формирует evidence table по чек-листу ТЗ

### Субагенты оркестратора
Субагенты используют ту же модель, что и оркестратор (наследование по умолчанию).

| Тип субагента | Доступ | Назначение |
|---|---|---|
| `general` | Полный (write, edit, bash) | Реализация кода, тесты, правки |
| `explore` | Read-only | Исследование кодовой базы, поиск |

### ТЗ для оркестратора
ТЗ под оркестратора разрабатывается с учётом параллелизма — юниты работы группируются по независимости:

- **Стадия 1**: независимые юниты → параллельный запуск (до 5)
- **Стадия 2**: юниты, зависящие от результатов стадии 1 → последовательно
- **Финализация**: интеграционные проверки, документация

### Параллелизм
- Максимум 5 субагентов одновременно
- Независимые по файлам/данным/порядку юниты — в одном batch
- Зависимые юниты — в разных стадиях

## Model Selection

No project file pins a model or provider for these modes.

Choose the model manually per session based on the task:

- strongest reasoning model for architecture, ADRs, and TZ writing;
- strong coding model for implementation;
- cheaper reasoning/coding model for focused debugging or mechanical checks.

## Project Config Boundary

Project config should stay limited to Warehouse-specific instructions and task workflow documents.

Global OpenCode config owns plugins, MCP servers, shell permissions, compaction, tool output limits, and global modes.
