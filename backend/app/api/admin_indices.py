from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models import PriceIndex, PriceQuarterlyIndex, User
from app.schemas import PriceIndexCreate, PriceIndexOut, PriceQuarterlyIndexCreate, PriceQuarterlyIndexOut

router = APIRouter(prefix="/admin/indices", tags=["admin"])


@router.get("", response_model=List[PriceIndexOut])
def list_indices(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(PriceIndex).order_by(PriceIndex.year.desc(), PriceIndex.quarter.desc()).all()


@router.post("", response_model=PriceIndexOut, status_code=201)
def create_index(
    body: PriceIndexCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if body.index_type != "vat" and body.quarter not in (1, 2, 3, 4):
        raise HTTPException(status_code=422, detail="Квартал должен быть от 1 до 4")
    existing = db.query(PriceIndex).filter(
        PriceIndex.year == body.year,
        PriceIndex.quarter == body.quarter,
        PriceIndex.index_type == body.index_type,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Индекс за {body.year} Q{body.quarter} ({body.index_type}) уже существует",
        )
    idx = PriceIndex(**body.model_dump())
    db.add(idx)
    db.commit()
    db.refresh(idx)
    return idx


@router.patch("/{index_id}", response_model=PriceIndexOut)
def update_index(
    index_id: int,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    idx = db.query(PriceIndex).filter(PriceIndex.id == index_id).first()
    if not idx:
        raise HTTPException(status_code=404, detail="Не найден")
    for field in ("year", "quarter", "index_value", "source_ref"):
        if field in body:
            setattr(idx, field, body[field])
    db.commit()
    db.refresh(idx)
    return idx


@router.delete("/{index_id}", status_code=204)
def delete_index(index_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    idx = db.query(PriceIndex).filter(PriceIndex.id == index_id).first()
    if not idx:
        raise HTTPException(status_code=404, detail="Индекс не найден")
    db.delete(idx)
    db.commit()


@router.get("/current", response_model=PriceIndexOut)
def get_current_index(index_type: str = "project", db: Session = Depends(get_db)):
    idx = (
        db.query(PriceIndex)
        .filter(PriceIndex.index_type == index_type)
        .order_by(PriceIndex.year.desc(), PriceIndex.quarter.desc())
        .first()
    )
    if not idx:
        raise HTTPException(status_code=404, detail="Индексы не найдены. Добавьте в разделе Администрирование.")
    return idx


# ── PriceQuarterlyIndex CRUD ─────────────────────────────────────────────────

@router.get("/quarterly", response_model=List[PriceQuarterlyIndexOut])
def list_quarterly(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return (
        db.query(PriceQuarterlyIndex)
        .order_by(
            PriceQuarterlyIndex.year.desc(),
            PriceQuarterlyIndex.quarter.desc(),
            PriceQuarterlyIndex.base_year,
        )
        .all()
    )


@router.post("/quarterly", response_model=PriceQuarterlyIndexOut, status_code=201)
def create_quarterly(
    body: PriceQuarterlyIndexCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if body.quarter not in (1, 2, 3, 4):
        raise HTTPException(status_code=422, detail="Квартал должен быть от 1 до 4")
    existing = db.query(PriceQuarterlyIndex).filter(
        PriceQuarterlyIndex.year == body.year,
        PriceQuarterlyIndex.quarter == body.quarter,
        PriceQuarterlyIndex.base_year == body.base_year,
        PriceQuarterlyIndex.work_type == body.work_type,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Индекс {body.year} Q{body.quarter} к уровню {body.base_year} уже существует",
        )
    rec = PriceQuarterlyIndex(**body.model_dump())
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.patch("/quarterly/{index_id}", response_model=PriceQuarterlyIndexOut)
def update_quarterly(
    index_id: int,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rec = db.query(PriceQuarterlyIndex).filter(PriceQuarterlyIndex.id == index_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Не найден")
    for field in ("index_value", "source_ref"):
        if field in body:
            setattr(rec, field, body[field])
    db.commit()
    db.refresh(rec)
    return rec


@router.delete("/quarterly/{index_id}", status_code=204)
def delete_quarterly(
    index_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rec = db.query(PriceQuarterlyIndex).filter(PriceQuarterlyIndex.id == index_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Не найден")
    db.delete(rec)
    db.commit()


@router.get("/stale-warning")
def stale_index_warning(db: Session = Depends(get_db)):
    idx = (
        db.query(PriceIndex)
        .filter(PriceIndex.index_type == "project")
        .order_by(PriceIndex.year.desc(), PriceIndex.quarter.desc())
        .first()
    )
    if not idx:
        return {"stale": True, "message": "Индексы отсутствуют"}
    # Approximate: quarter end date
    quarter_end_month = idx.quarter * 3
    quarter_end = datetime(idx.year, quarter_end_month, 28) + timedelta(days=4)
    age_days = (datetime.utcnow() - quarter_end).days
    stale = age_days > 90
    return {
        "stale": stale,
        "message": f"Актуальный индекс: {idx.year} Q{idx.quarter} = {idx.index_value}" + (
            f" (устарел на {age_days} дней)" if stale else ""
        ),
    }
