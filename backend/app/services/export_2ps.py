"""Generate Форма 2ПС ИР Excel from a calculation result dict."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


_THIN = Side(style="thin")
_ALL  = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_LRB  = Border(left=_THIN, right=_THIN, bottom=_THIN)  # summary rows (no top)
_LR   = Border(left=_THIN, right=_THIN)

_MAIN  = Font(name="Times New Roman", size=10)
_BOLD  = Font(name="Times New Roman", size=10, bold=True)
_SMALL = Font(name="Times New Roman", size=9)
_H1    = Font(name="Times New Roman", size=12, bold=True)

_FILL_HEADER = PatternFill(fill_type="solid", fgColor="D9D9D9")
_FILL_TOTAL  = PatternFill(fill_type="solid", fgColor="F2F2F2")

_AC  = Alignment(horizontal="center", vertical="center", wrap_text=True)
_AR  = Alignment(horizontal="right",  vertical="center")
_AWL = Alignment(horizontal="left",   vertical="top",    wrap_text=True)
_AL  = Alignment(horizontal="left",   vertical="center", wrap_text=True)

_COL_WIDTHS = [6, 38, 14, 10, 58, 28, 18]

_RUB_FMT = '# ##0.00'


def _set(ws, row: int, col: int, value, font=None, align=None, border=None, fill=None, fmt=None):
    cell = ws.cell(row=row, column=col, value=value)
    if font:   cell.font   = font
    if align:  cell.alignment = align
    if border: cell.border = border
    if fill:   cell.fill   = fill
    if fmt:    cell.number_format = fmt
    return cell


def generate_2ps_excel(project_name: str, stage: str, result: dict[str, Any]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Смета №1"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage   = True

    for i, w in enumerate(_COL_WIDTHS, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    year = datetime.now().year
    r = 1

    # ── Row 1: Приложение + Форма ──────────────────────────────────────────
    ws.merge_cells(f"A{r}:E{r}")
    _set(ws, r, 1,
         f"Приложение № 1  к договору №_____ от __.__.{year} г.",
         font=_MAIN, align=_AL)
    ws.merge_cells(f"F{r}:G{r}")
    _set(ws, r, 6, "Форма 2ПС ИР",
         font=_BOLD, align=Alignment(horizontal="right", vertical="center"))
    ws.row_dimensions[r].height = 18
    r += 1

    # ── Row 2: Title ───────────────────────────────────────────────────────
    ws.merge_cells(f"A{r}:G{r}")
    _set(ws, r, 1, "Смета № 1", font=_H1, align=_AC)
    ws.row_dimensions[r].height = 22
    r += 1

    # ── Header info block ─────────────────────────────────────────────────
    book_refs = list(dict.fromkeys(
        p["book_code"] for p in result.get("positions", []) if p.get("book_code")
    ))
    docs_text = (
        "Методические указания по применению справочников базовых цен на проектные "
        "работы в строительстве (приказ Минрегиона России №620 от 29 декабря 2009 г.)"
        + ("; " + "; ".join(f"Справочник базовых цен {c}" for c in book_refs) if book_refs else "")
    )

    info_rows = [
        ("Наименование предприятия,\nздания, сооружения", project_name),
        ("Стадия проектирования",                          stage),
        ("Вид проектных или\nизыскательских работ",        project_name),
        ("Наименование проектной\n(изыскательской) организации", ""),
        ("Наименование организации\nзаказчика",            ""),
        ("Сметный расчет составлен по\nследующим документам", docs_text),
    ]
    for label, value in info_rows:
        ws.merge_cells(f"A{r}:B{r}")
        _set(ws, r, 1, label,  font=_MAIN, align=_AWL, border=_ALL)
        ws.merge_cells(f"C{r}:G{r}")
        _set(ws, r, 3, value,  font=_MAIN, align=_AWL, border=_ALL)
        ws.row_dimensions[r].height = 30
        r += 1

    # ── Table header ───────────────────────────────────────────────────────
    col_headers = [
        "№ п/п", "Наименование работ и затрат", "Единица\nизмерения",
        "Кол-во", "Обоснование стоимости", "Расчет стоимости", "Стоимость работ, руб.",
    ]
    for col, h in enumerate(col_headers, 1):
        _set(ws, r, col, h, font=_BOLD, align=_AC, border=_ALL, fill=_FILL_HEADER)
    ws.row_dimensions[r].height = 32
    r += 1
    for col in range(1, 8):
        _set(ws, r, col, col, font=_SMALL, align=_AC, border=_ALL, fill=_FILL_HEADER)
    ws.row_dimensions[r].height = 14
    r += 1

    # ── Positions ──────────────────────────────────────────────────────────
    for pos in result.get("positions", []):
        _set(ws, r, 1, pos["num"],      font=_MAIN,  align=_AC,  border=_ALL)
        _set(ws, r, 2, pos["name"],     font=_MAIN,  align=_AWL, border=_ALL)
        _set(ws, r, 3, pos["unit"],     font=_SMALL, align=_AC,  border=_ALL)
        _set(ws, r, 4, pos["quantity"], font=_MAIN,  align=_AR,  border=_ALL, fmt='0.00##')
        _set(ws, r, 5, pos["justification"], font=_SMALL, align=_AWL, border=_ALL)
        _set(ws, r, 6, pos["formula"],  font=_SMALL, align=_AWL, border=_ALL)
        _set(ws, r, 7, pos["cost"],     font=_BOLD,  align=_AR,  border=_ALL, fmt=_RUB_FMT)
        ws.row_dimensions[r].height = 48
        r += 1

    # ── Summary rows ───────────────────────────────────────────────────────
    def _sum_row(label: str, value, bold: bool = False, fill=None):
        nonlocal r
        ws.merge_cells(f"A{r}:F{r}")
        lc = ws[f"A{r}"]
        lc.value  = label
        lc.font   = _BOLD if bold else _MAIN
        lc.alignment = _AL
        lc.border = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
        if fill: lc.fill = fill
        vc = ws.cell(row=r, column=7, value=value)
        vc.font   = _BOLD if bold else _MAIN
        vc.alignment = _AR
        vc.border = _ALL
        if fill:  vc.fill = fill
        if isinstance(value, (int, float)):
            vc.number_format = _RUB_FMT if bold or "НДС" in label else '0.00##'
        ws.row_dimensions[r].height = 18
        r += 1

    _sum_row("Базовая стоимость основных проектных работ (МУ №620 п.2.1.1)",
             result["base_cost"], bold=True, fill=_FILL_TOTAL)

    idx_label = f"Коэффициент пересчета базовой стоимости на {result.get('price_index_period', '—')}"
    if result.get("price_index_justification"):
        idx_label += f" ({result['price_index_justification']})"
    _sum_row(idx_label, result["price_index"])

    _sum_row("Текущая стоимость основных проектных работ (МУ №620 п.2.2.3)",
             result["current_cost"], bold=True, fill=_FILL_TOTAL)

    sf = result.get("stage_factor", 1.0)
    if sf != 1.0:
        _sum_row(
            f"Доля стоимости основных проектных работ, стадия {stage} (СБЦП п.1.7)",
            sf,
        )
        _sum_row(
            f"Итого с долей стоимости проектирования К={sf}",
            result["cost_with_stage"], bold=True, fill=_FILL_TOTAL,
        )

    vat = result.get("vat_rate", 22)
    _sum_row(f"НДС {vat:.0f}%", result["vat_amount"])
    _sum_row("ИТОГО с НДС", result["total_with_vat"], bold=True, fill=_FILL_TOTAL)

    # ── Signatures ─────────────────────────────────────────────────────────
    r += 1
    ws.merge_cells(f"A{r}:C{r}")
    _set(ws, r, 1, "Подрядчик:", font=_MAIN, align=_AL)
    ws.merge_cells(f"E{r}:G{r}")
    _set(ws, r, 5, "Заказчик:",  font=_MAIN, align=_AL)
    ws.row_dimensions[r].height = 16
    r += 1
    ws.merge_cells(f"A{r}:C{r}")
    _set(ws, r, 1, "Генеральный директор", font=_MAIN, align=_AL)
    ws.merge_cells(f"E{r}:G{r}")
    _set(ws, r, 5, "Генеральный директор", font=_MAIN, align=_AL)
    ws.row_dimensions[r].height = 16
    r += 1
    ws.merge_cells(f"A{r}:C{r}")
    _set(ws, r, 1, "____________________", font=_MAIN, align=_AL)
    ws.merge_cells(f"E{r}:G{r}")
    _set(ws, r, 5, "____________________", font=_MAIN, align=_AL)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
