import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, calculations, projects, admin_users, admin_references, admin_indices, admin_asutp
from app.api.auth import hash_password
from app.config import settings
from app.database import engine
from app.models import Base, User

_or_cache: dict = {"models": [], "fetched_at": 0.0}


def _ensure_admin() -> None:
    from sqlalchemy.orm import Session
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        if not db.query(User).filter(User.email == settings.admin_email).first():
            admin = User(
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
                role="admin",
                can_calculate=True,
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.uploads_dir, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _ensure_admin()
    yield


app = FastAPI(title="ИБ Калькулятор ПИР", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(calculations.router)
app.include_router(admin_users.router)
app.include_router(admin_users.settings_router)
app.include_router(admin_references.router)
app.include_router(admin_indices.router)
app.include_router(admin_asutp.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/openrouter/models")
async def openrouter_models():
    if not settings.openrouter_api_key:
        return []
    if time.time() - _or_cache["fetched_at"] < 3600 and _or_cache["models"]:
        return _or_cache["models"]

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://openrouter.ai/api/v1/models?supported_parameters=tools",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        )

    all_models = resp.json().get("data", [])
    filtered = [
        {
            "id": m["id"],
            "name": m.get("name", m["id"]),
            "context_length": m.get("context_length"),
            "pricing": m.get("pricing", {}),
        }
        for m in all_models
    ]
    filtered.sort(key=lambda m: m["name"])
    _or_cache["models"] = filtered
    _or_cache["fetched_at"] = time.time()
    return filtered
