"""Привязка Telegram-бота к учётной записи.

Модель безопасности:
  1. Пользователь в кабинете жмёт «Подключить Telegram» → backend выдаёт
     одноразовый ПОДПИСАННЫЙ код (JWT purpose=tg_link, живёт 15 мин) и deep-link
     t.me/<bot>?start=<code>.
  2. Пользователь открывает бота — тот присылает code на POST /auth/telegram/link
     с общим секретом X-Bot-Secret. backend проверяет подпись кода и секрет,
     пишет users.telegram_id.
  3. Дальше бот на каждое действие резолвит telegram_id → JWT пользователя через
     POST /auth/telegram/resolve и работает обычными ручками API от его имени.

Секрет бота (settings.bot_api_secret) отсекает произвольные запросы из интернета:
resolve отдаёт полноценный токен пользователя, link — меняет привязку.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import create_token
from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/auth/telegram", tags=["telegram"])

_LINK_TTL_MIN = 15


# ── Кабинет: выдать код привязки ──────────────────────────────────────────────

class LinkCodeOut(BaseModel):
    code: str
    deep_link: str
    bot_username: str


@router.get("/link-code", response_model=LinkCodeOut)
def get_link_code(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    expire = datetime.utcnow() + timedelta(minutes=_LINK_TTL_MIN)
    code = jwt.encode(
        {"sub": str(current_user.id), "purpose": "tg_link", "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    username = settings.telegram_bot_username or "ib_pir_bot"
    return LinkCodeOut(
        code=code,
        deep_link=f"https://t.me/{username}?start={code}",
        bot_username=username,
    )


@router.post("/unlink")
def unlink_telegram(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.telegram_id = None
    current_user.telegram_username = None
    db.commit()
    return {"linked": False}


# ── Бот: привилегированные вызовы (общий секрет) ──────────────────────────────

def _require_bot_secret(x_bot_secret: str = Header(default="")) -> None:
    if not settings.bot_api_secret or x_bot_secret != settings.bot_api_secret:
        raise HTTPException(status_code=403, detail="bot secret mismatch")


class LinkRequest(BaseModel):
    code: str
    telegram_id: int
    telegram_username: str = ""


class LinkResult(BaseModel):
    email: str
    can_calculate: bool


@router.post("/link", response_model=LinkResult, dependencies=[Depends(_require_bot_secret)])
def link_telegram(body: LinkRequest, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(body.code, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=400, detail="Код недействителен или истёк")
    if payload.get("purpose") != "tg_link":
        raise HTTPException(status_code=400, detail="Неверный код привязки")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Отвязать этот telegram_id от прежнего владельца, если был
    prev = db.query(User).filter(
        User.telegram_id == body.telegram_id, User.id != user.id
    ).first()
    if prev:
        prev.telegram_id = None
        prev.telegram_username = None

    user.telegram_id = body.telegram_id
    user.telegram_username = body.telegram_username or None
    db.commit()
    return LinkResult(email=user.email, can_calculate=user.can_calculate or user.role == "admin")


class ResolveRequest(BaseModel):
    telegram_id: int


class ResolveResult(BaseModel):
    access_token: str
    email: str
    can_calculate: bool
    is_active: bool


@router.post("/resolve", response_model=ResolveResult, dependencies=[Depends(_require_bot_secret)])
def resolve_telegram(body: ResolveRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.telegram_id == body.telegram_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Telegram не привязан")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Учётная запись заблокирована")
    return ResolveResult(
        access_token=create_token(user.id),
        email=user.email,
        can_calculate=user.can_calculate or user.role == "admin",
        is_active=user.is_active,
    )
