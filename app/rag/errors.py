from __future__ import annotations


class RAGError(RuntimeError):
    pass


class RAGValidationError(RAGError):
    pass


class RAGAuthorizationError(RAGError):
    pass


class RAGConfigurationError(RAGError):
    pass


class RAGContractError(RAGError):
    pass
