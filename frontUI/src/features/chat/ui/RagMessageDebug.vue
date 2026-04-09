<script setup>
import { useUiStore } from "@/stores/ui";

defineProps({
  debugPayload: {
    type: Object,
    default: null,
  },
  detailed: {
    type: Boolean,
    default: false,
  },
  condensed: {
    type: Boolean,
    default: false,
  },
});

const uiStore = useUiStore();
</script>

<template>
  <div class="rag-message-debug">
    <details v-if="debugPayload" class="rag-debug-section">
      <summary>{{ uiStore.t("ragDebugMessageSummary") }}</summary>
      <template v-if="condensed">
        <div class="rag-debug-mini">
          {{ uiStore.t("ragDebugLabelEmbedding") }}:
          {{ debugPayload?.vector?.embedderProvider || "-" }} /
          {{ debugPayload?.vector?.embeddingModel || "-" }} /
          dim={{ debugPayload?.vector?.embeddingDimension ?? "-" }}
        </div>
      </template>
      <template v-else>
        <div class="rag-debug-grid">
          <div>
            <strong>{{ uiStore.t("ragDebugLabelEmbedding") }}</strong>
            <div class="rag-debug-mini">
              {{ debugPayload?.vector?.embedderProvider || "-" }} / {{ debugPayload?.vector?.embeddingModel || "-" }}
            </div>
            <div class="rag-debug-mini">
              dim={{ debugPayload?.vector?.embeddingDimension ?? "-" }} norm={{ debugPayload?.vector?.queryVectorNorm ?? "-" }}
            </div>
            <div class="rag-debug-mini">
              sample={{ (debugPayload?.vector?.queryVectorSample || []).join(", ") }}
            </div>
          </div>
          <div>
            <strong>{{ uiStore.t("ragDebugLabelRetrieval") }}</strong>
            <div class="rag-debug-mini">
              raw={{ debugPayload?.retrieval?.rawCount ?? 0 }}, threshold={{ debugPayload?.retrieval?.afterThresholdCount ?? 0 }}
            </div>
            <div class="rag-debug-mini">latency={{ debugPayload?.latencyMs ?? "-" }}ms</div>
          </div>
        </div>
        <details v-if="detailed" class="rag-debug-section">
          <summary>{{ uiStore.t("ragDebugLabelRetrievalRaw") }}</summary>
          <ul class="rag-debug-list">
            <li
              v-for="item in debugPayload?.retrieval?.rawHits || []"
              :key="`raw_${item.chunkId}`"
              class="rag-debug-item"
            >
              <div><strong>{{ item.chunkId }}</strong> · {{ item.score }} · {{ item.source }}</div>
              <div class="rag-debug-preview">{{ item.contentPreview }}</div>
            </li>
          </ul>
        </details>
        <details v-if="detailed" class="rag-debug-section">
          <summary>{{ uiStore.t("ragDebugLabelRerankAfter") }}</summary>
          <ul class="rag-debug-list">
            <li
              v-for="item in debugPayload?.rerank?.after || debugPayload?.rerank?.afterRuntimeSort || []"
              :key="`rerank_${item.chunkId}`"
              class="rag-debug-item"
            >
              <div><strong>{{ item.chunkId }}</strong> · {{ item.score }} · {{ item.source }}</div>
              <div class="rag-debug-preview">{{ item.contentPreview }}</div>
            </li>
          </ul>
        </details>
      </template>
    </details>
  </div>
</template>

<style scoped>
.rag-message-debug {
  margin-top: 8px;
}

.rag-debug-section {
  margin-top: 8px;
  border: 1px solid rgba(47, 107, 255, 0.12);
  border-radius: 16px;
  padding: 8px;
  background: rgba(47, 107, 255, 0.04);
}

.rag-debug-section > summary {
  cursor: pointer;
  font-size: 12px;
  color: var(--text);
}

.rag-debug-grid {
  margin-top: 8px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}

.rag-debug-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.rag-debug-item {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
}

.rag-debug-preview {
  margin-top: 4px;
  color: var(--text-muted);
  white-space: pre-wrap;
  word-break: break-word;
}

.rag-debug-mini {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
