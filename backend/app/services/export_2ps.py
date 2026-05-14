"""Generate Форма 2ПС ИР Excel from a calculation result dict."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


_THIN = Side(style="thin")
_MED  = Side(style="medium")

def _border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN) -> Border:
    return Border(left=left, right=right, top=top, bottom=bottom)

# Pre-built border presets
_B_ALL      = _border()
_B_ALL_MED  = _border(_MED, _MED, _MED, _MED)
_B_TOP_MED  = _border(top=_MED)          # used for first data row
_B_BOT_MED  = _border(bottom=_MED)       # used for last data row
_B_LR_MED   = _border(left=_MED, right=_MED)   # inner data rows (thick sides)

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

# A=№, B=Наименование, C=Ед.изм, D=Кол-во, E=Обоснование, F=Расчёт, G=Стоимость
_COL_WIDTHS = [6, 38, 14, 10, 55, 28, 20]

_RUB_FMT  = '# ##0.00'
_COEF_FMT = '0.00##'


def _set(ws, row: int, col: int, value, font=None, align=None, border=None, fill=None, fmt=None):
    cell = ws.cell(row=row, column=col, value=value)
    if font:   cell.font        = font
    if align:  cell.alignment   = align
    if border: cell.border      = border
    if fill:   cell.fill        = fill
    if fmt:    cell.number_format = fmt
    return cell


def generate_2ps_excel(project_name: str, stage: str, result: dict[str, Any]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Смета №1"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage   = True
    ws.print_area = "A1:G200"

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

    # "Вид работ" from entity names — more descriptive than project filename
    pos_names = list(dict.fromkeys(p["name"] for p in result.get("positions", []) if p.get("name")))
    work_description = "; ".join(pos_names) if pos_names else project_name

    info_rows = [
        ("Наименование предприятия,\nздания, сооружения",              ""),
        ("Стадия проектирования",                                       stage),
        ("Вид проектных или\nизыскательских работ",                     work_description),
        ("Наименование проектной\n(изыскательской) организации",        ""),
        ("Наименование организации\nзаказчика",                         ""),
        ("Сметный расчет составлен по\nследующим документам",           docs_text),
    ]
    for label, value in info_rows:
        ws.merge_cells(f"A{r}:B{r}")
        _set(ws, r, 1, label,  font=_MAIN, align=_AWL, border=_B_ALL)
        ws.merge_cells(f"C{r}:G{r}")
        _set(ws, r, 3, value,  font=_MAIN, align=_AWL, border=_B_ALL)
        ws.row_dimensions[r].height = 30
        r += 1

    # ── Table header (medium outer border) ────────────────────────────────
    col_headers = [
        "№ п/п", "Наименование работ и затрат", "Единица\nизмерения",
        "Кол-во", "Обоснование стоимости", "Расчет стоимости", "Стоимость работ, руб.",
    ]
    n_cols = len(col_headers)
    for col, h in enumerate(col_headers, 1):
        left  = _MED if col == 1       else _THIN
        right = _MED if col == n_cols  else _THIN
        b = _border(left=left, right=right, top=_MED, bottom=_THIN)
        _set(ws, r, col, h, font=_BOLD, align=_AC, border=b, fill=_FILL_HEADER)
    ws.row_dimensions[r].height = 32
    r += 1

    # Number row (1-7)
    for col in range(1, n_cols + 1):
        left  = _MED if col == 1      else _THIN
        right = _MED if col == n_cols else _THIN
        b = _border(left=left, right=right, top=_THIN, bottom=_MED)
        _set(ws, r, col, col, font=_SMALL, align=_AC, border=b, fill=_FILL_HEADER)
    ws.row_dimensions[r].height = 14
    r += 1

    # ── Positions ──────────────────────────────────────────────────────────
    positions = result.get("positions", [])
    for pi, pos in enumerate(positions):
        is_last = (pi == len(positions) - 1)
        bot = _MED if is_last else _THIN

        def pb(col):
            left  = _MED if col == 1      else _THIN
            right = _MED if col == n_cols else _THIN
            return _border(left=left, right=right, top=_THIN, bottom=bot)

        _set(ws, r, 1, pos["num"],           font=_MAIN,  align=_AC,  border=pb(1))
        _set(ws, r, 2, pos["name"],          font=_MAIN,  align=_AWL, border=pb(2))
        _set(ws, r, 3, pos["unit"],          font=_SMALL, align=_AC,  border=pb(3))
        _set(ws, r, 4, pos["quantity"],      font=_MAIN,  align=_AR,  border=pb(4), fmt=_COEF_FMT)
        _set(ws, r, 5, pos["justification"], font=_SMALL, align=_AWL, border=pb(5))
        _set(ws, r, 6, pos["formula"],       font=_SMALL, align=_AWL, border=pb(6))
        _set(ws, r, 7, pos["cost"],          font=_BOLD,  align=_AR,  border=pb(7), fmt=_RUB_FMT)
        ws.row_dimensions[r].height = 48
        r += 1

    # ── Summary rows ───────────────────────────────────────────────────────
    def _sum_row(label: str, value, bold: bool = False, fill=None, last: bool = False):
        nonlocal r
        bot = _MED if last else _THIN
        ws.merge_cells(f"A{r}:F{r}")
        lc = ws[f"A{r}"]
        lc.value     = label
        lc.font      = _BOLD if bold else _MAIN
        lc.alignment = _AL
        lc.border    = _border(left=_MED, right=_THIN, top=_THIN, bottom=bot)
        if fill: lc.fill = fill
        vc = ws.cell(row=r, column=7, value=value)
        vc.font      = _BOLD if bold else _MAIN
        vc.alignment = _AR
        vc.border    = _border(left=_THIN, right=_MED, top=_THIN, bottom=bot)
        if fill:  vc.fill = fill
        if isinstance(value, (int, float)):
            vc.number_format = _RUB_FMT if (bold or "НДС" in label or "ИТОГО" in label) else _COEF_FMT
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
        book_code = book_refs[0] if book_refs else "СБЦП 81-2001-17"
        _sum_row(f"Доля стоимости основных проектных работ, стадия {stage} ({book_code}, п.1.7)", sf)
        _sum_row(f"Итого с долей стоимости проектирования К={sf}",
                 result["cost_with_stage"], bold=True, fill=_FILL_TOTAL)

    vat = result.get("vat_rate", 22)
    _sum_row(f"НДС {vat:.0f}%", result["vat_amount"])
    _sum_row("ИТОГО с НДС", result["total_with_vat"], bold=True, fill=_FILL_TOTAL, last=True)

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
