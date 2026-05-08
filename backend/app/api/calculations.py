import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_calculate
from app.database import get_db
from app.models import Calculation, Project, User
from app.schemas import CalculationOut
from app.services.document_parser import parse_project_files
from app.services.entity_extractor import extract_entities

router = APIRouter(prefix="/projects/{project_id}/calculations", tags=["calculations"])


@router.post("", response_model=CalculationOut, status_code=201)
def start_calculation(
    project_id: int,
    current_user: User = Depends(require_calculate),
    db: Session = Depends(get_db),
):
    project = _get_own_project(project_id, current_user.id, db)
    if not project.files:
        raise HTTPException(status_code=422, detail="Загрузите хотя бы один файл ТЗ")

    calc = Calculation(project_id=project.id)
    db.add(calc)
    project.status = "processing"
    db.commit()
    db.refresh(calc)
    return calc


@router.get("/{calc_id}/stream")
async def stream_extraction(
    project_id: int,
    calc_id: int,
    token: str | None = None,
    db: Session = Depends(get_db),
):
    from jose import JWTError, jwt as jose_jwt
    from app.config import settings as s
    try:
        payload = jose_jwt.decode(token or "", s.jwt_secret, algorithms=[s.jwt_algorithm])
        user_id = int(payload.get("sub"))
    except JWTError:
        raise HTTPException(status_code=401, detail="Неверный токен")
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or (not current_user.can_calculate and current_user.role != "admin"):
        raise HTTPException(status_code=403, detail="Нет доступа к расчётам")

    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(Calculation.id == calc_id, Calculation.project_id == project.id).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            yield _sse("progress", {"step": 1, "total": 3, "message": "Извлечение текста из файлов…"})
            await asyncio.sleep(0.1)

            combined_text = parse_project_files([f.file_path for f in project.files])

            yield _sse("progress", {"step": 2, "total": 3, "message": "AI-анализ технического задания…"})

            result = await extract_entities(combined_text)

            calc.extracted_entities = result.model_dump()
            db.query(Calculation).filter(Calculation.id == calc_id).update(
                {"extracted_entities": result.model_dump()}
            )
            db.query(Project).filter(Project.id == project.id).update({"status": "extracted"})
            db.commit()

            yield _sse("progress", {"step": 3, "total": 3, "message": "Готово"})
            yield _sse("done", {"calc_id": calc_id})

        except Exception as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{calc_id}", response_model=CalculationOut)
def get_calculation(
    project_id: int,
    calc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(Calculation.id == calc_id, Calculation.project_id == project.id).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")
    return calc


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _get_own_project(project_id: int, user_id: int, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return project
