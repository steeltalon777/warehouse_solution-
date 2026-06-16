# Role Matrix (V3.1)

## Roles
- root
- chief_storekeeper
- storekeeper
- observer

## Permissions

| Действие | root | chief_storekeeper | storekeeper | observer |
|---|---|---|---|---|
| Видеть всё (остатки, каталог, операции) | YES | YES | YES | YES |
| Создать черновик (любой склад) | YES | YES | YES | YES |
| Подтвердить операцию | YES (any) | YES (any) | YES (scope only) | NO |
| Принять поставку | YES (any) | YES (any) | YES (destination scope) | NO |
| Отменить подтверждённую | YES | NO | NO | NO |
| Отменить черновик | YES | YES | YES (свой) | NO |
| Удалить черновик | YES | YES | YES (свой) | NO |
| Управлять справочником | YES | YES | NO | NO |
| Управлять пользователями | YES | NO | NO | NO |
