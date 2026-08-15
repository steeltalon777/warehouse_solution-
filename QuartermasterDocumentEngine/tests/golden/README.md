# Golden артефакты

Structural + semantic регрессия для Quartermaster Document Engine
(TZ `doc/TZ-PHASE2-BACKEND-SPIKE.md` §13.6 / задача T11).

## LFS-политика (fallback TZ §13.6)

`git-lfs` в окружении **не установлен** (см. `doc/spike/INVESTIGATION.md`
§2.3). Применяем fallback: коммитим **только JSON**, PNG/PDF живут
в `spike-out/golden/` (CI/local artifacts, `.gitignore`).

`tests/golden/index.json` фиксирует `lfs_status =
"unavailable-git-lfs-not-installed"` и `lfs_fallback =
"json-only-assertions-png-pdf-as-ci-artifacts"`. Каждый entry имеет
`lfs: false`.

## Acceptance set

Шесть `(template × backend)` × шесть фикстур = **6 entries**
(одна фикстура на каждую пару backend'ов; см. TZ §13.6 — без полной
матрицы размеров). Полный список — в `index.json`.

| template@version | backend | fixture |
|---|---|---|
| `warehouse-waybill-ru@1.0` | weasyprint | `tests/fixtures/waybill/waybill-75.weasy.json` |
| `spike-waybill-typst@0.1.0` | typst | `tests/fixtures/waybill/waybill-75.typst.json` |
| `spike-route-sheet-weasy@0.1.0` | weasyprint | `tests/fixtures/route-sheet/vehicle-route-sheet-1.weasy.json` |
| `spike-route-sheet-typst@0.1.0` | typst | `tests/fixtures/route-sheet/vehicle-route-sheet-1.typst.json` |
| `spike-fuel-report-weasy@0.1.0` | weasyprint | `tests/fixtures/fuel/fuel-report-500.weasy.json` |
| `spike-fuel-report-typst@0.1.0` | typst | `tests/fixtures/fuel/fuel-report-500.typst.json` |

Каталог шаблона = `<id>-<version>` в нижнем регистре
(`warehouse-waybill-ru-1.0`, `spike-fuel-report-typst-0.1.0` и т.п.).

## Структура `expected.json`

```json
{
  "schema_version": 1,
  "template": "...",
  "backend": "...",
  "fixture": "...",
  "engine_version": "0.1.0",
  "backend_version": "69.0 | 0.15.1",
  "thresholds": {"ssim": 0.995, "changed_pixels": 0.001},
  "structural": {
    "page_count": 3,
    "paper_size": [595, 842],
    "orientation": "portrait",
    "required_blocks": {
      "header": {"expected_substrings": ["..."], "pass": true},
      "table":  {"expected_substrings": ["..."], "pass": true},
      "signatures": {"expected_substrings": ["..."], "pass": true},
      "footer": {"expected_substrings": ["..."], "pass": true}
    },
    "table_rows": 75
  },
  "semantic": {
    "document_number": {"expected": "...", "actual": "...", "pass": true},
    "line_count":       {"expected": 75, "actual": 75, "pass": true},
    "signers_present":  {"expected": ["..."], "actual": ["..."], "pass": true}
  }
}
```

- `pass` фиксируется **как есть** из T9 harness'а — если harness
  сообщил `pass: false` для блока/поля, не подделываем `true`.
- `structural.page_count` и `semantic.document_number.actual`
  обязаны совпадать с `spike-out/compare/<fixture>/{structural,semantic}.json`
  (это проверяет `test_golden_expected_values_match_t9_output`).
- Списки substrings и signers_expected берутся из
  `tests/harness/structural.py:BLOCK_EXPECTATIONS` (канонический
  источник для обоих backends).

## Обновление

```bash
python scripts/golden_update.py            # regenerate all (writes expected.json)
python scripts/golden_update.py --check    # CI gate (exit 1 on diff)
python scripts/golden_update.py --fixtures waybill-75   # subset
```

`--check` рендерит каждый entry заново через `qm-render`, прогоняет
`tests.harness.structural` и `tests.harness.semantic`, и diff'ит
против коммиченного `expected.json`. Скрипт идемпотентен —
повторный запуск без изменений даёт exit 0.

При ручном обновлении: править `expected.json` только если менялся
шаблон/backend — иначе выставить `REVIEW_REQUIRED` в коммите.

## Тесты

```bash
pytest -m golden -v
```

Маркер `golden` зарегистрирован в `pyproject.toml`
(`[tool.pytest.ini_options].markers`). Полный список проверок — в
`tests/unit/test_golden.py`.
