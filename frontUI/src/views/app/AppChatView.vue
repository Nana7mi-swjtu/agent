<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { storeToRefs } from "pinia";

import { useChatSession } from "@/composables/useChatSession";
import { useWorkspaceStore } from "@/stores/workspace";
import { useUiStore } from "@/stores/ui";
import { formatTraceDetailValue, getMessageRagDebug, getMessageTraceSteps } from "@/utils/chatMessage";
import { canDeleteRagDocument, getRagDocumentActionType } from "@/utils/rag";
import KnowledgeGraphCard from "@/components/chat/KnowledgeGraphCard.vue";

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
  agentTraceEnabled,
  ragDebugSnapshot,
  chunkingStrategy,
  chunkingAppliedText,
  ragActionDocumentId,
  loadDocuments,
  uploadDocument,
  startDocumentIndex,
  removeDocument,
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

const documentActionLabel = (document) => {
  const actionType = getRagDocumentActionType(document);
  if (actionType === "start") return uiStore.t("ragDocumentStartIndexing");
  if (actionType === "retry") return uiStore.t("ragDocumentRetry");
  if (actionType === "reindex") return uiStore.t("ragDocumentReindex");
  return "";
};

const onRunDocumentAction = async (document) => {
  await startDocumentIndex(document?.id);
};

const onDeleteDocument = async (document) => {
  await removeDocument(document?.id);
};

const isDocumentBusy = (document) => Number(ragActionDocumentId.value) === Number(document?.id);

const traceTitleMap = {
  planner: "agentTraceStepPlanner",
  clarify: "agentTraceStepClarify",
  search_subagent: "agentTraceStepSearchSubagent",
  rag_lookup: "agentTraceStepRagLookup",
  web_lookup: "agentTraceStepWebLookup",
  merge_results: "agentTraceStepMergeResults",
  mcp_subagent: "agentTraceStepMcpSubagent",
  compose_answer: "agentTraceStepComposeAnswer",
  citations: "agentTraceStepCitations",
};

const traceTitle = (step) => {
  const key = traceTitleMap[String(step?.id || "").trim()];
  return key ? uiStore.t(key) : step?.title || step?.id || "-";
};

const traceStatus = (step) => String(step?.status || "done").replaceAll("_", " ");

const traceDetailsEntries = (step) =>
  step?.details && typeof step.details === "object" ? Object.entries(step.details) : [];

const ragDebugForMessage = (msg) => getMessageRagDebug(msg);
const traceStepsForMessage = (msg) => getMessageTraceSteps(msg);
const showGroundingMeta = (msg) =>
  msg?.from === "agent" &&
  (
    Boolean(msg?.noEvidence)
    || (Array.isArray(msg?.citations) && msg.citations.length > 0)
    || traceStepsForMessage(msg).length > 0
    || Boolean(ragDebugForMessage(msg))
  );
const citationLabel = (citation) => {
  if (!citation || typeof citation !== "object") return "-";
  const labels = [String(citation.source || "-")];
  if (citation.page != null) labels.push(`p.${citation.page}`);
  if (citation.section) labels.push(String(citation.section));
  return labels.join(" · ");
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
        <input
          type="file"
          accept=".pdf,.docx,.md,.txt,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          @change="onChooseDocument"
        />
      </button>
    </div>
    <div class="rag-applied-row">{{ uiStore.t("ragUploadFormatsHint") }}</div>

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
              @click="onRunDocumentAction(doc)"
            >
              {{ documentActionLabel(doc) }}
            </button>
            <button
              v-if="canDeleteRagDocument(doc)"
              class="rag-doc-action-btn is-danger"
              :disabled="ragUploading || isDocumentBusy(doc)"
              @click="onDeleteDocument(doc)"
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
            <KnowledgeGraphCard v-if="msg.from === 'agent' && msg.graph" :graph="msg.graph" :graphMeta="msg.graphMeta" />
            <div v-if="msg.from === 'agent' && msg.noEvidence" class="rag-debug-mini">{{ uiStore.t("ragDebugNoEvidenceFlag") }}</div>
            <div v-if="msg.from === 'agent' && msg.citations?.length" class="agent-citations-panel">
              <div class="agent-citations-title">{{ uiStore.t("agentTraceCitationsTitle") }}</div>
              <ul class="agent-citations-list">
                <li v-for="(citation, citationIdx) in msg.citations" :key="`citation_${citationIdx}`" class="agent-citation-item">
                  {{ citationLabel(citation) }}
                </li>
              </ul>
            </div>
            <div v-else-if="showGroundingMeta(msg) && !msg.noEvidence" class="rag-debug-mini">
              {{ uiStore.t("agentTraceNoCitations") }}
            </div>
            <div v-if="agentTraceEnabled && msg.from === 'agent' && traceStepsForMessage(msg).length" class="agent-trace-panel">
              <div class="agent-trace-title">{{ uiStore.t("agentTracePanelTitle") }}</div>
              <div class="agent-trace-list">
                <div v-for="step in traceStepsForMessage(msg)" :key="step.id" class="agent-trace-step">
                  <div class="agent-trace-head">
                    <strong>{{ traceTitle(step) }}</strong>
                    <span class="agent-trace-status">{{ traceStatus(step) }}</span>
                  </div>
                  <div class="agent-trace-summary">{{ step.summary }}</div>
                  <div v-if="traceDetailsEntries(step).length" class="agent-trace-details">
                    <div class="rag-debug-mini">{{ uiStore.t("agentTraceDetailsLabel") }}</div>
                    <div
                      v-for="[key, value] in traceDetailsEntries(step)"
                      :key="`${step.id}_${key}`"
                      class="agent-trace-detail-row"
                    >
                      <span>{{ key }}</span>
                      <span>{{ formatTraceDetailValue(value) }}</span>
                    </div>
                  </div>
                  <div v-if="Array.isArray(step.children) && step.children.length" class="agent-trace-children">
                    <div v-for="child in step.children" :key="child.id" class="agent-trace-child">
                      <div class="agent-trace-head">
                        <strong>{{ traceTitle(child) }}</strong>
                        <span class="agent-trace-status">{{ traceStatus(child) }}</span>
                      </div>
                      <div class="agent-trace-summary">{{ child.summary }}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="ragDebugEnabled && msg.from === 'agent'" class="rag-message-debug">
              <details v-if="ragDebugForMessage(msg)" class="rag-debug-section">
                <summary>{{ uiStore.t("ragDebugMessageSummary") }}</summary>
                <div class="rag-debug-grid">
                  <div>
                    <strong>{{ uiStore.t("ragDebugLabelEmbedding") }}</strong>
                    <div class="rag-debug-mini">
                      {{ ragDebugForMessage(msg)?.vector?.embedderProvider || "-" }} / {{ ragDebugForMessage(msg)?.vector?.embeddingModel || "-" }}
                    </div>
                    <div class="rag-debug-mini">
                      dim={{ ragDebugForMessage(msg)?.vector?.embeddingDimension ?? "-" }} norm={{ ragDebugForMessage(msg)?.vector?.queryVectorNorm ?? "-" }}
                    </div>
                    <div class="rag-debug-mini">
                      sample={{ (ragDebugForMessage(msg)?.vector?.queryVectorSample || []).join(", ") }}
                    </div>
                  </div>
                  <div>
                    <strong>{{ uiStore.t("ragDebugLabelRetrieval") }}</strong>
                    <div class="rag-debug-mini">
                      raw={{ ragDebugForMessage(msg)?.retrieval?.rawCount ?? 0 }}, threshold={{ ragDebugForMessage(msg)?.retrieval?.afterThresholdCount ?? 0 }}
                    </div>
                    <div class="rag-debug-mini">latency={{ ragDebugForMessage(msg)?.latencyMs ?? "-" }}ms</div>
                  </div>
                </div>
                <details class="rag-debug-section">
                  <summary>{{ uiStore.t("ragDebugLabelRetrievalRaw") }}</summary>
                  <ul class="rag-debug-list">
                    <li
                      v-for="item in ragDebugForMessage(msg)?.retrieval?.rawHits || []"
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
                      v-for="item in ragDebugForMessage(msg)?.rerank?.after || ragDebugForMessage(msg)?.rerank?.afterRuntimeSort || []"
                      :key="`rerank_${item.chunkId}`"
                      class="rag-debug-item"
                    >
                      <div><strong>{{ item.chunkId }}</strong> · {{ item.score }} · {{ item.source }}</div>
                      <div class="rag-debug-preview">{{ item.contentPreview }}</div>
                    </li>
                  </ul>
                </details>
              </details>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="msg-avatar is-empty"></div>
          <div class="msg-body">
            <div class="msg-content">{{ msg.text }}</div>
            <KnowledgeGraphCard v-if="msg.from === 'agent' && msg.graph" :graph="msg.graph" :graphMeta="msg.graphMeta" />
            <div v-if="msg.from === 'agent' && msg.noEvidence" class="rag-debug-mini">{{ uiStore.t("ragDebugNoEvidenceFlag") }}</div>
            <div v-if="msg.from === 'agent' && msg.citations?.length" class="agent-citations-panel">
              <div class="agent-citations-title">{{ uiStore.t("agentTraceCitationsTitle") }}</div>
              <ul class="agent-citations-list">
                <li v-for="(citation, citationIdx) in msg.citations" :key="`grouped_citation_${citationIdx}`" class="agent-citation-item">
                  {{ citationLabel(citation) }}
                </li>
              </ul>
            </div>
            <div v-else-if="showGroundingMeta(msg) && !msg.noEvidence" class="rag-debug-mini">
              {{ uiStore.t("agentTraceNoCitations") }}
            </div>
            <div v-if="agentTraceEnabled && msg.from === 'agent' && traceStepsForMessage(msg).length" class="agent-trace-panel">
              <div class="agent-trace-title">{{ uiStore.t("agentTracePanelTitle") }}</div>
              <div class="agent-trace-list">
                <div v-for="step in traceStepsForMessage(msg)" :key="`group_${step.id}`" class="agent-trace-step">
                  <div class="agent-trace-head">
                    <strong>{{ traceTitle(step) }}</strong>
                    <span class="agent-trace-status">{{ traceStatus(step) }}</span>
                  </div>
                  <div class="agent-trace-summary">{{ step.summary }}</div>
                </div>
              </div>
            </div>
            <div v-if="ragDebugEnabled && msg.from === 'agent'" class="rag-message-debug">
              <details v-if="ragDebugForMessage(msg)" class="rag-debug-section">
                <summary>{{ uiStore.t("ragDebugMessageSummary") }}</summary>
                <div class="rag-debug-mini">
                  {{ uiStore.t("ragDebugLabelEmbedding") }}:
                  {{ ragDebugForMessage(msg)?.vector?.embedderProvider || "-" }} /
                  {{ ragDebugForMessage(msg)?.vector?.embeddingModel || "-" }} /
                  dim={{ ragDebugForMessage(msg)?.vector?.embeddingDimension ?? "-" }}
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
