from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ReportAgentStage:
    id: str
    prompt_id: str
    prompt_version: str = "v1"
    description: str = ""
    allowed_output_keys: tuple[str, ...] = field(default_factory=tuple)

    def run(self, payload: dict[str, Any], handler: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        result = handler(dict(payload))
        if not self.allowed_output_keys:
            return result
        return {key: value for key, value in result.items() if key in self.allowed_output_keys}


STAGES = {
    "intake": ReportAgentStage("intake", "material_intake", allowed_output_keys=("materials", "qualityFlags")),
    "normalization": ReportAgentStage("normalization", "semantic_normalizer", allowed_output_keys=("semanticModel", "qualityFlags")),
    "page_planning": ReportAgentStage("page_planning", "page_planner", allowed_output_keys=("pages", "qualityFlags")),
    "visual_design": ReportAgentStage("visual_design", "visual_designer", allowed_output_keys=("pages", "chartSpecs", "qualityFlags")),
    "writing": ReportAgentStage("writing", "narrative_writer", allowed_output_keys=("pages", "qualityFlags")),
    "quality_review": ReportAgentStage("quality_review", "quality_reviewer", allowed_output_keys=("bundle", "qualityFlags")),
}