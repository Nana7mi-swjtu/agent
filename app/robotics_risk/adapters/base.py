from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument


class SourceUnavailableError(RuntimeError):
    def __init__(self, source_type: str, message: str) -> None:
        super().__init__(message)
        self.source_type = str(source_type or "unknown")


@dataclass
class SourceCollectionResult:
    documents: list[SourceDocument] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


class EvidenceSourceAdapter(Protocol):
    source_type: str

    def collect(
        self,
        *,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
    ) -> SourceCollectionResult:
        ...
