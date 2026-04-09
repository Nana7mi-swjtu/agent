<script setup>
import AgentTracePanel from "@/features/chat/ui/AgentTracePanel.vue";
import RagMessageDebug from "@/features/chat/ui/RagMessageDebug.vue";
import { useUiStore } from "@/stores/ui";
import { getMessageRagDebug, getMessageTraceSteps } from "@/shared/lib/chatMessage";

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
  isGrouped: {
    type: Boolean,
    default: false,
  },
  displayTime: {
    type: Function,
    required: true,
  },
  agentTraceEnabled: {
    type: Boolean,
    default: false,
  },
  ragDebugEnabled: {
    type: Boolean,
    default: false,
  },
  traceTitle: {
    type: Function,
    required: true,
  },
  traceStatus: {
    type: Function,
    required: true,
  },
  traceDetailsEntries: {
    type: Function,
    required: true,
  },
});

const uiStore = useUiStore();

const ragDebugForMessage = (message) => getMessageRagDebug(message);
const traceStepsForMessage = (message) => getMessageTraceSteps(message);
const showGroundingMeta = (message) =>
  message?.from === "agent" &&
  (
    Boolean(message?.noEvidence)
    || (Array.isArray(message?.citations) && message.citations.length > 0)
    || traceStepsForMessage(message).length > 0
    || Boolean(ragDebugForMessage(message))
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
  <article class="msg-row" :class="{ 'is-first': !isGrouped }">
    <template v-if="!isGrouped">
      <div class="msg-avatar" :class="{ 'is-agent': message.from === 'agent' }">
        {{ message.from === "user" ? "U" : "AI" }}
      </div>
      <div class="msg-body">
        <div class="msg-meta">
          <span class="msg-author">{{ message.from === "user" ? "You" : "Agent Studio" }}</span>
          <span class="msg-timestamp">{{ displayTime(message.time) }}</span>
        </div>
        <div class="msg-content">{{ message.text }}</div>
        <div v-if="message.from === 'agent' && message.noEvidence" class="rag-debug-mini">{{ uiStore.t("ragDebugNoEvidenceFlag") }}</div>
        <div v-if="message.from === 'agent' && message.citations?.length" class="agent-citations-panel">
          <div class="agent-citations-title">{{ uiStore.t("agentTraceCitationsTitle") }}</div>
          <ul class="agent-citations-list">
            <li v-for="(citation, citationIdx) in message.citations" :key="`citation_${citationIdx}`" class="agent-citation-item">
              {{ citationLabel(citation) }}
            </li>
          </ul>
        </div>
        <div v-else-if="showGroundingMeta(message) && !message.noEvidence" class="rag-debug-mini">
          {{ uiStore.t("agentTraceNoCitations") }}
        </div>
        <AgentTracePanel
          v-if="agentTraceEnabled && message.from === 'agent' && traceStepsForMessage(message).length"
          :steps="traceStepsForMessage(message)"
          :title-resolver="traceTitle"
          :status-resolver="traceStatus"
          :detail-entries-resolver="traceDetailsEntries"
        />
        <RagMessageDebug
          v-if="ragDebugEnabled && message.from === 'agent'"
          :debug-payload="ragDebugForMessage(message)"
        />
      </div>
    </template>
    <template v-else>
      <div class="msg-avatar is-empty"></div>
      <div class="msg-body">
        <div class="msg-content">{{ message.text }}</div>
        <div v-if="message.from === 'agent' && message.noEvidence" class="rag-debug-mini">{{ uiStore.t("ragDebugNoEvidenceFlag") }}</div>
        <div v-if="message.from === 'agent' && message.citations?.length" class="agent-citations-panel">
          <div class="agent-citations-title">{{ uiStore.t("agentTraceCitationsTitle") }}</div>
          <ul class="agent-citations-list">
            <li v-for="(citation, citationIdx) in message.citations" :key="`grouped_citation_${citationIdx}`" class="agent-citation-item">
              {{ citationLabel(citation) }}
            </li>
          </ul>
        </div>
        <div v-else-if="showGroundingMeta(message) && !message.noEvidence" class="rag-debug-mini">
          {{ uiStore.t("agentTraceNoCitations") }}
        </div>
        <AgentTracePanel
          v-if="agentTraceEnabled && message.from === 'agent' && traceStepsForMessage(message).length"
          :steps="traceStepsForMessage(message)"
          :title-resolver="traceTitle"
          :status-resolver="traceStatus"
          :detail-entries-resolver="traceDetailsEntries"
          summary-only
        />
        <RagMessageDebug
          v-if="ragDebugEnabled && message.from === 'agent'"
          :debug-payload="ragDebugForMessage(message)"
          condensed
        />
      </div>
    </template>
  </article>
</template>

<style scoped>
.msg-row {
  display: flex;
  gap: 16px;
  padding: 2px 16px;
  transition: background 0.1s;
}

.msg-row:hover {
  background: rgba(0, 0, 0, 0.06);
}

.msg-row.is-first {
  padding-top: 16px;
  margin-top: 8px;
}

.msg-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 800;
  color: #fff;
  flex-shrink: 0;
  margin-top: 2px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
}

.msg-avatar.is-agent {
  background: linear-gradient(135deg, #3ba55d, #1f8b4c);
}

.msg-avatar.is-empty {
  background: transparent;
}

.msg-body {
  flex: 1;
  min-width: 0;
}

.msg-meta {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 2px;
}

.msg-author {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  cursor: pointer;
}

.msg-author:hover {
  text-decoration: underline;
}

.msg-timestamp {
  font-size: 12px;
  color: var(--text-muted);
}

.msg-content {
  font-size: 15px;
  line-height: 1.55;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.rag-debug-mini {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.agent-citations-panel {
  margin-top: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.02);
}

.agent-citations-title {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

.agent-citations-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.agent-citation-item {
  font-size: 12px;
  color: var(--text-muted);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 6px 8px;
}
</style>
