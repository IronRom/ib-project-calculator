# ИБ Калькулятор ПИР

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

Экстраполяция (МУ №620 Прил.1 / 707/пр п.131): `a + b × (0.4 × X_гран + 0.6 × X_задан)`.
Ниже Xмин/2 — 707/пр ф.8.4/8.5: цена в точке Xмин/2, умноженная на Кэ = X/(0.5·Xмин), Кэ ≥ 0.1.
Таблицы только с «а» (b=NULL, но есть границы) — 707/пр п.133 ф.8.6–8.8:
интерполяция между опорными точками; вне точек — наклон крайнего сегмента × 0.6.

**Штучные строки** (b=NULL и нет диапазона x_min/x_max): цена за единицу → `a × X`,
где X = количество (ячейки, шкафы, пункты). Характерно для НЗ (СИТО табл. 3.13 и т.п.).

**ПД/РД split** — per book: `reference_books.pd_pct / rd_pct` (NULL → МУ №620 п.1.4: 0.4/0.6).
НЗ задают своё распределение (707/пр п.17-д), например НЗ-847 табл.2.3: ПД=0.6, РД=0.4.
Редактируется в admin (PATCH /admin/references/{id}).

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

**Warnings** (result["warnings"], показывать пользователю всегда):
- коэффициент заявлен AI, но условия нет в book_conditions → «НЕ применён, цена занижена»
- индекс пересчёта отсутствует или старше текущего квартала

Все AI-вызовы (экстракция, vision, коррекция) — `temperature=0` (детерминизм смет).

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

### 2026-07-22
- Бенчмарк на ТЗ «НС7 ячейки+ПЧ» против эталонной сметы (Александров, Инфострой)
- Движок: штучные строки (b=NULL, без диапазона → a×X); per-book ПД/РД
  (`reference_books.pd_pct/rd_pct`, миграция e5f6a7b8c9d0); `book_conditions.apply_mode`
  (миграция f6a7b8c9d0e1) вместо белых списков ключей; конверсии км/м↔п.м
- Warnings в результате расчёта: дроп коэффициента без условия, устаревший/отсутствующий индекс
- temperature=0 на всех AI-вызовах; Pass 3 получает единицы таблиц справочника
- КП: строки ПД/РД суммируются из позиций (не пересплит 40/60); fix фильтра ИГИ на geology page
- Сид 82 условий НЗ-847 (`seed_sito_conditions.py`): Разд.2 + все табл. 3.X.1
  (vision-извлечение из PDF приказа); опасные «за каждую последующую» — с coeff_key=NULL
- Восстановлена БД из ib_calculator.dump (dump не коммитить — перс. данные)

### 2026-07-22 (вторая сессия — НЗ-53-ВК + 707/пр)
- ВАЖНО: табл.2.3 НЗ-847 и табл.1.2 НЗ-53 (П=60/Р=40) — ТОЛЬКО для информационной
  модели (BIM); обычное распределение = 40/60. pd_pct/rd_pct СИТО откачен на NULL
- Движок: 707/пр п.131 ф.8.4/8.5 (X<Xмин/2 → Кэ=X/(0.5·Xмин), ≥0.1) и п.133
  ф.8.6-8.8 (a-only таблицы: интерполяция/сглаженная 0.6 экстраполяция)
- НЗ-53-ВК реимпортирован (195 строк, тыс.руб как есть — БЫЛ двойной масштаб ×1000
  и битые запятые в «б»); import-скрипт исправлен; spot-checks Кашина сходятся
- Сид 90 условий НЗ-53 (`seed_ms53_conditions.py`): табл.2 общих положений,
  все 3.X.1, реконструкция К≤1.5 / капремонт К≤0.5 по 707/пр пп.156-159 (НЗ-53 пп.17-18)
- `audit_book_rows.py` — универсальный аудит строк книги (непрерывность цен на границах
  диапазонов + магнитуда b). НЗ-53 чист; у СБЦП-17 28 подозрений (в т.ч. x_unit «км»
  вместо «м» в табл.8) — НЕ разобрано, техдолг
- Единицы: м³↔тыс.м³, длинные формы НЗ-53, м²/га в _PHYSICAL_UNITS
- Hints (`seed_asutp_rza_hints.py`): калибровка факторов АСУТП (Ф8 консервативно,
  Ф5/Ф9/Ф10 по перечню ТЗ, Ф7 группа+ПЧ→п.4.3) + РЗА «применительно» СИТО→СБЦП-13
  табл.11; восстановлен description п.12 табл.11 СБЦП-13. Бенчмарк НС7: +26% → +6%
- АСУТП: невалидные коды факторов (Ф10=п.2.3) теперь дают warning, не тихий 0 баллов
- `documents/minstroy/` реструктурирован: publish/ (в БД: СИТО, НЗ-53, ИГИ,
  ХимВолокна, МУ-620, 707пр, письмо 20212-ИФ) и unpublish/ (геофиз 282пр,
  геодез 812пр, письма без индексов в БД); имена файлов: «КОД - Описание (Приказ N).pdf»
- Книги изысканий: `calc_method='survey'` (ИГИ/ИГДИ/ИГФИ) — основной calculate()
  их НЕ считает (строки в РУБЛЯХ, не тыс.руб!), выдаёт ошибку «блок Изыскания».
  Импорт survey-книг: `backend/scripts/import_nz_survey_book.py` (рубли as-is)
- Таблица техотчёта изысканий — data-driven через book_conditions:
  coeff_key='report_table' (номер таблицы), 'report_cat_N' (row_range категории).
  Хардкод табл.65 из igi_calculator удалён
