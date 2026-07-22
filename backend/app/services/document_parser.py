import base64
import io
import logging
import os
from typing import List

logger = logging.getLogger(__name__)


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
    result = "\n".join(texts)
    if result.strip():
        return result
    # Scanned PDF — no text layer, fall back to Claude Vision OCR
    logger.info("No text layer in %s — using Claude Vision OCR", os.path.basename(path))
    return _parse_pdf_vision(path)


def _parse_pdf_vision(path: str) -> str:
    """Extract text from a scanned PDF via OpenRouter vision (page by page).

    Переведён с anthropic client на OpenRouter (chat/completions c image_url,
    data-URI) — ключ Anthropic пуст и не пополняется (решение 22.07.2026).
    """
    import httpx
    from pdf2image import convert_from_path
    from app.config import settings

    images = convert_from_path(path, dpi=150, fmt="jpeg")
    texts = []

    with httpx.Client(timeout=180) as http:
        for i, img in enumerate(images):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            img_b64 = base64.standard_b64encode(buf.getvalue()).decode()

            resp = http.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "HTTP-Referer": "https://ib-pir-calculator.ru",
                    "X-Title": "IB PIR Calculator",
                },
                json={
                    "model": settings.ocr_model,
                    "max_tokens": 4096,
                    "temperature": 0,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_b64}",
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Извлеки весь текст с этой страницы документа точно как написано. "
                                    "Верни только текст, без пояснений и форматирования."
                                ),
                            },
                        ],
                    }],
                },
            )
            if not resp.is_success:
                raise ValueError(
                    f"OpenRouter OCR {resp.status_code} (стр. {i + 1}): {resp.text[:200]}"
                )
            data = resp.json()
            text = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
            if text:
                texts.append(text)
            logger.debug("Vision OCR page %d: %d chars", i + 1, len(text))

    return "\n\n".join(texts)


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
