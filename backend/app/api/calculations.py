import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_calculate
from app.api.utils import sse as _sse
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
    model: str | None = None,
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

    # Eagerly load everything before the generator — session closes when streaming starts
    file_paths = [f.file_path for f in project.files]
    project_db_id = project.id
    calc_db_id = calc.id
    openrouter_model = model  # capture for closure

    async def event_stream() -> AsyncGenerator[str, None]:
        from app.database import SessionLocal
        try:
            yield _sse("progress", {"step": 1, "total": 3, "message": "Извлечение текста из файлов…"})
            await asyncio.sleep(0.1)

            combined_text = parse_project_files(file_paths)

            provider_label = f"OpenRouter ({openrouter_model})" if openrouter_model else "Claude claude-sonnet-4-6"
            yield _sse("progress", {"step": 2, "total": 3, "message": f"AI-анализ технического задания… ({provider_label})"})

            with SessionLocal() as new_db:
                if openrouter_model:
                    from app.services.entity_extractor import extract_entities_openrouter
                    result = await extract_entities_openrouter(combined_text, openrouter_model, db=new_db)
                else:
                    result = await extract_entities(combined_text, db=new_db)

            with SessionLocal() as new_db:
                new_db.query(Calculation).filter(Calculation.id == calc_db_id).update(
                    {"extracted_entities": result.model_dump()}
                )
                new_db.query(Project).filter(Project.id == project_db_id).update({"status": "extracted"})
                new_db.commit()

            yield _sse("progress", {"step": 3, "total": 3, "message": "Готово"})
            yield _sse("done", {"calc_id": calc_db_id})

        except Exception as exc:
            import traceback
            traceback.print_exc()
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{calc_id}/compute")
def compute_calculation(
    project_id: int,
    calc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.calculator import calculate
    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(Calculation.id == calc_id, Calculation.project_id == project.id).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")
    if not calc.extracted_entities:
        raise HTTPException(status_code=422, detail="Сначала запустите извлечение сущностей")
    result = calculate(calc.extracted_entities, db)
    calc.price_index_id = result.pop("_price_index_id", None)
    calc.calculation_result = result
    db.commit()
    return result


@router.get("/{calc_id}/unit-check")
def unit_check(
    project_id: int,
    calc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.calculator import _find_active_book, _match_row
    from app.models import ReferenceRow

    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(Calculation.id == calc_id, Calculation.project_id == project.id).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")
    if not calc.extracted_entities:
        return []

    entities = calc.extracted_entities.get("entities", [])
    results = []

    for i, entity in enumerate(entities):
        x_value        = float(entity.get("x_value") or 0.0)
        x_unit         = entity.get("x_unit", "")
        table_num      = entity.get("sbts_table")
        sbts_code      = entity.get("sbts_code", "")
        object_type_id = entity.get("sbts_object_type_id")

        if not table_num:
            results.append({"index": i, "ok": False, "note": "таблица не определена"})
            continue

        book = _find_active_book(db, sbts_code)
        if not book:
            results.append({"index": i, "ok": False, "note": f"справочник «{sbts_code}» не найден"})
            continue

        match = _match_row(db, book.id, table_num, x_value, x_unit, object_type_id)
        if match:
            results.append({
                "index": i,
                "ok": True,
                "x_effective": match.x_effective,
                "x_unit_table": match.row.x_unit or x_unit,
                "note": match.note,
                "extrapolated": match.extrapolated,
            })
        else:
            table_units = list({
                r.x_unit for r in db.query(ReferenceRow)
                .filter(ReferenceRow.book_version_id == book.id, ReferenceRow.table_num == table_num)
                .all() if r.x_unit
            })
            results.append({
                "index": i,
                "ok": False,
                "note": f"нет конверсии «{x_unit}» → {', '.join(table_units) or '?'}",
            })

    return results


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


def _get_own_project(project_id: int, user_id: int, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return project
