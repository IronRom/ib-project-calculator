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


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Создание пользователя администратором.
    body: {email, password, company?, role?, can_calculate?}"""
    from app.api.auth import hash_password
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    if "@" not in email or len(password) < 6:
        raise HTTPException(status_code=422, detail="Нужны корректный email и пароль от 6 символов")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Пользователь с этой почтой уже существует")
    user = User(
        email=email,
        password_hash=hash_password(password),
        company=body.get("company"),
        role="admin" if body.get("role") == "admin" else "user",
        can_calculate=bool(body.get("can_calculate", True)),
    )
    db.add(user)
    db.add(AuditLog(user_id=current_user.id, action="admin_create_user",
                    details={"email": email}))
    db.commit()
    db.refresh(user)
    return user


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
    if body.is_active is not None:
        if user.id == current_user.id and not body.is_active:
            raise HTTPException(status_code=422, detail="Нельзя заблокировать самого себя")
        user.is_active = body.is_active
        changes["is_active"] = body.is_active

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
    if user.id == current_user.id:
        raise HTTPException(status_code=422, detail="Нельзя удалить самого себя")
    from app.models import Project
    n_projects = db.query(Project).filter(Project.user_id == user_id).count()
    if n_projects:
        raise HTTPException(
            status_code=409,
            detail=f"У пользователя {n_projects} проект(ов) — данные будут потеряны. "
                   f"Заблокируйте учётную запись вместо удаления.",
        )
    # его аудит-записи мешают FK — удаляем вместе с учёткой
    db.query(AuditLog).filter(AuditLog.user_id == user_id).delete()
    db.delete(user)
    db.commit()


# ═══ Настройки системы (модели AI и пр.) ══════════════════════════════════
# Отдельный роутер: /admin/settings (в /admin/users конфликтует с {user_id})
settings_router = APIRouter(prefix="/admin/settings", tags=["admin"])


@settings_router.get("")
def get_settings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models import AppSetting
    return {s.key: s.value for s in db.query(AppSetting).all()}


@settings_router.put("")
def put_settings(
    body: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Обновить настройки. body: {key: value, ...}.

    Ключи моделей: extraction_model, clarification_model (id OpenRouter).
    """
    from app.models import AppSetting
    allowed = {"extraction_model", "clarification_model", "ocr_model"}
    updated = {}
    for k, v in body.items():
        if k not in allowed:
            raise HTTPException(status_code=422, detail=f"Неизвестный ключ: {k}")
        rec = db.query(AppSetting).filter(AppSetting.key == k).first()
        if rec:
            rec.value = str(v)
        else:
            db.add(AppSetting(key=k, value=str(v)))
        updated[k] = str(v)
    db.commit()
    return updated
