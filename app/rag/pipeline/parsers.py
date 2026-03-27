from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from ..errors import RAGValidationError
from ..schemas import TextBlock


def _parse_txt(path: Path) -> list[TextBlock]:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    return [TextBlock(text=text, metadata={"source": path.name})] if text else []


def _parse_md(path: Path) -> list[TextBlock]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    sections = re.split(r"(?m)^#{1,6}\s+", raw)
    headers = re.findall(r"(?m)^#{1,6}\s+(.+)$", raw)
    blocks: list[TextBlock] = []
    lead = sections[0].strip()
    if lead:
        blocks.append(TextBlock(text=lead, metadata={"source": path.name, "section": "intro"}))
    for idx, body in enumerate(sections[1:]):
        text = body.strip()
        if not text:
            continue
        section = headers[idx].strip() if idx < len(headers) else f"section-{idx + 1}"
        blocks.append(TextBlock(text=text, metadata={"source": path.name, "section": section}))
    return blocks


def _parse_html(path: Path) -> list[TextBlock]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return [TextBlock(text=text, metadata={"source": path.name})] if text else []


def _parse_csv(path: Path) -> list[TextBlock]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(raw))
    rows: list[TextBlock] = []
    for idx, row in enumerate(reader, start=1):
        text = " | ".join(item.strip() for item in row if item.strip())
        if text:
            rows.append(TextBlock(text=text, metadata={"source": path.name, "section": f"row-{idx}"}))
    return rows


def _parse_pdf(path: Path) -> list[TextBlock]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RAGValidationError("pdf parsing requires pypdf dependency") from exc

    reader = PdfReader(str(path))
    blocks: list[TextBlock] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            blocks.append(TextBlock(text=text, metadata={"source": path.name, "page": idx}))
    if not blocks:
        raise RAGValidationError("ocr required for image-only pdf")
    return blocks


def _parse_docx(path: Path) -> list[TextBlock]:
    try:
        import docx
    except ImportError as exc:
        raise RAGValidationError("docx parsing requires python-docx dependency") from exc

    document = docx.Document(str(path))
    blocks: list[TextBlock] = []
    for idx, paragraph in enumerate(document.paragraphs, start=1):
        text = paragraph.text.strip()
        if text:
            blocks.append(TextBlock(text=text, metadata={"source": path.name, "section": f"paragraph-{idx}"}))
    return blocks


def parse_document_file(path: Path, extension: str) -> list[TextBlock]:
    ext = extension.lower().lstrip(".")
    if ext == "txt":
        return _parse_txt(path)
    if ext == "md":
        return _parse_md(path)
    if ext == "html":
        return _parse_html(path)
    if ext == "csv":
        return _parse_csv(path)
    if ext == "pdf":
        return _parse_pdf(path)
    if ext == "docx":
        return _parse_docx(path)
    raise RAGValidationError("unsupported document format")
