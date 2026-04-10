<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { storeToRefs } from "pinia";

import { useChatSession } from "@/composables/useChatSession";
import { useWorkspaceStore } from "@/stores/workspace";
import { useUiStore } from "@/stores/ui";

const router = useRouter();
const uiStore = useUiStore();
const workspaceStore = useWorkspaceStore();
const { ready } = storeToRefs(workspaceStore);
  const {
  input,
  selectedRole,
  selectedRoleName,
  systemPrompt,
  sending,
  chatError,
  activeSession,
  channelName,
  displayTime,
  ragUploading,
  uploadPercent,
  ragStageText,
    ragError,
  ragDocuments,
  ragDebugEnabled,
  ragDebugSnapshot,
  chunkingStrategy,
  chunkingAppliedText,
  loadDocuments,
  uploadDocument,
  loadRagDebugSnapshot,
  send,
} = useChatSession();

const sendMessage = async () => {
  const result = await send();
  if (result.noRole) {
    router.push("/app");
  }
};

onMounted(() => {
  if (!ready.value || !selectedRole.value) {
    router.push("/app");
    return;
  }
  loadDocuments();
});

const onChooseDocument = async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  await uploadDocument(file);
  event.target.value = "";
};

</script>

<template>
  <div class="dc-chat-layout">
    <div class="dc-toolbar">
      <span class="ch-hash">#</span>
      <span class="ch-name">{{ channelName }}</span>
      <span class="toolbar-divider"></span>
      <span class="ch-topic">{{ systemPrompt || "-" }}</span>
      <span class="badge-pill">{{ selectedRoleName || "-" }}</span>
      <label class="rag-strategy-select">
        <span>{{ uiStore.t("ragChunkStrategyLabel") }}</span>
        <select v-model="chunkingStrategy" :disabled="ragUploading">
          <option value="paragraph">{{ uiStore.t("ragChunkStrategyParagraph") }}</option>
          <option value="semantic_llm">{{ uiStore.t("ragChunkStrategySemanticLlm") }}</option>
        </select>
      </label>
      <button class="toolbar-upload-btn" :disabled="ragUploading">
        {{ uiStore.t("ragUploadFile") }}
        <input type="file" @change="onChooseDocument" />
      </button>
    </div>

    <div class="rag-status-row">
      <span class="rag-status-text">{{ ragStageText || uiStore.t("ragUploadIdle") }}</span>
      <div class="rag-progress-bar">
        <div class="rag-progress-fill" :style="{ width: `${uploadPercent}%` }"></div>
      </div>
      <button class="panel-icon-btn rag-refresh-btn" :title="uiStore.t('loading')" @click="loadDocuments">↻</button>
    </div>
    <div v-if="chunkingAppliedText" class="rag-applied-row">{{ chunkingAppliedText }}</div>
    <div v-if="ragError" class="msg-err rag-inline-err">{{ ragError }}</div>
    <div class="rag-docs-panel">
      <div class="rag-docs-title">{{ uiStore.t("ragUploadedFiles") }}</div>
      <ul class="rag-docs-list">
        <li v-for="doc in ragDocuments" :key="doc.id" class="rag-doc-item">
          <span class="rag-doc-name">{{ doc.sourceName || doc.fileName }}</span>
          <span class="rag-doc-status">
            {{ doc.status }}
            <template v-if="doc.chunkingApplied?.strategy"> · {{ doc.chunkingApplied.strategy }}</template>
            <template v-if="doc.chunkingApplied?.fallbackUsed"> ({{ uiStore.t("ragChunkFallback") }})</template>
          </span>
        </li>
        <li v-if="!ragDocuments.length" class="rag-doc-empty">{{ uiStore.t("ragNoFiles") }}</li>
      </ul>
    </div>
    <div v-if="ragDebugEnabled" class="rag-debug-panel">
      <div class="rag-debug-header">
        <div class="rag-docs-title">{{ uiStore.t("ragDebugPanelTitle") }}</div>
        <button class="panel-icon-btn rag-refresh-btn" :title="uiStore.t('loading')" @click="loadRagDebugSnapshot">↻</button>
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

    <div class="dc-feed">
      <div v-if="!activeSession || !activeSession.messages.length" class="feed-welcome">
        <h2># {{ channelName }}</h2>
        <p>{{ uiStore.t("inputPlaceholder") }}</p>
      </div>

      <article
        v-for="(msg, idx) in activeSession?.messages || []"
        :key="idx"
        class="msg-row"
        :class="{ 'is-first': idx === 0 || activeSession.messages[idx - 1].from !== msg.from }"
      >
        <template v-if="idx === 0 || activeSession.messages[idx - 1].from !== msg.from">
          <div class="msg-avatar" :class="{ 'is-agent': msg.from === 'agent' }">
            {{ msg.from === "user" ? "U" : "AI" }}
          </div>
          <div class="msg-body">
            <div class="msg-meta">
              <span class="msg-author">{{ msg.from === "user" ? "You" : "Agent Studio" }}</span>
              <span class="msg-timestamp">{{ displayTime(msg.time) }}</span>
            </div>
            <div class="msg-content">{{ msg.text }}</div>
            <div v-if="ragDebugEnabled && msg.from === 'agent'" class="rag-message-debug">
              <details v-if="msg.debug" class="rag-debug-section">
                <summary>{{ uiStore.t("ragDebugMessageSummary") }}</summary>
                <div class="rag-debug-grid">
                  <div>
                    <strong>{{ uiStore.t("ragDebugLabelEmbedding") }}</strong>
                    <div class="rag-debug-mini">
                      {{ msg.debug?.vector?.embedderProvider || "-" }} / {{ msg.debug?.vector?.embeddingModel || "-" }}
                    </div>
                    <div class="rag-debug-mini">
                      dim={{ msg.debug?.vector?.embeddingDimension ?? "-" }} norm={{ msg.debug?.vector?.queryVectorNorm ?? "-" }}
                    </div>
                    <div class="rag-debug-mini">
                      sample={{ (msg.debug?.vector?.queryVectorSample || []).join(", ") }}
                    </div>
                  </div>
                  <div>
                    <strong>{{ uiStore.t("ragDebugLabelRetrieval") }}</strong>
                    <div class="rag-debug-mini">
                      raw={{ msg.debug?.retrieval?.rawCount ?? 0 }}, threshold={{ msg.debug?.retrieval?.afterThresholdCount ?? 0 }}
                    </div>
                    <div class="rag-debug-mini">latency={{ msg.debug?.latencyMs ?? "-" }}ms</div>
                  </div>
                </div>
                <details class="rag-debug-section">
                  <summary>{{ uiStore.t("ragDebugLabelRetrievalRaw") }}</summary>
                  <ul class="rag-debug-list">
                    <li
                      v-for="item in msg.debug?.retrieval?.rawHits || []"
                      :key="`raw_${item.chunkId}`"
                      class="rag-debug-item"
                    >
                      <div><strong>{{ item.chunkId }}</strong> · {{ item.score }} · {{ item.source }}</div>
                      <div class="rag-debug-preview">{{ item.contentPreview }}</div>
                    </li>
                  </ul>
                </details>
                <details class="rag-debug-section">
                  <summary>{{ uiStore.t("ragDebugLabelRerankAfter") }}</summary>
                  <ul class="rag-debug-list">
                    <li
                      v-for="item in msg.debug?.rerank?.after || msg.debug?.rerank?.afterRuntimeSort || []"
                      :key="`rerank_${item.chunkId}`"
                      class="rag-debug-item"
                    >
                      <div><strong>{{ item.chunkId }}</strong> · {{ item.score }} · {{ item.source }}</div>
                      <div class="rag-debug-preview">{{ item.contentPreview }}</div>
                    </li>
                  </ul>
                </details>
              </details>
              <div v-if="msg.noEvidence" class="rag-debug-mini">{{ uiStore.t("ragDebugNoEvidenceFlag") }}</div>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="msg-avatar is-empty"></div>
          <div class="msg-body">
            <div class="msg-content">{{ msg.text }}</div>
            <div v-if="ragDebugEnabled && msg.from === 'agent'" class="rag-message-debug">
              <details v-if="msg.debug" class="rag-debug-section">
                <summary>{{ uiStore.t("ragDebugMessageSummary") }}</summary>
                <div class="rag-debug-mini">
                  {{ uiStore.t("ragDebugLabelEmbedding") }}:
                  {{ msg.debug?.vector?.embedderProvider || "-" }} /
                  {{ msg.debug?.vector?.embeddingModel || "-" }} /
                  dim={{ msg.debug?.vector?.embeddingDimension ?? "-" }}
                </div>
              </details>
            </div>
          </div>
        </template>
      </article>
    </div>

    <div class="dc-composer">
      <div class="dc-composer-inner">
        <input
          v-model="input"
          type="text"
          :placeholder="uiStore.t('inputPlaceholder')"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <button class="dc-composer-send" :disabled="sending" @click="sendMessage">➤</button>
      </div>
      <div class="msg-err" v-if="chatError">{{ chatError }}</div>
    </div>
  </div>
</template>
