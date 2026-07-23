import asyncio
import urllib.parse
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_calculate
from app.api.utils import sse as _sse
from app.database import get_db
from app.models import Calculation, Project, User
from app.schemas import CalculationOut, GeologicalSurvey as GeologicalSurveySchema
from app.services.document_parser import parse_project_files
from app.services.entity_extractor import extract_entities


class PatchGeologicalSurveysRequest(BaseModel):
    geological_surveys: list[GeologicalSurveySchema] = []

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

    if getattr(calc, "status", "draft") == "final":
        raise HTTPException(status_code=409, detail="Расчёт финализирован — создайте новую версию")

    # Eagerly load everything before the generator — session closes when streaming starts
    file_infos = [(f.id, f.file_path, f.extracted_text) for f in project.files]
    project_db_id = project.id
    calc_db_id = calc.id
    if not model:
        # модель по умолчанию — из настроек (админка админа)
        from app.services.clarify_service import get_setting
        model = get_setting(db, "extraction_model", "qwen/qwen3.7-plus")
    openrouter_model = model  # capture for closure

    async def event_stream() -> AsyncGenerator[str, None]:
        from app.database import SessionLocal
        try:
            yield _sse("progress", {"step": 1, "total": 3, "message": "Извлечение текста из файлов…"})
            await asyncio.sleep(0.1)

            # Кэш распарсенного текста в project_files.extracted_text —
            # vision-OCR сканов дорог и долог, повторять его на каждом
            # прогоне экстракции нельзя.
            from app.models import ProjectFile as _PF
            parts: list[str] = []
            for f_id, f_path, f_cached in file_infos:
                if f_cached and f_cached.strip():
                    parts.append(f_cached)
                    continue
                text = parse_project_files([f_path])
                parts.append(text)
                if text.strip() and not text.startswith("[Ошибка"):
                    with SessionLocal() as cache_db:
                        rec = cache_db.query(_PF).filter(_PF.id == f_id).first()
                        if rec:
                            rec.extracted_text = text
                            cache_db.commit()
            combined_text = "\n\n---\n\n".join(p for p in parts if p.strip())

            provider_label = f"OpenRouter ({openrouter_model})" if openrouter_model else "Claude claude-sonnet-4-6"
            yield _sse("progress", {"step": 2, "total": 3, "message": f"AI-анализ технического задания… ({provider_label})"})

            with SessionLocal() as new_db:
                if openrouter_model:
                    from app.services.entity_extractor import extract_entities_openrouter
                    result = await extract_entities_openrouter(combined_text, openrouter_model, db=new_db)
                else:
                    result = await extract_entities(combined_text, db=new_db)

            with SessionLocal() as new_db:
                # Preserve existing geological_surveys — they are managed separately
                # and ExtractionResult has no geological_surveys field.
                existing_calc = new_db.query(Calculation).filter(
                    Calculation.id == calc_db_id
                ).first()
                existing_surveys = (
                    (existing_calc.extracted_entities or {}).get("geological_surveys", [])
                    if existing_calc else []
                )
                new_ee = result.model_dump()
                new_ee.setdefault("geological_surveys", existing_surveys)
                new_db.query(Calculation).filter(Calculation.id == calc_db_id).update(
                    {"extracted_entities": new_ee}
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
    _ensure_draft(calc)
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
    _ensure_draft(calc)
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
    if "pd_sections_pct" in body:
        v = body["pd_sections_pct"]
        entity["pd_sections_pct"] = float(v) if v is not None else None
    if "rd_sections_pct" in body:
        v = body["rd_sections_pct"]
        entity["rd_sections_pct"] = float(v) if v is not None else None
    # clear missing reason once manually set
    if "x_value" in body and body["x_value"] is not None:
        entity["x_value_missing_reason"] = None
    flag_modified(calc, "extracted_entities")
    db.commit()
    return entity


@router.get("/{calc_id}/igi/books")
def list_survey_books(
    project_id: int,
    calc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Active survey books (изыскания) for the book picker on the geology page."""
    from app.models import ReferenceBook
    from app.services.igi_calculator import _survey_label

    _get_own_project(project_id, current_user.id, db)
    books = (
        db.query(ReferenceBook)
        .filter(ReferenceBook.is_active == True, ReferenceBook.calc_method == "survey")
        .order_by(ReferenceBook.code)
        .all()
    )
    return [
        {"book_id": b.id, "book_code": b.code, "label": _survey_label(b.code)}
        for b in books
    ]


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
            "work_category": ot.work_category or "field",
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
    body: PatchGeologicalSurveysRequest,
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

    _ensure_draft(calc)
    surveys = [s.model_dump() for s in body.geological_surveys]

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
        temperature=0,
        model=settings.extraction_model,
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


# ═══ Жизненный цикл расчёта: версии, уточнения, финализация ═══════════════
# Модель: цепочка версий (parent_id). Черновик (draft) редактируем;
# финал (final) заморожен навсегда, к нему привязаны файлы 2ПС/КП.
# Новая правка после финализации = новая версия от финала.

def _get_calc(project_id: int, calc_id: int, user_id: int, db: Session):
    project = _get_own_project(project_id, user_id, db)
    calc = db.query(Calculation).filter(
        Calculation.id == calc_id, Calculation.project_id == project.id
    ).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Расчёт не найден")
    return project, calc


def _ensure_draft(calc) -> None:
    if getattr(calc, "status", "draft") == "final":
        raise HTTPException(
            status_code=409,
            detail="Расчёт финализирован и неизменяем. Создайте новую версию "
                   "(POST /versions), чтобы вносить правки.",
        )


@router.get("")
def list_calculations(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Список расчётов проекта со статусами, версиями и файлами экспорта."""
    project = _get_own_project(project_id, current_user.id, db)
    calcs = (db.query(Calculation)
             .filter(Calculation.project_id == project.id)
             .order_by(Calculation.id).all())
    out = []
    for c in calcs:
        total = None
        if c.calculation_result:
            total = c.calculation_result.get("total_with_vat")
        out.append({
            "id": c.id,
            "version_num": c.version_num,
            "parent_id": c.parent_id,
            "status": c.status,
            "created_at": c.created_at,
            "finalized_at": c.finalized_at,
            "n_entities": len((c.extracted_entities or {}).get("entities") or []),
            "total_with_vat": total,
            "exports": [{"kind": e.kind, "filename": e.filename, "id": e.id}
                        for e in c.exports],
            "clarifications": [{"id": cl.id, "text": cl.text[:200],
                                "created_at": cl.created_at,
                                "summary": (cl.diff_json or {}).get("summary", "")}
                               for cl in c.clarifications],
        })
    return out


@router.post("/{calc_id}/versions", status_code=201)
def create_version(
    project_id: int,
    calc_id: int,
    current_user: User = Depends(require_calculate),
    db: Session = Depends(get_db),
):
    """Новая версия-черновик на базе существующего расчёта (обычно финала)."""
    _, calc = _get_calc(project_id, calc_id, current_user.id, db)
    new = Calculation(
        project_id=calc.project_id,
        book_version_id=calc.book_version_id,
        price_index_id=calc.price_index_id,
        extracted_entities=calc.extracted_entities,
        calculation_result=calc.calculation_result,
        parent_id=calc.id,
        status="draft",
        version_num=(calc.version_num or 1) + 1,
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return {"id": new.id, "version_num": new.version_num, "parent_id": calc.id}


@router.post("/{calc_id}/clarify")
async def clarify_calculation(
    project_id: int,
    calc_id: int,
    body: dict,
    current_user: User = Depends(require_calculate),
    db: Session = Depends(get_db),
):
    """Уточнение свободным текстом. body: {text, preview?: bool}.

    preview=true — вернуть diff БЕЗ применения (для подтверждения в UI).
    Иначе: применить патч, сохранить уточнение с diff, пересчитать.
    """
    from app.services.calculator import calculate
    from app.services.clarify_service import clarify_entities, get_setting
    from app.models import CalculationClarification
    from sqlalchemy.orm.attributes import flag_modified

    _, calc = _get_calc(project_id, calc_id, current_user.id, db)
    _ensure_draft(calc)
    text = (body.get("text") or "").strip()
    if len(text) < 3:
        raise HTTPException(status_code=422, detail="Пустое уточнение")
    ee = calc.extracted_entities or {}
    entities = ee.get("entities") or []
    if not entities:
        raise HTTPException(status_code=422, detail="Сначала выполните извлечение")

    model_id = get_setting(db, "clarification_model", "qwen/qwen3.7-plus")
    try:
        new_entities, diff = await clarify_entities(entities, text, model_id)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    old_total = (calc.calculation_result or {}).get("total_with_vat")

    if body.get("preview"):
        # посчитать «что будет» на копии, не трогая расчёт
        probe = dict(ee)
        probe["entities"] = new_entities
        result = calculate(probe, db)
        result.pop("_price_index_id", None)
        diff["total_before"] = old_total
        diff["total_after"] = result.get("total_with_vat")
        return {"preview": True, "diff": diff}

    ee["entities"] = new_entities
    calc.extracted_entities = ee
    flag_modified(calc, "extracted_entities")
    result = calculate(ee, db)
    calc.price_index_id = result.pop("_price_index_id", None)
    calc.calculation_result = result
    diff["total_before"] = old_total
    diff["total_after"] = result.get("total_with_vat")
    db.add(CalculationClarification(
        calculation_id=calc.id, text=text, diff_json=diff, model_used=model_id,
    ))
    db.commit()
    return {"preview": False, "diff": diff, "result": result}


@router.post("/{calc_id}/finalize")
def finalize_calculation(
    project_id: int,
    calc_id: int,
    current_user: User = Depends(require_calculate),
    db: Session = Depends(get_db),
):
    """Финализация: свежий пересчёт → генерация 2ПС/КП → заморозка версии."""
    import os
    from app.config import settings as cfg
    from app.services.calculator import calculate
    from app.services.export_2ps import generate_2ps_excel
    from app.services.kp_generator import generate_kp_pdf, generate_kp_word
    from app.models import CalculationExport

    project, calc = _get_calc(project_id, calc_id, current_user.id, db)
    _ensure_draft(calc)
    ee = calc.extracted_entities or {}
    if not (ee.get("entities") or ee.get("geological_surveys")):
        raise HTTPException(status_code=422, detail="Нечего финализировать")

    result = calculate(ee, db)
    calc.price_index_id = result.pop("_price_index_id", None)
    calc.calculation_result = result
    stage = ee.get("stage", "П+Р")
    tz_object_name = ee.get("tz_object_name", "")

    out_dir = os.path.join(cfg.uploads_dir, "exports", str(calc.id))
    os.makedirs(out_dir, exist_ok=True)
    artifacts = [
        ("2ps_xlsx", f"2ПС_ИР_{project.name}_v{calc.version_num}.xlsx",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         lambda: generate_2ps_excel(project.name, stage, result)),
        ("kp_docx", f"КП_{project.name}_v{calc.version_num}.docx",
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         lambda: generate_kp_word(project_name=project.name, stage=stage,
                                  result=result, tz_object_name=tz_object_name)),
        ("kp_pdf", f"КП_{project.name}_v{calc.version_num}.pdf",
         "application/pdf",
         lambda: generate_kp_pdf(project_name=project.name, stage=stage,
                                 result=result, tz_object_name=tz_object_name)),
    ]
    # пере-финализация той же версии невозможна (_ensure_draft), но чистим
    # возможные хвосты от прошлых неудачных попыток
    db.query(CalculationExport).filter(
        CalculationExport.calculation_id == calc.id).delete()
    for kind, filename, _mt, gen in artifacts:
        try:
            content = gen()
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500,
                                detail=f"Генерация {kind} упала: {exc}")
        path = os.path.join(out_dir, filename)
        with open(path, "wb") as f:
            f.write(content)
        db.add(CalculationExport(calculation_id=calc.id, kind=kind,
                                 file_path=path, filename=filename))

    calc.status = "final"
    calc.finalized_at = datetime.utcnow()
    db.commit()
    return {
        "status": "final",
        "finalized_at": calc.finalized_at,
        "total_with_vat": result.get("total_with_vat"),
        "exports": [{"kind": k, "filename": fn} for k, fn, _m, _g in artifacts],
        "warnings": result.get("warnings", []),
    }


@router.get("/{calc_id}/exports/{kind}/download")
def download_export(
    project_id: int,
    calc_id: int,
    kind: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models import CalculationExport
    _, calc = _get_calc(project_id, calc_id, current_user.id, db)
    rec = (db.query(CalculationExport)
           .filter(CalculationExport.calculation_id == calc.id,
                   CalculationExport.kind == kind).first())
    if not rec:
        raise HTTPException(status_code=404, detail="Файл не найден — финализируйте расчёт")
    media = {
        "2ps_xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "kp_docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "kp_pdf": "application/pdf",
    }.get(kind, "application/octet-stream")
    try:
        with open(rec.file_path, "rb") as f:
            content = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=410, detail="Файл экспорта утерян на диске")
    safe = urllib.parse.quote(rec.filename)
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition":
                             f"attachment; filename*=UTF-8''{safe}"})
