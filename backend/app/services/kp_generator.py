"""Generate Коммерческое предложение (КП) Word document."""
from __future__ import annotations

import io
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.oxml import OxmlElement


def _set_cell_border(cell, **kwargs):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for edge in ('top', 'bottom', 'left', 'right'):
        tag = OxmlElement(f'w:{edge}')
        tag.set(qn('w:val'), 'single')
        tag.set(qn('w:sz'), '4')
        tag.set(qn('w:color'), '000000')
        tcBorders.append(tag)
    tcPr.append(tcBorders)


def _fmt(n: float) -> str:
    return f"{n:,.2f}".replace(',', ' ').replace('.', ',')


def generate_kp_word(
    project_name: str,
    stage: str,
    result: dict[str, Any],
    company_name: str = "",
) -> bytes:
    """Generate КП Word document.

    КП shows work types without detailed breakdown — only stage-level totals.
    Detailed breakdown goes in 2ПС ИР.
    """
    doc = Document()

    # ── Page margins ──────────────────────────────────────────────────────────
    for section in doc.sections:
        section.top_margin = Pt(50)
        section.bottom_margin = Pt(50)
        section.left_margin = Pt(85)
        section.right_margin = Pt(42)

    def _para(text: str = "", bold: bool = False, size: int = 12,
              align=WD_ALIGN_PARAGRAPH.LEFT) -> None:
        p = doc.add_paragraph()
        p.alignment = align
        run = p.add_run(text)
        run.bold = bold
        run.font.size = Pt(size)
        run.font.name = "Times New Roman"
        return p

    # ── Header ────────────────────────────────────────────────────────────────
    if company_name:
        p = _para(f"Касательно: {company_name}", size=12)
    else:
        _para("Касательно: ", size=12)

    _para(
        f"Коммерческое предложение по объекту: «{project_name}»",
        size=12,
    )
    _para()

    # ── Title ─────────────────────────────────────────────────────────────────
    _para("Коммерческое предложение", bold=True, size=14,
          align=WD_ALIGN_PARAGRAPH.CENTER)
    _para()

    # ── Body text ─────────────────────────────────────────────────────────────
    stage_labels = {
        "П":   "проектной документации (стадия ПД)",
        "Р":   "рабочей документации (стадия РД)",
        "П+Р": "проектной и рабочей документации (стадии ПД и РД)",
    }
    stage_label = stage_labels.get(stage, "проектной документации")

    p = doc.add_paragraph()
    run = p.add_run(
        f"              Компания ООО «Интеллект-Строй» направляет Вам коммерческое "
        f"предложение на разработку {stage_label} объекта: «{project_name}»"
    )
    run.font.size = Pt(12)
    run.font.name = "Times New Roman"
    _para()

    # ── Cost table ────────────────────────────────────────────────────────────
    vat_rate = result.get("vat_rate", 22) / 100
    total_with_vat = result.get("total_with_vat", 0.0)
    cost_with_stage = result.get("cost_with_stage", 0.0)
    vat_amount = result.get("vat_amount", 0.0)

    # Build line items based on stage
    lines: list[tuple[str, float]] = []

    if stage == "П+Р":
        # Split 40% ПД + 60% РД (pre-НДС), then add НДС per line
        pd_cost = cost_with_stage * 0.4
        rd_cost = cost_with_stage * 0.6
        lines = [
            ("Разработка проектной документации", pd_cost * (1 + vat_rate)),
            ("Разработка рабочей документации", rd_cost * (1 + vat_rate)),
        ]
    elif stage == "П":
        lines = [("Разработка проектной документации", total_with_vat)]
    else:  # Р
        lines = [("Разработка рабочей документации", total_with_vat)]

    table = doc.add_table(rows=0, cols=3)
    table.style = "Table Grid"

    # Header row
    hdr = table.add_row()
    hdr.cells[0].text = "№ п/п"
    hdr.cells[1].text = "Наименование"
    hdr.cells[2].text = "Сумма, с НДС 22%"
    for cell in hdr.cells:
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.size = Pt(11)
            run.font.name = "Times New Roman"
        _set_cell_border(cell)

    # Data rows
    for num, (name, cost) in enumerate(lines, 1):
        row = table.add_row()
        row.cells[0].text = str(num)
        row.cells[1].text = name
        row.cells[2].text = _fmt(cost)
        for cell in row.cells:
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(11)
                run.font.name = "Times New Roman"
            _set_cell_border(cell)

    # НДС row
    row_vat = table.add_row()
    row_vat.cells[0].text = ""
    row_vat.cells[1].text = f"НДС {int(vat_rate*100)}%"
    row_vat.cells[2].text = _fmt(vat_amount)
    for cell in row_vat.cells:
        for run in cell.paragraphs[0].runs:
            run.font.size = Pt(11)
            run.font.name = "Times New Roman"
        _set_cell_border(cell)

    # Total row
    row_total = table.add_row()
    row_total.cells[0].text = ""
    row_total.cells[1].text = f"Итого с НДС {int(vat_rate*100)}%"
    row_total.cells[2].text = _fmt(total_with_vat)
    for cell in row_total.cells:
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.size = Pt(11)
            run.font.name = "Times New Roman"
        _set_cell_border(cell)

    # ── Footer ────────────────────────────────────────────────────────────────
    _para()
    _para("Данное коммерческое предложение действует в течение 15 (пятнадцати) рабочих дней.")
    _para()
    _para()
    _para("С уважением,")
    _para("Генеральный директор")
    _para("ООО «Интеллект-строй»                                                  И. А. Подопригора")

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()
