"""Оцифровка СБЦ/СЦ с ПСЕВДОГРАФИЧЕСКИМИ таблицами (│ ─ ┬ ┼) из текстового
слоя PDF (конвертации complexdoc/Гарант). Без AI.

Формат таблиц (СЦ-87/СБЦ-95/СБЦП-2001 текстовые):
  ───┬──────────────┬───────────┬───────┬───────┬─────
  N  │ Объект       │ Основной  │   a   │   b   │ K...
  ───┼──────────────┼───────────┼───────┼───────┼─────
  1  │От 436 до 2000│1 тыс. кВт │ 3145  │ 2,50  │ 0,2
  2  │Св. 2000 до...│ То же     │ 3705  │ 2,20  │ 0,2
  3  │" 4000 " 6000 │    "      │ 6810  │ 1,45  │ 0,2

Диапазон X — из текста строки («От N до M», «Св. N до M», «" N " M»);
юнит наследуется («То же», «"»). Числовые колонки: первая пара = а, б;
остальные сохраняются как доп. значения (стадийные доли и т.п.).
Примечания («Примечания. 1. …») собираются per таблица с коэффициентами.

Выход — JSON в формате mrr_digitize (tables/rows/vals/notes) →
импортируется общим import-конвейером.

Запуск: python sbc_digitize.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

RE_TABLE = re.compile(r"^\s*Таблица\s+([\w\d-]+)\s*$")
RE_SEP = re.compile(r"^\s*[─—-]{3,}[┬┼┴]?")
RE_NOTE = re.compile(r"^\s*Примечани[ея]")
RE_COEFF = re.compile(r"(?:коэффициент(?:ом|а|у)?\s+|К\s*=\s*)(\d+[.,]\d+)")
RE_NUM = re.compile(r"^-?\d[\d\s]*(?:[.,]\d+)?$")
# «От 436 до 2000», «Св. 2000 до 4000», «" 4000 " 6000», «до 500», «св. 100»
RE_RANGE = re.compile(
    r"(?:[Оо]т\s+([\d\s.,]+)\s+до\s+([\d\s.,]+))"
    r"|(?:[Сс]в\.?\s*([\d\s.,]+)\s+(?:до|\")\s*([\d\s.,]+))"
    r"|(?:^\"\s*([\d\s.,]+)\s+\"\s*([\d\s.,]+))"
    r"|(?:до\s+([\d\s.,]+))"
    r"|(?:[Сс]в\.?\s+([\d\s.,]+)\s*$)"
)


def _f(s):
    if not s:
        return None
    s = s.strip().replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_range(text):
    m = RE_RANGE.search(text or "")
    if not m:
        return None, None
    g = [(_f(x) if x else None) for x in m.groups()]
    for lo, hi in ((g[0], g[1]), (g[2], g[3]), (g[4], g[5])):
        if lo is not None or hi is not None:
            return lo, hi
    if g[6] is not None:
        return None, g[6]
    if g[7] is not None:
        return g[7], None
    return None, None


def parse_pdf(path):
    pdf = pdfplumber.open(path)
    all_lines = []
    for page in pdf.pages:
        t = page.extract_text() or ""
        all_lines.extend(t.split("\n"))

    tables = []
    skipped = []
    i = 0
    n = len(all_lines)
    while i < n:
        m = RE_TABLE.match(all_lines[i])
        if not m:
            i += 1
            continue
        tid = m.group(1)
        # заголовок: строки до первого сепаратора
        title_parts = []
        j = i + 1
        while j < n and not RE_SEP.match(all_lines[j]) and j - i < 6:
            ln = all_lines[j].strip()
            if ln and "│" not in ln:
                title_parts.append(ln)
            elif "│" in ln:
                break
            j += 1
        title = " ".join(title_parts)[:300]

        # тело таблицы: строки с │ и сепараторы, до строки без │ и без ───
        body = []
        while j < n:
            ln = all_lines[j]
            if "│" in ln or RE_SEP.match(ln):
                body.append(ln)
                j += 1
            elif not ln.strip():
                j += 1
            else:
                break
        # примечания сразу после таблицы
        notes_lines = []
        k = j
        if k < n and RE_NOTE.match(all_lines[k].strip()):
            while k < n and not RE_TABLE.match(all_lines[k]) \
                    and "│" not in all_lines[k] and not RE_SEP.match(all_lines[k]):
                if all_lines[k].strip():
                    notes_lines.append(all_lines[k].strip())
                k += 1
        i = k if k > j else j

        rows, hdr = _parse_body(body)
        notes = _split_notes(notes_lines)
        if rows:
            tables.append({"id": tid, "title": title, "labels": hdr,
                           "fmt": "pseudo", "rows": rows, "notes": notes})
        else:
            skipped.append({"id": tid, "title": title})
    return tables, skipped


def _parse_body(body):
    """Строки псевдотаблицы → records. Ячейки по │; многострочные шапки
    пропускаем (до строки нумерации «1 │ 2 │ 3» или первого сепаратора
    после текста-шапки)."""
    # шапка = всё до строки с последовательной нумерацией колонок
    data_start = 0
    for idx, ln in enumerate(body[:30]):
        cells = [c.strip() for c in ln.split("│")]
        digits = [c for c in cells if re.fullmatch(r"\d+", c)]
        if len(digits) >= 3 and digits == [str(x) for x in
                                           range(int(digits[0]), int(digits[0]) + len(digits))]:
            data_start = idx + 1
            break
    hdr_lines = body[:data_start] if data_start else body[:1]
    ncols = max((ln.count("│") + 1) for ln in body if "│" in ln) if body else 0
    labels = []
    for ci in range(ncols):
        parts = []
        for hl in hdr_lines:
            if "│" not in hl:
                continue
            cs = hl.split("│")
            if ci < len(cs):
                c = cs[ci].strip()
                if c and not re.fullmatch(r"\d+", c):
                    parts.append(c)
        labels.append(" ".join(parts)[:120])

    rows = []
    name_ctx = ""
    unit_ctx = ""
    cur = None

    def close():
        nonlocal cur
        if cur and (cur["a"] is not None or cur["b"] is not None or cur["extra"]):
            nums = {"а": [cur["a"]] if cur["a"] is not None else []}
            if cur["b"] is not None:
                nums["в"] = [cur["b"]]
            for lbl, v in cur["extra"]:
                nums.setdefault(lbl, []).append(v)
            rows.append({"num": cur["num"], "name": cur["name"].strip(),
                         "unit": cur["unit"], "vals": nums})
        cur = None

    for ln in body[data_start:]:
        if RE_SEP.match(ln):
            close()
            continue
        if "│" not in ln:
            continue
        cells = [c.strip() for c in ln.split("│")]
        num = cells[0].strip().rstrip(".")
        texts = []
        nums = []
        for ci, c in enumerate(cells[1:], 1):
            if not c:
                continue
            if RE_NUM.match(c):
                nums.append((ci, _f(c)))
            else:
                texts.append((ci, c))
        is_new = bool(re.fullmatch(r"\d+[a-яa-z]?", num))
        if is_new:
            close()
            name = texts[0][1] if texts else ""
            unit = ""
            for ci, c in texts[1:]:
                if any(u in c.lower() for u in ("кв", "квт", "гкал", "км", "м", "т", "шт",
                                                "га", "то же", '"', "объект", "мвт", "тонн")):
                    unit = c
                    break
            if unit in ('"', "То же", "то же", "-"):
                unit = unit_ctx
            elif unit:
                unit_ctx = unit
            else:
                unit = unit_ctx
            a = nums[0][1] if nums else None
            b = nums[1][1] if len(nums) > 1 else None
            extra = [(f"col{ci}", v) for ci, v in nums[2:]]
            full = f"{name_ctx} :: {name}".strip(" :") if name_ctx else name
            cur = {"num": num, "name": full, "unit": unit, "a": a, "b": b, "extra": extra}
        else:
            # строка-продолжение или контекст группы
            if not nums and texts:
                txt = " ".join(c for _, c in texts)
                if cur is None:
                    name_ctx = txt if not name_ctx else f"{name_ctx} {txt}"
                    if len(name_ctx) > 200:
                        name_ctx = name_ctx[-200:]
                else:
                    cur["name"] += " " + txt
            elif cur is not None and nums:
                have = (cur["a"] is not None) + (cur["b"] is not None)
                for _, v in nums:
                    if cur["a"] is None:
                        cur["a"] = v
                    elif cur["b"] is None:
                        cur["b"] = v
                    else:
                        cur["extra"].append((f"cont{len(cur['extra'])}", v))
    close()
    return rows, labels


def _split_notes(lines):
    if not lines:
        return []
    text = re.sub(r"^Примечани[ея][.:]?\s*", "", " ".join(lines))
    parts = re.split(r"(?<=[.;)])\s+(?=\d{1,2}\.\s)", text)
    items = []
    for part in parts:
        part = part.strip()
        if len(part) < 8:
            continue
        coeffs = [float(c.replace(",", ".")) for c in RE_COEFF.findall(part)]
        items.append({"text": part[:1200], "coeffs": coeffs})
    return items


_UNIT_TOKENS = {'м','км','га','шт','шт.','т','м2','м3','кв.м','куб.м','компл',
    'компл.','"','то','же','мвт','квт','гкал/ч','км2','тыс.квт','объект','узел',
    'т/ч','м3/ч','м3/сут','тыс.м3/сут','тыс.м3','п.м','пог.м','мест','чел',
    'тонн','кв','мм','место'}


def parse_whitespace(path):
    """Режим 3: таблицы без линий — колонки пробелами, значения в конце строки:
      «2.4 Круглые ... трубы отверстием до 2000 мм   м   5,61 0,24 34 66»
    Значения = хвостовые числовые токены (a, b[, %П, %Р]); юнит — токен перед
    ними; переносы имени копятся до строки со значениями. Группы «N. Имя»
    без значений — контекст. table id = целая часть номера строки."""
    pdf = pdfplumber.open(path)
    rows_by_table = {}
    notes_by_table = {}
    name_buf = []
    name_ctx = ""
    cur_table = None
    unit_ctx = ""
    for page in pdf.pages:
        for ln in (page.extract_text() or "").split("\n"):
            ln = ln.strip()
            if not ln:
                continue
            if RE_NOTE.match(ln):
                name_buf = []
                continue
            toks = ln.split()
            # хвостовые числа
            tail = []
            i = len(toks)
            while i > 0 and RE_NUM.match(toks[i-1].replace(",", ",")):
                tail.insert(0, toks[i-1]); i -= 1
            lead = toks[:i]
            m_num = re.match(r"^(\d+(?:\.\d+)*)\.?$", lead[0]) if lead else None
            if len(tail) >= 2 and (m_num or name_buf):
                unit = ""
                if lead and (lead[-1].lower() in _UNIT_TOKENS or lead[-1] == '"'):
                    unit = lead[-1]
                    lead = lead[:-1]
                if unit in ('"', 'же'):
                    unit = unit_ctx
                elif unit:
                    unit_ctx = unit
                else:
                    unit = unit_ctx
                if m_num:
                    row_num = m_num.group(1)
                    name = " ".join(lead[1:])
                else:
                    row_num = ""
                    name = " ".join(lead)
                if name_buf:
                    name = (" ".join(name_buf) + " " + name).strip()
                    name_buf = []
                tid = row_num.split(".")[0] if row_num else (cur_table or "1")
                cur_table = tid
                nums = [_f(x) for x in tail]
                # мусор: строка нумерации колонок «1 2 3 4 5…»
                if len(nums) >= 3 and all(v == float(i + 1) for i, v in enumerate(nums)):
                    name_buf = []
                    continue
                vals = {"а": [nums[0]]}
                if len(nums) > 1:
                    vals["в"] = [nums[1]]
                for j, v in enumerate(nums[2:]):
                    vals[f"k{j}"] = [v]
                full = f"{name_ctx} :: {name}".strip(" :") if name_ctx else name
                rows_by_table.setdefault(tid, []).append(
                    {"num": row_num, "name": full[:600], "unit": unit, "vals": vals})
            elif m_num and not tail:
                name_ctx = " ".join(lead[1:])[:200]
                name_buf = []
            elif not tail and lead and not m_num:
                name_buf.append(ln)
                if len(name_buf) > 4:
                    name_buf = name_buf[-4:]
            else:
                name_buf = []
    tables = [{"id": tid, "title": f"Раздел {tid} (whitespace-разбор)",
               "labels": ["а", "в"], "fmt": "ws", "rows": rows,
               "notes": notes_by_table.get(tid, [])}
              for tid, rows in rows_by_table.items() if rows]
    return tables, []


def main():
    src, dst = sys.argv[1], sys.argv[2]
    tables, skipped = parse_pdf(src)
    if len(tables) < 2:
        ws_tables, _ = parse_whitespace(src)
        if sum(len(t["rows"]) for t in ws_tables) > sum(len(t["rows"]) for t in tables):
            tables, skipped = ws_tables, []
    json.dump({"source": src, "tables": tables, "skipped": skipped},
              open(dst, "w"), ensure_ascii=False, indent=1)
    nrows = sum(len(t["rows"]) for t in tables)
    nnotes = sum(len(t.get("notes") or []) for t in tables)
    print(f"{src.split('/')[-1][:55]}: таблиц {len(tables)} (строк {nrows}, "
          f"примечаний {nnotes}), пропущено {len(skipped)}")


if __name__ == "__main__":
    main()
