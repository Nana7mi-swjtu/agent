<script setup>
import { useUiStore } from "@/stores/ui";
import { canDeleteRagDocument, getRagDocumentActionType } from "@/shared/lib/rag";

const props = defineProps({
  channelName: {
    type: String,
    default: "",
  },
  systemPrompt: {
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
  <div>
    <div class="dc-toolbar">
      <span class="ch-hash">#</span>
      <span class="ch-name">{{ channelName }}</span>
      <span class="toolbar-divider"></span>
      <span class="ch-topic">{{ systemPrompt || "-" }}</span>
      <span class="badge-pill">{{ selectedRoleName || "-" }}</span>
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
      <button class="toolbar-upload-btn" :disabled="ragUploading">
        {{ uiStore.t("ragUploadFile") }}
        <input
          type="file"
          accept=".pdf,.docx,.md,.txt,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          @change="emit('choose-document', $event)"
        />
      </button>
    </div>
    <div class="rag-applied-row">{{ uiStore.t("ragUploadFormatsHint") }}</div>

    <div class="rag-status-row">
      <span class="rag-status-text">{{ ragStageText || uiStore.t("ragUploadIdle") }}</span>
      <div class="rag-progress-bar">
        <div class="rag-progress-fill" :style="{ width: `${uploadPercent}%` }"></div>
      </div>
      <button class="panel-icon-btn rag-refresh-btn" :title="uiStore.t('loading')" @click="emit('load-documents')">↻</button>
    </div>
    <div v-if="chunkingAppliedText" class="rag-applied-row">{{ chunkingAppliedText }}</div>
    <div v-if="ragError" class="msg-err rag-inline-err">{{ ragError }}</div>
    <div class="rag-docs-panel">
      <div class="rag-docs-title">{{ uiStore.t("ragUploadedFiles") }}</div>
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
    <div v-if="ragDebugEnabled" class="rag-debug-panel">
      <div class="rag-debug-header">
        <div class="rag-docs-title">{{ uiStore.t("ragDebugPanelTitle") }}</div>
        <button class="panel-icon-btn rag-refresh-btn" :title="uiStore.t('loading')" @click="emit('load-rag-debug-snapshot')">↻</button>
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
    </div>
  </div>
</template>

<style scoped>
.dc-toolbar {
  height: 48px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid var(--line);
  gap: 8px;
  flex-shrink: 0;
  background: var(--bg-main);
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.2);
}

.ch-hash {
  font-size: 22px;
  font-weight: 900;
  color: var(--text-muted);
  line-height: 1;
}

.ch-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  flex: 1;
}

.ch-topic {
  font-size: 14px;
  color: var(--text-muted);
  max-width: 40ch;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.toolbar-upload-btn {
  position: relative;
  border: 1px solid var(--line);
  background: var(--bg-overlay);
  color: var(--text);
  font-size: 12px;
  border-radius: 6px;
  padding: 6px 10px;
  cursor: pointer;
}

.toolbar-upload-btn input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.toolbar-upload-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.rag-strategy-select {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.rag-strategy-select select {
  border: 1px solid var(--line);
  background: var(--bg-input);
  color: var(--text);
  border-radius: 6px;
  padding: 4px 6px;
  font-size: 12px;
}

.toolbar-divider {
  width: 1px;
  height: 24px;
  background: var(--line);
  margin: 0 4px;
}

.badge-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  background: var(--accent);
  color: #fff;
}

.rag-status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px 0;
}

.rag-status-text {
  min-width: 120px;
  font-size: 12px;
  color: var(--text-muted);
}

.rag-progress-bar {
  flex: 1;
  height: 8px;
  background: var(--bg-input);
  border-radius: 999px;
  overflow: hidden;
}

.rag-progress-fill {
  height: 100%;
  width: 0;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
  transition: width 0.2s ease;
}

.rag-refresh-btn {
  width: 24px;
  height: 24px;
  font-size: 13px;
}

.rag-inline-err {
  margin: 8px 16px 0;
}

.rag-applied-row {
  margin: 6px 16px 0;
  font-size: 12px;
  color: var(--text-muted);
}

.rag-docs-panel {
  margin: 10px 16px 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--bg-overlay);
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
  gap: 6px;
}

.rag-doc-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
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
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rag-doc-status {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
}

.rag-doc-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.rag-doc-action-btn {
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.04);
  color: var(--text);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
}

.rag-doc-action-btn:hover:not(:disabled) {
  background: var(--bg-hover);
}

.rag-doc-action-btn.is-danger {
  color: #ffb5b7;
  border-color: rgba(242, 63, 67, 0.4);
}

.rag-doc-action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.rag-doc-empty {
  font-size: 13px;
  color: var(--text-muted);
}

.rag-debug-panel {
  margin: 10px 16px 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--bg-overlay);
}

.rag-debug-header {
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
  border-radius: 6px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.02);
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
