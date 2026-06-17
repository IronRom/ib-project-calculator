import asyncio
import urllib.parse
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
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


@router.patch("/{calc_id}/entities/{entity_idx}")
def patch_entity_x_value(
    project_id: int,
    calc_id: int,
    entity_idx: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Patch x_value (and optionally x_unit) of a single entity by index."""
    from sqlalchemy.orm.attributes import flag_modified
    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(Calculation.id == calc_id, Calculation.project_id == project.id).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")
    entities = (calc.extracted_entities or {}).get("entities", [])
    if entity_idx < 0 or entity_idx >= len(entities):
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    entity = entities[entity_idx]
    if "x_value" in body:
        entity["x_value"] = float(body["x_value"]) if body["x_value"] is not None else None
    if "x_unit" in body:
        entity["x_unit"] = body["x_unit"]
    if "deleted" in body:
        entity["deleted"] = bool(body["deleted"])
    # clear missing reason once manually set
    if "x_value" in body and body["x_value"] is not None:
        entity["x_value_missing_reason"] = None
    flag_modified(calc, "extracted_entities")
    db.commit()
    return entity


@router.get("/{calc_id}/igi/book-rows")
def list_igi_book_rows(
    project_id: int,
    calc_id: int,
    book_code: str = "НЗ-2025-МС281-ИГИ",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all object types + rows for the given НЗ ИГИ book.

    Used by the frontend to build work item pickers.
    Response: list of { object_type_id, object_type_name, table_num, rows: [...] }
    """
    from app.models import BookObjectType, ReferenceBook, ReferenceRow

    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(
        Calculation.id == calc_id, Calculation.project_id == project.id
    ).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")

    book = db.query(ReferenceBook).filter(
        ReferenceBook.code == book_code,
        ReferenceBook.is_active == True,
    ).first()
    if not book:
        raise HTTPException(status_code=404, detail=f"Справочник {book_code} не найден")

    otypes = db.query(BookObjectType).filter(
        BookObjectType.book_version_id == book.id
    ).order_by(BookObjectType.table_num).all()

    # Fetch all rows for this book in one query
    all_rows = db.query(ReferenceRow).filter(
        ReferenceRow.book_version_id == book.id,
    ).order_by(ReferenceRow.table_num, ReferenceRow.row_num).all()

    # Group by object_type_id using a plain dict
    rows_by_ot: dict = {}
    for row in all_rows:
        rows_by_ot.setdefault(row.object_type_id, []).append(row)

    result = []
    for ot in otypes:
        rows = rows_by_ot.get(ot.id, [])
        result.append({
            "object_type_id": ot.id,
            "object_type_name": ot.name,
            "table_num": ot.table_num,
            "rows": [
                {
                    "id": r.id,
                    "row_num": r.row_num,
                    "description": r.description,
                    "x_unit": r.x_unit,
                    "x_min": float(r.x_min) if r.x_min is not None else None,
                    "x_max": float(r.x_max) if r.x_max is not None else None,
                    "b": float(r.b) if r.b is not None else 0.0,
                }
                for r in rows
            ],
        })

    return {"book_id": book.id, "book_code": book.code, "object_types": result}


@router.patch("/{calc_id}/geological-surveys")
def patch_geological_surveys(
    project_id: int,
    calc_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Replace geological_surveys in extracted_entities and re-run compute.

    Body: { "geological_surveys": [ <GeologicalSurvey>, ... ] }
    Returns updated calculation result.
    """
    from sqlalchemy.orm.attributes import flag_modified
    from app.services.calculator import calculate

    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(
        Calculation.id == calc_id, Calculation.project_id == project.id
    ).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")

    surveys = body.get("geological_surveys", [])

    # Ensure extracted_entities exists
    if not calc.extracted_entities:
        calc.extracted_entities = {"entities": [], "stage": "П+Р", "geological_surveys": []}

    calc.extracted_entities["geological_surveys"] = surveys
    flag_modified(calc, "extracted_entities")

    # Recompute
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
        _x_raw         = entity.get("x_value")
        x_value        = float(_x_raw) if _x_raw is not None else None
        x_unit         = entity.get("x_unit") or ""
        table_num      = entity.get("sbts_table")
        sbts_code      = entity.get("sbts_code") or ""
        object_type_id = entity.get("sbts_object_type_id")

        # ASUTP uses factor method — no table, skip unit check
        if entity.get("asutp_factors"):
            results.append({"index": i, "ok": True, "note": "АСУТП (факторный метод)"})
            continue

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


@router.get("/{calc_id}/export")
def export_2ps(
    project_id: int,
    calc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.export_2ps import generate_2ps_excel
    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(Calculation.id == calc_id, Calculation.project_id == project.id).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")
    if not calc.calculation_result:
        raise HTTPException(status_code=422, detail="Сначала выполните расчёт")

    result = calc.calculation_result
    stage  = (calc.extracted_entities or {}).get("stage", "П+Р")
    xlsx   = generate_2ps_excel(project.name, stage, result)

    safe_name = urllib.parse.quote(f"2ПС_ИР_{project.name}.xlsx")
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )


@router.post("/{calc_id}/correct-and-compute")
def correct_and_compute(
    project_id: int,
    calc_id: int,
    body: dict,
    current_user: User = Depends(require_calculate),
    db: Session = Depends(get_db),
):
    """Apply AI-based correction to entities, then recalculate.

    Body: {"correction_text": "...user instructions..."}
    """
    from sqlalchemy.orm.attributes import flag_modified
    from app.services.calculator import calculate
    from app.config import settings
    import anthropic
    import json

    correction_text = (body.get("correction_text") or "").strip()
    if not correction_text:
        raise HTTPException(status_code=422, detail="correction_text обязателен")

    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(
        Calculation.id == calc_id, Calculation.project_id == project.id
    ).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")
    if not calc.extracted_entities:
        raise HTTPException(status_code=422, detail="Сначала запустите извлечение сущностей")

    entities = (calc.extracted_entities or {}).get("entities", [])
    entities_json = json.dumps(entities, ensure_ascii=False, indent=2)

    # Build calc summary for context
    calc_summary = ""
    if calc.calculation_result:
        positions = calc.calculation_result.get("positions", [])
        errors = calc.calculation_result.get("errors", [])
        lines = []
        for p in positions:
            lines.append(f"  #{p.get('num')} {p.get('name')}: {p.get('cost', 0):,.0f} руб. (обосн: {p.get('justification','')})")
        if errors:
            lines.append("Ошибки: " + "; ".join(errors))
        calc_summary = "\n".join(lines)

    prompt = f"""Ты опытный сметчик ПИР. Пользователь хочет скорректировать список позиций.

ТЕКУЩИЕ ПОЗИЦИИ (JSON):
{entities_json}

РЕЗУЛЬТАТ ПОСЛЕДНЕГО РАСЧЁТА:
{calc_summary or "расчёт ещё не выполнялся"}

КОММЕНТАРИЙ ПОЛЬЗОВАТЕЛЯ:
{correction_text}

ЗАДАЧА: Скорректируй список позиций согласно комментарию пользователя.
Можно изменять: x_value, x_unit, asutp_factors, asutp_k, coefficients, section_num, section_name, quantity, deleted.
НЕ изменяй: category, sbts_code, sbts_table, object_type (если только пользователь не просит).

Верни ТОЛЬКО валидный JSON массив позиций (тот же формат, что и входной список entities).
Никаких пояснений — только JSON."""

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = msg.content[0].text.strip()

    # Extract JSON from response
    import re
    json_match = re.search(r'\[[\s\S]+\]', response_text)
    if not json_match:
        raise HTTPException(status_code=422, detail="AI не вернул корректный JSON список позиций")

    try:
        corrected_entities = json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Ошибка парсинга JSON от AI: {e}")

    # Save corrected entities
    calc.extracted_entities["entities"] = corrected_entities
    flag_modified(calc, "extracted_entities")

    # Recalculate
    result = calculate(calc.extracted_entities, db)
    calc.price_index_id = result.pop("_price_index_id", None)
    calc.calculation_result = result
    db.commit()
    return result


@router.get("/{calc_id}/export-kp")
def export_kp(
    project_id: int,
    calc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.kp_generator import generate_kp_word
    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(
        Calculation.id == calc_id, Calculation.project_id == project.id
    ).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")
    if not calc.calculation_result:
        raise HTTPException(status_code=422, detail="Сначала выполните расчёт")

    entities = calc.extracted_entities or {}
    stage = entities.get("stage", "П+Р")
    tz_object_name = entities.get("tz_object_name", "")
    docx_bytes = generate_kp_word(
        project_name=project.name,
        stage=stage,
        result=calc.calculation_result,
        tz_object_name=tz_object_name,
    )

    safe_name = urllib.parse.quote(f"КП_{project.name}.docx")
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )


@router.get("/{calc_id}/export-kp-pdf")
def export_kp_pdf(
    project_id: int,
    calc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.kp_generator import generate_kp_pdf
    project = _get_own_project(project_id, current_user.id, db)
    calc = db.query(Calculation).filter(
        Calculation.id == calc_id, Calculation.project_id == project.id
    ).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")
    if not calc.calculation_result:
        raise HTTPException(status_code=422, detail="Сначала выполните расчёт")

    entities = calc.extracted_entities or {}
    stage = entities.get("stage", "П+Р")
    tz_object_name = entities.get("tz_object_name", "")
    pdf_bytes = generate_kp_pdf(
        project_name=project.name,
        stage=stage,
        result=calc.calculation_result,
        tz_object_name=tz_object_name,
    )

    safe_name = urllib.parse.quote(f"КП_{project.name}.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )


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
