from __future__ import annotations

import json
import re
from dataclasses import asdict
from urllib import request as urllib_request

from ..errors import RAGChunkingError
from ..schemas import SemanticSegment


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[。！？!?\.])\s+|\n+", text)
    return [item.strip() for item in chunks if item and item.strip()]


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_with_mapping(text: str) -> tuple[str, list[int]]:
    normalized_chars: list[str] = []
    mapping: list[int] = []
    in_ws = False
    for idx, char in enumerate(text):
        if char.isspace():
            if not in_ws:
                normalized_chars.append(" ")
                mapping.append(idx)
            in_ws = True
            continue
        in_ws = False
        normalized_chars.append(char)
        mapping.append(idx)
    normalized = "".join(normalized_chars).strip()
    if not normalized:
        return "", []
    left_trim = 0
    while left_trim < len(normalized_chars) and normalized_chars[left_trim].isspace():
        left_trim += 1
    right_trim = len(normalized_chars)
    while right_trim > 0 and normalized_chars[right_trim - 1].isspace():
        right_trim -= 1
    return normalized, mapping[left_trim:right_trim]


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    local = text[start:end]
    left = len(local) - len(local.lstrip())
    right = len(local.rstrip())
    trimmed_start = start + left
    trimmed_end = start + right
    return trimmed_start, max(trimmed_start, trimmed_end)


def _find_span_in_block(*, block_text: str, segment_text: str, start_pos: int) -> tuple[int, int] | None:
    direct_idx = block_text.find(segment_text, max(0, start_pos))
    if direct_idx >= 0:
        return _trim_span(block_text, direct_idx, direct_idx + len(segment_text))

    normalized_segment = _collapse_whitespace(segment_text)
    if not normalized_segment:
        return None

    start_anchor = max(0, start_pos)
    suffix = block_text[start_anchor:]
    normalized_suffix, suffix_map = _normalize_with_mapping(suffix)
    if normalized_suffix and suffix_map:
        norm_idx = normalized_suffix.find(normalized_segment)
        if norm_idx >= 0:
            norm_end = norm_idx + len(normalized_segment)
            if norm_end <= len(suffix_map):
                raw_start = start_anchor + suffix_map[norm_idx]
                raw_end = start_anchor + suffix_map[norm_end - 1] + 1
                span_start, span_end = _trim_span(block_text, raw_start, raw_end)
                candidate = block_text[span_start:span_end]
                if _collapse_whitespace(candidate) == normalized_segment:
                    return span_start, span_end

    normalized_block, block_map = _normalize_with_mapping(block_text)
    if not normalized_block or not block_map:
        return None
    norm_idx = normalized_block.find(normalized_segment)
    if norm_idx < 0:
        return None
    norm_end = norm_idx + len(normalized_segment)
    if norm_end > len(block_map):
        return None
    raw_start = block_map[norm_idx]
    raw_end = block_map[norm_end - 1] + 1
    span_start, span_end = _trim_span(block_text, raw_start, raw_end)
    candidate = block_text[span_start:span_end]
    if _collapse_whitespace(candidate) == normalized_segment:
        return span_start, span_end
    return None


def _coerce_int(value) -> int | None:
    if isinstance(value, int):
        return value
    return None


class NoopSemanticChunkingProvider:
    provider_name = "noop"
    model_name = "noop-semantic-chunker"
    model_version = "1"

    def segment(
        self,
        *,
        strategy: str,
        source_name: str,
        blocks: list[dict],
    ) -> list[SemanticSegment]:
        segments: list[SemanticSegment] = []
        for block_index, block in enumerate(blocks):
            text = str(block.get("text", "")).strip()
            if not text:
                continue
            metadata = dict(block.get("metadata", {}))
            metadata["source"] = source_name
            metadata["block_index"] = block_index
            parts = _split_sentences(text)
            if not parts:
                parts = [text]
            for part in parts:
                segments.append(
                    SemanticSegment(
                        text=part,
                        metadata=dict(metadata),
                        topic=None,
                        summary=None,
                    )
                )
        return segments


class OpenAICompatibleSemanticChunkingProvider:
    provider_name = "openai-compatible"

    def __init__(self, *, model_name: str, api_key: str, base_url: str, timeout_seconds: int) -> None:
        self.model_name = model_name
        self.model_version = "1"
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = max(1, int(timeout_seconds))

    def _build_prompt(self, *, strategy: str, source_name: str, blocks: list[dict]) -> str:
        sample = [
            {
                "block_index": idx,
                "text": str(block.get("text", "")),
                "metadata": dict(block.get("metadata", {})),
            }
            for idx, block in enumerate(blocks)
        ]
        return (
            "You are a semantic chunking engine.\n"
            f"Strategy: {strategy}\n"
            "Return ONLY valid JSON with shape: "
            '{"segments":[{"text":"<exact source span>","block_index":0,"topic":"...","metadata":{}}]}.\n'
            "Rules:\n"
            "1) segment.text MUST be copied verbatim from source blocks; never paraphrase or summarize.\n"
            "2) Each segment should represent one coherent semantic unit.\n"
            "3) Keep original language and wording.\n"
            "4) Return JSON only.\n"
            "Do not output markdown.\n"
            f"Source: {source_name}\n"
            f"Blocks: {json.dumps(sample, ensure_ascii=False)}"
        )

    def _align_segment_to_source(
        self,
        *,
        item: dict,
        blocks: list[dict],
        source_name: str,
        search_offsets: list[int],
        index: int,
    ) -> SemanticSegment:
        text = str(item.get("text", "")).strip()
        if not text:
            raise RAGChunkingError(f"semantic segment at index {index} has empty text")

        hinted_block_index = _coerce_int(item.get("block_index"))
        candidate_indexes = list(range(len(blocks)))
        if hinted_block_index is not None and 0 <= hinted_block_index < len(blocks):
            candidate_indexes = [hinted_block_index] + [i for i in candidate_indexes if i != hinted_block_index]

        matched_block = None
        matched_span = None
        for block_index in candidate_indexes:
            block = blocks[block_index]
            block_text = str(block.get("text", ""))
            if not block_text:
                continue
            span = _find_span_in_block(
                block_text=block_text,
                segment_text=text,
                start_pos=search_offsets[block_index],
            )
            if span is None and search_offsets[block_index] > 0:
                span = _find_span_in_block(block_text=block_text, segment_text=text, start_pos=0)
            if span is None:
                continue
            matched_block = block_index
            matched_span = span
            break

        if matched_block is None or matched_span is None:
            raise RAGChunkingError(
                f"semantic segment at index {index} is not a verbatim span of the source text"
            )

        span_start, span_end = matched_span
        search_offsets[matched_block] = max(search_offsets[matched_block], span_end)
        block = blocks[matched_block]
        block_text = str(block.get("text", ""))
        matched_text = block_text[span_start:span_end].strip()
        if not matched_text:
            raise RAGChunkingError(f"semantic segment at index {index} resolved to empty source span")
        metadata = dict(block.get("metadata", {}))
        model_metadata = item.get("metadata")
        if isinstance(model_metadata, dict):
            metadata.update(model_metadata)
        metadata["source"] = source_name
        metadata["block_index"] = matched_block
        metadata["offset_start"] = span_start
        metadata["offset_end"] = span_end
        topic = item.get("topic")
        return SemanticSegment(
            text=matched_text,
            metadata=metadata,
            topic=str(topic).strip() if isinstance(topic, str) and topic.strip() else None,
            summary=None,
        )

    def segment(
        self,
        *,
        strategy: str,
        source_name: str,
        blocks: list[dict],
    ) -> list[SemanticSegment]:
        if not self._api_key:
            raise RAGChunkingError("chunking provider api key is missing")
        if not self._base_url:
            raise RAGChunkingError("chunking provider base url is missing")
        if not blocks:
            return []
        body = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": self._build_prompt(strategy=strategy, source_name=source_name, blocks=blocks)},
            ],
            "temperature": 0,
        }
        req = urllib_request.Request(
            url=f"{self._base_url}/chat/completions",
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
            raise RAGChunkingError(f"semantic chunking provider request failed: {exc}") from exc

        try:
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            items = parsed["segments"]
        except Exception as exc:
            raise RAGChunkingError("semantic chunking provider returned invalid response payload") from exc

        segments: list[SemanticSegment] = []
        if not isinstance(items, list):
            raise RAGChunkingError("semantic chunking provider response segments must be a list")
        search_offsets = [0 for _ in blocks]
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise RAGChunkingError(f"semantic segment at index {idx} must be an object")
            segments.append(
                self._align_segment_to_source(
                    item=item,
                    blocks=blocks,
                    source_name=source_name,
                    search_offsets=search_offsets,
                    index=idx,
                )
            )
        if not segments:
            raise RAGChunkingError("semantic chunking provider returned no valid segments")
        return segments


def serialize_semantic_segments(segments: list[SemanticSegment]) -> list[dict]:
    return [asdict(segment) for segment in segments]
