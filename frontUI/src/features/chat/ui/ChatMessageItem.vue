<script setup>
import AgentTracePanel from "@/features/chat/ui/AgentTracePanel.vue";
import RagMessageDebug from "@/features/chat/ui/RagMessageDebug.vue";
import { getMessageRagDebug, getMessageTraceSteps } from "@/entities/chat/lib/message";
import { useUiStore } from "@/shared/model/ui-store";
import MarkdownContent from "@/shared/ui/MarkdownContent.vue";

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
  traceDetailsVisible: {
    type: Boolean,
    default: false,
  },
  ragDebugEnabled: {
    type: Boolean,
    default: false,
  },
  ragDebugDetailsVisible: {
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

const isPendingAgent = (message) => message?.from === "agent" && Boolean(message?.pending);
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
        <div v-if="isPendingAgent(message)" class="msg-pending-card">
          <div class="msg-pending-line">
            <span class="msg-pending-dots" aria-hidden="true">
              <span></span>
              <span></span>
              <span></span>
            </span>
            <strong>{{ message.pendingStage || uiStore.t("assistantWorking") }}</strong>
          </div>
          <p>{{ uiStore.t("assistantWorkingHint") }}</p>
        </div>
        <MarkdownContent v-else :source="message.text" :markdown="message.from === 'agent'" class="msg-content" />
        <div v-if="message.from === 'agent' && message.noEvidence" class="rag-debug-mini">{{ uiStore.t("ragDebugNoEvidenceFlag") }}</div>
        <div v-if="message.from === 'agent' && !message.pending && message.citations?.length" class="agent-citations-panel">
          <div class="agent-citations-title">{{ uiStore.t("agentTraceCitationsTitle") }}</div>
          <ul class="agent-citations-list">
            <li v-for="(citation, citationIdx) in message.citations" :key="`citation_${citationIdx}`" class="agent-citation-item">
              {{ citationLabel(citation) }}
            </li>
          </ul>
        </div>
        <div v-else-if="showGroundingMeta(message) && !message.noEvidence && !message.pending" class="rag-debug-mini">
          {{ uiStore.t("agentTraceNoCitations") }}
        </div>
        <AgentTracePanel
          v-if="agentTraceEnabled && message.from === 'agent' && !message.pending && traceStepsForMessage(message).length"
          :steps="traceStepsForMessage(message)"
          :details-visible="traceDetailsVisible"
          :title-resolver="traceTitle"
          :status-resolver="traceStatus"
          :detail-entries-resolver="traceDetailsEntries"
        />
        <RagMessageDebug
          v-if="ragDebugEnabled && message.from === 'agent' && !message.pending"
          :debug-payload="ragDebugForMessage(message)"
          :detailed="ragDebugDetailsVisible"
        />
      </div>
    </template>
    <template v-else>
      <div class="msg-avatar is-empty"></div>
      <div class="msg-body">
        <MarkdownContent :source="message.text" :markdown="message.from === 'agent'" class="msg-content" />
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
          :details-visible="false"
          :title-resolver="traceTitle"
          :status-resolver="traceStatus"
          :detail-entries-resolver="traceDetailsEntries"
          summary-only
        />
        <RagMessageDebug
          v-if="ragDebugEnabled && message.from === 'agent'"
          :debug-payload="ragDebugForMessage(message)"
          :detailed="ragDebugDetailsVisible"
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
  padding: 10px 24px;
  transition: background 0.18s ease;
}

.msg-row:hover {
  background: rgba(47, 107, 255, 0.04);
}

.msg-row.is-first {
  padding-top: 20px;
}

.msg-avatar {
  width: 42px;
  height: 42px;
  border-radius: 16px;
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
  background: linear-gradient(135deg, #1f9d74, #54caa2);
}

.msg-avatar.is-empty {
  background: transparent;
}

.msg-body {
  flex: 1;
  min-width: 0;
  max-width: 88ch;
}

.msg-meta {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}

.msg-author {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  cursor: pointer;
}

.msg-author:hover {
  text-decoration: none;
}

.msg-timestamp {
  font-size: 12px;
  color: var(--text-muted);
}

.msg-content {
  margin-top: 0;
}

.msg-pending-card {
  display: grid;
  gap: 10px;
  margin-top: 4px;
  padding: 14px 16px;
  border: 1px solid rgba(47, 107, 255, 0.12);
  border-radius: 18px;
  background: var(--surface-panel-subtle);
}

.msg-pending-line {
  display: flex;
  align-items: center;
  gap: 12px;
}

.msg-pending-line strong {
  color: var(--text);
  font-size: 14px;
}

.msg-pending-card p {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}

.msg-pending-dots {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.msg-pending-dots span {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  animation: pendingPulse 1.2s ease-in-out infinite;
}

.msg-pending-dots span:nth-child(2) {
  animation-delay: 0.15s;
}

.msg-pending-dots span:nth-child(3) {
  animation-delay: 0.3s;
}

.rag-debug-mini {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.agent-citations-panel {
  margin-top: 12px;
}

.agent-citations-title {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 10px;
}

.agent-citations-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-citation-item {
  font-size: 12px;
  color: var(--text-channel);
  border: 1px solid rgba(47, 107, 255, 0.12);
  border-radius: 999px;
  padding: 7px 10px;
  background: rgba(47, 107, 255, 0.05);
}

@keyframes pendingPulse {
  0%,
  80%,
  100% {
    transform: scale(0.72);
    opacity: 0.45;
  }

  40% {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
