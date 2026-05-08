import os
from typing import List


def parse_project_files(file_paths: List[str]) -> str:
    parts = []
    for path in file_paths:
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".pdf":
                parts.append(_parse_pdf(path))
            elif ext in (".docx", ".doc"):
                parts.append(_parse_docx(path))
        except Exception as exc:
            parts.append(f"[Ошибка чтения файла {os.path.basename(path)}: {exc}]")
    return "\n\n---\n\n".join(p for p in parts if p.strip())


def _parse_pdf(path: str) -> str:
    import pdfplumber
    texts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
    return "\n".join(texts)


def _parse_docx(path: str) -> str:
    from docx import Document
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def _cell_text(tc) -> str:
        return "".join(node.text or "" for node in tc.iter() if node.tag == f"{{{W}}}t")

    doc = Document(path)
    parts = []
    for block in doc.element.body:
        tag = block.tag.split("}")[-1] if "}" in block.tag else block.tag
        if tag == "p":
            text = "".join(node.text or "" for node in block.iter() if node.tag == f"{{{W}}}t")
            if text.strip():
                parts.append(text.strip())
        elif tag == "tbl":
            for tr in block.findall(f".//{{{W}}}tr"):
                cells = [_cell_text(tc).strip() for tc in tr.findall(f".//{{{W}}}tc")]
                row_text = " | ".join(c for c in cells if c)
                if row_text:
                    parts.append(row_text)
    return "\n".join(parts)
