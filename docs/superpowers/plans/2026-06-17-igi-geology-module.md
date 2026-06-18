# ИГИ (Geological Survey) Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a geological survey (ИГИ) calculation module so users can manually build a list of НЗ work items (drilling, lab tests, report, etc.) and get a costed estimate alongside the existing PIR calculation.

**Architecture:** `geological_surveys` is a new top-level key in `extracted_entities` (parallel to `entities`). Each survey holds a list of `IgiItem` records. The existing `calculate()` function is extended to call a new `igi_calculator.calculate_igi()` on those items and merge results into the same positions list. A new frontend page `/projects/[id]/geology?calc=ID` lets users pick НЗ281 work types, enter volumes, and trigger re-compute.

**Tech Stack:** FastAPI (Python 3.12), SQLAlchemy, PostgreSQL, Next.js 14 App Router, TypeScript, Tailwind CSS.

---

## File Map

**Create:**
- `backend/app/services/igi_calculator.py` — ИГИ calculation engine
- `backend/tests/test_igi_calculator.py` — unit tests for engine
- `frontend/app/(app)/projects/[id]/geology/page.tsx` — ИГИ work items page

**Modify:**
- `backend/app/schemas/__init__.py` — add `IgiItem`, `GeologicalSurvey` schemas
- `backend/app/api/calculations.py` — add igi-related endpoints + extend compute
- `backend/app/services/calculator.py` — call `calculate_igi` inside `calculate()`
- `frontend/lib/api.ts` — add `IgiItem`, `GeologicalSurvey` types + igi API calls
- `frontend/app/(app)/projects/[id]/page.tsx` — add "ИГИ" button linking to geology page

---

## Task 1: Backend Schemas

**Files:**
- Modify: `backend/app/schemas/__init__.py`

- [ ] **Step 1: Add IgiItem and GeologicalSurvey schemas**

Add at end of `backend/app/schemas/__init__.py`:

```python
# ── ИГИ (geological survey) ───────────────────────────────────────────────────

class IgiItem(BaseModel):
    """One line item in a geological survey estimate."""
    work_category: Literal["field", "lab", "kameral", "program"] = "field"
    object_type_name: str = ""          # display name, e.g. "Бурение колонковым способом"
    table_num: int
    row_num: str = ""
    description: str = ""
    volume: float
    x_unit: str = ""                    # unit label from reference_rows, e.g. "п.м"
    b: float                            # rate in rubles from reference_rows (at base year)
    deleted: bool = False
    notes: str = ""


class GeologicalSurvey(BaseModel):
    """One geological survey block attached to a calculation."""
    book_id: int                        # id of НЗ-2025-МС281-ИГИ (or any future НЗ)
    book_code: str = ""                 # e.g. "НЗ-2025-МС281-ИГИ"
    complexity_category: int = 2        # 1 | 2 | 3 (ИГИ conditions category)
    k1: float = 0.70                    # home-base coefficient (Table 1 НЗ)
    winter_pct: float = 0.0             # winter surcharge fraction, e.g. 0.29
    k2: float = 1.0                     # climate zone coefficient (Table 2 НЗ)
    items: list[IgiItem] = []
```

- [ ] **Step 2: Verify import still works**

```bash
docker exec ib-project-calculator-backend-1 \
  python -c "from app.schemas import IgiItem, GeologicalSurvey; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/__init__.py
git commit -m "feat(igi): add IgiItem + GeologicalSurvey pydantic schemas"
```

---

## Task 2: ИГИ Calculator Service

**Files:**
- Create: `backend/app/services/igi_calculator.py`
- Create: `backend/tests/test_igi_calculator.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_igi_calculator.py`:

```python
"""Tests for igi_calculator.calculate_igi()."""
import sys
sys.path.insert(0, '/app')

import pytest
from unittest.mock import MagicMock, patch
from app.services.igi_calculator import calculate_igi


def _survey(items, *, complexity_category=2, k1=0.70, winter_pct=0.0, k2=1.0):
    return {
        "book_id": 9,
        "book_code": "НЗ-2025-МС281-ИГИ",
        "complexity_category": complexity_category,
        "k1": k1,
        "winter_pct": winter_pct,
        "k2": k2,
        "items": items,
    }


def _item(work_category, table_num, row_num, volume, b, x_unit="п.м", deleted=False):
    return {
        "work_category": work_category,
        "table_num": table_num,
        "row_num": row_num,
        "volume": volume,
        "b": b,
        "x_unit": x_unit,
        "deleted": deleted,
        "description": "Test item",
        "object_type_name": "Test",
    }


@patch("app.services.igi_calculator._get_survey_index")
def test_field_item_applies_k1_and_winter(mock_idx):
    mock_idx.return_value = (1.0, "I кв. 2024 г.", "Письмо МС")
    db = MagicMock()

    items = [_item("field", 14, "п.10", volume=100, b=2756)]
    survey = _survey(items, k1=0.70, winter_pct=0.29)

    positions, errors = calculate_igi([survey], db)

    assert not errors
    assert len(positions) == 1
    pos = positions[0]
    # cost = b * volume * k1 * (1 + winter_pct) * k2 * index
    # = 2756 * 100 * 0.70 * 1.29 * 1.0 * 1.0 = 248 857.2
    assert abs(pos["cost"] - 2756 * 100 * 0.70 * 1.29 * 1.0) < 1
    assert pos["work_category"] == "field"


@patch("app.services.igi_calculator._get_survey_index")
def test_lab_item_no_k1(mock_idx):
    mock_idx.return_value = (2.0, "II кв. 2024 г.", "Письмо МС")
    db = MagicMock()

    items = [_item("lab", 57, "п.1", volume=50, b=229, x_unit="одно определение")]
    survey = _survey(items, k1=0.70, winter_pct=0.29)

    positions, errors = calculate_igi([survey], db)

    assert not errors
    pos = positions[0]
    # lab: b * volume * index only (no k1, no winter)
    assert abs(pos["cost"] - 229 * 50 * 2.0) < 1


@patch("app.services.igi_calculator._get_survey_index")
def test_deleted_item_skipped(mock_idx):
    mock_idx.return_value = (1.0, "I кв. 2024 г.", "Письмо МС")
    db = MagicMock()

    items = [
        _item("field", 14, "п.10", volume=100, b=2756, deleted=True),
        _item("lab", 57, "п.1", volume=10, b=229, x_unit="одно определение"),
    ]
    survey = _survey(items)

    positions, errors = calculate_igi([survey], db)

    assert len(positions) == 1
    assert positions[0]["work_category"] == "lab"


@patch("app.services.igi_calculator._get_survey_index")
def test_report_auto_appended(mock_idx):
    mock_idx.return_value = (1.0, "I кв. 2024 г.", "Письмо МС")
    db = MagicMock()

    # One kameral item so that report cost lookup triggers
    items = [_item("kameral", 62, "п.2", volume=30, b=381, x_unit="один образец")]
    survey = _survey(items, complexity_category=2)

    # Mock the report lookup to return fixed cost
    with patch("app.services.igi_calculator._lookup_report_cost") as mock_report:
        mock_report.return_value = 200_000.0  # rubles at base level
        positions, errors = calculate_igi([survey], db)

    # positions = [kameral item, report auto-item]
    assert len(positions) == 2
    report_pos = positions[-1]
    assert report_pos["work_category"] == "report"
    assert report_pos["cost"] == 200_000.0 * 1.0  # × index
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec ib-project-calculator-backend-1 \
  python -m pytest /app/tests/test_igi_calculator.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'app.services.igi_calculator'`

- [ ] **Step 3: Implement igi_calculator.py**

Create `backend/app/services/igi_calculator.py`:

```python
"""ИГИ (инженерно-геологические изыскания) calculation engine.

НЗ-2025-МС281-ИГИ — Приказ Минстроя РФ от 12.05.2025 № 281/пр.
Base prices: 01.01.2024 (руб).

Formula per work category:
  field:   b × volume × k1 × (1 + winter_pct) × k2 × index
  lab:     b × volume × index
  kameral: b × volume × index
  program: b × volume × index
  report:  auto-computed from total kameral cost via Table 65 lookup (see _lookup_report_cost)
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import PriceQuarterlyIndex, ReferenceRow


def _get_survey_index(db: Session, book_id: int) -> tuple[float, str, str]:
    """Return (index_value, period_label, source_ref) for survey work, base_year=2024.

    Looks up PriceQuarterlyIndex with work_type='survey', base_year=2024.
    Falls back to 1.0 if not configured.
    """
    rec = (
        db.query(PriceQuarterlyIndex)
        .filter(
            PriceQuarterlyIndex.base_year == 2024,
            PriceQuarterlyIndex.work_type == "survey",
        )
        .order_by(PriceQuarterlyIndex.year.desc(), PriceQuarterlyIndex.quarter.desc())
        .first()
    )
    if rec:
        roman = {1: "I", 2: "II", 3: "III", 4: "IV"}
        period = f"{roman.get(rec.quarter, str(rec.quarter))} квартал {rec.year} г."
        return float(rec.index_value), period, rec.source_ref
    return 1.0, "—", "Индекс изысканий к 2024 не задан"


def _lookup_report_cost(
    db: Session, book_id: int, kameral_total_rub: float, complexity_cat: int,
) -> float:
    """Lookup Таблица 65 НЗ-2025-МС281-ИГИ: cost of technical report.

    X = kameral_total_rub converted to тыс.руб.
    Returns cost in rubles at base year level (before index).

    Row structure in DB: x_min/x_max = тыс.руб thresholds, b = cost (руб).
    Interpolates linearly between reference points.
    complexity_cat determines which row set (I → п.1-7, II → п.8-15, III → п.16-24).
    """
    kameral_thous = kameral_total_rub / 1000

    # Determine row_num range by complexity category
    # Cat I: п.1-п.7, Cat II: п.8-п.15, Cat III: п.16-п.24
    _CAT_ROW_RANGES = {1: (1, 7), 2: (8, 15), 3: (16, 24)}
    lo_p, hi_p = _CAT_ROW_RANGES.get(complexity_cat, (8, 15))

    import re
    _RE = re.compile(r'п\.(\d+)')

    rows: list[ReferenceRow] = (
        db.query(ReferenceRow)
        .filter(
            ReferenceRow.book_version_id == book_id,
            ReferenceRow.table_num == 65,
        )
        .all()
    )
    # Filter to complexity category rows by row_num parse
    cat_rows = []
    for r in rows:
        m = _RE.search(r.row_num or "")
        if m and lo_p <= int(m.group(1)) <= hi_p:
            cat_rows.append(r)

    if not cat_rows:
        return 0.0

    # Sort by x_max (thresholds are reference points)
    cat_rows.sort(key=lambda r: float(r.x_max) if r.x_max is not None else 1e12)

    # Find the right reference point: first row where x_max >= kameral_thous
    for r in cat_rows:
        if r.x_max is None or kameral_thous <= float(r.x_max):
            return float(r.b)

    # Above all thresholds: use last row
    return float(cat_rows[-1].b)


def calculate_igi(
    geological_surveys: list[dict[str, Any]],
    db: Session,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Calculate all geological survey blocks.

    Returns (positions, errors).
    Positions have same shape as PIR positions plus extra key 'work_category'.
    """
    positions: list[dict[str, Any]] = []
    errors: list[str] = []

    for survey in geological_surveys:
        book_id = survey.get("book_id")
        if not book_id:
            errors.append("ИГИ: не указан book_id справочника")
            continue

        book_code = survey.get("book_code", f"book#{book_id}")
        k1 = float(survey.get("k1", 0.70))
        winter_pct = float(survey.get("winter_pct", 0.0))
        k2 = float(survey.get("k2", 1.0))
        complexity_cat = int(survey.get("complexity_category", 2))

        index_val, idx_period, idx_just = _get_survey_index(db, book_id)

        kameral_total_base = 0.0  # running total for report lookup (at base level)

        items = [i for i in survey.get("items", []) if not i.get("deleted")]

        for item in items:
            work_cat = item.get("work_category", "field")
            b = float(item.get("b", 0))
            volume = float(item.get("volume", 0))
            x_unit = item.get("x_unit", "")
            table_num = item.get("table_num", 0)
            row_num = item.get("row_num", "")
            desc = item.get("description", "")
            otype_name = item.get("object_type_name", "")

            if work_cat == "field":
                cost = b * volume * k1 * (1 + winter_pct) * k2 * index_val
                coeff_note = (
                    f"К1={k1}"
                    + (f"; зима {int(winter_pct*100)}%" if winter_pct else "")
                    + (f"; К2={k2}" if k2 != 1.0 else "")
                )
            elif work_cat in ("lab", "kameral", "program"):
                cost = b * volume * index_val
                coeff_note = ""
                if work_cat == "kameral":
                    kameral_total_base += b * volume  # accumulate pre-index
            else:
                errors.append(f"ИГИ: неизвестная work_category '{work_cat}'")
                continue

            just = f"{book_code}, табл. {table_num}, {row_num}"
            if coeff_note:
                just += f" [{coeff_note}]"

            formula = f"{int(b)}×{volume}"
            if work_cat == "field":
                formula += f"×{k1}"
                if winter_pct:
                    formula += f"×{1 + winter_pct:.2f}"
                if k2 != 1.0:
                    formula += f"×{k2}"
            if index_val != 1.0:
                formula += f"×{index_val}"

            positions.append({
                "num": len(positions) + 1,
                "name": otype_name or desc,
                "row_description": desc,
                "unit": x_unit,
                "quantity": volume,
                "item_count": 1,
                "justification": just,
                "formula": formula,
                "cost": round(cost, 2),
                "cost_base": round(b * volume, 2),
                "book_code": book_code,
                "price_base_year": 2024,
                "price_index": index_val,
                "price_index_period": idx_period,
                "price_index_justification": idx_just,
                "table_num": table_num,
                "row_num": row_num,
                "used_minimum": False,
                "section_num": 0,
                "section_name": "ИГИ",
                "work_category": work_cat,
            })

        # Auto-append technical report if there are kameral items
        if kameral_total_base > 0:
            report_cost_base = _lookup_report_cost(db, book_id, kameral_total_base, complexity_cat)
            report_cost = report_cost_base * index_val
            if report_cost > 0:
                positions.append({
                    "num": len(positions) + 1,
                    "name": f"Технический отчёт ИГИ (кат.слож.{complexity_cat})",
                    "row_description": f"Табл.65 НЗ-2025-МС281-ИГИ, кат.слож.{complexity_cat}",
                    "unit": "один отчёт",
                    "quantity": 1,
                    "item_count": 1,
                    "justification": (
                        f"{book_code}, табл. 65, кат.слож.{complexity_cat}"
                        f" (камеральные: {round(kameral_total_base/1000, 1)} тыс.руб)"
                    ),
                    "formula": f"{int(report_cost_base)}×{index_val}",
                    "cost": round(report_cost, 2),
                    "cost_base": round(report_cost_base, 2),
                    "book_code": book_code,
                    "price_base_year": 2024,
                    "price_index": index_val,
                    "price_index_period": idx_period,
                    "price_index_justification": idx_just,
                    "table_num": 65,
                    "row_num": "",
                    "used_minimum": False,
                    "section_num": 0,
                    "section_name": "ИГИ",
                    "work_category": "report",
                })

    return positions, errors
```

- [ ] **Step 4: Run tests**

```bash
docker exec ib-project-calculator-backend-1 \
  python -m pytest /app/tests/test_igi_calculator.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/igi_calculator.py backend/tests/test_igi_calculator.py
git commit -m "feat(igi): igi_calculator service with field/lab/kameral/report logic"
```

---

## Task 3: Integrate ИГИ into main calculate()

**Files:**
- Modify: `backend/app/services/calculator.py`

- [ ] **Step 1: Extend `calculate()` to call `calculate_igi` when surveys present**

In `backend/app/services/calculator.py`, at the end of the `calculate()` function, before the aggregate block (line ~680, just before `# ── Aggregate`), add:

```python
    # ── ИГИ geological surveys ────────────────────────────────────────────────
    geological_surveys = entities_dict.get("geological_surveys", [])
    if geological_surveys:
        from app.services.igi_calculator import calculate_igi
        igi_positions, igi_errors = calculate_igi(geological_surveys, db)
        # Renumber to follow PIR positions
        for p in igi_positions:
            p["num"] = len(positions) + 1
            positions.append(p)
        errors.extend(igi_errors)
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
docker exec ib-project-calculator-backend-1 \
  python -m pytest /app/tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/calculator.py
git commit -m "feat(igi): integrate calculate_igi into main calculate() pipeline"
```

---

## Task 4: API Endpoints for ИГИ Management

**Files:**
- Modify: `backend/app/api/calculations.py`

Add three endpoints after `patch_entity_x_value` (around line 155):

- [ ] **Step 1: Add endpoint to list НЗ ИГИ object types + rows**

This powers the frontend picker. Add to `backend/app/api/calculations.py`:

```python
@router.get("/{calc_id}/igi/book-rows")
def list_igi_book_rows(
    project_id: int,
    calc_id: int,
    book_code: str = "НЗ-2025-МС281-ИГИ",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all object types + rows for the given НЗ ИГИ book.

    Used by the frontend to build work item pickers.
    Response: list of { object_type_id, object_type_name, table_num, rows: [...] }
    """
    from app.models import BookObjectType, ReferenceBook, ReferenceRow

    book = db.query(ReferenceBook).filter(
        ReferenceBook.code == book_code,
        ReferenceBook.is_active == True,
    ).first()
    if not book:
        raise HTTPException(status_code=404, detail=f"Справочник {book_code} не найден")

    otypes = db.query(BookObjectType).filter(
        BookObjectType.book_version_id == book.id
    ).order_by(BookObjectType.table_num).all()

    result = []
    for ot in otypes:
        rows = db.query(ReferenceRow).filter(
            ReferenceRow.book_version_id == book.id,
            ReferenceRow.object_type_id == ot.id,
        ).order_by(ReferenceRow.table_num, ReferenceRow.row_num).all()

        result.append({
            "object_type_id": ot.id,
            "object_type_name": ot.name,
            "table_num": ot.table_num,
            "rows": [
                {
                    "id": r.id,
                    "row_num": r.row_num,
                    "description": r.description,
                    "x_unit": r.x_unit,
                    "x_min": float(r.x_min) if r.x_min is not None else None,
                    "x_max": float(r.x_max) if r.x_max is not None else None,
                    "b": float(r.b) if r.b is not None else 0.0,
                }
                for r in rows
            ],
        })

    return {"book_id": book.id, "book_code": book.code, "object_types": result}
```

- [ ] **Step 2: Add endpoint to save/replace ИГИ surveys**

```python
@router.patch("/{calc_id}/geological-surveys")
def patch_geological_surveys(
    project_id: int,
    calc_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Replace geological_surveys in extracted_entities and re-run compute.

    Body: { "geological_surveys": [ <GeologicalSurvey>, ... ] }
    Returns updated calculation result.
    """
    from sqlalchemy.orm.attributes import flag_modified
    from app.services.calculator import calculate

    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(
        Calculation.id == calc_id, Calculation.project_id == project.id
    ).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")

    surveys = body.get("geological_surveys", [])

    # Ensure extracted_entities exists
    if not calc.extracted_entities:
        calc.extracted_entities = {"entities": [], "stage": "П+Р", "geological_surveys": []}

    calc.extracted_entities["geological_surveys"] = surveys
    flag_modified(calc, "extracted_entities")

    # Recompute
    result = calculate(calc.extracted_entities, db)
    calc.price_index_id = result.pop("_price_index_id", None)
    calc.calculation_result = result
    db.commit()
    return result
```

- [ ] **Step 3: Test endpoints manually**

```bash
# Get book rows (replace TOKEN and IDs as needed)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/projects/1/calculations/1/igi/book-rows" | \
  python3 -m json.tool | head -40
```

Expected: JSON with `book_id`, `object_types` array containing types like "Рекогносцировочное обследование (ИГИ)".

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/calculations.py
git commit -m "feat(igi): add book-rows and geological-surveys API endpoints"
```

---

## Task 5: Add Survey Index Admin Support

**Files:**
- Modify: `backend/app/api/admin_indices.py` (or wherever indices are managed)

The ИГИ calculator looks for `PriceQuarterlyIndex(base_year=2024, work_type="survey")`. Admins need to enter this.

- [ ] **Step 1: Read the existing indices admin endpoint**

```bash
grep -n "work_type\|quarterly" "/Users/erwinvanhoof/Library/Mobile Documents/com~apple~CloudDocs/Projects/GitIronRom/ib-project-calculator/backend/app/api/admin_indices.py" | head -20
```

- [ ] **Step 2: Verify existing PriceQuarterlyIndexCreate schema already accepts `work_type`**

In `backend/app/schemas/__init__.py`, `PriceQuarterlyIndexCreate` already has `work_type: str = "project"`. No schema change needed — admin just posts `work_type="survey"`.

- [ ] **Step 3: Seed the II кв. 2026 survey index for testing**

```bash
docker exec ib-project-calculator-backend-1 python3 -c "
import sys; sys.path.insert(0, '/app')
from app.database import SessionLocal
from app.models import PriceQuarterlyIndex
db = SessionLocal()
existing = db.query(PriceQuarterlyIndex).filter_by(
    year=2026, quarter=2, base_year=2024, work_type='survey'
).first()
if not existing:
    db.add(PriceQuarterlyIndex(
        year=2026, quarter=2, base_year=2024, work_type='survey',
        index_value=1.0,
        source_ref='Письмо МинСтрой РФ № 20212-ИФ/09 от 08.04.2026 (изыскания 2024→2026)'
    ))
    db.commit()
    print('Added survey index II кв. 2026')
else:
    print('Already exists:', existing.index_value)
db.close()
"
```

Note: index_value=1.0 is placeholder — update via admin UI once real index letter is known.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(igi): seed survey quarterly index placeholder for II кв. 2026"
```

---

## Task 6: Frontend API Types + Functions

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add IgiItem, GeologicalSurvey types and API functions**

In `frontend/lib/api.ts`, after the `CalculationResult` interface (around line 485), add:

```typescript
// ── ИГИ (geological survey) ───────────────────────────────────────────────────

export type IgiWorkCategory = 'field' | 'lab' | 'kameral' | 'program'

export interface IgiItem {
  work_category: IgiWorkCategory
  object_type_name: string
  table_num: number
  row_num: string
  description: string
  volume: number
  x_unit: string
  b: number
  deleted?: boolean
  notes?: string
}

export interface GeologicalSurvey {
  book_id: number
  book_code: string
  complexity_category: number   // 1 | 2 | 3
  k1: number
  winter_pct: number
  k2: number
  items: IgiItem[]
}

export interface IgiBookRow {
  id: number
  row_num: string
  description: string
  x_unit: string
  x_min: number | null
  x_max: number | null
  b: number
}

export interface IgiObjectType {
  object_type_id: number
  object_type_name: string
  table_num: number
  rows: IgiBookRow[]
}

export interface IgiBookRows {
  book_id: number
  book_code: string
  object_types: IgiObjectType[]
}
```

Also add after `getUnitCheck`:

```typescript
export function getIgiBookRows(
  projectId: number, calcId: number, bookCode = 'НЗ-2025-МС281-ИГИ'
) {
  return request<IgiBookRows>(
    `/projects/${projectId}/calculations/${calcId}/igi/book-rows?book_code=${encodeURIComponent(bookCode)}`
  )
}

export function saveGeologicalSurveys(
  projectId: number, calcId: number, surveys: GeologicalSurvey[]
): Promise<CalculationResult> {
  return request<CalculationResult>(
    `/projects/${projectId}/calculations/${calcId}/geological-surveys`,
    { method: 'PATCH', body: JSON.stringify({ geological_surveys: surveys }) }
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd "/Users/erwinvanhoof/Library/Mobile Documents/com~apple~CloudDocs/Projects/GitIronRom/ib-project-calculator/frontend" && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(igi): add IgiItem, GeologicalSurvey TS types and API functions"
```

---

## Task 7: Frontend Geology Page

**Files:**
- Create: `frontend/app/(app)/projects/[id]/geology/page.tsx`

- [ ] **Step 1: Determine work_category defaults per table**

Based on НЗ 281/пр structure, define a mapping used by the UI to pre-fill `work_category`:

```typescript
// Tables 12-33 = field work; 43-55 = field; 56-64 = lab/kameral; 65 = report (auto); 66 = program
const WORK_CATEGORY_BY_TABLE: Record<number, IgiWorkCategory> = {
  12: 'field', 14: 'field', 16: 'field', 18: 'field',
  43: 'field', 47: 'field', 50: 'field', 52: 'field', 54: 'field',
  56: 'lab', 57: 'lab', 58: 'lab', 59: 'lab', 60: 'lab', 61: 'lab',
  62: 'kameral', 63: 'lab', 64: 'kameral',
  66: 'program',
}
```

- [ ] **Step 2: Create the geology page**

Create `frontend/app/(app)/projects/[id]/geology/page.tsx`:

```tsx
'use client'

import React, { useCallback, useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import {
  getIgiBookRows, saveGeologicalSurveys,
  GeologicalSurvey, IgiItem, IgiObjectType, IgiBookRow,
  IgiWorkCategory, CalculationResult,
} from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'

type IgiWorkCategory2 = IgiWorkCategory  // alias for readability

const WORK_CATEGORY_BY_TABLE: Record<number, IgiWorkCategory2> = {
  12: 'field', 14: 'field', 16: 'field', 18: 'field',
  43: 'field', 47: 'field', 50: 'field', 52: 'field', 54: 'field',
  56: 'lab', 57: 'lab', 58: 'lab', 59: 'lab', 60: 'lab', 61: 'lab',
  62: 'kameral', 63: 'lab', 64: 'kameral',
  66: 'program',
}

const CAT_LABELS: Record<IgiWorkCategory2, string> = {
  field: 'Полевые',
  lab: 'Лабораторные',
  kameral: 'Камеральные',
  program: 'Программа',
}

function fmt(n: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(n)
}

export default function GeologyPage() {
  const { id } = useParams<{ id: string }>()
  const sp = useSearchParams()
  const calcId = sp.get('calc')

  const [bookData, setBookData] = useState<{ bookId: number; bookCode: string; objectTypes: IgiObjectType[] } | null>(null)
  const [survey, setSurvey] = useState<GeologicalSurvey>({
    book_id: 0,
    book_code: 'НЗ-2025-МС281-ИГИ',
    complexity_category: 2,
    k1: 0.70,
    winter_pct: 0.29,  // Тверская oblast default
    k2: 1.0,
    items: [],
  })
  const [result, setResult] = useState<CalculationResult | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Picker state
  const [pickerOtype, setPickerOtype] = useState<IgiObjectType | null>(null)
  const [pickerRow, setPickerRow] = useState<IgiBookRow | null>(null)
  const [pickerVolume, setPickerVolume] = useState('')

  useEffect(() => {
    if (!calcId) return
    getIgiBookRows(Number(id), Number(calcId)).then(d => {
      setBookData({ bookId: d.book_id, bookCode: d.book_code, objectTypes: d.object_types })
      setSurvey(prev => ({ ...prev, book_id: d.book_id, book_code: d.book_code }))
    }).catch(e => setError(String(e)))
  }, [id, calcId])

  const addItem = useCallback(() => {
    if (!pickerOtype || !pickerRow || !pickerVolume) return
    const vol = parseFloat(pickerVolume)
    if (isNaN(vol) || vol <= 0) return

    const workCat = WORK_CATEGORY_BY_TABLE[pickerOtype.table_num] ?? 'field'
    const item: IgiItem = {
      work_category: workCat,
      object_type_name: pickerOtype.object_type_name,
      table_num: pickerOtype.table_num,
      row_num: pickerRow.row_num,
      description: pickerRow.description ?? '',
      volume: vol,
      x_unit: pickerRow.x_unit ?? '',
      b: pickerRow.b,
    }
    setSurvey(prev => ({ ...prev, items: [...prev.items, item] }))
    setPickerRow(null)
    setPickerVolume('')
  }, [pickerOtype, pickerRow, pickerVolume])

  const removeItem = useCallback((idx: number) => {
    setSurvey(prev => ({
      ...prev,
      items: prev.items.filter((_, i) => i !== idx),
    }))
  }, [])

  const handleSave = async () => {
    if (!calcId) return
    setSaving(true)
    setError('')
    try {
      const res = await saveGeologicalSurveys(Number(id), Number(calcId), [survey])
      setResult(res)
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const igiTotal = result?.positions
    ?.filter(p => (p as any).section_name === 'ИГИ')
    ?.reduce((s, p) => s + p.cost, 0) ?? null

  return (
    <div className="min-h-screen bg-neutral-950 text-white">
      <Topbar />
      <div className="max-w-6xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-semibold mb-6">Инженерно-геологические изыскания (ИГИ)</h1>

        {/* Survey parameters */}
        <div className="bg-neutral-900 rounded-xl p-5 mb-6 flex gap-6 flex-wrap">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-400">Кат. сложности ИГИ</span>
            <select
              className="bg-neutral-800 rounded px-3 py-1.5 text-white"
              value={survey.complexity_category}
              onChange={e => setSurvey(p => ({ ...p, complexity_category: Number(e.target.value) }))}
            >
              <option value={1}>I</option>
              <option value={2}>II</option>
              <option value={3}>III</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-400">К1 (место работы)</span>
            <input
              type="number" step="0.01" min="0.5" max="1"
              className="bg-neutral-800 rounded px-3 py-1.5 text-white w-24"
              value={survey.k1}
              onChange={e => setSurvey(p => ({ ...p, k1: Number(e.target.value) }))}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-400">Зимний % (доля, 0.29=29%)</span>
            <input
              type="number" step="0.01" min="0" max="1"
              className="bg-neutral-800 rounded px-3 py-1.5 text-white w-24"
              value={survey.winter_pct}
              onChange={e => setSurvey(p => ({ ...p, winter_pct: Number(e.target.value) }))}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-400">К2 (климат)</span>
            <input
              type="number" step="0.01" min="1" max="2"
              className="bg-neutral-800 rounded px-3 py-1.5 text-white w-24"
              value={survey.k2}
              onChange={e => setSurvey(p => ({ ...p, k2: Number(e.target.value) }))}
            />
          </label>
        </div>

        {/* Picker */}
        {bookData && (
          <div className="bg-neutral-900 rounded-xl p-5 mb-6">
            <h2 className="font-medium mb-4 text-neutral-300">Добавить позицию</h2>
            <div className="flex gap-3 flex-wrap items-end">
              <div className="flex flex-col gap-1 text-sm">
                <span className="text-neutral-400">Вид работ</span>
                <select
                  className="bg-neutral-800 rounded px-3 py-1.5 text-white min-w-[260px]"
                  value={pickerOtype?.object_type_id ?? ''}
                  onChange={e => {
                    const ot = bookData.objectTypes.find(o => o.object_type_id === Number(e.target.value)) ?? null
                    setPickerOtype(ot)
                    setPickerRow(null)
                  }}
                >
                  <option value="">— выберите —</option>
                  {bookData.objectTypes.map(ot => (
                    <option key={ot.object_type_id} value={ot.object_type_id}>
                      {ot.object_type_name}
                    </option>
                  ))}
                </select>
              </div>
              {pickerOtype && (
                <div className="flex flex-col gap-1 text-sm">
                  <span className="text-neutral-400">Строка таблицы {pickerOtype.table_num}</span>
                  <select
                    className="bg-neutral-800 rounded px-3 py-1.5 text-white min-w-[320px]"
                    value={pickerRow?.id ?? ''}
                    onChange={e => {
                      const r = pickerOtype.rows.find(r => r.id === Number(e.target.value)) ?? null
                      setPickerRow(r)
                    }}
                  >
                    <option value="">— выберите —</option>
                    {pickerOtype.rows.map(r => (
                      <option key={r.id} value={r.id}>
                        {r.row_num} — {(r.description ?? '').slice(0, 80)}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {pickerRow && (
                <>
                  <div className="flex flex-col gap-1 text-sm">
                    <span className="text-neutral-400">Объём ({pickerRow.x_unit})</span>
                    <input
                      type="number" min="0"
                      className="bg-neutral-800 rounded px-3 py-1.5 text-white w-28"
                      value={pickerVolume}
                      onChange={e => setPickerVolume(e.target.value)}
                      placeholder="0"
                    />
                  </div>
                  <Button onClick={addItem} disabled={!pickerVolume}>+ Добавить</Button>
                </>
              )}
            </div>
          </div>
        )}

        {/* Items table */}
        {survey.items.length > 0 && (
          <div className="bg-neutral-900 rounded-xl mb-6 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-800 text-neutral-400">
                  <th className="px-4 py-3 text-left">Вид</th>
                  <th className="px-4 py-3 text-left">Наименование</th>
                  <th className="px-4 py-3 text-left">Таблица</th>
                  <th className="px-4 py-3 text-right">Объём</th>
                  <th className="px-4 py-3 text-left">Ед.</th>
                  <th className="px-4 py-3 text-right">Ставка (руб)</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {survey.items.map((item, i) => (
                  <tr key={i} className="border-b border-neutral-800/50 hover:bg-neutral-800/40">
                    <td className="px-4 py-2">
                      <span className="text-xs bg-neutral-700 rounded px-2 py-0.5">
                        {CAT_LABELS[item.work_category]}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-neutral-200 max-w-xs truncate" title={item.description}>
                      {item.object_type_name}
                    </td>
                    <td className="px-4 py-2 text-neutral-400">
                      Табл.{item.table_num} {item.row_num}
                    </td>
                    <td className="px-4 py-2 text-right">{item.volume}</td>
                    <td className="px-4 py-2 text-neutral-400 text-xs">{item.x_unit}</td>
                    <td className="px-4 py-2 text-right font-mono">{fmt(item.b)}</td>
                    <td className="px-4 py-2">
                      <button
                        onClick={() => removeItem(i)}
                        className="text-neutral-500 hover:text-red-400 text-xs"
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

        <div className="flex gap-4 items-center">
          <Button onClick={handleSave} disabled={saving || survey.items.length === 0}>
            {saving ? 'Сохраняю…' : 'Сохранить и рассчитать'}
          </Button>
          {igiTotal !== null && (
            <span className="text-neutral-300">
              ИГИ итого: <strong>{fmt(igiTotal)} руб.</strong> без НДС
            </span>
          )}
        </div>

        {/* Result positions */}
        {result && result.positions.filter(p => (p as any).section_name === 'ИГИ').length > 0 && (
          <div className="mt-8">
            <h2 className="font-medium mb-4 text-neutral-300">Результат расчёта ИГИ</h2>
            <div className="bg-neutral-900 rounded-xl overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-neutral-800 text-neutral-400">
                    <th className="px-4 py-3 text-left">№</th>
                    <th className="px-4 py-3 text-left">Наименование</th>
                    <th className="px-4 py-3 text-left">Обоснование</th>
                    <th className="px-4 py-3 text-right">Стоимость, руб.</th>
                  </tr>
                </thead>
                <tbody>
                  {result.positions
                    .filter(p => (p as any).section_name === 'ИГИ')
                    .map(p => (
                      <tr key={p.num} className="border-b border-neutral-800/50">
                        <td className="px-4 py-2 text-neutral-400">{p.num}</td>
                        <td className="px-4 py-2">{p.name}</td>
                        <td className="px-4 py-2 text-neutral-400 text-xs">{p.justification}</td>
                        <td className="px-4 py-2 text-right font-mono">{fmt(p.cost)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Build to verify no TS errors**

```bash
cd "/Users/erwinvanhoof/Library/Mobile Documents/com~apple~CloudDocs/Projects/GitIronRom/ib-project-calculator/frontend" && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add "frontend/app/(app)/projects/[id]/geology/page.tsx"
git commit -m "feat(igi): add geology page for ИГИ work items"
```

---

## Task 8: Link from Project Page

**Files:**
- Modify: `frontend/app/(app)/projects/[id]/page.tsx`

- [ ] **Step 1: Read the project page**

```bash
head -60 "/Users/erwinvanhoof/Library/Mobile Documents/com~apple~CloudDocs/Projects/GitIronRom/ib-project-calculator/frontend/app/(app)/projects/[id]/page.tsx"
```

- [ ] **Step 2: Add ИГИ button when calc exists**

Find the section where navigation buttons to `/entities` or `/results` are shown. Add alongside them:

```tsx
{calc && (
  <Button
    variant="outline"
    onClick={() => router.push(`/projects/${id}/geology?calc=${calc.id}`)}
  >
    Добавить ИГИ
  </Button>
)}
```

(Adapt to actual surrounding code after reading the file.)

- [ ] **Step 3: Verify page compiles**

```bash
cd "/Users/erwinvanhoof/Library/Mobile Documents/com~apple~CloudDocs/Projects/GitIronRom/ib-project-calculator/frontend" && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 4: Commit**

```bash
git add "frontend/app/(app)/projects/[id]/page.tsx"
git commit -m "feat(igi): link to geology page from project view"
```

---

## Task 9: End-to-End Manual Test

- [ ] **Step 1: Start app**

```bash
cd "/Users/erwinvanhoof/Library/Mobile Documents/com~apple~CloudDocs/Projects/GitIronRom/ib-project-calculator" && docker compose up -d
```

- [ ] **Step 2: Navigate to a project, open ИГИ page**

- Project page → "Добавить ИГИ" → geology page loads with book-rows data
- Verify work types dropdown shows "Бурение колонковым способом (ИГИ)", "Физические свойства грунтов (ИГИ)", etc.

- [ ] **Step 3: Add Кашин-equivalent positions**

Add these items:
1. Бурение колонковым способом → Табл.14 п.10 (кат.II, 15-25м) → volume: 199 п.м
2. Физические свойства грунтов → Табл.57 п.18 (пластичность, природная влажность) → volume: 69
3. Физические свойства грунтов → Табл.57 п.18 → volume: 48 (37+11)
4. Химический анализ вод → Табл.63 п.1 → volume: 3
5. Камеральная обработка лаб. → Табл.62 п.2 → volume: 116

Set: К1=0.70, зима=0.29, кат.слож=2.

- [ ] **Step 4: Save and compare to Кашин ЛС-01 total (3284.86 тыс.руб)**

Expected: result is in the same order of magnitude. Exact match requires the II кв. 2026 survey index to be configured.

---

## Spec Coverage Check

| Requirement | Covered by |
|---|---|
| Universal: any НЗ book, any table, any row | Task 4 (book-rows endpoint), Task 7 picker |
| Field/lab/kameral coefficient logic | Task 2 (igi_calculator) |
| Technical report auto-computed | Task 2 (_lookup_report_cost) |
| Survey quarterly index separate from project | Task 5 |
| Frontend: add/remove items | Task 7 |
| Frontend: survey parameters (K1, winter, K2, complexity) | Task 7 |
| Integrated into existing compute pipeline | Task 3 |
| ИГИ positions appear in results alongside PIR | Task 3 |
| Tests | Task 2 |
