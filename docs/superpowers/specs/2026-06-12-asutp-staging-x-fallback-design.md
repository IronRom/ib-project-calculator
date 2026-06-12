# Design: АСУТП Admin + Этапность + X-fallback

**Date:** 2026-06-12  
**Scope:** 3 independent features that together close the gap between AI-calculated and estimator results

---

## Context

Analysis of a real estimator calculation (НС7 Екатеринбург) revealed three root causes of large price errors:

1. **X missing from TZ** — AI correctly identifies positions but cannot derive quantities (e.g. 20 ячеек, 300 п.м кабелей). Current system returns ~0.
2. **No stage grouping** — TZ explicitly defines 3 stages; estimator splits into ЛС-01/02/03 with per-stage subtotals. AI puts all into one flat list.
3. **АСУТП factor data unmanageable** — `asutp_factor_options` and `asutp_modules` tables are seeded via script only; no admin UI.

---

## Part 1: X-Fallback to Minimum Row

### Problem
When `x_value is None`, calculator currently fails to match any row → position produces 0 cost. This is worse than a rough estimate.

### Solution
In `calculator.py`, in `_match_row()`: when `x_value is None`, fall back to the row with the smallest `x_min` (first row of the table for this object type). Apply that row's formula. Flag the result.

### Schema changes
Add two fields to each entity in `extracted_entities` JSONB:

```json
{
  "missing_x_hint": "укажите количество ячеек (шт.)",
  ...existing fields...
}
```

AI fills `missing_x_hint` in Pass 1 when it cannot find X in TZ text. Empty string when X is found.

### Calculator changes (`calculator.py`)
In `_match_row()`:
- If `x_value is None` → query rows for this object_type ordered by `x_min ASC NULLS LAST`, take first
- Evaluate formula at `x = row.x_min` (minimum of that row's range)
- Return row + set `used_minimum=True` on the result
- In `justification`: append " [по минимальному X={row.x_min}; для точного расчёта необходимо: {missing_x_hint}]"
- If no rows found (object_type has 0 rows in DB) → existing error handling unchanged

### Position result JSONB
Add `used_minimum: bool` to each position in `calculation_result`. Description is in `justification`.

### UI (`frontend/app/(app)/entities/page.tsx`)
- Yellow "Минимум" badge on rows where `used_minimum=True`
- Tooltip on badge: content from `missing_x_hint`
- Summary banner above table if any positions use minimum: "Расчёт частично по минимальным значениям. Уточните данные для точной стоимости."

### Invariants
- Never overwrite a non-null `x_value` with minimum
- `used_minimum` appears in calculation result, not in extracted_entities (it's a calc artifact)
- Minimum fallback applies to `linear` calc_method only; АСУТП uses its own factor logic

---

## Part 2: Staging (Этапность)

### Problem
TZ defines explicit stages ("1 Этап: ...", "2 Этап: ..."). AI extracts a flat entity list. Estimator groups into separate ЛС with per-stage subtotals. Without grouping, the summary structure is lost.

### Solution
Add `section_num` and `section_name` to each entity. Pass 1 extracts them from TZ text. UI groups by section.

### Schema changes
Add to each entity in JSON schema for Pass 1:

```json
{
  "section_num": 1,
  "section_name": "Ячейки РП-601",
  ...existing fields...
}
```

Rules for AI:
- `section_num`: integer starting at 1. Use 0 if entity does not belong to any TZ-defined stage.
- `section_name`: short name derived from TZ stage description (AI shortens to ≤60 chars). Empty string when section_num=0.
- If TZ has no explicit stages → all entities get section_num=0.

### Extractor changes (`entity_extractor.py`)
- Add `section_num` and `section_name` to the entity JSON schema definition (both required fields)
- Update Pass 1 system prompt section: "Если ТЗ содержит явные этапы ('1 Этап', '2 Этап', ...) — присвой каждой сущности section_num (1,2,3...) и section_name (краткое название этапа ≤60 символов). Если сущность не относится к конкретному этапу — section_num=0, section_name=''."
- Default values in `_merge_resolved_x()` and `_validate_entities()`: if field missing, set section_num=0

### Calculator
No changes. section_num/section_name pass through as-is into `confirmed_positions`.

### Frontend — Entities page
Group confirmed positions by (section_num, section_name):
- section_num>0 → render as collapsible group with header: "Этап {num}: {name}", sorted by section_num
- section_num=0 → render at bottom as "Без этапа" group, only if at least one entity has section_num>0; otherwise no grouping headers at all
- Per-group subtotal row (sum of cost without НДС for positions in group)
- Grand total row unchanged

### Frontend — UI components needed
- `SectionGroup` component: header + collapse toggle + subtotal
- Update entities table to accept grouped data structure

### Export (`export_2ps.py`)
- Group positions by section_num in the generated ПС form
- Add section header rows with subtotals (matching estimator ПС structure)
- No separate ЛС sheets per section in this iteration (future work)

---

## Part 3: АСУТП Factors Admin Tab

### Problem
`asutp_factor_options` and `asutp_modules` are populated via seed script only. When a new СБЦП-22 edition updates scores or S values, there's no admin UI to make changes.

### Solution
Add "Факторы АСУТП" sub-tab to the book detail panel in `/admin/references`. Visible only when `book.calc_method === 'asutp'`.

### Backend — new endpoints (new file `admin_asutp.py`)

```
GET  /api/admin/books/{id}/asutp-factors         → list all factor options (grouped by factor_code)
POST /api/admin/books/{id}/asutp-factors         → create new option row
PUT  /api/admin/books/{id}/asutp-factors/{opt_id} → update scores/description
DEL  /api/admin/books/{id}/asutp-factors/{opt_id} → delete option row

GET  /api/admin/books/{id}/asutp-modules         → list all 6 modules
PUT  /api/admin/books/{id}/asutp-modules/{mod_id} → update S value + stage % ranges
```

All endpoints: admin role required (same auth pattern as existing admin endpoints).

### Backend — Pydantic schemas
```python
class AsutpFactorOptionOut(BaseModel):
    id: int
    factor_code: str
    factor_name: str
    option_code: str
    option_description: str
    score_or: int | None
    score_oo: int | None
    score_io: int | None
    score_to: int | None
    score_mo: int | None
    score_po: int | None

class AsutpFactorOptionIn(BaseModel):
    factor_code: str
    factor_name: str
    option_code: str
    option_description: str
    score_or: int | None = None
    score_oo: int | None = None
    score_io: int | None = None
    score_to: int | None = None
    score_mo: int | None = None
    score_po: int | None = None

class AsutpModuleOut(BaseModel):
    id: int
    module_code: str
    s_value: float
    sort_order: int
    stage_r_min: int
    stage_r_max: int
    stage_p_min: int
    stage_p_max: int

class AsutpModulePatch(BaseModel):
    s_value: float | None = None
    stage_r_min: int | None = None
    stage_r_max: int | None = None
    stage_p_min: int | None = None
    stage_p_max: int | None = None
```

### Frontend — AsutpTab component

Location: `frontend/components/admin/AsutpTab.tsx`

Structure:
```
[ Факторы ] [ Модули ]  ← inner tabs

Факторы table:
┌─────┬──────────┬────────────────────────┬────┬────┬────┬────┬────┬────┬───────┐
│ Фак │ Код      │ Описание               │ ОР │ ОО │ ИО │ ТО │ МО │ ПО │       │
├─────┼──────────┼────────────────────────┼────┼────┼────┼────┼────┼────┼───────┤
│ Ф2  │ п.1.1    │ Непрерывный            │ 1  │ 1  │ 1  │ 1  │ 1  │ 1  │ ✎ 🗑 │
│ Ф2  │ п.1.2    │ Полунепрерывный        │ 2  │ 1  │ 2  │ 1  │ 2  │ 2  │ ✎ 🗑 │
├─────┤  ...                                                              │      │
Rows grouped by factor_code with sticky factor header rows.
[+ Добавить вариант] button at bottom.

Модули table (read-only structure, editable values):
┌──────┬──────────┬─────────────┬─────────────┐
│ Код  │ S (тыс.) │ Стадия Р %  │ Стадия П %  │
├──────┼──────────┼─────────────┼─────────────┤
│ ОР   │ [15.73]  │ [20] – [30] │ [70] – [80] │
│ ОО   │ [9.56]   │ [60] – [70] │ [30] – [40] │
Inline edit on click. Save on blur or Enter.
No add/delete for modules (6 is fixed by standard).
```

### Integration with existing references page
- Add `calc_method` field to `ReferenceBook` API response (already in model, check if in schema)
- In `AdminReferencesPage`: when expanding a book, if `calc_method === 'asutp'`, show "Факторы АСУТП" tab alongside existing "Строки" and "Hints" tabs
- Tab content: lazy-load `AsutpTab` component with `bookId`

---

## Implementation Order

1. **X-fallback** (calculator.py + extractor schema + entities UI) — highest impact, fixes "0 cost" problem
2. **Staging** (extractor schema + entities page grouping) — improves structure
3. **АСУТП admin** (backend endpoints + frontend component) — enables data management

Each part is independently deployable.

---

## Out of Scope

- Separate ЛС sheets per section in export (future)
- Per-stage index/stage overrides (confirmed not needed)
- AI auto-scoring АСУТП factors from TZ text (separate future feature)
- book_extraction_hints seeding for НЗ-СИТО (separate data task, not architecture)
