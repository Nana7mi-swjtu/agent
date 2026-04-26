from __future__ import annotations

from typing import Any

from .contracts import as_list


def write_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    written = []
    for page in pages:
        page = dict(page)
        if page.get("pageType") not in {"cover", "table_of_contents"}:
            blocks = as_list(page.get("blocks"))
            page["blocks"] = [b for b in blocks if isinstance(b, dict)]
        written.append(page)
    return written
