<script setup>
import { canDeleteRagDocument, getRagDocumentActionType } from "@/features/rag/lib/document";
import { useUiStore } from "@/shared/model/ui-store";

const props = defineProps({
  channelName: {
    type: String,
    default: "",
  },
  selectedRoleName: {
    type: String,
    default: "",
  },
  ragUploading: {
    type: Boolean,
    default: false,
  },
  uploadPercent: {
    type: Number,
    default: 0,
  },
  ragStageText: {
    type: String,
    default: "",
  },
  ragError: {
    type: String,
    default: "",
  },
  ragDocuments: {
    type: Array,
    default: () => [],
  },
  ragDebugEnabled: {
    type: Boolean,
    default: false,
  },
  ragDebugSnapshot: {
    type: Object,
    default: null,
  },
  chunkingStrategy: {
    type: String,
    default: "paragraph",
  },
  chunkingAppliedText: {
    type: String,
    default: "",
  },
  ragActionDocumentId: {
    type: [Number, String],
    default: null,
  },
});

const emit = defineEmits([
  "update:chunkingStrategy",
  "choose-document",
  "load-documents",
  "run-document-action",
  "delete-document",
  "load-rag-debug-snapshot",
]);

const uiStore = useUiStore();

const documentActionLabel = (document) => {
  const actionType = getRagDocumentActionType(document);
  if (actionType === "start") return uiStore.t("ragDocumentStartIndexing");
  if (actionType === "retry") return uiStore.t("ragDocumentRetry");
  if (actionType === "reindex") return uiStore.t("ragDocumentReindex");
  return "";
};

const isDocumentBusy = (document) => Number(props.ragActionDocumentId) === Number(document?.id);
</script>

<template>
  <section class="knowledge-panel">
    <header class="knowledge-header">
      <div>
        <div class="knowledge-kicker">{{ selectedRoleName || channelName || "Agent" }}</div>
        <h2>{{ uiStore.t("ragUploadedFiles") }}</h2>
        <p>{{ uiStore.t("ragUploadFormatsHint") }}</p>
      </div>
      <button class="panel-icon-btn rag-refresh-btn" :title="uiStore.t('loading')" @click="emit('load-documents')">Sync</button>
    </header>

    <div class="knowledge-upload-row">
      <label class="toolbar-upload-btn" :class="{ disabled: ragUploading }">
        <span>{{ uiStore.t("ragUploadFile") }}</span>
        <input
          type="file"
          accept=".pdf,.docx,.md,.txt,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          :disabled="ragUploading"
          @change="emit('choose-document', $event)"
        />
      </label>
      <label class="rag-strategy-select">
        <span>{{ uiStore.t("ragChunkStrategyLabel") }}</span>
        <select
          :value="chunkingStrategy"
          :disabled="ragUploading"
          @change="emit('update:chunkingStrategy', $event.target.value)"
        >
          <option value="paragraph">{{ uiStore.t("ragChunkStrategyParagraph") }}</option>
          <option value="semantic_llm">{{ uiStore.t("ragChunkStrategySemanticLlm") }}</option>
        </select>
      </label>
    </div>

    <div class="rag-status-row">
      <div class="rag-status-copy">
        <strong>{{ ragStageText || uiStore.t("ragUploadIdle") }}</strong>
        <span v-if="chunkingAppliedText">{{ chunkingAppliedText }}</span>
      </div>
      <div class="rag-progress-bar">
        <div class="rag-progress-fill" :style="{ width: `${uploadPercent}%` }"></div>
      </div>
    </div>
    <div v-if="ragError" class="msg-err rag-inline-err">{{ ragError }}</div>

    <div class="rag-docs-panel">
      <ul class="rag-docs-list">
        <li v-for="doc in ragDocuments" :key="doc.id" class="rag-doc-item">
          <div class="rag-doc-main">
            <span class="rag-doc-name">{{ doc.sourceName || doc.fileName }}</span>
            <span class="rag-doc-status">
              {{ doc.status }}
              <template v-if="doc.chunkingApplied?.strategy"> · {{ doc.chunkingApplied.strategy }}</template>
              <template v-if="doc.chunkingApplied?.fallbackUsed"> ({{ uiStore.t("ragChunkFallback") }})</template>
            </span>
          </div>
          <div class="rag-doc-actions">
            <button
              v-if="documentActionLabel(doc)"
              class="rag-doc-action-btn"
              :disabled="ragUploading || isDocumentBusy(doc)"
              @click="emit('run-document-action', doc)"
            >
              {{ documentActionLabel(doc) }}
            </button>
            <button
              v-if="canDeleteRagDocument(doc)"
              class="rag-doc-action-btn is-danger"
              :disabled="ragUploading || isDocumentBusy(doc)"
              @click="emit('delete-document', doc)"
            >
              {{ uiStore.t("ragDocumentDelete") }}
            </button>
          </div>
        </li>
        <li v-if="!ragDocuments.length" class="rag-doc-empty">{{ uiStore.t("ragNoFiles") }}</li>
      </ul>
    </div>

    <details v-if="ragDebugEnabled" class="rag-debug-panel">
      <summary>Engineering</summary>
      <div class="rag-debug-header">
        <div class="rag-docs-title">{{ uiStore.t("ragDebugPanelTitle") }}</div>
        <button class="panel-icon-btn rag-refresh-btn" :title="uiStore.t('loading')" @click="emit('load-rag-debug-snapshot')">Sync</button>
      </div>
      <div class="rag-debug-metrics">
        <span>{{ uiStore.t("ragDebugMetricDocuments") }}: {{ ragDebugSnapshot?.totalDocuments || 0 }}</span>
        <span>{{ uiStore.t("ragDebugMetricIndexedDocuments") }}: {{ ragDebugSnapshot?.indexedDocuments || 0 }}</span>
        <span>{{ uiStore.t("ragDebugMetricLatestChunks") }}: {{ ragDebugSnapshot?.latestDocumentChunks?.length || 0 }}</span>
      </div>
      <details class="rag-debug-section" open>
        <summary>{{ uiStore.t("ragDebugSectionLatestChunks") }}</summary>
        <ul class="rag-debug-list">
          <li v-for="chunk in ragDebugSnapshot?.latestDocumentChunks || []" :key="chunk.chunkId" class="rag-debug-item">
            <div>
              <strong>{{ chunk.chunkId }}</strong>
              <span class="rag-debug-mini"> · {{ chunk.source }}</span>
              <span class="rag-debug-mini"> · {{ uiStore.t("ragDebugLabelTokenCount") }} {{ chunk.tokenCount ?? "-" }}</span>
            </div>
            <div class="rag-debug-preview">{{ chunk.contentPreview }}</div>
          </li>
          <li v-if="!(ragDebugSnapshot?.latestDocumentChunks || []).length" class="rag-doc-empty">{{ uiStore.t("ragNoFiles") }}</li>
        </ul>
      </details>
      <details class="rag-debug-section">
        <summary>{{ uiStore.t("ragDebugSectionRecentJobs") }}</summary>
        <ul class="rag-debug-list">
          <li v-for="job in ragDebugSnapshot?.recentJobs || []" :key="job.jobId" class="rag-debug-item">
            <div><strong>Job #{{ job.jobId }}</strong> · doc {{ job.documentId }} · {{ job.status }} · chunks {{ job.chunksCount }}</div>
            <div class="rag-debug-mini">{{ job.chunkingApplied?.strategy }} / {{ job.chunkingApplied?.provider }} / {{ job.chunkingApplied?.model }}</div>
          </li>
        </ul>
      </details>
    </details>
  </section>
</template>

<style scoped>
.knowledge-panel {
  display: grid;
  gap: 16px;
  height: 100%;
  align-content: start;
  overflow-y: auto;
  padding: 22px 20px;
  border: 1px solid var(--line);
  border-radius: 30px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(243, 248, 255, 0.95));
  box-shadow: var(--shadow-sm);
}

.knowledge-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.knowledge-header h2 {
  margin: 6px 0 6px;
  font-size: 20px;
}

.knowledge-header p {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

.knowledge-kicker {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}

.knowledge-upload-row {
  display: grid;
  gap: 12px;
}

.toolbar-upload-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  border: 1px dashed rgba(47, 107, 255, 0.26);
  background: rgba(47, 107, 255, 0.05);
  color: var(--accent);
  border-radius: 18px;
  padding: 0 14px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
}

.toolbar-upload-btn input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.toolbar-upload-btn.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.rag-strategy-select {
  display: grid;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.rag-strategy-select select {
  border: 1px solid var(--line);
  min-height: 42px;
  background: rgba(255, 255, 255, 0.9);
  color: var(--text);
  border-radius: 14px;
  padding: 0 12px;
  font-size: 13px;
}

.rag-status-row {
  display: grid;
  gap: 10px;
}

.rag-status-copy {
  display: grid;
  gap: 4px;
}

.rag-status-copy strong {
  font-size: 13px;
  color: var(--text);
}

.rag-status-copy span {
  font-size: 12px;
  color: var(--text-muted);
}

.rag-progress-bar {
  height: 8px;
  background: var(--bg-input);
  border-radius: 999px;
  overflow: hidden;
}

.rag-progress-fill {
  height: 100%;
  width: 0;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
  transition: width 0.18s ease;
}

.rag-refresh-btn {
  min-width: 56px;
  font-size: 11px;
}

.rag-inline-err {
  margin: 0;
}

.rag-docs-panel {
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.82);
}

.rag-docs-title {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

.rag-docs-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}

.rag-doc-item {
  display: grid;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(213, 226, 243, 0.66);
}

.rag-doc-item:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.rag-doc-main {
  min-width: 0;
  display: grid;
  gap: 2px;
  flex: 1;
}

.rag-doc-name {
  font-size: 13px;
  color: var(--text);
  line-height: 1.35;
}

.rag-doc-status {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.rag-doc-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rag-doc-action-btn {
  min-height: 30px;
  border: 1px solid rgba(47, 107, 255, 0.12);
  background: rgba(47, 107, 255, 0.05);
  color: var(--text-channel);
  border-radius: 999px;
  padding: 0 10px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}

.rag-doc-action-btn:hover:not(:disabled) {
  background: rgba(47, 107, 255, 0.1);
}

.rag-doc-action-btn.is-danger {
  color: var(--danger);
  border-color: rgba(217, 92, 92, 0.18);
  background: rgba(217, 92, 92, 0.05);
}

.rag-doc-action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.rag-doc-empty {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  padding: 12px 0;
}

.rag-debug-panel {
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 12px 14px;
  background: rgba(244, 248, 255, 0.86);
}

.rag-debug-panel > summary {
  cursor: pointer;
  color: var(--text-channel);
  font-size: 12px;
  font-weight: 700;
  list-style: none;
}

.rag-debug-panel > summary::-webkit-details-marker {
  display: none;
}

.rag-debug-header {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.rag-debug-metrics {
  margin: 8px 0;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: var(--text-muted);
}

.rag-debug-section {
  margin-top: 8px;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.9);
}

.rag-debug-section > summary {
  cursor: pointer;
  font-size: 12px;
  color: var(--text);
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
  border-radius: 12px;
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

@media (max-width: 1200px) {
  .knowledge-panel {
    height: auto;
  }
}
</style>
