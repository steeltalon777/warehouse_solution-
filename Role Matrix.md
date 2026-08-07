# Role Matrix (V3.1 + ADR-0030 agent)

## Roles
- root
- chief_storekeeper
- storekeeper
- observer
- agent (ADR-0030 — доверенный LLM-агент главного кладовщика)

## Permissions

| Действие | root | chief_storekeeper | storekeeper | observer | agent |
|---|---|---|---|---|---|
| Видеть всё (остатки, каталог, операции) | YES | YES | YES | YES | YES |
| Создать черновик (любой склад) | YES | YES | YES | YES | YES |
| Править каталог: создать Item/Category/Unit | YES | YES | NO | NO | YES |
| Править каталог: PATCH business-полей (allow-list) | YES | YES | NO | NO | YES |
| Merge Item/Category | YES | YES | NO | NO | YES |
| Удалять/деактивировать каталог, `/catalog/admin/batch` | YES | YES | NO | NO | NO |
| Подтвердить операцию | YES (any) | YES (any) | YES (scope only) | NO | NO |
| Принять поставку | YES (any) | YES (any) | YES (destination scope) | NO | NO |
| Отменить подтверждённую | YES | NO | NO | NO | NO |
| Отменить черновик | YES | YES | YES (свой) | NO | YES (свой) |
| Удалить черновик | YES | YES | YES (свой) | NO | NO |
| Управлять справочником (lifecycle) | YES | YES | NO | NO | NO |
| Управлять пользователями | YES | NO | NO | NO | NO |

Примечание: agent использует собственный `X-User-Token`; права PATCH/MERGE существующего каталога применяются только после явной команды главного кладовщика (behavioural rule agent wrapper, не security boundary — ADR-0030).
