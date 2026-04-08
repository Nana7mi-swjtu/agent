from __future__ import annotations

import re

from ..schemas import TextBlock

_INLINE_LINK_RE = re.compile(r"!?\[([^\]]+)\]\([^)]+\)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|~~)")


def normalize_plain_text(text: str) -> str:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    raw = "".join(char if char == "\n" or char == "\t" or ord(char) >= 32 else " " for char in raw)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.split("\n")]
    compacted: list[str] = []
    blank_run = 0
    for line in lines:
        if not line:
            blank_run += 1
            if blank_run > 1:
                continue
            compacted.append("")
            continue
        blank_run = 0
        compacted.append(line)
    return "\n".join(compacted).strip()


def _clean_markdown_inline(text: str) -> str:
    cleaned = _INLINE_LINK_RE.sub(lambda match: match.group(1).strip(), str(text or ""))
    cleaned = _INLINE_CODE_RE.sub(lambda match: match.group(1).strip(), cleaned)
    cleaned = _EMPHASIS_RE.sub("", cleaned)
    cleaned = cleaned.replace("\\", "")
    return normalize_plain_text(cleaned)


def normalize_markdown_to_blocks(*, source_name: str, raw: str) -> list[TextBlock]:
    lines = str(raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[TextBlock] = []
    section_title = "intro"
    buffer: list[str] = []
    section_index = 0
    in_code_block = False
    code_language = ""

    def flush() -> None:
        text = "\n".join(item for item in buffer if item is not None).strip()
        if not text:
            return
        blocks.append(TextBlock(text=text, metadata={"source": source_name, "section": section_title}))

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_language = stripped[3:].strip()
                buffer.append(f"Code block{': ' + code_language if code_language else ''}")
            else:
                in_code_block = False
                code_language = ""
            continue

        if in_code_block:
            if line:
                buffer.append(line)
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            flush()
            buffer = []
            section_index += 1
            section_title = _clean_markdown_inline(heading_match.group(2)) or f"section-{section_index}"
            buffer.append(f"Section: {section_title}")
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [normalize_plain_text(cell) for cell in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell):
                continue
            rendered = ", ".join(cell for cell in cells if cell)
            if rendered:
                buffer.append(f"Row: {rendered}")
            continue

        unordered_match = re.match(r"^[-*+]\s+(.+)$", stripped)
        if unordered_match:
            item = _clean_markdown_inline(unordered_match.group(1))
            if item:
                buffer.append(f"- {item}")
            continue

        ordered_match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if ordered_match:
            item = _clean_markdown_inline(ordered_match.group(2))
            if item:
                buffer.append(f"{ordered_match.group(1)}. {item}")
            continue

        quote_match = re.match(r"^>\s*(.+)$", stripped)
        if quote_match:
            item = _clean_markdown_inline(quote_match.group(1))
            if item:
                buffer.append(f"Quote: {item}")
            continue

        cleaned = _clean_markdown_inline(stripped)
        if cleaned:
            buffer.append(cleaned)
        elif buffer and buffer[-1] != "":
            buffer.append("")

    flush()
    return blocks
