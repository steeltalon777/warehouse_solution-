# warehouse-storekeeper

Hermes-скилл «помощник кладовщика» для Warehouse SyncServer: фото/PDF
накладной → распознавание встроенными скиллами Hermes → сопоставление
каталога → черновик операции. Операцию не проводит.

## Структура

```
warehouse-storekeeper/
├── SKILL.md                     # инструкции скилла (Hermes)
├── README.md                    # этот файл
├── requirements.txt             # httpx (+ pytest для тестов)
├── scripts/
│   ├── warehouse_api.py         # CLI-клиент SyncServer (Python 3.10+, httpx)
│   ├── bootstrap.ps1            # установка зависимостей и скилла
│   ├── protect_secrets.ps1      # ACL на файл секретов (user + SYSTEM)
│   └── smoke_test.ps1           # безопасный smoke-тест
├── references/
│   ├── SYNC_SERVER_API.md       # карта реального API (по коду SyncServer)
│   ├── AUTH.md                  # auth, токены, роли
│   ├── WORKFLOW.md              # сценарий помощника
│   ├── ERROR_HANDLING.md        # форматы ошибок и реакции
│   ├── SECURITY.md              # секреты, ACL, prompt injection
│   └── API_GAPS.md              # отсутствующие возможности сервера
├── schemas/                     # JSON Schema: extracted_document,
│                                # operation_intent, draft_request
├── templates/
│   └── syncserver.env.example   # шаблон конфигурации (без секретов)
└── tests/                       # unit-тесты (MockTransport, без сети)
    └── fixtures/
```

## Установка на Windows (COMP2)

Требования: Windows 10/11, Python 3.10+ в PATH, Hermes Agent
(проверено: `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\hermes.exe`).

1. Скопируйте папку `warehouse-storekeeper` на целевой компьютер.
2. В PowerShell выполните из папки скилла:

```powershell
cd <путь>\warehouse-storekeeper
.\scripts\bootstrap.ps1
```

`bootstrap.ps1`:
- проверяет Python, создаёт `.venv` в папке скилла, ставит зависимости;
- копирует скилл в `%LOCALAPPDATA%\hermes\skills\warehouse-storekeeper`;
- создаёт `%LOCALAPPDATA%\WarehouseAgent\secrets\`, кладёт туда
  `syncserver.env` из шаблона (если ещё нет) и вызывает
  `protect_secrets.ps1` (ACL: только вы и SYSTEM);
- показывает итоговое дерево файлов.

3. Заполните токены в `%LOCALAPPDATA%\WarehouseAgent\secrets\syncserver.env`
   (значения выдаёт администратор SyncServer; в git/чат не вставлять).
4. Проверьте регистрацию скилла:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\hermes.exe" skills list
# ожидается строка: warehouse-storekeeper | local | local | enabled

Get-ChildItem "$env:LOCALAPPDATA\hermes\skills\warehouse-storekeeper" -Recurse
```

5. Smoke-тест (без создания черновика):

```powershell
.\scripts\smoke_test.ps1
# на devstand с тестовым токеном можно: .\scripts\smoke_test.ps1 -SmokeDraft
```

После установки скилл доступен как `/warehouse-storekeeper`.

## Использование CLI вручную

```powershell
$env:PYTHONIOENCODING="utf-8"
& "$env:LOCALAPPDATA\hermes\skills\warehouse-storekeeper\.venv\Scripts\python.exe" `
  "$env:LOCALAPPDATA\hermes\skills\warehouse-storekeeper\scripts\warehouse_api.py" health
```

Все ответы — JSON-конверт `{"ok","command","request_id","status_code",
"data","warnings","errors"}`. Массовые данные — только через `--input <файл>`.

## Граница полномочий

Скилл читает справочники/остатки и создаёт/правит только свои черновики.
submit/accept/cancel/restore/delete/merge/admin/ADJUSTMENT запрещены
и в SKILL.md, и в allowlist `warehouse_api.py` (см. `references/SECURITY.md`).

## Тесты

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Unit-тесты используют `httpx.MockTransport` — без сети и production.
Интеграционные тесты допустимы только на devstand с отдельным тестовым
токеном и явным флагом `--integration` (в текущем наборе интеграционных
тестов нет; smoke с `-SmokeDraft` — их роль на devstand).
