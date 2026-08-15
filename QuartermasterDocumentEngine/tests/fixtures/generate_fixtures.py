"""Deterministic Phase 2 fixture generator (TZ §8 T3).

Run from repo root: ``python tests/fixtures/generate_fixtures.py``.

Re-running without source changes produces byte-identical files (asserted by
``tests/unit/test_fixtures.py``).

Produces 9 logical fixtures × 2 envelopes = 18 JSON files:

* ``tests/fixtures/waybill/waybill-{1,20,75,200,500}.{weasy,typst}.json``
* ``tests/fixtures/route-sheet/vehicle-route-sheet-1.{weasy,typst}.json``
* ``tests/fixtures/fuel/fuel-report-{100,500,1500}.{weasy,typst}.json``

All Cyrillic text is emitted via ``json.dump(..., ensure_ascii=False)`` so the
resulting bytes match what producers in the warehouse pipeline will emit.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SEED = 0x7BADC0DE  # deterministic across machines/runs.

# Template references (cross-checked against TZ §T7).
WAYBILL_WEASY_TEMPLATE_ID = "warehouse-waybill-ru"
WAYBILL_WEASY_TEMPLATE_VERSION = "1.0"
WAYBILL_TYPST_TEMPLATE_ID = "spike-waybill-typst"
WAYBILL_TYPST_TEMPLATE_VERSION = "0.1.0"

ROUTE_SHEET_WEASY_TEMPLATE_ID = "spike-route-sheet-weasy"
ROUTE_SHEET_TYPST_TEMPLATE_ID = "spike-route-sheet-typst"
SPIKE_TEMPLATE_VERSION = "0.1.0"

FUEL_WEASY_TEMPLATE_ID = "spike-fuel-report-weasy"
FUEL_TYPST_TEMPLATE_ID = "spike-fuel-report-typst"

REPO = Path(__file__).resolve().parents[2]
WAYBILL_DIR = REPO / "tests" / "fixtures" / "waybill"
ROUTE_DIR = REPO / "tests" / "fixtures" / "route-sheet"
FUEL_DIR = REPO / "tests" / "fixtures" / "fuel"


# ---------------------------------------------------------------------------
# Shared catalogue: realistic Russian names from auto/warehouse domain.
# Each entry has a short base, a long descriptive form, the SKU kind, units,
# default category, and acceptance-spread defaults.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ItemTemplate:
    """Base shape used to derive a waybill line."""

    short_name: str
    long_name: str
    default_quantity: float
    unit_name: str
    unit_symbol: str
    default_category: str
    sku_prefix: str


_ITEM_TEMPLATES: tuple[_ItemTemplate, ...] = (
    _ItemTemplate(
        short_name="Колодка тормозная",
        long_name=(
            "Колодка тормозная переднего моста КамАЗ-65115 в сборе с "
            "противоскрипными пластинами, оцинкованная, класс трения FF"
        ),
        default_quantity=4.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Тормозная система",
        sku_prefix="BRK-PAD",
    ),
    _ItemTemplate(
        short_name="Болт колеса",
        long_name=(
            "Болт колеса М18х1.5 с внутренним шестигранником, класс прочности "
            "10.9, оцинкованный, для дисковых и бездисковых колёс грузовых а/м"
        ),
        default_quantity=20.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Крепёж",
        sku_prefix="WHL-BOLT",
    ),
    _ItemTemplate(
        short_name="Фильтр топливный",
        long_name=(
            "Фильтр топливный грубой очистки для дизельных двигателей КамАЗ-740, "
            "сменный элемент в металлическом корпусе с отстойником"
        ),
        default_quantity=2.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Топливная система",
        sku_prefix="FUEL-FLT",
    ),
    _ItemTemplate(
        short_name="Комплект ремонта шин",
        long_name=(
            "Комплект для ремонта бескамерных шин R17-R20, включающий жгуты, "
            "вулканизирующую химию и монтажный инструмент в металлическом кейсе"
        ),
        default_quantity=5.0,
        unit_name="Штука",
        unit_symbol="упак",
        default_category="Шиномонтаж",
        sku_prefix="TIRE-KIT",
    ),
    _ItemTemplate(
        short_name="Масло моторное М-10Г2к",
        long_name=(
            "Масло моторное М-10Г2к SAE 30, минеральное для дизельных "
            "двигателей грузовых автомобилей, фасовка 5 литров в металлической "
            "канистре с длинным носиком"
        ),
        default_quantity=12.0,
        unit_name="Литр",
        unit_symbol="л",
        default_category="ГСМ",
        sku_prefix="OIL-10G2",
    ),
    _ItemTemplate(
        short_name="Подшипник 6204",
        long_name=(
            "Подшипник шариковый радиальный однорядный 6204-2RS закрытого типа, "
            "производства SKF, для ступиц передних колёс легковых и грузовых а/м"
        ),
        default_quantity=8.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Подшипники",
        sku_prefix="BRG-6204",
    ),
    _ItemTemplate(
        short_name="Пружина пневматическая",
        long_name=(
            "Пружина пневматическая (рессора пневматическая) для подвески кабины "
            "КамАЗ, двухсекционная, усиленная, с металлическими фланцами и "
            "стальным баллоном"
        ),
        default_quantity=2.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Подвеска",
        sku_prefix="AIR-SPR",
    ),
    _ItemTemplate(
        short_name="Шланг РВД",
        long_name=(
            "Шланг гидравлический высокого давления РВД DN12, длина 1200 мм, "
            "с фитингами под ключ 22 мм, рабочее давление 350 бар, импульсный"
        ),
        default_quantity=3.0,
        unit_name="Метр",
        unit_symbol="м",
        default_category="Гидравлика",
        sku_prefix="HYD-HOSE",
    ),
    _ItemTemplate(
        short_name="Прокладка ГБЦ",
        long_name=(
            "Прокладка головки блока цилиндров КамАЗ-740, многослойная "
            "сталь-паронит, толщина 1.5 мм, с уплотнительными кольцами "
            "коллекторов и масляных каналов"
        ),
        default_quantity=1.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Двигатель",
        sku_prefix="GASKET",
    ),
    _ItemTemplate(
        short_name="Свеча накаливания",
        long_name=(
            "Свеча накаливания для предпускового подогрева дизельного двигателя, "
            "с керамическим нагревательным элементом и никелевым корпусом, "
            "рабочее напряжение 11V, резьба М10х1.0"
        ),
        default_quantity=4.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Электрооборудование",
        sku_prefix="GLOW-PL",
    ),
    _ItemTemplate(
        short_name="Перчатки комбинированные",
        long_name=(
            "Перчатки рабочие комбинированные (спилок + х/б ткань), утеплённые, "
            "размер L, для работы с металлом и ГСМ в зимних условиях"
        ),
        default_quantity=10.0,
        unit_name="Пара",
        unit_symbol="пара",
        default_category="СИЗ",
        sku_prefix="PPE-GLV",
    ),
    _ItemTemplate(
        short_name="Канат буксировочный",
        long_name=(
            "Канат буксировочный синтетический (полиэстер), 8 метров, нагрузка "
            "до 5 тонн, с двумя стальными карабинами и защитным чехлом"
        ),
        default_quantity=2.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Аксессуары",
        sku_prefix="TOW-ROPE",
    ),
    _ItemTemplate(
        short_name="Антифриз G11",
        long_name=(
            "Антифриз G11 зелёный на основе этиленгликоля, температура "
            "замерзания -40°C, фасовка 5 литров в пластиковой канистре с "
            "ручкой и мерной шкалой"
        ),
        default_quantity=15.0,
        unit_name="Литр",
        unit_symbol="л",
        default_category="ГСМ",
        sku_prefix="AF-G11",
    ),
    _ItemTemplate(
        short_name="Трос ручного тормоза",
        long_name=(
            "Трос стояночного тормоза КамАЗ в сборе с наконечниками и "
            "регулировочной гайкой, длина 1450 мм, металлическая оболочка"
        ),
        default_quantity=1.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Тормозная система",
        sku_prefix="BRK-CBL",
    ),
    _ItemTemplate(
        short_name="Фильтр масляный",
        long_name=(
            "Фильтр масляный неразборный для дизельных двигателей, с обратным "
            "клапаном и уплотнительным кольцом, рабочее давление до 4 бар"
        ),
        default_quantity=6.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Двигатель",
        sku_prefix="OIL-FLT",
    ),
    _ItemTemplate(
        short_name="Ремень генератора",
        long_name=(
            "Ремень генератора клиновой для двигателей КамАЗ, сечение 12.5х9.5, "
            "длина 1120 мм, с усиленным кордом, повышенный ресурс"
        ),
        default_quantity=2.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Двигатель",
        sku_prefix="ALT-BELT",
    ),
    _ItemTemplate(
        short_name="Диск сцепления",
        long_name=(
            "Диск сцепления ведомый для КПП КамАЗ, Ø 350 мм, 10 зубьев, "
            "с демпферной пружиной, фрикционные накладки безасбестовые"
        ),
        default_quantity=1.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Трансмиссия",
        sku_prefix="CL-DISC",
    ),
    _ItemTemplate(
        short_name="Шланг тормозной",
        long_name=(
            "Шланг тормозной передний армированный для грузовых а/м, длина 480 "
            "мм, резьба М10х1.0 с обеих сторон, рабочее давление 200 бар"
        ),
        default_quantity=4.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Тормозная система",
        sku_prefix="BRK-HOSE",
    ),
    _ItemTemplate(
        short_name="Вкладыши коренные",
        long_name=(
            "Вкладыши коренные верхние и нижние для двигателя КамАЗ-740, "
            "комплект на 1 цилиндр, биметаллические с антифрикционным покрытием"
        ),
        default_quantity=2.0,
        unit_name="Штука",
        unit_symbol="шт",
        default_category="Двигатель",
        sku_prefix="BRG-MAIN",
    ),
    _ItemTemplate(
        short_name="Лампа Н4",
        long_name=(
            "Лампа автомобильная галогенная Н4 24V 75/70W, цоколь P43t-38, "
            "усиленная вибростойкая, для головной оптики грузовых а/м"
        ),
        default_quantity=2.5,
        unit_name="Килограмм",
        unit_symbol="кг",
        default_category="Без категории",
        sku_prefix="BULB-H4",
    ),
)


_CATEGORIES_WITH_NONE = (
    "Без категории",
    "Тормозная система",
    "Крепёж",
    "Топливная система",
    "Шиномонтаж",
    "ГСМ",
    "Подшипники",
    "Подвеска",
    "Гидравлика",
    "Двигатель",
    "Электрооборудование",
    "СИЗ",
    "Аксессуары",
    "Трансмиссия",
)

_TRIP_PURPOSES = (
    "Грузовая перевозка ТМЦ",
    "Доставка запасных частей",
    "Перегон техники на базу",
    "Перевозка ГСМ к месту заправки",
    "Транспортировка оборудования",
    "Служебная поездка",
)

_TRIP_ORIGINS = (
    "База «Северный терминал»",
    "Производственная площадка № 2",
    "Склад ГСМ «Угдан»",
    "АЗС «Лукойл-247»",
    "Мастерская ТО «ДЭУ (КСК)»",
    "Гаражный бокс № 14",
)

_TRIP_DESTINATIONS = (
    "Склад заказчика № 14",
    "Площадка временного хранения",
    "Ремонтная зона № 3",
    "Терминал «Восточный»",
    "База «Центральный склад»",
    "Полевой лагерь «Чарочная»",
)

_REFUEL_STATIONS = (
    "АЗС «Лукойл-247»",
    "АЗС «Газпромнефть-105»",
    "АЗС «Роснефть-37»",
    "АЗС «Татнефть-13»",
    "АЗС «Шелл-77»",
)

_FUEL_TYPES = (
    "Дизельное топливо",
    "Бензин АИ-92",
    "Бензин АИ-95",
    "Бензин АИ-98",
    "Газ пропан-бутан",
)

_VEHICLES: tuple[dict[str, Any], ...] = (
    {
        "id": "V-KAM-001",
        "name": "КамАЗ 65115",
        "plate": "А 123 ВС 75",
        "unit": "л",
        "norm_l_per_100km": 28.5,
    },
    {
        "id": "V-KAM-002",
        "name": "КамАЗ 65116",
        "plate": "А 124 ВС 75",
        "unit": "л",
        "norm_l_per_100km": 30.2,
    },
    {
        "id": "V-KAM-003",
        "name": "КамАЗ 6520",
        "plate": "А 125 ВС 75",
        "unit": "л",
        "norm_l_per_100km": 34.8,
    },
    {
        "id": "V-KAM-004",
        "name": "КамАЗ 43118",
        "plate": "А 126 ВС 75",
        "unit": "л",
        "norm_l_per_100km": 31.6,
    },
    {
        "id": "V-KAM-005",
        "name": "КамАЗ 65206",
        "plate": "А 127 ВС 75",
        "unit": "л",
        "norm_l_per_100km": 27.4,
    },
    {
        "id": "V-UAZ-001",
        "name": "УАЗ 3909",
        "plate": "В 456 ОК 75",
        "unit": "л",
        "norm_l_per_100km": 17.2,
    },
    {
        "id": "V-UAZ-002",
        "name": "УАЗ 3151",
        "plate": "В 457 ОК 75",
        "unit": "л",
        "norm_l_per_100km": 16.8,
    },
    {
        "id": "V-GAZ-001",
        "name": "ГАЗель Next",
        "plate": "К 234 МН 75",
        "unit": "л",
        "norm_l_per_100km": 12.5,
    },
    {
        "id": "V-ZIL-001",
        "name": "ЗИЛ 4331",
        "plate": "М 789 АА 75",
        "unit": "л",
        "norm_l_per_100km": 26.4,
    },
    {
        "id": "V-MAZ-001",
        "name": "МАЗ 5440",
        "plate": "Н 012 ВК 75",
        "unit": "л",
        "norm_l_per_100km": 29.1,
    },
)


# ---------------------------------------------------------------------------
# Helpers (stable JSON emission).
# ---------------------------------------------------------------------------


def _dumps(payload: Mapping[str, Any]) -> str:
    """Emit JSON with stable key order, UTF-8 (no \\uXXXX escapes for Cyrillic)."""

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dumps(payload), encoding="utf-8")


def _rng() -> random.Random:
    """Fresh seeded PRNG so determinism test can re-call builders."""
    return random.Random(SEED)


# ---------------------------------------------------------------------------
# Waybill envelopes (§9.1).
# ---------------------------------------------------------------------------


def _build_waybill_line(rng: random.Random, line_number: int, base_index: int) -> dict[str, Any]:
    tpl = _ITEM_TEMPLATES[base_index % len(_ITEM_TEMPLATES)]
    # ~80% of lines use the long name (2–4 visual lines @ 40 chars),
    # the rest use a short reference name.
    use_long = rng.random() < 0.8
    name = tpl.long_name if use_long else tpl.short_name
    # Quantity: prefer integer (60%), otherwise integer (35%), otherwise one
    # of the three TZ-mandated decimals. The integer branch dominates, the
    # integer-with-zero-decimals tail gives 0.0/1.0 which we re-roll away.
    qty_bucket = rng.random()
    if qty_bucket < 0.6:
        quantity = float(rng.randint(1, 25))
    elif qty_bucket < 0.85:
        quantity = float(rng.randint(10, 80))
    elif qty_bucket < 0.92:
        quantity = 2.5
    elif qty_bucket < 0.97:
        quantity = 12.75
    else:
        quantity = 0.333

    # SKU: ~70% set, ~30% empty string (matches prod envelope).
    sku: str | None = f"{tpl.sku_prefix}-{line_number:04d}" if rng.random() < 0.7 else ""

    # Category: 35% "Без категории", otherwise pick from the rest.
    category = (
        "Без категории"
        if rng.random() < 0.35
        else _CATEGORIES_WITH_NONE[rng.randrange(1, len(_CATEGORIES_WITH_NONE))]
    )

    # Batch: ~30% set, otherwise None.
    batch: str | None = (
        f"B-{rng.randint(2024, 2026)}-{rng.randint(1000, 9999)}" if rng.random() < 0.3 else None
    )

    # Comment: line 50 (if present) always gets a long descriptive comment,
    # otherwise ~25% of the remaining lines get a short catalog comment.
    comment: str | None
    if line_number == 50:
        comment = (
            "Обратить внимание: применять только с новой прокладкой ГБЦ; "
            "перед установкой проверить плоскость; момент затяжки 9 кгс·м "
            "крест-накрест в два приёма; после обкатки 1000 км повторный "
            "контроль момента."
        )
    elif rng.random() < 0.25:
        candidates = (
            "Перед установкой обезжирить.",
            "Партия проверена ОТК.",
            "Срочный заказ по заявке № 4711.",
            "Поставка ожидается в течение недели.",
            "По решению главного механика.",
            "Только под комплектацию с VIN X9L0…",
        )
        comment = candidates[rng.randrange(len(candidates))]
    else:
        comment = None

    # The prod envelope uses both item_id (int) and line_number (int).
    item_id = 100000 + base_index * 7 + line_number

    # Field order matches prod waybill envelope for small diffs.
    return {
        "batch": batch,
        "comment": comment,
        "item_id": item_id,
        "item_sku": sku,
        "quantity": quantity,
        "item_name": name,
        "unit_name": tpl.unit_name,
        "line_number": line_number,
        "unit_symbol": tpl.unit_symbol,
        "category_name": category,
    }


def build_waybill_envelope(
    n_lines: int,
    template_id: str,
    template_version: str,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Build a MOVE waybill envelope with ``n_lines`` deterministically generated."""

    if rng is None:
        rng = _rng()
    document_number = f"WB-FIX-{n_lines}"
    lines = [_build_waybill_line(rng, idx, idx) for idx in range(1, n_lines + 1)]

    basis_label = "Перемещение Угдан → ДЭУ (КСК)"
    now = "2026-08-10T03:43:53.693546+00:00"
    document = {
        "basis": {
            "date": None,
            "type": None,
            "label": basis_label,
            "number": None,
            "operation_type_label": "Перемещение",
        },
        "lines": lines,
        "sender": {
            "site_id": 1,
            "site_code": "1",
            "site_name": "Угдан",
            "description": "",
            "organization": {
                "tax_id": None,
                "address": "",
                "contacts": None,
                "legal_name": "Угдан",
            },
        },
        "language": "ru",
        "receiver": {
            "site_id": 4,
            "site_code": "4",
            "site_name": "ДЭУ (КСК)",
            "description": "",
            "organization": {
                "tax_id": None,
                "address": "",
                "contacts": None,
                "legal_name": "ДЭУ (КСК)",
            },
        },
        "issued_to": None,
        "operation": {
            "id": "867f0f48-f8d2-42d0-955f-65a25d0885c3",
            "type": "MOVE",
            "status": "draft",
            "site_id": 1,
            "created_at": now,
            "type_label": "Перемещение",
            "effective_at": "2026-08-10T03:42:00+00:00",
            "submitted_at": None,
            "display_number": "1/0343/100826",
            "source_site_id": 1,
            "issue_object_id": None,
            "issue_object_name": None,
            "destination_site_id": 4,
        },
        "recipient": None,
        "created_by": {
            "role": "chief_storekeeper",
            "user_id": "7337709e-a82b-4813-8b4d-283addc7a9c3",
            "username": "Svetlana",
            "full_name": "Светлана Викторовна",
        },
        "signatures": {
            "roles": {
                "accepted_by": None,
                "handed_over": None,
                "chief_accountant": "________________",
            },
            "created_by": "Светлана Викторовна",
            "submitted_by": None,
        },
        "basis_label": basis_label,
        "source_site": {
            "site_id": 1,
            "site_code": "1",
            "site_name": "Угдан",
            "description": "",
            "organization": {
                "tax_id": None,
                "address": "",
                "contacts": None,
                "legal_name": "Угдан",
            },
        },
        "total_lines": n_lines,
        "generated_at": now,
        "localization": {
            "currency": "RUB",
            "language": "ru",
            "date_format": "%d.%m.%Y",
            "datetime_format": "%d.%m.%Y %H:%M:%S",
            "thousands_separator": " ",
            "number_decimal_separator": ",",
        },
        "operation_id": "867f0f48-f8d2-42d0-955f-65a25d0885c3",
        "submitted_by": None,
        "document_title": "Товарная накладная",
        "operation_type": "MOVE",
        "consignee_label": "ДЭУ (КСК)",
        "operation_notes": None,
        "destination_site": {
            "site_id": 4,
            "site_code": "4",
            "site_name": "ДЭУ (КСК)",
            "description": "",
            "organization": {
                "tax_id": None,
                "address": "",
                "contacts": None,
                "legal_name": "ДЭУ (КСК)",
            },
        },
        "operation_status": "draft",
        "operation_created_at": now,
        "operation_type_label": "Перемещение",
        "operation_effective_at": "2026-08-10T03:42:00+00:00",
        "operation_submitted_at": None,
        "operation_display_number": "1/0343/100826",
        "operation_acceptance_state": "pending",
    }

    return {
        "engine_contract_version": "1.0.0",
        "document_contract": "warehouse.operation-document/v2",
        "document_type": "waybill",
        "template_id": template_id,
        "template_version": template_version,
        "locale": "ru-RU",
        "render_profile": "print",
        "document_id": "8c2ef0d8-695f-4d57-8073-a9aba81b16ca",
        "document_number": document_number,
        "document": document,
        "assets": {},
    }


# ---------------------------------------------------------------------------
# Vehicle route sheet (§9.2).
# ---------------------------------------------------------------------------


def _iso_datetime(rng: random.Random, year: int, month: int) -> str:
    day = rng.randint(1, 28)
    hour = rng.randint(5, 22)
    minute = rng.choice((5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 0))
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00+03:00"


def _build_trip(rng: random.Random, year: int, month: int) -> dict[str, Any]:
    departure_at = _iso_datetime(rng, year, month)
    duration_min = rng.randint(15, 480)
    departure_dt = _parse_dt_partial(departure_at, duration_min)
    return_at = departure_dt
    distance_km = round(rng.uniform(5.0, 180.0), 1)
    purpose = _TRIP_PURPOSES[rng.randrange(len(_TRIP_PURPOSES))]
    origin = _TRIP_ORIGINS[rng.randrange(len(_TRIP_ORIGINS))]
    destination = _TRIP_DESTINATIONS[rng.randrange(len(_TRIP_DESTINATIONS))]
    return {
        "departure_at": departure_at,
        "return_at": return_at,
        "origin": origin,
        "destination": destination,
        "purpose": purpose,
        "distance_km": distance_km,
        "duration_min": duration_min,
    }


def _parse_dt_partial(iso: str, plus_min: int) -> str:
    head, tz = iso.rsplit("+", 1)
    head_part, time_part = head.split("T", 1)
    hh, mm, ss = (int(x) for x in time_part.split(":"))
    total = hh * 60 + mm + plus_min
    days = total // (24 * 60)
    new_hh = (total % (24 * 60)) // 60
    new_mm = total % 60
    yyyy, mo, dd = (int(x) for x in head_part.split("-"))
    # advance day, clamp within month (use 28-day max).
    new_dd = min(28, dd + days)
    return f"{yyyy:04d}-{mo:02d}-{new_dd:02d}T{new_hh:02d}:{new_mm:02d}:{ss:02d}+{tz}"


def _build_refuel(rng: random.Random, year: int, month: int) -> dict[str, Any]:
    volume_l = round(rng.uniform(30.0, 300.0), 1)
    # Рубли: грубо 60–80 руб/литр → меняется по типу топлива и сетке.
    fuel_type = _FUEL_TYPES[rng.randrange(len(_FUEL_TYPES))]
    rate = {
        "Дизельное топливо": 65.0,
        "Бензин АИ-92": 58.0,
        "Бензин АИ-95": 67.0,
        "Бензин АИ-98": 78.0,
        "Газ пропан-бутан": 32.0,
    }[fuel_type]
    cost = round(volume_l * rate * rng.uniform(0.95, 1.10), 2)
    station = _REFUEL_STATIONS[rng.randrange(len(_REFUEL_STATIONS))]
    return {
        "refueled_at": _iso_datetime(rng, year, month),
        "station": station,
        "fuel_type": fuel_type,
        "volume_l": volume_l,
        "cost": cost,
    }


def build_route_sheet_envelope(
    template_id: str,
    template_version: str,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Build a vehicle route sheet envelope (1 vehicle, 1 driver, 50 trips, 10 refuels)."""

    if rng is None:
        rng = _rng()

    year, month = 2026, 7
    trips = [_build_trip(rng, year, month) for _ in range(50)]
    refuels = [_build_refuel(rng, year, month) for _ in range(10)]

    document = {
        "vehicle": {
            "make": "КамАЗ",
            "model": "65115",
            "plate": "А123ВС 75",
            "garage_number": "Г-042",
        },
        "driver": {
            "full_name": "Иванов Иван Иванович",
            "employee_id": "T-1032",
            "class": "C",
        },
        "trips": trips,
        "refuels": refuels,
        "odometer": {"start": 12345.6, "end": 12789.4},
        "fuel_balance": {"start_l": 50.0, "end_l": 32.0, "received_total_l": 320.0},
        "fuel_consumption": {"norm": 28.5, "actual": 28.9},
        "signers": {
            "driver": {
                "label": "Водитель",
                "name": "Иванов Иван Иванович",
                "signed_at": "2026-07-31T17:30:00+03:00",
            },
            "mechanic": {
                "label": "Механик",
                "name": "",
                "signed_at": "",
            },
            "dispatcher": {
                "label": "Диспетчер",
                "name": "Соколова Ольга Петровна",
                "signed_at": "2026-07-31T18:00:00+03:00",
            },
        },
        "period": {"start_date": "2026-07-01", "end_date": "2026-07-31"},
    }

    return {
        "engine_contract_version": "1.0.0",
        "document_contract": "transport.vehicle-route-sheet/v1",
        "document_type": "vehicle_route_sheet",
        "template_id": template_id,
        "template_version": template_version,
        "locale": "ru-RU",
        "render_profile": "print",
        "document_id": "8c2ef0d8-695f-4d57-8073-route9999",
        "document_number": "RS-FIX-1",
        "document": document,
        "assets": {},
    }


# ---------------------------------------------------------------------------
# Fuel report (§9.3).
# ---------------------------------------------------------------------------


def _build_fuel_row(
    rng: random.Random,
    year: int,
    month: int,
) -> dict[str, Any]:
    vehicle = _VEHICLES[rng.randrange(len(_VEHICLES))]
    fuel_type = _FUEL_TYPES[rng.randrange(len(_FUEL_TYPES))]
    volume_l = round(rng.uniform(20.0, 500.0), 1)
    distance_km = round(rng.uniform(50.0, 800.0), 1)
    rate = {
        "Дизельное топливо": 65.0,
        "Бензин АИ-92": 58.0,
        "Бензин АИ-95": 67.0,
        "Бензин АИ-98": 78.0,
        "Газ пропан-бутан": 32.0,
    }[fuel_type]
    cost = round(volume_l * rate * rng.uniform(0.95, 1.10), 2)
    return {
        "date": f"{year:04d}-{month:02d}-{rng.randint(1, 28):02d}",
        "vehicle_id": vehicle["id"],
        "fuel_type": fuel_type,
        "volume_l": volume_l,
        "distance_km": distance_km,
        "cost": cost,
    }


def _summarize(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_vehicle: dict[str, dict[str, float]] = {}
    grand = {"total_volume_l": 0.0, "total_distance_km": 0.0, "total_cost": 0.0}
    for row in rows:
        bucket = by_vehicle.setdefault(
            row["vehicle_id"],
            {"total_volume_l": 0.0, "total_distance_km": 0.0, "total_cost": 0.0},
        )
        bucket["total_volume_l"] += row["volume_l"]
        bucket["total_distance_km"] += row["distance_km"]
        bucket["total_cost"] += row["cost"]
        grand["total_volume_l"] += row["volume_l"]
        grand["total_distance_km"] += row["distance_km"]
        grand["total_cost"] += row["cost"]

    subtotals = [
        {
            "vehicle_id": vid,
            "total_volume_l": round(v["total_volume_l"], 2),
            "total_distance_km": round(v["total_distance_km"], 1),
            "total_cost": round(v["total_cost"], 2),
        }
        for vid, v in sorted(by_vehicle.items())
    ]
    grand_total = {
        "total_volume_l": round(grand["total_volume_l"], 2),
        "total_distance_km": round(grand["total_distance_km"], 1),
        "total_cost": round(grand["total_cost"], 2),
    }
    return subtotals, grand_total


def build_fuel_report_envelope(
    n_rows: int,
    template_id: str,
    template_version: str,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Build a monthly fuel report envelope with ``n_rows`` deterministically generated."""

    if rng is None:
        rng = _rng()

    year, month = 2026, 7
    rows = [_build_fuel_row(rng, year, month) for _ in range(n_rows)]
    subtotals, grand_total = _summarize(rows)

    document: dict[str, Any] = {
        "period": {"year": year, "month": month},
        "vehicles": [dict(v) for v in _VEHICLES],
        "rows": rows,
        "subtotals": subtotals,
        "grand_total": grand_total,
    }
    # Per TZ §9.3 + task instructions: chart block is OMITTED in Phase 2
    # (chart-via-assets is a stretch goal documented in README).

    return {
        "engine_contract_version": "1.0.0",
        "document_contract": "fuel.monthly-report/v1",
        "document_type": "fuel_monthly_report",
        "template_id": template_id,
        "template_version": template_version,
        "locale": "ru-RU",
        "render_profile": "print",
        "document_id": "8c2ef0d8-695f-4d57-8073-fuel202607",
        "document_number": f"FR-FIX-{n_rows}",
        "document": document,
        "assets": {},
    }


# ---------------------------------------------------------------------------
# Disk writer helpers.
# ---------------------------------------------------------------------------


def make_pair(
    *,
    stem: str,
    pair_dir: Path,
    payload: dict[str, Any],
    weasy_template_id: str,
    weasy_template_version: str,
    typst_template_id: str,
    typst_template_version: str,
) -> tuple[Path, Path]:
    """Write the envelope twice — once for WeasyPrint, once for Typst.

    Returns ``(weasy_path, typst_path)``. The data section is identical between
    them; only ``template_id`` / ``template_version`` differ.
    """

    weasy = dict(payload)
    weasy["template_id"] = weasy_template_id
    weasy["template_version"] = weasy_template_version
    typst = dict(payload)
    typst["template_id"] = typst_template_id
    typst["template_version"] = typst_template_version

    weasy_path = pair_dir / f"{stem}.weasy.json"
    typst_path = pair_dir / f"{stem}.typst.json"
    _write_json(weasy_path, weasy)
    _write_json(typst_path, typst)
    return weasy_path, typst_path


def main() -> int:
    """Generate all 18 fixtures. Returns ``0``. Run from repo root."""

    WAYBILL_DIR.mkdir(parents=True, exist_ok=True)
    ROUTE_DIR.mkdir(parents=True, exist_ok=True)
    FUEL_DIR.mkdir(parents=True, exist_ok=True)

    pairs: list[tuple[Path, Path]] = []

    # Waybills: 1, 20, 75, 200, 500 lines.
    for n in (1, 20, 75, 200, 500):
        stem = f"waybill-{n}"
        # Seed the payload with the weasy template; make_pair below
        # overwrites ``template_id``/``template_version`` for both backends.
        payload = build_waybill_envelope(
            n,
            template_id=WAYBILL_WEASY_TEMPLATE_ID,
            template_version=WAYBILL_WEASY_TEMPLATE_VERSION,
        )
        pairs.append(
            make_pair(
                stem=stem,
                pair_dir=WAYBILL_DIR,
                payload=payload,
                weasy_template_id=WAYBILL_WEASY_TEMPLATE_ID,
                weasy_template_version=WAYBILL_WEASY_TEMPLATE_VERSION,
                typst_template_id=WAYBILL_TYPST_TEMPLATE_ID,
                typst_template_version=WAYBILL_TYPST_TEMPLATE_VERSION,
            )
        )

    # Vehicle route sheet (one logical fixture, two envelopes).
    rs_payload = build_route_sheet_envelope(
        template_id=ROUTE_SHEET_WEASY_TEMPLATE_ID,
        template_version=SPIKE_TEMPLATE_VERSION,
    )
    pairs.append(
        make_pair(
            stem="vehicle-route-sheet-1",
            pair_dir=ROUTE_DIR,
            payload=rs_payload,
            weasy_template_id=ROUTE_SHEET_WEASY_TEMPLATE_ID,
            weasy_template_version=SPIKE_TEMPLATE_VERSION,
            typst_template_id=ROUTE_SHEET_TYPST_TEMPLATE_ID,
            typst_template_version=SPIKE_TEMPLATE_VERSION,
        )
    )

    # Fuel reports: 100, 500, 1500 rows.
    for n in (100, 500, 1500):
        payload = build_fuel_report_envelope(
            n,
            template_id=FUEL_WEASY_TEMPLATE_ID,
            template_version=SPIKE_TEMPLATE_VERSION,
        )
        pairs.append(
            make_pair(
                stem=f"fuel-report-{n}",
                pair_dir=FUEL_DIR,
                payload=payload,
                weasy_template_id=FUEL_WEASY_TEMPLATE_ID,
                weasy_template_version=SPIKE_TEMPLATE_VERSION,
                typst_template_id=FUEL_TYPST_TEMPLATE_ID,
                typst_template_version=SPIKE_TEMPLATE_VERSION,
            )
        )

    written = sorted(p for pair in pairs for p in pair)
    print(f"Wrote {len(written)} envelope files:")
    for path in written:
        print(f"  {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
