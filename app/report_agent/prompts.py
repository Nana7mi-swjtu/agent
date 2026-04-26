from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).with_name("prompts")


def load_prompt(prompt_id: str, version: str = "v1") -> dict[str, str]:
    safe_id = "".join(ch for ch in str(prompt_id) if ch.isalnum() or ch in {"_", "-"}).strip(".-_")
    safe_version = "".join(ch for ch in str(version or "v1") if ch.isalnum() or ch in {"_", "-"}).strip(".-_") or "v1"
    filename = f"{safe_id}.{safe_version}.md"
    path = PROMPT_DIR / filename
    if not path.exists():
        return {"id": safe_id, "version": safe_version, "text": ""}
    return {"id": safe_id, "version": safe_version, "text": path.read_text(encoding="utf-8")}


def load_default_prompts() -> dict[str, dict[str, str]]:
    return {
        name: load_prompt(name, "v1")
        for name in (
            "material_intake",
            "semantic_normalizer",
            "page_planner",
            "visual_designer",
            "narrative_writer",
            "quality_reviewer",
        )
    }