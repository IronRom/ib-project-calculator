from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models import AuditLog, User
from app.schemas import UserOut, UserUpdateAdmin

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdateAdmin,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    changes = {}
    if body.can_calculate is not None:
        user.can_calculate = body.can_calculate
        changes["can_calculate"] = body.can_calculate
    if body.role is not None:
        if body.role not in ("admin", "user"):
            raise HTTPException(status_code=422, detail="Допустимые роли: admin, user")
        user.role = body.role
        changes["role"] = body.role

    db.add(AuditLog(
        user_id=current_user.id, action="update_user",
        resource_type="user", resource_id=user_id, details=changes,
    ))
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=422, detail="Нельзя удалить собственную учётную запись")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    db.delete(user)
    db.commit()
