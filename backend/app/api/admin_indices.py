from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models import PriceIndex, User
from app.schemas import PriceIndexCreate, PriceIndexOut

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
    if body.quarter not in (1, 2, 3, 4):
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
