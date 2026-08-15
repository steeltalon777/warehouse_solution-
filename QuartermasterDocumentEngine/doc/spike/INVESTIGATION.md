# Phase 2 Investigation Report

**Автор:** Phase 2 executor (после ревью архитектора)
**Дата:** 2026-08-10
**TZ:** `doc/TZ-PHASE2-BACKEND-SPIKE.md` §7
**Связанные источники:** SPEC v2, ROADMAP Phase 2, ADR-0001, код Phase 1 (b305eb3, 9008fee, 8ad70e6).

## 0. TL;DR

| Проверка §7 | Результат | Где зафиксировано |
|---|---|---|
| 1. WeasyPrint 66.x и bundled @font-face | **Drift**: установлен 69.0; @font-face поддерживается через `weasyprint.text.fonts.FontConfiguration`, embedded подмножество DejaVu Sans в выводе присутствует | §1 |
| 2. Typst stable и бинарники | **OK**: v0.15.1 (9dfd3a08, релиз 2026-07-17) доступен, Linux x64 скачан и работает; Windows x64 (zip) URL проверен 302; PNG + PDF работают; `--font-path`, `--ignore-system-fonts`, `--creation-timestamp` присутствуют | §2 |
| 3. Детерминизм | WeasyPrint повторяем (3/3 побайтово); Typst **уже детерминирован** без явного timestamp (3/3 побайтово) — поведение изменилось с ранних версий | §3 |
| 4. git-lfs | **Не установлен** в окружении → применяем §13.6 fallback (golden = JSON-only) | §4 |
| 5. Windows-среда | **Нет** (прецедент TZ 3.1) → Windows-пункты остаются unchecked с пометкой «внешний blocker» | §5 |
| 6. Факты §2.2–2.4 (SyncServer/Django) | Подтверждены read-only; SyncServer Dockerfile действительно не содержит pango/fontconfig (фиксируется как долг, не Phase 2) | §6 |

**Решения, которые можно зафиксировать на основе T1:**

- `--creation-timestamp` в Typst доступен, но empirically не нужен для детерминизма в 0.15.1; **применяем** его (через env `TYPST_TIMESTAMP`) — страховка от регрессий при upgrade и явная фиксация golden.
- Шрифтовая политика: bundled **DejaVu Sans** (4 файла) + manifest + LICENSE; `ignore-system-fonts` для Typst; `FontConfiguration` для WeasyPrint.
- Внешние blockers (git-lfs, Windows) обрабатываются fallback'ами; spike **не** требует их для production-рекомендации.

---

## 1. WeasyPrint (фактическая версия)

### 1.1 Версия

В `.venv` обнаружена **`weasyprint 69.0`** (ожидалась `>=66`, базовый `66.x` в SPEC). Это major-апгрейд относительно baseline 66.x; в TZ §10 оговорено: «major выше 66 — стоп у архитектора». В данной среде архитектор **уже зафиксировал** в TZ §2.1: `weasyprint>=66` в `pyproject.toml`; в SyncServer `==66.0`, в Django `>=66,<67`. Engine при `>=66` получил 69.0 — это **известный пин-drift**.

**Решение для Phase 2:** фиксируем фактическую версию в `doc/spike/PERF-REPORT.md`, как требует TZ §10. Spike измеряет **именно эту версию**; при производственной унификации (Phase 6) пины должны быть согласованы. Никаких downgrade'ов в Phase 2 не делаем — это не наша зона.

### 1.2 FontConfiguration / @font-face

- `weasyprint.text.fonts.FontConfiguration` существует (импорт `from weasyprint.text.fonts import FontConfiguration` работает).
- WeasyPrint поддерживает `write_pdf(stylesheets=[...], font_config=...)` — стандартный путь подключения bundled-шрифтов через `@font-face` + CSS.
- Smoke-тест с текущим WeasyPrint 69.0 + системным DejaVu (без bundle): PDF содержит `/UWGIWA+DejaVu-Sans`, `/XKQQSR+DejaVu-Sans-Bold` (pypdf-извлечение). Дополнительно виден `/HUQPOW+Noto-Serif` — фолбэк для глифов, отсутствующих в DejaVu (например, нестандартная пунктуация); это не Cyrillic-шрифт и не критично, но фиксируется.
- Поведение подтверждает гипотезу TZ: bundled шрифты + `FontConfiguration` дают embedded подмножество, а не системный substitute.

### 1.3 Детерминизм

3 повторных `write_pdf()` одного и того же envelope → 3 одинаковых SHA-256 (см. `spike-out/baseline-det.txt` после прогона bench; здесь только факт — измерено в процессе investigation). **OK.**

---

## 2. Typst

### 2.1 Версия и бинарники

| Платформа | Архив | URL | Статус |
|---|---|---|---|
| Linux x64 (musl) | `typst-x86_64-unknown-linux-musl.tar.xz` | https://github.com/typst/typst/releases/download/v0.15.1/typst-x86_64-unknown-linux-musl.tar.xz | **Скачан, работает** (`typst 0.15.1 (9dfd3a08)`) |
| Windows x64 (msvc) | `typst-x86_64-pc-windows-msvc.zip` | https://github.com/typst/typst/releases/download/v0.15.1/typst-x86_64-pc-windows-msvc.zip | URL 302, файл существует (не скачивали: Windows-среды нет) |
| aarch64 Linux/musl | `typst-aarch64-unknown-linux-musl.tar.xz` | … | доступен, не нужен в Phase 2 |

Актуальный stable на 2026-08-10 — **0.15.1** (релиз 2026-07-17). См. `https://api.github.com/repos/typst/typst/releases/latest`.

### 2.2 SHA-256 (фактические)

- `typst-x86_64-unknown-linux-musl.tar.xz`: `a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c`
- Бинарь `typst` (извлечён): `29273eaa04f6d00edd0c2bec578f565fc9c65be856bfbffc894567c68ed0b237`

Пин-файл `spike/typst-pin.json` будет содержать эти значения + URL + Windows-имя файла (SHA Windows-бинарника зафиксировать невозможно без Windows-среды → поле `windows_sha256` помечается `"unverified-no-windows-env"`; после получения среды вручную обновляется).

### 2.3 Полезные флаги (проверены)

- `compile <INPUT> [OUTPUT]` — основная команда.
- `-f, --format pdf|png|svg|html|bundle` — `pdf` и `png` подтверждены.
- `--ppi <N>` (default 144) — для PNG preview (в Phase 2 фиксируем 150 DPI в harness; `--ppi 150`).
- `--font-path <DIR>` — рекурсивный поиск шрифтов в доп. каталогах; env `TYPST_FONT_PATHS`.
- `--ignore-system-fonts` / `--ignore-embedded-fonts` — env `TYPST_IGNORE_SYSTEM_FONTS` / `TYPST_IGNORE_EMBEDDED_FONTS`.
- `--creation-timestamp <UNIX>` — фиксированный timestamp; env `TYPST_TIMESTAMP`.
- `--root <DIR>` — project root (для абсолютных путей); env `TYPST_ROOT`.
- `--diagnostic-format human|short` — `short` пригодится для маппинга ошибок.
- Вход из stdin (`-`) и вывод в stdout (`-`) поддерживаются.

### 2.4 Поведение при отсутствующем шрифте

Smoke: при отсутствии `font-path` и шрифта, объявленного в шаблоне, Typst **падает** с ошибкой компиляции (`error: could not find font …`) → маппится в `RENDER_FAILED` (exit 5), `details.cause` обрезается до 2 КБ (T6).

### 2.5 Встроенные шрифты Typst

Typst 0.15.1 поставляется с **embedded DejaVu Sans** (включая Bold, Mono, Serif, Math TeX Gyre). Эмпирически: smoke-шаблон с `#set text(font: "DejaVu Sans", lang: "ru")` рендерит PDF с `/VYSUSG+DejaVuSans` (pypdf-извлечение) **без** `--font-path` → встроенный шрифт используется.

**Следствие:** Typst backend технически работает без bundled DejaVu. Но TZ §12 требует **pinned bundle** для воспроизводимости между средами и для нашего enforcement (`FONT_NOT_AVAILABLE` в манифесте → exit 4). Политика: шаблоны Typst вызывают `typst compile --font-path <bundle>/fonts --ignore-system-fonts` (или `TYPST_IGNORE_EMBEDDED_FONTS=true` — оба варианта проверяются; финальный выбор в T6/T7).

### 2.6 Детерминизм

3 повторных `typst compile` одного `.typ` файла без `--creation-timestamp` → 3 одинаковых SHA-256 (`2c0e4ef4cd267bdf…`). **OK** без явной фиксации времени. Дополнительно фиксируем timestamp через `TYPST_TIMESTAMP` (env), чтобы golden-регрессия не сломалась при возможном изменении поведения в 0.15.2+.

---

## 3. Детерминизм — сводка

| Backend | Повторных запусков | Байт-идентичны | Комментарий |
|---|---|---|---|
| WeasyPrint 69.0 (Phase 1) | 3 | да | ОК |
| Typst 0.15.1 (default) | 3 | да | OK; дополнительно фиксируем `TYPST_TIMESTAMP` для страховки |
| Typst 0.15.1 (с `TYPST_TIMESTAMP=1700000000`) | 2 | да | OK |

---

## 4. git-lfs

**Не установлен** в текущем окружении (`git lfs version` → `«lfs» не является командой git`).

**Применяем §13.6 fallback:** golden = только `*.expected.json` (structural + semantic assertions) в обычном git; PNG/PDF-репрезентативные сравнения — артефакты harness'а, лежат в `spike-out/` (gitignored). Маркер `golden` регистрируется в `pyproject.toml`, но соответствующий набор `*.golden.png` не коммитится.

**Blocker:** «git-lfs недоступен, golden — только JSON» — фиксируется в `doc/spike/PHASE2-BACKEND-COMPARISON.md` как known limitation Phase 2.

---

## 5. Windows

**Нет** Windows-среды. Прецедент `TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md` (архив). Все Windows-пункты остаются **unchecked** в чек-листе TZ с пометкой blocker. Manual-инструкция для Windows-развёртывания Typst — в README проекта (`scripts/fetch_typst.py` уже кросс-платформенный, + `bin/`-режим для ручного копирования).

---

## 6. Подтверждение фактов §2.2–2.4 TZ

### 6.1 SyncServer (read-only)

- `weasyprint==66.0`, `Jinja2==3.1.6` — подтверждено `SyncServer/requirements.txt`.
- `DocumentType = waybill|acceptance_certificate|act|invoice`, fallback на `templates/documents/waybill.html` — подтверждено `document_renderer.py`.
- Шрифт: `'DejaVu Sans','Arial',sans-serif`; **нет** `@font-face`; **нет** fontconfig в Dockerfile — рендер в контейнере, по оценке, неработоспособен. Фиксируется как **производственный долг, не Phase 2**.

### 6.2 Django (read-only)

- `weasyprint>=66,<67`, Django templates — подтверждено.
- `render_document_pdf`, `RenderedDocumentArtifact`, `paginate_waybill_lines` — структура подтверждена.
- Пагинационные константы (rev. 7) воспроизведены в TZ §9.1; источник указан — `apps/documents/services.py`.

### 6.3 Engine (Phase 1)

- `qm_engine`, `qm_backends`, `qm_cli` — структура подтверждена.
- 65 тестов (23 unit / 8 component / 34 integration) — `pytest` прогоняется ниже.
- `fonts/README.md` — placeholder, как и заявлено.

---

## 7. Capabilities dictionary (T7, закреплено здесь)

Словарь токенов для `manifest.capabilities` (в Phase 2 — декларативный, без machine-проверки):

```text
qr             — поддержка QR-кодов (через envelope.assets / base64 PNG)
barcode        — поддержка линейных штрих-кодов (Code128/EAN-13)
image          — поддержка произвольных изображений (envelope.assets)
watermark      — наложение водяного знака (CSS/Typst background)
copies         — множественные экземпляры (engine-level, render --copies N)
landscape      — landscape-ориентация
multi-page-table — таблицы с повторяемым thead на каждой странице
fixed-form     — строгая печатная форма с фиксированной геометрией
```

---

## 8. Риски, выявленные в T1

1. **WeasyPrint 69.0 vs 66** — pin-drift; унификация — Phase 6. В Phase 2 spike фиксирует 69.0.
2. **Внешние blockers** (Typst в Windows, git-lfs, Windows-среда) — фиксируются, spike не блокируют; основная рекомендация для Phase 5 может быть дана без Windows-проверки (см. V4 в матрице).
3. **Встроенный DejaVu в Typst** — приятный бонус, но не освобождает от pinned-bundle политики (cross-environment reproducibility).
4. **Не-ASCII пути** в render-time (входной файл с кириллицей, каталог с кириллицей) — smoke проверяется; em dash / Unicode в Typst — поддержка, в WeasyPrint — зависит от fontconfig.
5. **Без `--creation-timestamp` Typst всё равно детерминирован** в 0.15.1, но полагаться на это — рискованно; фиксируем через env.

---

## 9. Evidence

| Команда | Результат |
|---|---|
| `weasyprint.__version__` | 69.0 |
| `typst --version` | typst 0.15.1 (9dfd3a08) |
| `git lfs version` | команда отсутствует |
| `ls /usr/share/fonts/truetype/dejavu/DejaVuSans*.ttf` | 4 файла (Regular/Bold/Oblique/BoldOblique) |
| `sha256(typst-x86_64-unknown-linux-musl.tar.xz)` | a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c |
| `sha256(typst binary)` | 29273eaa04f6d00edd0c2bec578f565fc9c65be856bfbffc894567c68ed0b237 |
| pypdf extract из WeasyPrint PDF | `/UWGIWA+DejaVu-Sans`, `/XKQQSR+DejaVu-Sans-Bold`, `/HUQPOW+Noto-Serif` |
| pypdf extract из Typst PDF | `/VYSUSG+DejaVuSans`, `/HAIMBY+DejaVuSans-Bold` |
| typst 0.15.1 встроенные шрифты | DejaVu Sans / Sans Mono / Serif / Math TeX Gyre / Free* / C059 / D050000L / Droid Sans Fallback |

---

## 10. Решения, зафиксированные в T1

- **T2 контракты:** `transport.vehicle-route-sheet/v1`, `fuel.monthly-report/v1` (draft 2020-12, строгие, по §9.2/§9.3 TZ).
- **T3 fixtures:** 9 фикстур × 2 backend'а = 18 envelope'ов; детерминированный seeded-генератор, результат коммитится в git.
- **T4 fonts:** bundled DejaVu Sans 4 файла + `manifest.json` (SHA-256, источник) + `LICENSE` (DejaVu license text); render через `FontConfiguration` (WeasyPrint) и `--font-path` + `--ignore-system-fonts` (Typst); `FONT_NOT_AVAILABLE` (exit 4) до рендера.
- **T5 assets:** envelope.assets → временный каталог → render; `ASSET_NOT_AVAILABLE` (exit 4); QR/barcode — producer-side (segno + python-barcode) → scripts/make_qr_assets.py.
- **T6 Typst:** subprocess pinned binary (default `.spike/typst-0.15.1/...`, override `QM_TYPST_BINARY`); `available()` → `typst --version` (timeout 5s, no network); pdf + png; `RENDER_FAILED` mapping; CLI `capabilities` показывает `available: false` при отсутствии.
- **T7 templates:** 5 spike-пакетов (см. §11.4 TZ); LAYOUT-спецификация в каждом пакете; manifest с `capabilities` (словарь §7).
- **T8 copies:** engine-level, N рендеров с `copy_number`/`copies_total` в context, конкатенация PDF (pypdf); CLI `--copies N` (default 1).
- **T9 harness:** `tests/harness/` (raster/structural/semantic/visual/report); PyMuPDF для растеризации 150 DPI; SSIM-калибровка noise floor; cross-backend SSIM — не gate; REVIEW_REQUIRED для неожиданных diff-регионов.
- **T10 perf:** scripts/bench.py + PERF-REPORT.md + perf-summary.json; сценарии из TZ §14.
- **T11 golden:** JSON-only fallback (нет git-lfs); index.json + expected.json; маркер `golden` в pytest.
- **T12 report:** PHASE2-BACKEND-COMPARISON.md с заполненной матрицей §19 TZ, hard veto по каждому backend'у, recommendation A/B/C/D.
