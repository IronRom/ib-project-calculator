import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, calculations, projects, admin_users, admin_references, admin_indices
from app.config import settings
from app.database import engine
from app.models import Base, User
from app.api.auth import hash_password

app = FastAPI(title="ИБ Калькулятор ПИР", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(calculations.router)
app.include_router(admin_users.router)
app.include_router(admin_references.router)
app.include_router(admin_indices.router)


@app.on_event("startup")
def startup():
    os.makedirs(settings.uploads_dir, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _ensure_admin()


def _ensure_admin():
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


@app.get("/health")
def health():
    return {"status": "ok"}
