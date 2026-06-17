"""Generate ПС / ЛС Excel export matching Форма 1ПС + Форма 2ПС template."""
from __future__ import annotations

import io
from datetime import datetime
from math import floor
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import column_index_from_string, get_column_letter

# ── Styles ────────────────────────────────────────────────────────────────────

_T = Side(style="thin")
_M = Side(style="medium")
_N = Side(style=None)

def _bdr(l=_T, r=_T, t=_T, b=_T): return Border(left=l, right=r, top=t, bottom=b)

_F_MAIN = Font(name="Times New Roman", size=10)
_F_BOLD = Font(name="Times New Roman", size=10, bold=True)
_F_SM   = Font(name="Times New Roman", size=9)
_F_H1   = Font(name="Times New Roman", size=13, bold=True)
_F_H2   = Font(name="Times New Roman", size=11, bold=True)

_FILL_H = PatternFill(fill_type="solid", fgColor="D9D9D9")
_FILL_T = PatternFill(fill_type="solid", fgColor="F2F2F2")

_AC  = Alignment(horizontal="center", vertical="center",  wrap_text=True)
_AL  = Alignment(horizontal="left",   vertical="center",  wrap_text=True)
_AR  = Alignment(horizontal="right",  vertical="center",  wrap_text=False)
_AWT = Alignment(horizontal="left",   vertical="top",     wrap_text=True)

_RUB = '# ##0.00'
_THO = '# ##0.0000'


# ── Core helpers ──────────────────────────────────────────────────────────────

def _v(ws, r, c, value=None, font=None, align=None, fill=None, fmt=None, border=None):
    """Set a single cell."""
    cell = ws.cell(r, c)
    if value  is not None: cell.value        = value
    if font:               cell.font         = font
    if align:              cell.alignment    = align
    if fill:               cell.fill         = fill
    if fmt:                cell.number_format = fmt
    if border:             cell.border       = border
    return cell


def _mv(ws, r, c1, c2, value=None, font=None, align=None, fill=None, fmt=None):
    """
    Merge cells c1..c2 in row r, set value + style, apply proper outer borders.
    - Left  border  on c1
    - Right border  on c2
    - Top + Bottom  on ALL cells c1..c2
    This ensures the merged box has a complete visible border in Excel.
    """
    if c1 < c2:
        ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
    _v(ws, r, c1, value=value, font=font, align=align, fill=fill, fmt=fmt)
    for c in range(c1, c2 + 1):
        l = _T if c == c1 else _N
        rr = _T if c == c2 else _N
        ws.cell(r, c).border = _bdr(l=l, r=rr, t=_T, b=_T)
        if fill and c != c1:
            ws.cell(r, c).fill = fill
    return ws.cell(r, c1)


def _row(r_h, ws, r): ws.row_dimensions[r].height = r_h


# ── Ruble words ───────────────────────────────────────────────────────────────

def _rub_words(amount: float) -> str:
    total   = floor(amount)
    kopecks = round((amount - total) * 100)
    units   = ["","один","два","три","четыре","пять","шесть","семь","восемь","девять",
               "десять","одиннадцать","двенадцать","тринадцать","четырнадцать","пятнадцать",
               "шестнадцать","семнадцать","восемнадцать","девятнадцать"]
    units_f = ["","одна","две","три","четыре","пять","шесть","семь","восемь","девять",
               "десять","одиннадцать","двенадцать","тринадцать","четырнадцать","пятнадцать",
               "шестнадцать","семнадцать","восемнадцать","девятнадцать"]
    tens    = ["","десять","двадцать","тридцать","сорок","пятьдесят",
               "шестьдесят","семьдесят","восемьдесят","девяносто"]
    hunds   = ["","сто","двести","триста","четыреста","пятьсот",
               "шестьсот","семьсот","восемьсот","девятьсот"]

    def _chunk(n, fem=False):
        u = units_f if fem else units
        p = []
        if n // 100: p.append(hunds[n // 100])
        rr = n % 100
        if rr < 20:
            if rr: p.append(u[rr])
        else:
            p.append(tens[rr // 10])
            if rr % 10: p.append(u[rr % 10])
        return " ".join(p)

    def _sfx(n, m1, m24, m5):
        r10, r100 = n % 10, n % 100
        if r10 == 1 and r100 != 11:             return m1
        if 2 <= r10 <= 4 and not 11 <= r100 <= 14: return m24
        return m5

    parts, tmp = [], total
    bn = tmp // 1_000_000_000; tmp %= 1_000_000_000
    mn = tmp // 1_000_000;     tmp %= 1_000_000
    th = tmp // 1_000;          rm = tmp % 1_000

    if bn: parts.append(f"{_chunk(bn)} {_sfx(bn,'миллиард','миллиарда','миллиардов')}")
    if mn: parts.append(f"{_chunk(mn)} {_sfx(mn,'миллион','миллиона','миллионов')}")
    if th: parts.append(f"{_chunk(th,fem=True)} {_sfx(th,'тысяча','тысячи','тысяч')}")
    if rm: parts.append(_chunk(rm))

    w = " ".join(parts) if parts else "ноль"
    return f"{w[0].upper()}{w[1:]} рублей {kopecks:02d} копеек"


# ── ЛС detail sheet ───────────────────────────────────────────────────────────
# 9 columns: A=№, B:E=Наименование, F:G=Ссылка, H=Расчёт, I=Стоимость тыс.руб.

_LS_W = [5, 13, 10, 8, 9, 20, 16, 28, 16]   # A..I


def _write_ls_sheet(ws, ls_num: str, project_name: str, stage: str,
                    section_name: str, positions: list[dict],
                    vat_rate: float, quarter: str):
    ws.page_setup.orientation = "landscape"
    for i, w in enumerate(_LS_W, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    r = 1
    # R1: form reference
    _mv(ws, r, 1, 6, ""); _row(6, ws, r)
    _mv(ws, r, 7, 9, "Приложение №7\nк приказу МС №707/пр\nот 01.09.2021 г.",
        font=_F_SM, align=Alignment(horizontal="right", vertical="center", wrap_text=True))
    _row(42, ws, r); r += 1

    # R2: blank
    _row(6, ws, r); r += 1

    # R3-R4: titles (no border)
    ws.merge_cells(f"A{r}:I{r}")
    _v(ws, r, 1, f"Смета № {ls_num}", font=_F_H1, align=_AC); _row(22, ws, r); r += 1
    ws.merge_cells(f"A{r}:I{r}")
    _v(ws, r, 1, "на проектные работы", font=_F_MAIN, align=_AC); _row(16, ws, r); r += 1
    ws.merge_cells(f"A{r}:I{r}")
    _v(ws, r, 1, section_name or project_name, font=_F_MAIN, align=_AC); _row(18, ws, r); r += 1
    ws.merge_cells(f"A{r}:I{r}")
    _v(ws, r, 1, "(наименование стройки)", font=_F_SM, align=_AC); _row(12, ws, r); r += 1

    # Info rows (bordered)
    for label, val in [
        ("Заказчик",                ""),
        ("Проектная организация",   "ООО «Интеллект-Строй»"),
        ("Составлена в ценах на",   quarter or datetime.now().strftime("%I кв. %Y г.")),
    ]:
        _mv(ws, r, 1, 2, label,  font=_F_MAIN, align=_AL)
        _mv(ws, r, 3, 9, val,    font=_F_MAIN, align=_AL)
        _row(16, ws, r); r += 1

    # Blank
    _row(6, ws, r); r += 1

    # ── Header (2 rows) ───────────────────────────────────────────────────────
    # Row 1
    _mv(ws, r, 1, 1, "№\nп/п",
        font=_F_BOLD, align=_AC, fill=_FILL_H)
    _mv(ws, r, 2, 5, "Наименование объекта проектирования\nили вида работы",
        font=_F_BOLD, align=_AC, fill=_FILL_H)
    _mv(ws, r, 6, 7, "Наименование, номера глав, таблиц,\nпараграфов нормативных документов",
        font=_F_BOLD, align=_AC, fill=_FILL_H)
    _mv(ws, r, 8, 8, "Расчет стоимости",
        font=_F_BOLD, align=_AC, fill=_FILL_H)
    _mv(ws, r, 9, 9, "Сметная стоимость,\nтыс. руб.",
        font=_F_BOLD, align=_AC, fill=_FILL_H)
    _row(42, ws, r); r += 1

    # Row 2: number row
    _mv(ws, r, 1, 1, "1", font=_F_SM, align=_AC, fill=_FILL_H)
    _mv(ws, r, 2, 5, "2", font=_F_SM, align=_AC, fill=_FILL_H)
    _mv(ws, r, 6, 7, "3", font=_F_SM, align=_AC, fill=_FILL_H)
    _mv(ws, r, 8, 8, "4", font=_F_SM, align=_AC, fill=_FILL_H)
    _mv(ws, r, 9, 9, "5", font=_F_SM, align=_AC, fill=_FILL_H)
    _row(14, ws, r); r += 1

    # ── Positions ──────────────────────────────────────────────────────────────
    for pos in positions:
        cost_tys = pos["cost"] / 1000
        _mv(ws, r, 1, 1, pos["num"],          font=_F_MAIN, align=_AC)
        _mv(ws, r, 2, 5, pos["name"],          font=_F_MAIN, align=_AWT)
        _mv(ws, r, 6, 7, pos["justification"], font=_F_SM,   align=_AWT)
        _mv(ws, r, 8, 8, pos["formula"],       font=_F_SM,   align=_AWT)
        _mv(ws, r, 9, 9, cost_tys,             font=_F_BOLD, align=_AR, fmt=_THO)
        _row(52, ws, r); r += 1

    # ── Summary ────────────────────────────────────────────────────────────────
    total_cost     = sum(p["cost"] for p in positions)
    vat_amount     = round(total_cost * vat_rate / 100, 2)
    total_with_vat = round(total_cost + vat_amount, 2)
    c_tys, v_tys, t_tys = total_cost/1000, vat_amount/1000, total_with_vat/1000

    _mv(ws, r, 1, 8, "Итого без учета НДС",
        font=_F_BOLD, align=_AL, fill=_FILL_T)
    _mv(ws, r, 9, 9, c_tys, font=_F_BOLD, align=_AR, fill=_FILL_T, fmt=_THO)
    _row(18, ws, r); r += 1

    _mv(ws, r, 1, 1, "1", font=_F_MAIN, align=_AC)
    _mv(ws, r, 2, 8, "Итого без НДС",  font=_F_MAIN, align=_AL)
    _mv(ws, r, 9, 9, c_tys, font=_F_MAIN, align=_AR, fmt=_THO)
    _row(16, ws, r); r += 1

    _mv(ws, r, 1, 1, "2", font=_F_MAIN, align=_AC)
    _mv(ws, r, 2, 7, "Налог на добавленную стоимость (НДС)", font=_F_MAIN, align=_AL)
    _mv(ws, r, 8, 8, f"{vat_rate:.0f} %", font=_F_MAIN, align=_AC)
    _mv(ws, r, 9, 9, v_tys, font=_F_MAIN, align=_AR, fmt=_THO)
    _row(16, ws, r); r += 1

    _mv(ws, r, 1, 1, "3", font=_F_MAIN, align=_AC)
    _mv(ws, r, 2, 8, "Итого по смете",
        font=_F_BOLD, align=_AL, fill=_FILL_T)
    _mv(ws, r, 9, 9, t_tys, font=_F_BOLD, align=_AR, fill=_FILL_T, fmt=_THO)
    _row(16, ws, r); r += 1

    _row(8, ws, r); r += 1
    ws.merge_cells(f"A{r}:I{r}")
    _v(ws, r, 1, f"Итого по смете: {total_with_vat:,.2f} руб. ({_rub_words(total_with_vat)})",
       font=_F_MAIN, align=_AWT); _row(28, ws, r)


# ── ПС summary sheet ──────────────────────────────────────────────────────────
# 10 columns: A=№, B:C=Перечень, D=Характеристики, E=Ссылка,
#             F:H=Изыскательских, I=Проектных, J=Всего

_PS_W = [5, 22, 8, 20, 12, 9, 9, 9, 15, 15]   # A..J
_PS_N = 10   # total column count


def _write_ps_sheet(ws, project_name: str, stage: str,
                    result: dict, ls_info: list[dict], vat_rate: float):
    ws.page_setup.orientation = "landscape"
    for i, w in enumerate(_PS_W, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    N = _PS_N
    year    = datetime.now().year
    quarter = result.get("price_index_period", "")
    r = 1

    # R1: Приложение + Форма 1ПС
    _mv(ws, r, 1, N-2,
        f"Приложение № 1  к договору №_____ от __.__.{year} г.",
        font=_F_MAIN, align=_AL)
    _mv(ws, r, N-1, N, "Форма 1ПС",
        font=_F_BOLD,
        align=Alignment(horizontal="right", vertical="center"))
    _row(18, ws, r); r += 1

    # R2: blank
    _row(6, ws, r); r += 1

    # R3: Смета ПС (no border)
    ws.merge_cells(f"A{r}:{get_column_letter(N)}{r}")
    _v(ws, r, 1, "Смета ПС", font=_F_H1, align=_AC); _row(24, ws, r); r += 1

    # R4: subtitle
    ws.merge_cells(f"A{r}:{get_column_letter(N)}{r}")
    _v(ws, r, 1, "на проектные (изыскательские) работы",
       font=_F_MAIN, align=_AC); _row(16, ws, r); r += 1

    # R5-8: Info block (full-width borders)
    for label, val, h in [
        ("Наименование строительства",                      project_name,                30),
        ("Стадии проектирования",                           stage,                       18),
        ("Наименование проектной организации - ген. проектировщик",
                                                            "ООО «Интеллект-Строй»",    30),
        ("Составлена в ценах",                              quarter or "—",              18),
    ]:
        _mv(ws, r, 1, 2, label, font=_F_MAIN, align=_AWT)
        _mv(ws, r, 3, N, val,   font=_F_MAIN, align=_AL)
        _row(h, ws, r); r += 1

    # Blank
    _row(6, ws, r); r += 1

    # ── Column header row 1 ───────────────────────────────────────────────────
    _mv(ws, r, 1, 1, "№\nп.п.",                               font=_F_BOLD, align=_AC, fill=_FILL_H)
    _mv(ws, r, 2, 3, "Перечень выполняемых работ",             font=_F_BOLD, align=_AC, fill=_FILL_H)
    _mv(ws, r, 4, 4, "Характеристики\nпроектируемого объекта", font=_F_BOLD, align=_AC, fill=_FILL_H)
    _mv(ws, r, 5, 5, "Ссылка на\n№ сметы",                    font=_F_BOLD, align=_AC, fill=_FILL_H)
    _mv(ws, r, 6, N, "Стоимость работ, тыс. руб.",             font=_F_BOLD, align=_AC, fill=_FILL_H)
    _row(34, ws, r); r += 1

    # ── Column header row 2 ───────────────────────────────────────────────────
    _mv(ws, r, 1, 1, "",              fill=_FILL_H)
    _mv(ws, r, 2, 3, "",              fill=_FILL_H)
    _mv(ws, r, 4, 4, "",              fill=_FILL_H)
    _mv(ws, r, 5, 5, "",              fill=_FILL_H)
    _mv(ws, r, 6, 8, "Изыскательских", font=_F_BOLD, align=_AC, fill=_FILL_H)
    _mv(ws, r, 9, 9, "Проектных",      font=_F_BOLD, align=_AC, fill=_FILL_H)
    _mv(ws, r, N, N, "Всего",          font=_F_BOLD, align=_AC, fill=_FILL_H)
    _row(20, ws, r); r += 1

    # ── Data rows ─────────────────────────────────────────────────────────────
    total_no_vat = sum(ls["cost"] for ls in ls_info)
    vat_amount   = round(total_no_vat * vat_rate / 100, 2)
    grand_total  = round(total_no_vat + vat_amount, 2)

    for i, ls in enumerate(ls_info, 1):
        c_tys = ls["cost"] / 1000
        _mv(ws, r, 1, 1, i,          font=_F_MAIN, align=_AC)
        _mv(ws, r, 2, 3, ls["name"], font=_F_MAIN, align=_AWT)
        _mv(ws, r, 4, 4, "",         font=_F_MAIN, align=_AL)
        _mv(ws, r, 5, 5, ls["sheet"],font=_F_MAIN, align=_AC)
        _mv(ws, r, 6, 8, 0,          font=_F_MAIN, align=_AR, fmt=_THO)
        _mv(ws, r, 9, 9, c_tys,      font=_F_MAIN, align=_AR, fmt=_THO)
        _mv(ws, r, N, N, c_tys,      font=_F_MAIN, align=_AR, fmt=_THO)
        _row(22, ws, r); r += 1

    # ── Итого row ─────────────────────────────────────────────────────────────
    t_tys  = total_no_vat / 1000
    _mv(ws, r, 1, 4, "Итого:",                    font=_F_BOLD, align=_AL, fill=_FILL_T)
    _mv(ws, r, 5, 5, "",                           fill=_FILL_T)
    _mv(ws, r, 6, 8, 0,                            font=_F_BOLD, align=_AR, fill=_FILL_T, fmt=_THO)
    _mv(ws, r, 9, 9, t_tys,                        font=_F_BOLD, align=_AR, fill=_FILL_T, fmt=_THO)
    _mv(ws, r, N, N, t_tys,                        font=_F_BOLD, align=_AR, fill=_FILL_T, fmt=_THO)
    _row(18, ws, r); r += 1

    # Blank
    _row(6, ws, r); r += 1

    # ── НДС summary block ─────────────────────────────────────────────────────
    v_tys = vat_amount / 1000
    g_tys = grand_total / 1000

    # 1: Итого без НДС
    _mv(ws, r, 1, 1, "1",               font=_F_MAIN, align=_AC)
    _mv(ws, r, 2, 8, "Итого без НДС",   font=_F_MAIN, align=_AL)
    _mv(ws, r, 9, 9, t_tys,             font=_F_MAIN, align=_AR, fmt=_THO)
    _mv(ws, r, N, N, t_tys,             font=_F_MAIN, align=_AR, fmt=_THO)
    _row(18, ws, r); r += 1

    # 2: НДС
    _mv(ws, r, 1, 1, "2",               font=_F_MAIN, align=_AC)
    _mv(ws, r, 2, 7, "НДС (НДС)",       font=_F_MAIN, align=_AL)
    _mv(ws, r, 8, 8, f"{vat_rate:.0f}%",font=_F_MAIN, align=_AC)
    _mv(ws, r, 9, 9, v_tys,             font=_F_MAIN, align=_AR, fmt=_THO)
    _mv(ws, r, N, N, v_tys,             font=_F_MAIN, align=_AR, fmt=_THO)
    _row(18, ws, r); r += 1

    # 3: Итого по смете
    _mv(ws, r, 1, 1, "3",               font=_F_MAIN, align=_AC)
    _mv(ws, r, 2, 8, "Итого по смете",  font=_F_BOLD, align=_AL, fill=_FILL_T)
    _mv(ws, r, 9, 9, g_tys,             font=_F_BOLD, align=_AR, fill=_FILL_T, fmt=_THO)
    _mv(ws, r, N, N, g_tys,             font=_F_BOLD, align=_AR, fill=_FILL_T, fmt=_THO)
    _row(18, ws, r); r += 1

    # ── Total text ────────────────────────────────────────────────────────────
    _row(8, ws, r); r += 1
    ws.merge_cells(f"A{r}:{get_column_letter(N)}{r}")
    _v(ws, r, 1,
       f"Итого по смете: {grand_total:,.2f} руб. ({_rub_words(grand_total)})",
       font=_F_MAIN, align=_AWT); _row(32, ws, r); r += 1
    ws.merge_cells(f"A{r}:{get_column_letter(N)}{r}")
    _v(ws, r, 1, "(сумма прописью)", font=_F_SM, align=_AC); _row(14, ws, r); r += 1

    # Signature
    _row(8, ws, r); r += 1
    _mv(ws, r, 1, 4, "Подрядчик: ____________________", font=_F_MAIN, align=_AL)
    _mv(ws, r, 7, N, "Заказчик: ____________________",  font=_F_MAIN, align=_AL)
    _row(22, ws, r)


# ── Entry point ───────────────────────────────────────────────────────────────

def generate_2ps_excel(project_name: str, stage: str, result: dict[str, Any]) -> bytes:
    positions = result.get("positions", [])
    vat_rate  = float(result.get("vat_rate", 22))
    quarter   = result.get("price_index_period", "")

    # Group by section_num
    sections: dict[int, dict] = {}
    for pos in positions:
        snum  = int(pos.get("section_num") or 0)
        sname = pos.get("section_name") or ""
        if snum not in sections:
            sections[snum] = {"name": sname, "positions": []}
        sections[snum]["positions"].append(pos)

    wb = openpyxl.Workbook()
    ls_info: list[dict] = []

    for i, snum in enumerate(sorted(sections.keys()), 1):
        sec          = sections[snum]
        ls_name      = f"ЛС-{i:02d}"
        ws           = wb.create_sheet(title=ls_name)
        sec_positions = sec["positions"]
        sec_cost     = sum(p["cost"] for p in sec_positions)

        _write_ls_sheet(ws, ls_name, project_name, stage,
                        sec["name"] or project_name,
                        sec_positions, vat_rate, quarter)
        ls_info.append({
            "sheet": ls_name,
            "name":  sec["name"] or project_name,
            "cost":  sec_cost,
        })

    ps_ws = wb.create_sheet(title="ПС", index=0)
    _write_ps_sheet(ps_ws, project_name, stage, result, ls_info, vat_rate)

    for name in list(wb.sheetnames):
        if name in ("Sheet", "Лист", "Лист1"):
            del wb[name]

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
