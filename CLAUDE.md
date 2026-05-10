# ИБ Калькулятор ПИР

## Obsidian

Все задачи и лог — через Obsidian vault13.
Проект: `01 Actions/Projects/Project - IB AI Calculator PIR.md`
Каждое изменение кода требует задачи в vault. Команда: `obsidian vault=vault13 ...`

## Архитектура

> При изменении архитектуры — вносить правки в эту секцию.

**Стек**: Next.js 14 (App Router) + FastAPI + PostgreSQL + Claude API (claude-sonnet-4-6)
**Дизайн**: `design/DESIGN_SYSTEM.md`

### Поток данных

```
Upload ТЗ файлы в проект
  → POST /api/projects/{id}/calculate
  → document_parser: PDF/DOCX → plain text
  → entity_extractor: Claude API → ExtractionResult
  → Экран /entities: таблица для валидации (Категория / Тип / Адрес / X / Коэф.)
  → [Фаза 2] confirm → calculator → results → export 2ПС ИР
```

### Data models (PostgreSQL)

- `reference_books` — СБЦП/МРР версии (requires_validation → consistent → archived)
- `book_object_types` — типы объектов из справочника (КНС, Водовод, ...), извлекаются при парсинге
- `reference_rows` — строки справочника (table_num, x_min, x_max, a, b)
- `price_indices` — квартальные индексы Минстроя (Прил.3 п.1 = проектные работы)
- `users` — role: admin|user, can_calculate=false по умолчанию
- `projects` — контейнер файлов ТЗ per user
- `project_files` — загруженные файлы ТЗ (pdf_path, extracted_text)
- `calculations` — хранит book_version_id (FK, зафиксирован), extracted_entities JSONB
- `audit_logs`

### Классификация объекта (AI извлекает из ТЗ)

- **Категория**: new_construction | reconstruction | overhaul
- **Тип объекта**: из `book_object_types` активного справочника
- **Адрес/регион**: влияет на сейсмику, МРР и другие коэффициенты

### Формула расчёта

```
(a + b×X) × коэф. × индекс × стадия_фактор × (1 + НДС)
```

Экстраполяция (МУ №620 Прил.1): `a + b × (0.4 × X_гран + 0.6 × X_задан)`

### Admin panel

Кастомная `/admin` секция в Next.js. Не Payload CMS, не react-admin.

Функции:
- Пользователи: toggle can_calculate, роли
- Справочники: загрузить PDF → parse → скачать Excel → загрузить Excel → активировать/откатить
- Каждый справочник имеет `parse_prompt` (кастомизируется в admin)
- Индексы Минстроя: добавить вручную per квартал

### Entity extractor — многопроходная логика

`backend/app/services/entity_extractor.py`

```
Step 0  _build_book_list()         → AI определяет нужные справочники из текста ТЗ
Pass 1  _build_types_context()     → AI извлекает позиции (category/type/address/X/qty)
        _build_hints_context()       вместе с типами: правила из book_extraction_hints
        _fill_sbts_codes()          детерминированный: table_num → book.code из БД
Pass 2  _build_conditions_context() → AI проставляет коэффициенты (keyed conditions)
Pass 3  _build_resolve_x_context() → AI заполняет null x_value (targeted call)
        _merge_resolved_x()          никогда не перезаписывает уже заполненные x_value
        _validate_entities()         sanity check: tz_quote + x_value в тексте ТЗ
```

**Данные для AI только из БД**, не из кода:
- Типы объектов → `book_object_types` (type_id, name, table_num)
- Правила извлечения → `book_extraction_hints` (trigger_condition, hint_for_ai)
- Коэффициенты → `book_conditions` (coeff_key, coeff_min, coeff_max, row_range)

`ANTHROPIC_API_KEY` — в `.env`, не в коде.

### Calculation engine

`backend/app/services/calculator.py`

**Поиск строки** (`_match_row`):
1. Exact range match с unit conversion (UNIT_CONVERSIONS dict)
2. Extrapolation МУ №620 Прил.1: `a + b × (0.4·X_гран + 0.6·X_задан)`
3. Fallback: если object_type_id даёт 0 строк → retry без фильтра по типу

**Коэффициенты**:
- `_resolve_coeff_values()`: заменяет AI-флаг (value=1.0) на реальный coeff_min из book_conditions
  Lookup: table-specific → global (table_num=NULL)
- `_apply_coefficients()` по МУ №620 п.3.14:
  - ценообразующие (reconstruction, overhaul) → перемножить
  - усложняющие (asu, seismic, deepening, fishery) → сумма дробных частей + 1

**Формула** (русский формат): `(147380+242530*0,15316)*1,2`
**Обоснование**: `СБЦП 81-2001-17, табл. 9, п. 1 (до 0,25); п. 2.9 (АСУ К=1,2)`

### ПРАВИЛО УНИВЕРСАЛЬНОСТИ — обязательно соблюдать

> Система рассчитана на **любой** СБЦП/МРР из любой отрасли. Их будут десятки.

**НЕЛЬЗЯ хардкодить:**
- коды справочников (81-2001-17, МРР и т.п.) в calc engine или extractor
- номера таблиц или диапазоны X для конкретного типа объекта
- значения коэффициентов (все берутся из `book_conditions`)
- названия типов объектов (все из `book_object_types`)
- любую логику вида "если тип=КНС → таблица 9" или "если ГНБ → x_value = ..."

**МОЖНО (и нужно):**
- добавлять записи в `book_extraction_hints` — правила per справочник, редактируемые в admin
- добавлять записи в `book_conditions` — коэффициенты per справочник/таблица
- добавлять unit conversions в `UNIT_CONVERSIONS` dict (универсальные)
- улучшать общие алгоритмы match/extrapolation/apply

Нарушение этого правила — всегда техдолг. Если хочется хардкодить → ищи способ вынести в БД.

### Roadmap (не реализуем сейчас)

- `chapter_coefficients` — раздело-специфичные коэф. (пример: ×1.2 к разделу КР за прогрессирующее обрушение)
- МРР (Москва) — добавить как отдельный справочник после MVP

## Лог

### 2026-05-08
- Составлен план, утверждена архитектура
- Начало реализации: Docker, DB schema, auth, frontend skeleton, entity extractor
