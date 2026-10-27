# PILOT QUICK-FIX REPORT — 2026-10-27 (EXECUTED)

Пилот по EXECUTION_TZ / DEVELOPMENT_WORKFLOW v3 §3. Весь цикл — без production, без push, без изменения действующих dev/main/prod.

## Что сделано (полный цикл)

| Шаг workflow | Артефакт | Факт |
|---|---|---|
| deployed SHA | cfb93e1 (SyncServer prod image release-4.0-cfb93e1-20260917) | из аудита 2026-10-26 |
| fix-ветка | fix/pilot-search-fallback (worktree feature-env) | cfb93e1 + merge backup/vps-search-fallback = ae92e53 |
| тесты | feature-env feat-pilot-hotfix (127.0.0.1:9100, своя БД, alembic 0038) | см. ниже |
| release-ветка | release/pilot-search-fallback (от fix-head) | создана |
| release image | syncserver:release-pilot-search-fallback-ae92e53 | image_id sha256:30711c48… (локальная сборка, без registry) |
| условный deployment | контейнер feature-env из образа fix-head | health {"status":"ok"}; search endpoint 400 без токена (роутинг жив) |
| manifest | manifest/releases/pilot.yaml (ветка docs/workflow-v3) | записан |
| backport | backport/pilot-search-fallback от origin/dev, cherry-pick -x | 8dca791, f14d838, eea61da; diff с d5be1f3 ПУСТ |
| конфликт-прогноз | git merge-tree dev↔backport | чисто (c902c8c) |
| draft PR | docs/pr/PR_BACKPORT_SEARCH_FALLBACK.md + команды gh | готов, публикация — по разрешению владельца |

## Результаты тестов

| Набор | Условия | Результат |
|---|---|---|
| baseline cfb93e1 (deployed код), полный | feature-env контейнер, общий network+БД, последовательно | **1015 passed, 0 failed**, 3 skipped, 6 xfailed (701s) |
| fix ae92e53, полный (1-й) | там же | 1032 passed, 1 failed (888s) |
| fix, точечно integrity-тест | тот же контейнер | failed → на свежей БД: **44/44 passed**; вместе с fallback-тестами: 62/62 passed; на baseline: 44/44 passed |
| fix, полный 3-й контрольный | там же | см. дополнение ниже |
| интеграция (конфликт разрешён), целевые | /tmp/ss-integrate в сети feature-env | **18 passed** (fallback + batch error format) |

Единственный провал — test_integrity_check_cli::test_repeat_run_is_idempotent — классифицирован как flaky (не воспроизводится: изолированно / в комбинации / на свежей БД / на baseline-полностью). Новых регрессий от 3 hotfix-коммитов не обнаружено; все +17 новых тестов fallback/ошибок проходят.

Delta fix vs baseline: +17 тестов (новые тесты hotfix-коммитов), 0 новых провалов.

## Параллельный конфликт (workflow §4)

- feat/pilot-parallel от cfb93e1 (2 коммита: вставка telemetry-блока + правка той же строки import search_utils, которую переписывает hotfix).
- Временная интеграционная ветка (detached /tmp/ss-integrate от fix-head): merge → **КОНФЛИКТ** app/repos/catalog_repo.py → разрешён (форма hotfix сохранена, параллельный маркер перенесён комментарием) → py_compile OK → целевые тесты 18 passed.
- Реальные ветки не пострадали; интеграционная ветка одноразовая (detached HEAD c5ad5ea).

## Сохранность VPS-кода (архив)

- Дев-машина: backups/vps_search_fallback_2026-10-26/ (bundle sha256 4067da25… + 3 patch), ref backup/vps-search-fallback.
- Вторая копия: VPS ~/backups/vps_search_fallback_2026-10-26/ (sha256 совпадает) — вне единственной машины.
- Оригиналы (VPS-репо, ветка hotfix/search-fallback-zero-results) не удалялись и не менялись.

## Ограничения / честные оговорки

1. Образ собран локально, без registry digest — provenance подтверждается git worktree + image_id, но для прод-цепочки нужен registry (решение владельца).
2. Flaky integrity-тест: в пилоте зафиксирован; требует отдельной задачи (вероятно, тестовая изоляция).
3. Smoke поиска без авторизационных токенов (400) — полнотекстовый smoke с данными не выполнялся: стендовая БД пустая (синтетика по ТЗ).
4. Push/PR/branch protection не выполнялись — прямое указание ТЗ; команды подготовлены.

## Дополнение (3-й контрольный прогон)
3-й полный прогон fix-набора (ae92e53): **1033 passed, 0 failed**, 3 skipped, 6 xfailed (710s).
Итог: fix 1033/0 vs baseline 1015/0 — +18 тестов (все новые тесты hotfix-коммитов), регрессий НЕТ.
Провал 1-го прогона окончательно классифицирован как flaky (test_integrity_check_cli::test_repeat_run_is_idempotent).
