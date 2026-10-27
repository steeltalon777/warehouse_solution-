# [DRAFT PR] backport/pilot-search-fallback -> dev (SyncServer)

## Что
Backport VPS search-fallback hotfix (3 коммита, сохранены с прод-сервера 2026-10-26) в dev.

- Ветка: `backport/pilot-search-fallback` от `origin/dev` (cfb93e1)
- Коммиты: cherry-pick -x f0c649d, 9cc17d3, d5be1f3 -> 8dca791, f14d838, eea61da
- Эквивалентность контента: `git diff d5be1f3 HEAD` пуст (деревья идентичны)
- Конфликтность с dev (c902c8c): `git merge-tree` — чисто

## Проверки (пилот 2026-10-27)
- fix-набор на ae92e53 в feature-env: 1032 passed / 1 env-провал (test_integrity_check_cli::test_repeat_run_is_idempotent — воспроизводится только на загрязнённой конкурентными прогонами БД; на свежей БД 44/44 passed, на baseline тоже проходит)
- Пофайловая сверка patch-id: см. docs/audit/PILOT_QUICKFIX_REPORT_2026-10-27.md

## Команды для публикации (после разрешения владельца)
```
git -C SyncServer push origin backport/pilot-search-fallback
gh pr create -R steeltalon777/SyncServer \
  --base dev --head backport/pilot-search-fallback \
  --title "Backport: VPS search-fallback hotfix (pilot quick-fix)" \
  --body-file docs/pr/PR_BACKPORT_SEARCH_FALLBACK.md --draft
```
