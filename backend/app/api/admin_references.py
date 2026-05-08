import os
import shutil
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.config import settings
from app.database import get_db
from app.models import AuditLog, ReferenceBook, User
from app.schemas import ReferenceBookOut, ReferenceBookUpdate

router = APIRouter(prefix="/admin/references", tags=["admin"])


@router.get("", response_model=List[ReferenceBookOut])
def list_references(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(ReferenceBook).order_by(ReferenceBook.code, ReferenceBook.version.desc()).all()


@router.post("", response_model=ReferenceBookOut, status_code=201)
def upload_reference(
    code: str,
    official_name: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Допустимый формат: PDF")

    # Determine next version for this code
    last = db.query(ReferenceBook).filter(ReferenceBook.code == code).order_by(ReferenceBook.version.desc()).first()
    next_version = (last.version + 1) if last else 1

    dest_dir = os.path.join(settings.uploads_dir, "references", code)
    os.makedirs(dest_dir, exist_ok=True)
    filename = f"v{next_version}_{uuid.uuid4().hex}.pdf"
    dest_path = os.path.join(dest_dir, filename)
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    book = ReferenceBook(
        code=code,
        official_name=official_name,
        version=next_version,
        pdf_filename=file.filename,
        pdf_path=dest_path,
        status="requires_validation",
    )
    db.add(book)
    db.flush()
    db.add(AuditLog(
        user_id=current_user.id, action="upload_reference",
        resource_type="reference_book", resource_id=book.id,
        details={"code": code, "version": next_version},
    ))
    db.commit()
    db.refresh(book)
    return book


@router.get("/{book_id}", response_model=ReferenceBookOut)
def get_reference(book_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    book = _get_book(book_id, db)
    return book


@router.patch("/{book_id}", response_model=ReferenceBookOut)
def update_reference(
    book_id: int, body: ReferenceBookUpdate,
    db: Session = Depends(get_db), _: User = Depends(require_admin),
):
    book = _get_book(book_id, db)
    if body.notes is not None:
        book.notes = body.notes
    if body.parse_prompt is not None:
        book.parse_prompt = body.parse_prompt
    db.commit()
    db.refresh(book)
    return book


@router.post("/{book_id}/activate", response_model=ReferenceBookOut)
def activate_reference(
    book_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    book = _get_book(book_id, db)
    if book.status != "consistent":
        raise HTTPException(status_code=422, detail="Активировать можно только валидированный справочник (consistent)")

    # Deactivate previous active version of same code
    db.query(ReferenceBook).filter(
        ReferenceBook.code == book.code,
        ReferenceBook.is_active == True,
        ReferenceBook.id != book.id,
    ).update({"is_active": False, "status": "archived"})

    from datetime import datetime
    book.is_active = True
    book.activated_at = datetime.utcnow()
    db.add(AuditLog(
        user_id=current_user.id, action="activate_reference",
        resource_type="reference_book", resource_id=book.id,
    ))
    db.commit()
    db.refresh(book)
    return book


@router.post("/{book_id}/rollback", response_model=ReferenceBookOut)
def rollback_reference(
    book_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    book = _get_book(book_id, db)
    if not book.is_active:
        raise HTTPException(status_code=422, detail="Справочник не активен")

    book.is_active = False
    book.status = "archived"

    # Re-activate previous consistent version
    prev = (
        db.query(ReferenceBook)
        .filter(
            ReferenceBook.code == book.code,
            ReferenceBook.status == "consistent",
            ReferenceBook.id != book.id,
        )
        .order_by(ReferenceBook.version.desc())
        .first()
    )
    if prev:
        from datetime import datetime
        prev.is_active = True
        prev.activated_at = datetime.utcnow()

    db.add(AuditLog(
        user_id=current_user.id, action="rollback_reference",
        resource_type="reference_book", resource_id=book.id,
    ))
    db.commit()
    db.refresh(book)
    return book


def _get_book(book_id: int, db: Session) -> ReferenceBook:
    book = db.query(ReferenceBook).filter(ReferenceBook.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Справочник не найден")
    return book
