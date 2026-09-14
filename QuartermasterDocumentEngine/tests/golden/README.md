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

**17 entries** (полный список — `index.json`):

| Набор | template@version | entries | fixtures |
|---|---|---|---|
| Phase 2 spike-матрица | `warehouse-waybill-ru@1.0`, `spike-*@0.1.0` | 6 | `tests/fixtures/{waybill,route-sheet,fuel}/*` |
| Каноническая продакшн-форма | `warehouse-waybill-ru@2.0.0` | 5 | `tests/fixtures/waybill/waybill-qde-{1,20,75,200,500}.typst.json` |
| Null-safety патч (ADR-0034) | `warehouse-waybill-ru@2.2.1` | 6 | `tests/fixtures/waybill-null/*.typst.json`, `tests/fixtures/waybill-221/waybill-qde221-75.typst.json` |

### `t9_compare`

T9-артефакты (`spike-out/compare/<fixture>/{structural,semantic}.json`)
зафиксированы только для базовых фикстур Phase 2 / 6C. Записи с
`"t9_compare": false` исключены из проверки
`test_golden_expected_values_match_t9_output`: страницы 2.2.x
намеренно отличаются от замороженного legacy-базлайна
(measurable pagination rebalance, LAYOUT.md §10), поэтому сравнение с
T9 для них не имеет смысла. Все остальные golden-гейты
(`golden_update.py --check`, required keys, LFS-флаг) применяются к
ним в полном объёме.

Для null-safety записей `pass: false` в отдельных полях — это
**ожидаемый** результат, а не дефект: исторический receiver=null
capture и sender=null вариант сознательно уходят в computed-title
fallback, поэтому `semantic.document_number` не совпадает с
envelope-номером (запись фиксируется «как есть», см. ниже).

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
