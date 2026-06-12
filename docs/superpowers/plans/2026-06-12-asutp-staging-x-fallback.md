# АСУТП Admin + Этапность + X-fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the AI vs estimator accuracy gap: calculate with minimum row when X is missing, group positions by TZ stages, and add admin UI for АСУТП factor data.

**Architecture:** Three independent features sharing no runtime coupling. X-fallback lives entirely in `calculator.py`. Staging adds two fields to the entity schema and propagates through extractor → calculator → frontend → export. АСУТП admin adds a new FastAPI router and a single React component.

**Tech Stack:** Python/FastAPI, SQLAlchemy, pytest/unittest.mock, Next.js 14, TypeScript, React

---

## File Map

**Modified:**
- `backend/app/services/calculator.py` — RowMatch.used_minimum, _match_row Optional[float], section passthrough
- `backend/app/services/entity_extractor.py` — JSON schema + SYSTEM_PROMPT section rules
- `backend/app/services/export_2ps.py` — section header rows in Excel
- `backend/app/schemas/__init__.py` — ExtractedEntity section fields, ReferenceBookOut calc_method, ASUTP schemas
- `backend/app/main.py` — register admin_asutp router
- `frontend/lib/api.ts` — ExtractedEntity, CalcPosition, ReferenceBook types; ASUTP API functions
- `frontend/app/(app)/projects/[id]/entities/page.tsx` — used_minimum badge + section grouping
- `frontend/app/(app)/admin/references/page.tsx` — AsutpTab integration

**Created:**
- `backend/tests/__init__.py`
- `backend/tests/conftest.py`
- `backend/tests/test_calculator_x_fallback.py`
- `backend/app/api/admin_asutp.py`
- `frontend/components/admin/AsutpTab.tsx`

---

## Task 1: Test infrastructure + RowMatch.used_minimum

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Modify: `backend/app/services/calculator.py:64-70` (RowMatch dataclass)

- [ ] **Step 1: Create test package**

```bash
mkdir -p backend/tests
touch backend/tests/__init__.py
```

- [ ] **Step 2: Create conftest.py**

`backend/tests/conftest.py`:
```python
"""Shared fixtures for calculator unit tests."""
from unittest.mock import MagicMock


def make_db_returning(rows: list) -> MagicMock:
    """Return a mock Session where any query chain ending in .all() returns rows."""
    db = MagicMock()
    # Handles both: .filter(a,b).all() and .filter(a,b).filter(c).all()
    q = db.query.return_value
    q.filter.return_value.filter.return_value.all.return_value = rows
    q.filter.return_value.all.return_value = rows
    return db


def make_row(
    x_min=None, x_max=None,
    a=10.0, b=2.0,
    row_num="п.1", x_unit="шт",
    description="Test row",
) -> MagicMock:
    """Minimal ReferenceRow mock."""
    row = MagicMock()
    row.x_min = x_min
    row.x_max = x_max
    row.a = a
    row.b = b
    row.row_num = row_num
    row.x_unit = x_unit
    row.description = description
    return row
```

- [ ] **Step 3: Add `used_minimum` field to RowMatch**

In `backend/app/services/calculator.py`, change lines 64-70:

```python
@dataclass
class RowMatch:
    row: ReferenceRow
    x_effective: float          # x converted to row's unit
    extrapolated: bool
    x_boundary: Optional[float] # boundary value used for extrapolation
    note: str                   # human-readable conversion / extrapolation note
    used_minimum: bool = False  # True when x_value was None and minimum row was used
```

- [ ] **Step 4: Verify no existing tests break**

```bash
cd backend && python -m pytest tests/ -v 2>&1 | head -30
```

Expected: "no tests ran" or "collected 0 items" (no failures).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/ backend/app/services/calculator.py
git commit -m "test: add pytest infrastructure; add RowMatch.used_minimum field"
```

---

## Task 2: X-fallback in calculator

**Files:**
- Modify: `backend/app/services/calculator.py:79-154` (_match_row), `:480-608` (calculate)
- Create: `backend/tests/test_calculator_x_fallback.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_calculator_x_fallback.py`:
```python
"""Tests for X-fallback: when x_value is None, use minimum row."""
import pytest
from unittest.mock import MagicMock, patch
from backend.tests.conftest import make_db_returning, make_row


def _call_match_row(db, rows_override=None):
    """Helper: call _match_row with x_value=None."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from app.services.calculator import _match_row
    return _match_row(db, book_version_id=1, table_num=9,
                      x_value=None, x_unit="шт")


def test_x_none_returns_minimum_row():
    """When x_value is None, return the row with lowest x_min."""
    rows = [
        make_row(x_min=10.0, x_max=50.0, a=100.0, b=5.0, row_num="п.1"),
        make_row(x_min=50.0, x_max=200.0, a=300.0, b=3.0, row_num="п.2"),
    ]
    db = make_db_returning(rows)
    match = _call_match_row(db)
    assert match is not None
    assert match.used_minimum is True
    assert match.row.row_num == "п.1"
    assert match.x_effective == 10.0


def test_x_none_row_without_x_min_gets_zero():
    """Row with x_min=None gets x_effective=0.0."""
    rows = [make_row(x_min=None, x_max=None, a=50.0, b=0.0)]
    db = make_db_returning(rows)
    match = _call_match_row(db)
    assert match is not None
    assert match.used_minimum is True
    assert match.x_effective == 0.0


def test_x_none_empty_table_returns_none():
    """No rows → None even with x_value=None."""
    db = make_db_returning([])
    match = _call_match_row(db)
    assert match is None


def test_x_provided_not_used_minimum():
    """When x_value is given (not None), used_minimum must be False."""
    from app.services.calculator import _match_row
    rows = [make_row(x_min=5.0, x_max=50.0, a=100.0, b=2.0)]
    db = make_db_returning(rows)
    match = _match_row(db, 1, 9, x_value=10.0, x_unit="шт")
    assert match is not None
    assert match.used_minimum is False
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend && python -m pytest tests/test_calculator_x_fallback.py -v
```

Expected: FAIL — `_match_row` doesn't handle `x_value=None` yet (TypeError or wrong result).

- [ ] **Step 3: Update `_match_row` signature and add fallback branch**

In `backend/app/services/calculator.py`, replace lines 79-105:

```python
def _match_row(
    db: Session,
    book_version_id: int,
    table_num: int,
    x_value: Optional[float],
    x_unit: str,
    object_type_id: Optional[int] = None,
) -> Optional[RowMatch]:
    q = db.query(ReferenceRow).filter(
        ReferenceRow.book_version_id == book_version_id,
        ReferenceRow.table_num == table_num,
    )
    if object_type_id is not None:
        q = q.filter(ReferenceRow.object_type_id == object_type_id)
    all_rows: list[ReferenceRow] = q.all()
    # Fallback: type_id gave no rows → retry without type filter
    if not all_rows and object_type_id is not None:
        all_rows = (
            db.query(ReferenceRow)
            .filter(
                ReferenceRow.book_version_id == book_version_id,
                ReferenceRow.table_num == table_num,
            )
            .all()
        )
    if not all_rows:
        return None

    # ── X-fallback: use minimum row when X is unknown ─────────────────────
    if x_value is None:
        candidates_with_min = [r for r in all_rows if r.x_min is not None]
        min_row = min(candidates_with_min, key=lambda r: float(r.x_min)) \
                  if candidates_with_min else all_rows[0]
        x_eff = float(min_row.x_min) if min_row.x_min is not None else 0.0
        return RowMatch(min_row, x_eff, False, None, "", used_minimum=True)

    x_unit_norm = _normalize_unit(x_unit)
    # ... rest of function unchanged
```

- [ ] **Step 4: Update `calculate()` to preserve None x_value**

In `backend/app/services/calculator.py`, line 484, change:
```python
x_value        = float(entity.get("x_value") or 0.0)
```
to:
```python
_x_raw         = entity.get("x_value")
x_value        = float(_x_raw) if _x_raw is not None else None
```

- [ ] **Step 5: Add used_minimum and section fields to position dict**

In `backend/app/services/calculator.py`, after the `match = _match_row(...)` call (around line 508), add to the justification block. Find this section (around line 552):

```python
        justification = f"{book.code}, табл. {table_num}"
```

After the existing justification is fully built (after line 568), add:
```python
        if match.used_minimum:
            missing_hint = entity.get("x_value_missing_reason") or ""
            justification += f" [по мин. X={_fmt_ru(match.x_effective)}"
            if missing_hint:
                justification += f"; для точного расчёта: {missing_hint}"
            justification += "]"
```

Then in the `positions.append({...})` dict (around line 589), add these fields:
```python
            "used_minimum":        match.used_minimum,
            "section_num":         entity.get("section_num", 0),
            "section_name":        entity.get("section_name", ""),
```

Also update the АSUTP position passthrough in `_calculate_asutp_position` — add to the returned dict (around line 466):
```python
    result["section_num"]  = entity.get("section_num", 0)
    result["section_name"] = entity.get("section_name", "")
    result["used_minimum"] = False
```

(Check the exact lines in `_calculate_asutp_position` return — look for `"_stage_embedded": True` and add the three lines before it.)

- [ ] **Step 6: Run tests — expect pass**

```bash
cd backend && python -m pytest tests/test_calculator_x_fallback.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/calculator.py backend/tests/test_calculator_x_fallback.py
git commit -m "feat: X-fallback to minimum row when x_value is None; add used_minimum flag"
```

---

## Task 3: Entity schema — section_num/section_name

**Files:**
- Modify: `backend/app/schemas/__init__.py` (ExtractedEntity)
- Modify: `backend/app/services/entity_extractor.py` (JSON schema + SYSTEM_PROMPT)

- [ ] **Step 1: Add fields to ExtractedEntity Pydantic model**

In `backend/app/schemas/__init__.py`, in the `ExtractedEntity` class, add after `deleted: bool = False`:

```python
    section_num: int = 0            # 0 = no explicit stage in TZ
    section_name: str = ""          # short stage name ≤60 chars, empty when section_num=0
```

- [ ] **Step 2: Add fields to EXTRACTION_TOOL JSON schema**

In `backend/app/services/entity_extractor.py`, in `EXTRACTION_TOOL["input_schema"]["properties"]["entities"]["items"]["properties"]`, add after `"notes"`:

```python
                        "section_num": {
                            "type": "integer",
                            "description": "Номер этапа ТЗ (1, 2, 3...). 0 если ТЗ не разбито на этапы или позиция не привязана к конкретному этапу.",
                        },
                        "section_name": {
                            "type": "string",
                            "description": "Краткое название этапа из ТЗ (≤60 символов). Пустая строка если section_num=0.",
                        },
```

- [ ] **Step 3: Add section extraction rules to SYSTEM_PROMPT**

In `backend/app/services/entity_extractor.py`, in `SYSTEM_PROMPT`, find the line:
```
СТАДИЯ — из текста ТЗ:
```
(around line 385). Directly before that block, insert:

```python
# In the SYSTEM_PROMPT string, add this section between the end of КОЭФФИЦИЕНТЫ block and СТАДИЯ:
```

The text to insert into the SYSTEM_PROMPT string:

```
ЭТАПЫ — группировка позиций по ТЗ:
  Если ТЗ явно содержит пронумерованные этапы ("1 Этап:", "2 Этап:", "Этап 1:", "Stage 1:" и т.п.) —
  присвой каждой извлекаемой позиции:
    section_num = номер этапа (1, 2, 3...)
    section_name = короткое название этапа из ТЗ (≤60 символов; убери лишние детали)
  Позиции, которые не относятся к конкретному этапу (например, общие требования):
    section_num = 0, section_name = ""
  Если ТЗ не содержит явных этапов:
    section_num = 0, section_name = "" для всех позиций.
  Один этап ТЗ может порождать несколько позиций (ячейка, кабель, РЗА — все из Этапа 1).

```

- [ ] **Step 4: Add defaults in `_validate_entities` for backward compat**

In `backend/app/services/entity_extractor.py`, find the `_validate_entities` function (search for `def _validate_entities`). At the start of the loop over entities, add:

```python
        entity.section_num  = getattr(entity, "section_num", 0) or 0
        entity.section_name = getattr(entity, "section_name", "") or ""
```

- [ ] **Step 5: Verify import still works**

```bash
cd backend && python -c "from app.services.entity_extractor import EXTRACTION_TOOL; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/services/entity_extractor.py
git commit -m "feat: add section_num/section_name to entity schema and Pass 1 prompt"
```

---

## Task 4: Frontend — types, used_minimum badge, section grouping

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/(app)/projects/[id]/entities/page.tsx`

- [ ] **Step 1: Update TypeScript interfaces in api.ts**

In `frontend/lib/api.ts`, update `ExtractedEntity` interface — add after `deleted?`:
```typescript
  section_num?: number
  section_name?: string
```

Update `CalcPosition` interface — add after `row_num`:
```typescript
  used_minimum?: boolean
  section_num?: number
  section_name?: string
```

- [ ] **Step 2: Add used_minimum badge to entity row**

In `frontend/app/(app)/projects/[id]/entities/page.tsx`, find the section where the position result is displayed (search for `calcResult`). Find where positions are rendered (search for `pos.cost` or `pos.justification`).

Add a "Минимум" badge next to the cost column when `pos.used_minimum` is true. Locate the cost display and wrap it:

```tsx
{pos.used_minimum && (
  <span
    title={`Рассчитано по минимальному X. ${entity?.x_value_missing_reason ?? 'Уточните X для точного расчёта.'}`}
    style={{
      display: 'inline-block', marginRight: 4,
      background: '#fef3c7', color: '#92400e',
      border: '1px solid #f59e0b', borderRadius: 4,
      fontSize: 10, padding: '1px 5px', fontWeight: 600,
    }}
  >
    Минимум
  </span>
)}
```

Add a banner above the positions table when any position has `used_minimum=true`:
```tsx
{calcResult && calcResult.positions.some(p => p.used_minimum) && (
  <div style={{
    background: '#fffbeb', border: '1px solid #f59e0b', borderRadius: 6,
    padding: '8px 14px', marginBottom: 12, fontSize: 13, color: '#78350f',
  }}>
    ⚠️ Часть позиций рассчитана по минимальным значениям. Уточните параметры для точной стоимости.
  </div>
)}
```

- [ ] **Step 3: Group confirmed positions by section in the entities table**

In `frontend/app/(app)/projects/[id]/entities/page.tsx`, find where entities are rendered in the table (around the entity loop). Currently entities are rendered flat. Wrap with section grouping:

Add a helper function before the component return:
```tsx
function groupBySections(entities: ExtractedEntity[]) {
  const sections: Map<number, { name: string; indices: number[] }> = new Map()
  entities.forEach((e, i) => {
    const num = e.section_num ?? 0
    const name = e.section_name ?? ''
    if (!sections.has(num)) sections.set(num, { name, indices: [] })
    sections.get(num)!.indices.push(i)
  })
  // Sort: staged groups first (1,2,3...), then ungrouped (0) last
  return [...sections.entries()].sort(([a], [b]) => {
    if (a === 0) return 1
    if (b === 0) return -1
    return a - b
  })
}
```

In the render, replace the flat entity loop with a grouped render. Find the table body where entities are mapped and replace with:

```tsx
{(() => {
  const allEntities = calc.extracted_entities?.entities ?? []
  const sections = groupBySections(allEntities)
  const hasMultipleSections = sections.some(([num]) => num > 0)

  return sections.map(([sectionNum, { name, indices }]) => (
    <React.Fragment key={sectionNum}>
      {hasMultipleSections && (
        <tr>
          <td colSpan={9} style={{
            background: '#f0f4ff', padding: '6px 12px',
            fontWeight: 600, fontSize: 13, color: '#1e40af',
            borderTop: '2px solid #3b82f6',
          }}>
            {sectionNum === 0
              ? 'Без этапа'
              : `Этап ${sectionNum}: ${name}`}
          </td>
        </tr>
      )}
      {indices.map(i => (
        <EntityRow
          key={i}
          index={i}
          entity={allEntities[i]}
          override={overrides[i] ?? {}}
          onOverride={(patch) => handleOverride(i, patch)}
          position={calcResult?.positions?.find(p => p.num === i + 1)}
        />
      ))}
      {hasMultipleSections && sectionNum !== 0 && calcResult && (() => {
        const sectionCost = indices
          .map(i => calcResult.positions?.find(p => p.num === i + 1)?.cost ?? 0)
          .reduce((s, v) => s + v, 0)
        return sectionCost > 0 ? (
          <tr style={{ background: '#f8fafc' }}>
            <td colSpan={8} style={{ padding: '4px 12px', textAlign: 'right', fontSize: 12, color: '#64748b' }}>
              Итог этапа:
            </td>
            <td style={{ padding: '4px 12px', textAlign: 'right', fontWeight: 600, fontSize: 12 }}>
              {fmt(sectionCost)}
            </td>
          </tr>
        ) : null
      })()}
    </React.Fragment>
  ))
})()}
```

Note: This assumes the entity table has a consistent `EntityRow` sub-component or equivalent pattern. Adapt to the actual rendering pattern in the file (the entities page uses inline rendering — check the actual JSX structure around line 300-430 and match the pattern).

- [ ] **Step 4: Check TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors (or only pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/\(app\)/projects/\[id\]/entities/page.tsx
git commit -m "feat: used_minimum badge and section grouping on entities page"
```

---

## Task 5: Export section grouping

**Files:**
- Modify: `backend/app/services/export_2ps.py:120-145` (Positions loop)

- [ ] **Step 1: Add section header rows to the positions loop**

In `backend/app/services/export_2ps.py`, find the positions loop (around line 120):
```python
    positions = result.get("positions", [])
    for pi, pos in enumerate(positions):
```

Replace with:

```python
    positions = result.get("positions", [])

    # Group by section_num for headers
    section_changes: dict[int, str] = {}
    prev_section = None
    for pos in positions:
        snum = pos.get("section_num", 0)
        if snum != prev_section and snum > 0:
            section_changes[pos["num"]] = f"Этап {snum}: {pos.get('section_name', '')}"
        prev_section = snum

    for pi, pos in enumerate(positions):
        # Insert section header row if section changed
        if pos["num"] in section_changes:
            ws.merge_cells(f"A{r}:G{r}")
            _set(ws, r, 1, section_changes[pos["num"]],
                 font=Font(name="Times New Roman", size=10, bold=True),
                 align=Alignment(horizontal="left", vertical="center"),
                 fill=PatternFill(fgColor="D6E4F7", fill_type="solid"))
            ws.row_dimensions[r].height = 16
            r += 1
```

The rest of the loop (`is_last`, border logic, `_set` calls) remains unchanged.

- [ ] **Step 2: Verify export still generates valid Excel**

```bash
cd backend && python -c "
from app.services.export_2ps import generate_2ps_excel
result = {
    'positions': [
        {'num':1,'name':'Кабель','row_description':'','unit':'п.м','quantity':100,
         'justification':'СБЦП','formula':'500000','cost':500000,'book_code':'СБЦП',
         'price_base_year':2001,'price_index':7.1,'price_index_period':'II кв 2026',
         'price_index_justification':'','table_num':1,'row_num':'п.1',
         'used_minimum':False,'section_num':1,'section_name':'Ячейки РП-601'},
    ],
    'base_cost':500000,'current_cost':500000,'stage_factor':1.0,
    'cost_with_stage':500000,'vat_amount':110000,'total_with_vat':610000,
    'index_summary':[]
}
data = generate_2ps_excel('Test', 'Р', result)
print(f'OK, {len(data)} bytes')
"
```

Expected: `OK, NNNNN bytes` (no exception).

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/export_2ps.py
git commit -m "feat: add section header rows to 2ПС export when positions have section_num"
```

---

## Task 6: АСУТП admin backend

**Files:**
- Modify: `backend/app/schemas/__init__.py` — ASUTP Pydantic schemas
- Modify: `backend/app/schemas/__init__.py` — ReferenceBookOut.calc_method
- Create: `backend/app/api/admin_asutp.py`
- Modify: `backend/app/main.py` — register router

- [ ] **Step 1: Add calc_method to ReferenceBookOut**

In `backend/app/schemas/__init__.py`, in `ReferenceBookOut`, add after `notes: Optional[str]`:
```python
    calc_method: str = "standard"
```

- [ ] **Step 2: Add ASUTP Pydantic schemas**

In `backend/app/schemas/__init__.py`, at the end of the file, add:

```python
# ── ASUTP Admin ───────────────────────────────────────────────────────────────

class AsutpFactorOptionOut(BaseModel):
    id: int
    factor_code: str
    factor_name: str
    option_code: str
    option_description: str
    score_or: Optional[int]
    score_oo: Optional[int]
    score_io: Optional[int]
    score_to: Optional[int]
    score_mo: Optional[int]
    score_po: Optional[int]

    class Config:
        from_attributes = True


class AsutpFactorOptionIn(BaseModel):
    factor_code: str
    factor_name: str
    option_code: str
    option_description: str
    score_or: Optional[int] = None
    score_oo: Optional[int] = None
    score_io: Optional[int] = None
    score_to: Optional[int] = None
    score_mo: Optional[int] = None
    score_po: Optional[int] = None


class AsutpModuleOut(BaseModel):
    id: int
    module_code: str
    s_value: float
    sort_order: int
    stage_r_min: int
    stage_r_max: int
    stage_p_min: int
    stage_p_max: int

    class Config:
        from_attributes = True


class AsutpModulePatch(BaseModel):
    s_value: Optional[float] = None
    stage_r_min: Optional[int] = None
    stage_r_max: Optional[int] = None
    stage_p_min: Optional[int] = None
    stage_p_max: Optional[int] = None
```

- [ ] **Step 3: Create admin_asutp.py**

`backend/app/api/admin_asutp.py`:
```python
"""Admin endpoints for ASUTP factor options and modules."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.database import get_db
from app.models import AsutpFactorOption, AsutpModule, ReferenceBook
from app.schemas import (
    AsutpFactorOptionIn, AsutpFactorOptionOut,
    AsutpModuleOut, AsutpModulePatch,
)

router = APIRouter(prefix="/admin/books", tags=["admin-asutp"])


def _get_book_or_404(book_id: int, db: Session) -> ReferenceBook:
    book = db.query(ReferenceBook).filter(ReferenceBook.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


# ── Factor options ────────────────────────────────────────────────────────────

@router.get("/{book_id}/asutp-factors", response_model=list[AsutpFactorOptionOut])
def list_asutp_factors(
    book_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    _get_book_or_404(book_id, db)
    return (
        db.query(AsutpFactorOption)
        .filter(AsutpFactorOption.book_version_id == book_id)
        .order_by(AsutpFactorOption.factor_code, AsutpFactorOption.option_code)
        .all()
    )


@router.post("/{book_id}/asutp-factors", response_model=AsutpFactorOptionOut, status_code=201)
def create_asutp_factor(
    book_id: int,
    data: AsutpFactorOptionIn,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    _get_book_or_404(book_id, db)
    option = AsutpFactorOption(book_version_id=book_id, **data.model_dump())
    db.add(option)
    db.commit()
    db.refresh(option)
    return option


@router.put("/{book_id}/asutp-factors/{option_id}", response_model=AsutpFactorOptionOut)
def update_asutp_factor(
    book_id: int,
    option_id: int,
    data: AsutpFactorOptionIn,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    option = db.query(AsutpFactorOption).filter(
        AsutpFactorOption.id == option_id,
        AsutpFactorOption.book_version_id == book_id,
    ).first()
    if not option:
        raise HTTPException(status_code=404, detail="Factor option not found")
    for k, v in data.model_dump().items():
        setattr(option, k, v)
    db.commit()
    db.refresh(option)
    return option


@router.delete("/{book_id}/asutp-factors/{option_id}", status_code=204)
def delete_asutp_factor(
    book_id: int,
    option_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    option = db.query(AsutpFactorOption).filter(
        AsutpFactorOption.id == option_id,
        AsutpFactorOption.book_version_id == book_id,
    ).first()
    if not option:
        raise HTTPException(status_code=404, detail="Factor option not found")
    db.delete(option)
    db.commit()


# ── Modules ───────────────────────────────────────────────────────────────────

@router.get("/{book_id}/asutp-modules", response_model=list[AsutpModuleOut])
def list_asutp_modules(
    book_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    _get_book_or_404(book_id, db)
    return (
        db.query(AsutpModule)
        .filter(AsutpModule.book_version_id == book_id)
        .order_by(AsutpModule.sort_order)
        .all()
    )


@router.put("/{book_id}/asutp-modules/{module_id}", response_model=AsutpModuleOut)
def update_asutp_module(
    book_id: int,
    module_id: int,
    data: AsutpModulePatch,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    module = db.query(AsutpModule).filter(
        AsutpModule.id == module_id,
        AsutpModule.book_version_id == book_id,
    ).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(module, k, v)
    db.commit()
    db.refresh(module)
    return module
```

- [ ] **Step 4: Register router in main.py**

In `backend/app/main.py`, add:
```python
from app.api import admin_asutp
```
and:
```python
app.include_router(admin_asutp.router)
```

- [ ] **Step 5: Verify backend starts without errors**

```bash
cd backend && python -c "from app.main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/__init__.py backend/app/api/admin_asutp.py backend/app/main.py
git commit -m "feat: АСУТП admin endpoints — CRUD for factor options and modules"
```

---

## Task 7: АСУТП admin frontend

**Files:**
- Modify: `frontend/lib/api.ts` — ReferenceBook.calc_method + ASUTP API functions
- Create: `frontend/components/admin/AsutpTab.tsx`
- Modify: `frontend/app/(app)/admin/references/page.tsx` — wire AsutpTab

- [ ] **Step 1: Add calc_method to ReferenceBook interface and ASUTP API functions**

In `frontend/lib/api.ts`, update `ReferenceBook` interface — add after `notes?`:
```typescript
  calc_method?: string
  price_base_year?: number
```

Add these functions after the existing `deleteHint` function:

```typescript
// ── ASUTP admin ───────────────────────────────────────────────────────────────

export interface AsutpFactorOption {
  id: number
  factor_code: string
  factor_name: string
  option_code: string
  option_description: string
  score_or: number | null
  score_oo: number | null
  score_io: number | null
  score_to: number | null
  score_mo: number | null
  score_po: number | null
}

export interface AsutpFactorOptionIn {
  factor_code: string
  factor_name: string
  option_code: string
  option_description: string
  score_or?: number | null
  score_oo?: number | null
  score_io?: number | null
  score_to?: number | null
  score_mo?: number | null
  score_po?: number | null
}

export interface AsutpModule {
  id: number
  module_code: string
  s_value: number
  sort_order: number
  stage_r_min: number
  stage_r_max: number
  stage_p_min: number
  stage_p_max: number
}

export interface AsutpModulePatch {
  s_value?: number
  stage_r_min?: number
  stage_r_max?: number
  stage_p_min?: number
  stage_p_max?: number
}

export function listAsutpFactors(bookId: number) {
  return request<AsutpFactorOption[]>(`/admin/books/${bookId}/asutp-factors`)
}

export function createAsutpFactor(bookId: number, data: AsutpFactorOptionIn) {
  return request<AsutpFactorOption>(`/admin/books/${bookId}/asutp-factors`, {
    method: 'POST', body: JSON.stringify(data),
  })
}

export function updateAsutpFactor(bookId: number, optionId: number, data: AsutpFactorOptionIn) {
  return request<AsutpFactorOption>(`/admin/books/${bookId}/asutp-factors/${optionId}`, {
    method: 'PUT', body: JSON.stringify(data),
  })
}

export function deleteAsutpFactor(bookId: number, optionId: number) {
  return request<void>(`/admin/books/${bookId}/asutp-factors/${optionId}`, { method: 'DELETE' })
}

export function listAsutpModules(bookId: number) {
  return request<AsutpModule[]>(`/admin/books/${bookId}/asutp-modules`)
}

export function updateAsutpModule(bookId: number, moduleId: number, data: AsutpModulePatch) {
  return request<AsutpModule>(`/admin/books/${bookId}/asutp-modules/${moduleId}`, {
    method: 'PUT', body: JSON.stringify(data),
  })
}
```

- [ ] **Step 2: Create AsutpTab.tsx**

`frontend/components/admin/AsutpTab.tsx`:
```tsx
'use client'

import React, { useEffect, useState } from 'react'
import {
  listAsutpFactors, createAsutpFactor, updateAsutpFactor, deleteAsutpFactor,
  listAsutpModules, updateAsutpModule,
  AsutpFactorOption, AsutpFactorOptionIn, AsutpModule, AsutpModulePatch,
} from '@/lib/api'

const SCORE_COLS = ['score_or', 'score_oo', 'score_io', 'score_to', 'score_mo', 'score_po'] as const
const SCORE_LABELS = ['ОР', 'ОО', 'ИО', 'ТО', 'МО', 'ПО']

interface Props { bookId: number }

export function AsutpTab({ bookId }: Props) {
  const [innerTab, setInnerTab] = useState<'factors' | 'modules'>('factors')
  const [factors, setFactors]   = useState<AsutpFactorOption[]>([])
  const [modules, setModules]   = useState<AsutpModule[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [editingId, setEditingId]   = useState<number | null>(null)
  const [editDraft, setEditDraft]   = useState<AsutpFactorOptionIn | null>(null)
  const [addDraft, setAddDraft]     = useState<AsutpFactorOptionIn | null>(null)
  const [moduleEdits, setModuleEdits] = useState<Record<number, AsutpModulePatch>>({})

  useEffect(() => {
    Promise.all([listAsutpFactors(bookId), listAsutpModules(bookId)])
      .then(([f, m]) => { setFactors(f); setModules(m) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [bookId])

  // ── Factor helpers ──────────────────────────────────────────────────────────

  async function handleSaveEdit(id: number) {
    if (!editDraft) return
    try {
      const updated = await updateAsutpFactor(bookId, id, editDraft)
      setFactors(f => f.map(x => x.id === id ? updated : x))
      setEditingId(null); setEditDraft(null)
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Ошибка') }
  }

  async function handleDelete(id: number) {
    if (!confirm('Удалить вариант фактора?')) return
    try {
      await deleteAsutpFactor(bookId, id)
      setFactors(f => f.filter(x => x.id !== id))
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Ошибка') }
  }

  async function handleAdd() {
    if (!addDraft) return
    try {
      const created = await createAsutpFactor(bookId, addDraft)
      setFactors(f => [...f, created])
      setAddDraft(null)
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Ошибка') }
  }

  // ── Module helpers ──────────────────────────────────────────────────────────

  async function handleSaveModule(id: number) {
    const patch = moduleEdits[id]
    if (!patch) return
    try {
      const updated = await updateAsutpModule(bookId, id, patch)
      setModules(m => m.map(x => x.id === id ? updated : x))
      setModuleEdits(e => { const n = {...e}; delete n[id]; return n })
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Ошибка') }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  if (loading) return <div style={{ padding: 16, color: '#64748b' }}>Загрузка...</div>

  const grouped = new Map<string, AsutpFactorOption[]>()
  for (const f of factors) {
    if (!grouped.has(f.factor_code)) grouped.set(f.factor_code, [])
    grouped.get(f.factor_code)!.push(f)
  }

  const cellStyle: React.CSSProperties = {
    padding: '4px 8px', border: '1px solid #e2e8f0', fontSize: 12,
  }
  const numInputStyle: React.CSSProperties = {
    width: 44, textAlign: 'center', border: '1px solid #cbd5e1',
    borderRadius: 4, padding: '2px 4px', fontSize: 12,
  }

  return (
    <div style={{ padding: '12px 0' }}>
      {error && (
        <div style={{ color: '#dc2626', marginBottom: 8, fontSize: 13 }}>{error}</div>
      )}

      {/* Inner tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['factors', 'modules'] as const).map(t => (
          <button
            key={t}
            onClick={() => setInnerTab(t)}
            style={{
              padding: '4px 14px', borderRadius: 6, fontSize: 13,
              border: innerTab === t ? '2px solid #3b82f6' : '1px solid #cbd5e1',
              background: innerTab === t ? '#eff6ff' : 'white',
              fontWeight: innerTab === t ? 600 : 400, cursor: 'pointer',
            }}
          >
            {t === 'factors' ? 'Факторы' : 'Модули'}
          </button>
        ))}
      </div>

      {/* ── Factors table ── */}
      {innerTab === 'factors' && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                <th style={cellStyle}>Фак.</th>
                <th style={cellStyle}>Код</th>
                <th style={{ ...cellStyle, minWidth: 220 }}>Описание</th>
                {SCORE_LABELS.map(l => (
                  <th key={l} style={{ ...cellStyle, textAlign: 'center' }}>{l}</th>
                ))}
                <th style={cellStyle}></th>
              </tr>
            </thead>
            <tbody>
              {[...grouped.entries()].map(([fcode, opts]) => (
                <React.Fragment key={fcode}>
                  <tr>
                    <td colSpan={3 + SCORE_LABELS.length + 1}
                        style={{ ...cellStyle, background: '#f0f4ff', fontWeight: 600, color: '#1e40af' }}>
                      {fcode} — {opts[0]?.factor_name}
                    </td>
                  </tr>
                  {opts.map(opt => (
                    <tr key={opt.id}>
                      {editingId === opt.id && editDraft ? (
                        <>
                          <td style={cellStyle}>{opt.factor_code}</td>
                          <td style={cellStyle}>
                            <input value={editDraft.option_code}
                              onChange={e => setEditDraft({...editDraft, option_code: e.target.value})}
                              style={{ width: 60, ...numInputStyle }} />
                          </td>
                          <td style={cellStyle}>
                            <input value={editDraft.option_description}
                              onChange={e => setEditDraft({...editDraft, option_description: e.target.value})}
                              style={{ width: '100%', border: '1px solid #cbd5e1', borderRadius: 4, padding: '2px 4px', fontSize: 12 }} />
                          </td>
                          {SCORE_COLS.map(k => (
                            <td key={k} style={{ ...cellStyle, textAlign: 'center' }}>
                              <input type="number"
                                value={editDraft[k] ?? ''}
                                onChange={e => setEditDraft({...editDraft, [k]: e.target.value === '' ? null : Number(e.target.value)})}
                                style={numInputStyle} />
                            </td>
                          ))}
                          <td style={{ ...cellStyle, whiteSpace: 'nowrap' }}>
                            <button onClick={() => handleSaveEdit(opt.id)}
                              style={{ marginRight: 4, color: '#16a34a', cursor: 'pointer', background: 'none', border: 'none', fontWeight: 600 }}>
                              ✓
                            </button>
                            <button onClick={() => { setEditingId(null); setEditDraft(null) }}
                              style={{ color: '#dc2626', cursor: 'pointer', background: 'none', border: 'none' }}>
                              ✕
                            </button>
                          </td>
                        </>
                      ) : (
                        <>
                          <td style={cellStyle}>{opt.factor_code}</td>
                          <td style={cellStyle}>{opt.option_code}</td>
                          <td style={cellStyle}>{opt.option_description}</td>
                          {SCORE_COLS.map(k => (
                            <td key={k} style={{ ...cellStyle, textAlign: 'center' }}>
                              {opt[k] ?? '—'}
                            </td>
                          ))}
                          <td style={{ ...cellStyle, whiteSpace: 'nowrap' }}>
                            <button
                              onClick={() => { setEditingId(opt.id); setEditDraft({ ...opt }) }}
                              style={{ marginRight: 6, cursor: 'pointer', background: 'none', border: 'none', color: '#3b82f6' }}>
                              ✎
                            </button>
                            <button onClick={() => handleDelete(opt.id)}
                              style={{ cursor: 'pointer', background: 'none', border: 'none', color: '#dc2626' }}>
                              🗑
                            </button>
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </React.Fragment>
              ))}

              {/* Add row */}
              {addDraft ? (
                <tr style={{ background: '#f0fdf4' }}>
                  <td style={cellStyle}>
                    <input value={addDraft.factor_code}
                      onChange={e => setAddDraft({...addDraft, factor_code: e.target.value})}
                      placeholder="Ф2" style={{ width: 40, ...numInputStyle }} />
                  </td>
                  <td style={cellStyle}>
                    <input value={addDraft.option_code}
                      onChange={e => setAddDraft({...addDraft, option_code: e.target.value})}
                      placeholder="п.1.1" style={{ width: 60, ...numInputStyle }} />
                  </td>
                  <td style={cellStyle}>
                    <input value={addDraft.option_description}
                      onChange={e => setAddDraft({...addDraft, option_description: e.target.value})}
                      placeholder="Описание варианта"
                      style={{ width: '100%', border: '1px solid #cbd5e1', borderRadius: 4, padding: '2px 4px', fontSize: 12 }} />
                  </td>
                  {SCORE_COLS.map(k => (
                    <td key={k} style={{ ...cellStyle, textAlign: 'center' }}>
                      <input type="number"
                        value={addDraft[k] ?? ''}
                        onChange={e => setAddDraft({...addDraft, [k]: e.target.value === '' ? null : Number(e.target.value)})}
                        style={numInputStyle} />
                    </td>
                  ))}
                  <td style={{ ...cellStyle, whiteSpace: 'nowrap' }}>
                    <button onClick={handleAdd}
                      style={{ marginRight: 4, color: '#16a34a', cursor: 'pointer', background: 'none', border: 'none', fontWeight: 600 }}>
                      ✓
                    </button>
                    <button onClick={() => setAddDraft(null)}
                      style={{ color: '#dc2626', cursor: 'pointer', background: 'none', border: 'none' }}>
                      ✕
                    </button>
                  </td>
                </tr>
              ) : (
                <tr>
                  <td colSpan={3 + SCORE_LABELS.length + 1} style={{ padding: 8 }}>
                    <button
                      onClick={() => setAddDraft({
                        factor_code: '', factor_name: '', option_code: '',
                        option_description: '',
                        score_or: null, score_oo: null, score_io: null,
                        score_to: null, score_mo: null, score_po: null,
                      })}
                      style={{
                        fontSize: 12, color: '#3b82f6', cursor: 'pointer',
                        background: 'none', border: 'none', padding: 0,
                      }}
                    >
                      + Добавить вариант
                    </button>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Modules table ── */}
      {innerTab === 'modules' && (
        <table style={{ borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#f8fafc' }}>
              <th style={cellStyle}>Код</th>
              <th style={cellStyle}>S (тыс.руб.)</th>
              <th style={cellStyle}>Стадия Р мин%</th>
              <th style={cellStyle}>Стадия Р макс%</th>
              <th style={cellStyle}>Стадия П мин%</th>
              <th style={cellStyle}>Стадия П макс%</th>
              <th style={cellStyle}></th>
            </tr>
          </thead>
          <tbody>
            {modules.map(mod => {
              const patch = moduleEdits[mod.id] ?? {}
              const v = (field: keyof AsutpModule) =>
                patch[field as keyof AsutpModulePatch] ?? mod[field]
              return (
                <tr key={mod.id}>
                  <td style={{ ...cellStyle, fontWeight: 600 }}>{mod.module_code}</td>
                  {(['s_value', 'stage_r_min', 'stage_r_max', 'stage_p_min', 'stage_p_max'] as const).map(f => (
                    <td key={f} style={cellStyle}>
                      <input
                        type="number"
                        value={String(v(f))}
                        onChange={e => setModuleEdits(eds => ({
                          ...eds,
                          [mod.id]: { ...(eds[mod.id] ?? {}), [f]: Number(e.target.value) },
                        }))}
                        style={{ ...numInputStyle, width: f === 's_value' ? 70 : 50 }}
                      />
                    </td>
                  ))}
                  <td style={cellStyle}>
                    {moduleEdits[mod.id] && (
                      <button onClick={() => handleSaveModule(mod.id)}
                        style={{ color: '#16a34a', cursor: 'pointer', background: 'none', border: 'none', fontWeight: 600 }}>
                        Сохранить
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Wire AsutpTab into references page**

In `frontend/app/(app)/admin/references/page.tsx`:

Add import:
```tsx
import { AsutpTab } from '@/components/admin/AsutpTab'
```

Find where the book expansion renders tabs (search for `expandedHintsId` or the tab buttons for "Строки" and "Hints"). In the tab list, add a third tab that only shows when `book.calc_method === 'asutp'`:

Locate the tab/section buttons for a book and add:
```tsx
{book.calc_method === 'asutp' && (
  <button
    onClick={() => setActiveTab('asutp')}
    style={{ /* match existing tab button style */ }}
  >
    Факторы АСУТП
  </button>
)}
```

And in the tab content area:
```tsx
{activeTab === 'asutp' && book.calc_method === 'asutp' && (
  <AsutpTab bookId={book.id} />
)}
```

Note: The references page uses `expandedHintsId` to track which book is expanded and shows hints inline. Adapt the tab switching to the actual pattern in the file — add `activeTab` state per expanded book, or use a `Map<number, string>` keyed by bookId.

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no new errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/components/admin/AsutpTab.tsx frontend/app/\(app\)/admin/references/page.tsx
git commit -m "feat: АСУТП factors/modules admin tab in references page"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ X-fallback to minimum row (Tasks 1-2)
- ✅ `used_minimum` flag in position result (Task 2)
- ✅ Banner + badge in UI (Task 4)
- ✅ section_num/section_name in entity schema (Task 3)
- ✅ Section grouping in entities page (Task 4)
- ✅ Section headers in export (Task 5)
- ✅ ASUTP admin endpoints (Task 6)
- ✅ ASUTP admin frontend (Task 7)
- ✅ `calc_method` exposed in API response (Task 6)

**Gaps:**
- Task 4 Step 3 references `EntityRow` component that may not exist as a named component — the entities page renders inline. Implementer must adapt to actual JSX structure.
- Task 7 Step 3 references tab state that doesn't exist yet (`activeTab`) — implementer must add state to the references page.
- `_validate_entities` function location not confirmed — implementer should grep for it.
- `_calculate_asutp_position` return dict location (Task 2 Step 5) — implementer should check exact lines before modifying.
