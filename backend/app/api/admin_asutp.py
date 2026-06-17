"""Admin endpoints for ASUTP factor options and modules."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models import AsutpFactorOption, AsutpModule, ReferenceBook, User
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
    _: User = Depends(require_admin),
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
    _: User = Depends(require_admin),
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
    _: User = Depends(require_admin),
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
    _: User = Depends(require_admin),
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
    _: User = Depends(require_admin),
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
    _: User = Depends(require_admin),
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
