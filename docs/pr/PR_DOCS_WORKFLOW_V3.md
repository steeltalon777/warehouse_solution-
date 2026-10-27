# [DRAFT PR] docs/workflow-v3 -> dev (warehouse_solution)

## Что
Установка утверждённой модели разработки: docs/DEVELOPMENT_WORKFLOW.md v3 + краткая ссылка в AGENTS.md (без переписывания правил) + manifest/releases/pilot.yaml (пилотный quick-fix цикл) + отчёт пилота и PR-заготовки.

- Ветка: docs/workflow-v3 от dev (8be27b6)
- Действующие dev/main/prod, compose, сервисы — не тронуты

## Команды для публикации (после разрешения владельца)
```
git -C /home/makc/AI_sandbox/warehouse_solution push origin docs/workflow-v3
gh pr create -R steeltalon777/warehouse_solution- \
  --base dev --head docs/workflow-v3 \
  --title "docs: install Development Workflow v3 + quick-fix pilot evidence" \
  --body-file docs/pr/PR_DOCS_WORKFLOW_V3.md --draft
```
