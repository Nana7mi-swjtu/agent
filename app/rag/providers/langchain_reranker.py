from __future__ import annotations

import json
from urllib import request as urllib_request

from langchain_community.cross_encoders.fake import FakeCrossEncoder

from ..errors import RAGConfigurationError, RAGValidationError
from ..schemas import RetrievalHit


class OpenAICompatibleReranker:
    provider_name = "openai-compatible"

    def __init__(self, *, model_name: str, api_key: str, base_url: str, timeout_seconds: int) -> None:
        if not model_name.strip():
            raise RAGConfigurationError("RAG_RERANKER_MODEL must be configured")
        if not api_key.strip():
            raise RAGConfigurationError("RAG_RERANKER_API_KEY must be configured")
        if not base_url.strip():
            raise RAGConfigurationError("RAG_RERANKER_BASE_URL must be configured")
        self.model_name = model_name.strip()
        self.model_version = "1"
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = max(1, int(timeout_seconds))

    def _request_scores(self, *, query: str, documents: list[str], top_k: int) -> list[tuple[int, float]]:
        body = {
            "model": self.model_name,
            "query": query,
            "documents": documents,
            "top_n": top_k,
        }
        req = urllib_request.Request(
            url=f"{self._base_url}/rerank",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self._timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise RAGValidationError(f"openai-compatible reranker request failed: {exc}") from exc

        try:
            raw_items = payload.get("data")
            if not isinstance(raw_items, list):
                raw_items = payload.get("results")
            if not isinstance(raw_items, list):
                output = payload.get("output")
                if isinstance(output, dict):
                    raw_items = output.get("results")
            if not isinstance(raw_items, list):
                raise TypeError("reranker response items are missing")

            ranked: list[tuple[int, float]] = []
            for idx, item in enumerate(raw_items):
                if not isinstance(item, dict):
                    raise TypeError(f"reranker item at index {idx} is invalid")
                order = int(item.get("index"))
                score_value = item.get("relevance_score", item.get("score"))
                if score_value is None:
                    raise TypeError(f"reranker score missing for index {idx}")
                ranked.append((order, float(score_value)))
        except Exception as exc:
            raise RAGValidationError("openai-compatible reranker returned invalid response payload") from exc
        if not ranked:
            raise RAGValidationError("openai-compatible reranker returned empty ranking results")
        return ranked

    def rerank(self, *, query: str, hits: list[RetrievalHit], top_k: int) -> list[RetrievalHit]:
        if not hits:
            return []

        documents = [hit.content for hit in hits]
        ranked_scores = self._request_scores(query=query, documents=documents, top_k=top_k)
        scores_by_index = {idx: score for idx, score in ranked_scores if 0 <= idx < len(hits)}
        ranked_hits = [
            (hit, scores_by_index.get(idx, float("-inf")))
            for idx, hit in enumerate(hits)
        ]
        ranked_hits.sort(key=lambda item: float(item[1]), reverse=True)
        return [item[0] for item in ranked_hits[:top_k]]

# 这是是使用案例，对下面的clss进行模型替换，可以以在不改变接口的前提下，替换成任何其他的reranker模型，只要它们符合Reranker协议即可。
class FakeReranker:
    provider_name = "fake"

    def __init__(self) -> None:
        self.model_name = "fake-cross-encoder"
        self._cross_encoder = FakeCrossEncoder()

    def rerank(self, *, query: str, hits: list[RetrievalHit], top_k: int) -> list[RetrievalHit]:
        if not hits:
            return []
        pairs = [[query, hit.content] for hit in hits]
        scores = self._cross_encoder.score(pairs)
        ranked = list(zip(hits, scores, strict=False))
        ranked.sort(key=lambda item: float(item[1]), reverse=True)
        return [item[0] for item in ranked[:top_k]]
