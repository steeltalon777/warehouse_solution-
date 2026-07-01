# Дорожная карта — Quartermaster

> Последнее обновление: 2026-07-01

## Стратегическая линия

```
3.x — Product Foundation      «Мы перестаём быть кучей кода и становимся системой»
4.x — Operational Platform    «Платформа учёта имущества и операций для организации»
5.x — Multi-Organization      «Self-hosted framework: несколько организаций, общий движок»
```

Система выросла из «надо бы склад, чтобы ТМЦ не терялись» в зачаток производственного self-hosted framework'а для учёта, операций и снабжения. Ниже — пройденный путь и план.

---

## ✅ 3.x — Product Foundation

### v3.0 — Онлайн-клиент (выполнено)

| Этап | Статус |
|------|--------|
| Контракты агентов и документации | ✅ |
| Стабильность backend-контракта (SyncServer 410+ тестов) | ✅ |
| Django как активный web-клиент и BFF | ✅ |
| Angular SPA shell | ✅ |
| Warehouse Client Core — Rust foundation | ✅ |

### ✅ v3.1 — Foundation Release (выполнено)

> **Quartermaster 3.1: Foundation Release**
> Брендинг, AI-friendly документация, ADR, карта API, подготовка offline-contract, выравнивание каталога/номенклатуры, hardening админки и operations UX.

| Блок | Статус |
|------|--------|
| 3.1A Branding: Quartermaster | ✅ |
| 3.1B SyncServer: sync_state + offline contract | ✅ sync_state table, GET /sync/status/{device_id}, ping/pull/push updates |
| 3.1C Rust core: compatibility gate | ✅ payload_hash (canonical JSON+SHA-256), stand smoke pass |
| 3.1D WPF: Layer 0 FFI spike | [ ] |
| 3.1E Documentation: ADR-0015/0016/0017 | ✅ ADR созданы, docs Stage 5 выполнено |
| 3.1F Admin Panel Hardening: password fix, multi-site, device parity, reset flow | [ ] TZ создан |
| 3.1G Operations UX Hardening: submit error tracebacks, inline-SKU validation | [ ] |
| 3.1H Waybill PDF Fixes: metadata sync, multi-page rendering, on-demand PDF | [ ] TZ создан |
| 3.1I Operation Lines Sorting: default sort by lineNumber in modal | ✅ выполнено |

### v3.2 — Desktop client migration

- WPF Layers 1-7: Bootstrap → Auth → Directory → Operations → Balances → Documents → Sync → Cleanup
- Полный переход WarehouseWorkstation на Rust core через FFI

### v3.3 — Android client

- Kotlin/UniFFI обвязка вокруг `Warehouse_client_core`
- Экран входа + каталог + draft-операции

### v3.4 — Advanced offline UX

- Полный conflict resolution (merge)
- Печать, QR/штрихкоды, сканы, вложения

---

## 🔮 4.x — Operational Platform

> **Quartermaster 4.0: Field Operations Release**
> Клиенты, offline-first desktop/mobile, AI-интеграция, заявки, workflow, уведомления, черновики, очереди, ассистент кладовщика/снабженца, интеграция с документами. Операционная система имущества для организации.

| Компонент | Статус |
|-----------|--------|
| Desktop offline client (WPF → Rust core) | Планируется |
| Mobile offline client (Android) | Планируется |
| AI-интеграция (ассистент, рекомендации) | WarehouseWorkstation AI на паузе |
| Заявки / workflow | Планируется |
| Уведомления | Планируется |
| Ассистент кладовщика/снабженца | Планируется |

---

## 🔮 5.x — Multi-Organization Platform

> **Quartermaster 5.0: Multi-Organization Platform**
> Несколько организаций, изоляция tenant'ов, общий движок, разные контуры доступа, разные базы/схемы или tenant_id, подключаемые клиенты, разные политики синхронизации, разные администраторы организаций.

| Компонент | Статус |
|-----------|--------|
| Мультиорганизация (tenant isolation) | Планируется |
| Marketplace-модули | Планируется |
| Подключаемые клиенты | Планируется |
| Разные политики синхронизации | Планируется |

---

## На паузе

- `WarehouseAIWorkstation/` — AI-функционал (чат, governance, бюджет токенов) до явного возобновления

---

## История

Проект начался в феврале 2026 с «надо бы склад, чтобы ТМЦ не терялись в болотах и Excel не был богом бухгалтерии». За 4 месяца вырос в платформу учёта имущества и операций: SyncServer (источник истины), Django (web-клиент/BFF), Angular (SPA), Rust core (offline-first runtime), WPF AI Workstation. Почти WMS, местами задевает ERP-контур, местами начинает походить на маленький Nextcloud для производственной организации.
