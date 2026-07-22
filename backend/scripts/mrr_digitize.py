"""Оцифровка сборников МРР из текстового слоя PDF (pdfplumber, без AI).

Generic-подход: для каждой «Таблица N[.N…]» собирается grid (включая
«Продолжение таблицы»), шапка любой глубины сворачивается в подписи колонок,
тело — в строки {num, name, unit, cells: {col_label: "значение"}}.
Ячейки с двумя числами «5690,4\n2644,08» — это полевые/камеральные (изыскания).

Таблицы без числовых данных (коэффициенты, классификаторы) попадают в skipped.

Запуск: python mrr_digitize.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

RE_TABLE = re.compile(r"^Таблица\s+(\d+(?:\.\d+){0,3}[аб]?)\s*$")
RE_CONT = re.compile(r"^Продолжение\s+таблицы\s+(\d+(?:\.\d+){0,3}[аб]?)", re.I)


def _cell(s):
    return (s or "").replace("\n", " ").strip()


def _nums_in_cell(s):
    """Числа из ячейки (могут быть 1-2 через перенос строки)."""
    if not s:
        return []
    out = []
    for part in s.split("\n"):
        part = part.strip().replace(" ", "").replace(" ", "")
        if part in ("-", "–", "—", ""):
            continue
        p = part.replace(",", ".")
        try:
            out.append(float(p))
        except ValueError:
            return []  # не числовая ячейка
    return out


def _is_colnum_row(cells):
    digits = [c for c in cells if re.fullmatch(r"\d+", c)]
    return len(digits) >= 3 and digits == [str(i) for i in range(int(digits[0]), int(digits[0]) + len(digits))]


def parse_grid(raw):
    """raw grid → (col_labels, data_rows). Шапка = строки до «1 2 3 4…»."""
    hdr_end = 0
    for i, row in enumerate(raw[:8]):
        if _is_colnum_row([_cell(c) for c in row]):
            hdr_end = i
            break
    if hdr_end == 0:
        # шапка без нумерации колонок: считаем шапкой строки без чисел
        for i, row in enumerate(raw):
            has_nums = any(_nums_in_cell(c) for c in row[2:])
            if has_nums:
                hdr_end = max(0, i - 1) if i else 0
                break
        header_rows = raw[:hdr_end + 1] if hdr_end else raw[:1]
        data_rows = raw[hdr_end + 1:] if hdr_end else raw[1:]
    else:
        header_rows = raw[:hdr_end]
        data_rows = raw[hdr_end + 1:]

    ncols = max(len(r) for r in raw)
    labels = []
    for ci in range(ncols):
        parts = []
        last = None
        for hr in header_rows:
            c = _cell(hr[ci]) if ci < len(hr) else ""
            if c and c != last:
                parts.append(c)
                last = c
        labels.append(" / ".join(parts))
    return labels, data_rows


def parse_pdf(path):
    pdf = pdfplumber.open(path)
    tables = {}
    order = []
    current_for_cont = None

    for page in pdf.pages:
        text = page.extract_text() or ""
        lines = [ln.strip() for ln in text.split("\n")]

        page_new = []
        for j, ln in enumerate(lines):
            m = RE_TABLE.match(ln)
            if m:
                title = []
                for k in range(j + 1, min(j + 5, len(lines))):
                    if RE_TABLE.match(lines[k]) or not lines[k]:
                        break
                    if re.match(r"^№\s|^Наименование\s", lines[k]):
                        break
                    title.append(lines[k])
                page_new.append((m.group(1), " ".join(title)[:300]))
        cont_ids = [RE_CONT.match(ln).group(1) for ln in lines if RE_CONT.match(ln)]

        grids = page.extract_tables()
        if not grids:
            continue

        def _looks_like_data(g):
            """Grid похож на таблицу данных: «№» в шапке, нумерация колонок
            или числовые/процентные ячейки в теле."""
            if not g:
                return False
            head = _cell(g[0][0]) if g[0] else ""
            if head.startswith("№"):
                return True
            for row in g[:6]:
                if _is_colnum_row([_cell(c) for c in row]):
                    return True
            for row in g:
                for c in row[1:]:
                    if isinstance(c, str) and (_nums_in_cell(c) or "%" in c):
                        return True
            return False

        gi = 0
        if cont_ids and grids:
            cid = cont_ids[0]
            if cid in tables:
                tables[cid]["raw"].extend(grids[0])
                gi = 1
        elif not page_new and current_for_cont and grids and current_for_cont in tables:
            # страница без заголовков — молчаливое продолжение текущей таблицы
            first = grids[0]
            # приклеиваем только если ширина совпадает
            if first and len(first[0]) == len(tables[current_for_cont]["raw"][0]):
                tables[current_for_cont]["raw"].extend(first)
                gi = 1

        for tid, title in page_new:
            # пропустить врезки-описания перед настоящей таблицей
            while gi < len(grids) and not _looks_like_data(grids[gi]) and gi + 1 < len(grids):
                gi += 1
            if gi >= len(grids):
                break
            g = grids[gi]
            gi += 1
            if tid in tables:
                tables[tid]["raw"].extend(g)
            else:
                tables[tid] = {"id": tid, "title": title, "raw": list(g)}
                order.append(tid)
            current_for_cont = tid

    out, skipped = [], []
    for tid in order:
        t = tables[tid]
        labels, data = parse_grid(t["raw"])

        # ── ab_dense: шапка содержит «а, тыс.руб» и «в, тыс.руб» и сетка
        # «плавает» (rowspan имён, интервалы X). Плотный разбор построчно.
        flat_hdr = " ".join(lb.lower() for lb in labels if lb)
        if re.search(r"а,\s*тыс", flat_hdr) and re.search(r"в,\s*тыс", flat_hdr):
            rows = []
            num_ctx = name_ctx = ""
            for row in data:
                cells = [_cell(c) for c in row]
                if not any(cells) or _is_colnum_row(cells):
                    continue
                nums, texts = [], []
                for c in cells:
                    if not c:
                        continue
                    if c in ("-", "–", "—"):
                        continue
                    ns = _nums_in_cell(c)
                    # интервалы («от 1 до 5») содержат числа, но с текстом
                    if ns and not re.search(r"[А-Яа-яA-Za-z]", c):
                        nums.extend(ns)
                    else:
                        texts.append(c)
                if cells[0]:
                    num_ctx = cells[0].rstrip(".")
                rng = next((tx for tx in texts
                            if re.search(r"^(до|от|свыше)\s", tx)), "")
                names = [tx for tx in texts if tx is not rng and not re.fullmatch(r"\d+\.?", tx)]
                if names:
                    name_ctx = " ".join(names)
                if not nums:
                    continue
                a = nums[0]
                b = nums[1] if len(nums) > 1 else None
                rows.append({
                    "num": num_ctx,
                    "name": (f"{name_ctx} :: {rng}" if rng else name_ctx),
                    "unit": "",
                    "vals": {"а": [a], "в": [b] if b is not None else []},
                })
            if rows:
                out.append({"id": tid, "title": t["title"], "labels": ["а", "в"],
                            "fmt": "ab_dense", "rows": rows})
            else:
                skipped.append({"id": tid, "title": t["title"]})
            continue

        unit_col = next((i for i, lb in enumerate(labels) if "змеритель" in lb), None)
        rows = []
        name_ctx = ""
        unit_ctx = ""
        for row in data:
            cells = [_cell(c) for c in row]
            if not any(cells):
                continue
            if _is_colnum_row(cells):
                continue
            raw_cells = list(row) + [None] * (len(labels) - len(row))
            num = cells[0].rstrip(".") if cells else ""
            # значения: ячейки, парсящиеся как числа, начиная с колонки 1
            vals = {}
            texts = {}
            for ci in range(1, len(labels)):
                cval = raw_cells[ci]
                ns = _nums_in_cell(cval if isinstance(cval, str) else None)
                if ns:
                    vals[ci] = ns
                elif _cell(cval):
                    texts[ci] = _cell(cval)
            name_parts = [texts[ci] for ci in sorted(texts) if ci != unit_col]
            unit = texts.get(unit_col, "") if unit_col is not None else ""
            if unit:
                unit_ctx = unit
            name = " | ".join(name_parts)
            if not vals:
                if name:
                    name_ctx = name
                continue
            full = f"{name_ctx} :: {name}".strip(" :") if name_ctx and name else (name or name_ctx)
            rows.append({
                "num": num,
                "name": full,
                "unit": unit or unit_ctx,
                "vals": {labels[ci] or f"col{ci}": v for ci, v in vals.items()},
            })
        if rows:
            out.append({"id": tid, "title": t["title"], "labels": labels, "rows": rows})
            continue
        # Нормативные таблицы-формулы («3679+2,4% от стоимости свыше…»):
        # чисел нет, но есть проценты/формулы — сохраняем текстом
        text_rows = []
        for row in data:
            cells = [_cell(c) for c in row]
            if not any(cells) or _is_colnum_row(cells):
                continue
            if any("%" in c for c in cells[1:]):
                text_rows.append({
                    "num": cells[0].rstrip("."),
                    "cells": {labels[ci] or f"col{ci}": cells[ci]
                              for ci in range(1, min(len(cells), len(labels))) if cells[ci]},
                })
        if len(text_rows) >= 2:
            out.append({"id": tid, "title": t["title"], "labels": labels,
                        "rows": [], "text_rows": text_rows})
        else:
            skipped.append({"id": tid, "title": t["title"]})
    return out, skipped


def main():
    src, dst = sys.argv[1], sys.argv[2]
    tables, skipped = parse_pdf(src)
    with open(dst, "w") as f:
        json.dump({"source": src, "tables": tables, "skipped": skipped}, f, ensure_ascii=False, indent=1)
    n = sum(len(t["rows"]) for t in tables)
    print(f"{src.split('/')[-1]}: таблиц {len(tables)} (строк {n}), пропущено {len(skipped)}")
    for s in skipped:
        print(f"  skip {s['id']}: {s['title'][:75]}")


if __name__ == "__main__":
    main()
