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
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
