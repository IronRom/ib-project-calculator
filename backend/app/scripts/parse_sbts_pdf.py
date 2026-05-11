"""Parse СБЦП 81-2001-17 PDF deterministically via pdftotext -layout.

Usage (inside Docker):
  python3 -m app.scripts.parse_sbts_pdf /path/to/sbts.pdf [--dry-run]
"""
import re
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedRow:
    table_num: int
    row_num: Optional[str]
    description: Optional[str]
    x_min: Optional[float]
    x_max: Optional[float]
    x_unit: Optional[str]
    a: float
    b: Optional[float]
    _point_value: Optional[float] = None  # internal: numeric расход for consecutive range build


# ── Regex ─────────────────────────────────────────────────────────────────────

RE_TABLE = re.compile(r'Таблица\s+N\s+(\d+)', re.IGNORECASE)
# Data row start: 0-4 leading spaces, 1-3 digits, 2+ spaces, then content
RE_DATA_START = re.compile(r'^(\s{0,4})(\d{1,3})\s{2,}(.+)')
# Column header "1  2  3  4  5"
RE_COL_HDR = re.compile(r'^\s*1\s+2\s+3\s+4\s+5\s*$')
# Ditto mark
DITTO = re.compile(r'^["""„‟''""\']+$')

SKIP_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'^\s*[Nn]\s*$',
        r'^\s*п/п\s*$',
        r'Наименование объекта',
        r'Единица\s+измерения',
        r'основного\s+показателя',
        r'Постоянные\s+величины',
        r'базовой\s+цены',
        r'проектной\s+и\s+рабочей',
        r'документации[,.]?\s*(тыс|руб)',
        r'^\s*объекта\s*$',
        r'^\s*показателя\s*$',
        r'^\s*a\s*$',
        r'^\s*b\s*$',
        r'объекта\s+a\s+b',
        r'^\s*a\s+b\s*$',
        r'^\s*документации\s*$',
    ]
]

UNIT_HINTS = [
    'тыс.', 'м3', 'м²', 'м2', 'км', 'кг', 'объект',
    '/сут', '/ч', '/г.', 'шт', 'га', 'Гкал', 'м3/с', 'м/с',
]

# Exact standalone units (token stripped of leading "1" matches one of these)
_STANDALONE_UNITS = {'м', 'м2', 'м3', 'км', 'кг', 'шт', 'шт.', 'га', 'л', 'т'}

RE_RANGE = re.compile(
    r'(?:свыше|от)\s+([\d\s,]+)\s+до\s+([\d\s,]+)'
    r'|до\s+([\d\s,]+)'
    r'|свыше\s+([\d\s,]+)$',
    re.IGNORECASE,
)


def _skip(line: str) -> bool:
    if not line.strip():
        return True
    for p in SKIP_PATTERNS:
        if p.search(line):
            return True
    return False


def _parse_num(s: str) -> Optional[float]:
    s = s.strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def _looks_like_unit(s: str) -> bool:
    # Strip "1" or "1 " prefix artifact before matching (PDF layout: "1м", "1 км")
    check = re.sub(r'^1\s*', '', s).strip() if re.match(r'^1\s*[а-яА-Яa-zA-Z/]', s) else s
    sl = check.lower()
    if sl in _STANDALONE_UNITS:
        return True
    return any(h in sl for h in UNIT_HINTS)


def _extract_ab(tokens: list[str]) -> tuple[Optional[float], Optional[float], list[str]]:
    remaining = list(tokens)
    nums: list[Optional[float]] = []
    while remaining:
        t = remaining[-1].strip()
        if not t:
            remaining.pop()
            continue
        if t in ('-', '—'):
            nums.insert(0, None)
            remaining.pop()
            continue
        n = _parse_num(t)
        if n is not None:
            nums.insert(0, n)
            remaining.pop()
        else:
            break
    if len(nums) >= 2:
        return nums[-2], nums[-1], remaining
    if len(nums) == 1:
        return nums[0], None, remaining
    return None, None, remaining


def _extract_range(text: str) -> tuple[Optional[float], Optional[float]]:
    m = RE_RANGE.search(text)
    if not m:
        return None, None
    if m.group(1) and m.group(2):
        return _parse_num(m.group(1)), _parse_num(m.group(2))
    if m.group(3):
        return None, _parse_num(m.group(3))
    if m.group(4):
        return _parse_num(m.group(4)), None
    return None, None


def _is_pure_range_text(text: str) -> bool:
    """True if text is fully consumed by a range expression (no extra words)."""
    if not text:
        return False
    t = text.strip()
    m = RE_RANGE.search(t)
    if not m:
        return False
    return m.start() == 0 and m.end() == len(t)


def _build_consecutive_ranges(rows: list['ParsedRow']) -> None:
    """Post-process: rows with _point_value → consecutive [x_min, x_max] ranges.

    Used for T16/T17 where each row's расход is a point value in column 2.
    Groups are identified by (table_num, description); each group gets fresh ranges.
    """
    group_prev: dict[tuple, float] = {}
    for row in rows:
        if row._point_value is None:
            continue
        key = (row.table_num, row.description)
        prev = group_prev.get(key)
        row.x_min = prev
        row.x_max = row._point_value
        group_prev[key] = row._point_value
        row._point_value = None


def _parse_logical_row(
    lines_buf: list[str],
    row_num_int: int,
    table_num: int,
    type_prefix: Optional[str],
    last_x_unit: Optional[str],
) -> tuple[Optional['ParsedRow'], Optional[str]]:
    """
    Parse a logical multi-line data row into a ParsedRow.
    Returns (row, updated_last_x_unit).
    """
    # Join continuation lines. Use rstrip() (not strip()) so that leading spaces
    # in continuation lines are preserved and act as 2+-space column separators.
    full_text = ' '.join(l.rstrip() for l in lines_buf if l.strip())

    # Split on 2+ spaces to get column tokens (must happen BEFORE any whitespace collapse).
    parts = [p.strip() for p in re.split(r'\s{2,}', full_text) if p.strip()]
    a_val, b_val, left = _extract_ab(parts)

    # Fallback: for multi-line rows where values are on the FIRST line and
    # description continues on subsequent lines, the join above places continuation
    # text after the values, breaking extraction. Try first-line-only parse.
    continuation_extra: str = ''
    if a_val is None and len(lines_buf) > 1:
        first_parts = [p.strip() for p in re.split(r'\s{2,}', lines_buf[0]) if p.strip()]
        a_val, b_val, left = _extract_ab(first_parts)
        if a_val is not None:
            continuation_extra = ' '.join(l.strip() for l in lines_buf[1:] if l.strip())

    if a_val is None:
        return None, last_x_unit

    # From left: [range_text, x_unit] or just [range_text]
    x_unit: Optional[str] = None
    range_text = ''

    if len(left) >= 2:
        last_left = left[-1]
        if DITTO.match(last_left):
            x_unit = last_x_unit
            range_text = ' '.join(left[:-1])
        elif _looks_like_unit(last_left):
            x_unit = last_left
            range_text = ' '.join(left[:-1])
        else:
            range_text = ' '.join(left)
    elif left:
        candidate = left[0]
        if DITTO.match(candidate):
            x_unit = last_x_unit
        elif _looks_like_unit(candidate):
            x_unit = candidate
        else:
            range_text = candidate

    # Append continuation description (from fallback path) to range_text.
    if continuation_extra:
        range_text = (range_text + ' ' + continuation_extra).strip()

    # Strip "1" or "1 " prefix artifact from first-occurrence units (PDF layout: "1 км"→"км", "1м"→"м").
    if x_unit and re.match(r'^1\s*[а-яА-Яa-zA-Z/]', x_unit):
        x_unit = re.sub(r'^1\s*', '', x_unit).strip()

    if x_unit:
        last_x_unit = x_unit
    elif last_x_unit:
        x_unit = last_x_unit

    # Decide whether range_text goes into description.
    # When type_prefix is set:
    #   • pure number  → point_value (расход marker, T16/T17); excluded from desc
    #   • pure range   → x_min/x_max capture it; excluded from desc (avoids T15 "до 50" in name)
    #   • mixed text   → keep in desc as usual
    point_value: Optional[float] = None
    include_range_in_desc = True

    if type_prefix and range_text:
        pn = _parse_num(range_text)
        if pn is not None:
            point_value = pn
            include_range_in_desc = False
        elif _is_pure_range_text(range_text):
            include_range_in_desc = False

    # Build description
    if type_prefix and range_text and include_range_in_desc:
        description = f"{type_prefix} {range_text}".strip()
    elif type_prefix:
        description = type_prefix
    elif range_text:
        description = range_text
    else:
        description = None

    if description:
        description = re.sub(r'\s+', ' ', description).strip()

    x_min, x_max = _extract_range(range_text)

    row = ParsedRow(
        table_num=table_num,
        row_num=f"п.{row_num_int}",
        description=description,
        x_min=x_min,
        x_max=x_max,
        x_unit=x_unit,
        a=a_val,
        b=b_val,
        _point_value=point_value,
    )
    return row, last_x_unit


# ── Type-header helpers ───────────────────────────────────────────────────────

TYPE_KEYWORDS = [
    'производительностью', 'мощностью', 'длиной', 'протяженностью',
    'емкостью', 'площадью', 'объемом', 'количество', 'диаметром',
    'глубиной', 'сечением', 'м3/ч', 'тыс. м', 'кг/ч', 'м3/сут',
]


def _is_type_header_line(line: str) -> bool:
    """Indented non-data line that likely introduces a type group."""
    if RE_DATA_START.match(line):
        return False
    if _skip(line):
        return False
    leading = len(line) - len(line.lstrip())
    if leading < 5:
        return False
    s = line.strip()
    if not s or len(s) < 5:
        return False
    # Must not start with a digit (would be data)
    if s[0].isdigit():
        return False
    return True


# ── Main parser ───────────────────────────────────────────────────────────────

def parse_pdf(pdf_path: str) -> list[ParsedRow]:
    proc = subprocess.run(
        ['pdftotext', '-layout', pdf_path, '-'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {proc.stderr}")

    lines = proc.stdout.splitlines()
    rows: list[ParsedRow] = []

    current_table: Optional[int] = None
    type_prefix: Optional[str] = None
    pending_header: Optional[str] = None   # accumulating type group header
    last_x_unit: Optional[str] = None
    in_data_section: bool = False

    # Multi-line row state
    current_row_num: Optional[int] = None
    current_row_lines: list[str] = []
    prev_blank: bool = False   # True if the immediately preceding line was blank

    def flush_row():
        nonlocal current_row_num, current_row_lines, last_x_unit
        if current_row_num is None or not current_row_lines:
            return
        parsed, new_unit = _parse_logical_row(
            current_row_lines, current_row_num,
            current_table, type_prefix, last_x_unit,
        )
        if parsed:
            rows.append(parsed)
            last_x_unit = new_unit
        current_row_num = None
        current_row_lines = []

    for line in lines:
        # ── Blank line ────────────────────────────────────────────────────────
        # Track blank lines for the continuation-vs-type-header heuristic.
        # A blank line signals a logical boundary; no blank = same unit.
        if not line.strip():
            prev_blank = True
            continue

        # ── Table boundary ────────────────────────────────────────────────────
        m_tbl = RE_TABLE.search(line)
        if m_tbl:
            flush_row()
            tnum = int(m_tbl.group(1))
            prev_blank = False
            if tnum > 21:
                current_table = None
                continue
            current_table = tnum
            type_prefix = None
            pending_header = None
            last_x_unit = None
            in_data_section = False
            continue

        if current_table is None:
            prev_blank = False
            continue

        # ── Column-header row ("1  2  3  4  5") ──────────────────────────────
        if RE_COL_HDR.match(line):
            flush_row()
            in_data_section = True
            prev_blank = False
            continue

        # ── Blank / boilerplate lines ─────────────────────────────────────────
        if _skip(line):
            prev_blank = False
            continue

        stripped = line.strip()
        leading = len(line) - len(line.lstrip())

        # ── Data row start ────────────────────────────────────────────────────
        m_data = RE_DATA_START.match(line)
        if m_data:
            flush_row()
            # Flush any pending type header
            if pending_header:
                type_prefix = pending_header.rstrip(':').strip()
                pending_header = None
            current_row_num = int(m_data.group(2))
            current_row_lines = [m_data.group(3)]
            prev_blank = False
            continue

        # ── Non-data indented line ────────────────────────────────────────────
        if leading >= 4:
            if current_row_num is not None:
                # Distinguish continuation vs type header using blank-line boundary:
                # a blank line before this line means a new logical group starts here.
                if in_data_section and _is_type_header_line(line) and prev_blank:
                    flush_row()
                    # fall through to type-header handling below
                else:
                    current_row_lines.append(line)
                    prev_blank = False
                    continue

            if in_data_section and _is_type_header_line(line):
                # Type group header (possibly multi-line)
                if pending_header:
                    pending_header = pending_header.rstrip(':').strip() + ' ' + stripped
                else:
                    pending_header = stripped
                # Finalize when ends with ":"
                if pending_header and pending_header.rstrip().endswith(':'):
                    type_prefix = pending_header.rstrip(':').strip()
                    pending_header = None

        prev_blank = False

    flush_row()
    _build_consecutive_ranges(rows)
    return rows


# ── DB import ─────────────────────────────────────────────────────────────────

def import_to_db(rows: list[ParsedRow], book_code: str = "81-2001-17") -> None:
    from app.database import SessionLocal
    from app.models import ReferenceBook, ReferenceRow
    from app.services.reference_parser import rebuild_object_types

    db = SessionLocal()
    try:
        book = (
            db.query(ReferenceBook)
            .filter(ReferenceBook.is_active == True)
            .filter(ReferenceBook.code.ilike(f"%{book_code}%"))
            .first()
        )
        if not book:
            print(f"Active book '{book_code}' not found.")
            return

        print(f"Book: {book.code} id={book.id}")
        deleted = db.query(ReferenceRow).filter(ReferenceRow.book_version_id == book.id).delete()
        print(f"Deleted {deleted} existing rows")

        for r in rows:
            db.add(ReferenceRow(
                book_version_id=book.id,
                table_num=r.table_num,
                row_num=r.row_num,
                description=r.description,
                x_min=r.x_min,
                x_max=r.x_max,
                x_unit=r.x_unit,
                a=r.a,
                b=r.b,
                notes=None,
            ))

        db.commit()
        print(f"Inserted {len(rows)} rows")

        n_types = rebuild_object_types(db, book.id)
        print(f"Rebuilt {n_types} object types")

    finally:
        db.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf_path')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--book-code', default='81-2001-17')
    ap.add_argument('--show-table', type=int, default=None)
    args = ap.parse_args()

    print(f"Parsing {args.pdf_path} …")
    rows = parse_pdf(args.pdf_path)

    from collections import Counter
    counts = Counter(r.table_num for r in rows)
    for t in sorted(counts):
        print(f"  Table {t:2d}: {counts[t]:3d} rows")
    print(f"Total: {len(rows)} rows across {len(counts)} tables")

    if args.show_table:
        print(f"\n=== Table {args.show_table} ===")
        for r in rows:
            if r.table_num == args.show_table:
                print(f"  {r.row_num:6s} | {(r.description or '')[:62]:62s} | "
                      f"unit={r.x_unit} | [{r.x_min},{r.x_max}] | a={r.a} b={r.b}")
        return

    if args.dry_run:
        print("\n--dry-run: first row of each table:")
        seen: set[int] = set()
        for r in rows:
            if r.table_num not in seen:
                seen.add(r.table_num)
                print(f"  T{r.table_num:2d}: {r.row_num} | {(r.description or '?')[:65]}")
                print(f"       unit={r.x_unit} [{r.x_min},{r.x_max}] a={r.a} b={r.b}")
        return

    import_to_db(rows, args.book_code)


if __name__ == '__main__':
    main()
