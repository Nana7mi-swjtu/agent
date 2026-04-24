<script setup>
import { ref } from "vue";

import AgentTracePanel from "@/features/chat/ui/AgentTracePanel.vue";
import KnowledgeGraphPanel from "@/features/chat/ui/KnowledgeGraphPanel.vue";
import RagMessageDebug from "@/features/chat/ui/RagMessageDebug.vue";
import {
  formatSourceMeta,
  getMessageMemoryInfo,
  getMessageRagDebug,
  getMessageSources,
  getMessageTraceSteps,
} from "@/entities/chat/lib/message";
import { buildApiUrl } from "@/shared/api/client";
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
  generateReport: {
    type: Function,
    default: () => {},
  },
  regenerateReport: {
    type: Function,
    default: () => {},
  },
});

const uiStore = useUiStore();
const selectedGenerateRenderStyle = ref("professional");
const selectedRegenerateRenderStyle = ref("professional");

const ragDebugForMessage = (message) => getMessageRagDebug(message);
const traceStepsForMessage = (message) => getMessageTraceSteps(message);
const sourcesForMessage = (message) => getMessageSources(message);
const memoryInfoForMessage = (message) => getMessageMemoryInfo(message);
const reportForMessage = (message) =>
  message?.analysisReport && typeof message.analysisReport === "object" ? message.analysisReport : null;
const reportRequestForMessage = (message) =>
  message?.reportGenerationRequest && typeof message.reportGenerationRequest === "object" ? message.reportGenerationRequest : null;
const renderStylesForRequest = (request) =>
  Array.isArray(request?.renderStyles) && request.renderStyles.length
    ? request.renderStyles
    : [{ id: "professional", label: "专业白底" }];
const renderStylesForReport = (report) =>
  Array.isArray(report?.regeneration?.renderStyles) && report.regeneration.renderStyles.length
    ? report.regeneration.renderStyles
    : [{ id: "professional", label: "专业白底" }];
const resolveReportDownloadUrl = (url) => {
  const cleanUrl = String(url || "").trim();
  if (!cleanUrl) return "";
  if (/^https?:\/\//i.test(cleanUrl)) return cleanUrl;
  return cleanUrl.startsWith("/api/") ? buildApiUrl(cleanUrl) : cleanUrl;
};
const reportPreviewUrl = (message) => resolveReportDownloadUrl(reportForMessage(message)?.previewUrl);
const reportDownloadEntries = (message) => {
  const report = reportForMessage(message);
  const urls = report?.downloadUrls && typeof report.downloadUrls === "object" ? report.downloadUrls : {};
  return [
    { key: "pdf", label: "PDF", url: resolveReportDownloadUrl(urls.pdf) },
  ].filter((item) => item.url);
};
const runReportGeneration = (message) => {
  const request = reportRequestForMessage(message);
  if (!request) return;
  props.generateReport(request, selectedGenerateRenderStyle.value || request.defaultRenderStyle || "professional");
};
const runReportRegeneration = (message) => {
  const report = reportForMessage(message);
  if (!report) return;
  props.regenerateReport(report, selectedRegenerateRenderStyle.value || report.renderStyle || "professional");
};
const showGroundingMeta = (message) =>
  message?.from === "agent" &&
  (
    Boolean(message?.noEvidence)
    || sourcesForMessage(message).length > 0
    || (Array.isArray(message?.citations) && message.citations.length > 0)
    || traceStepsForMessage(message).length > 0
    || Boolean(ragDebugForMessage(message))
  );

const isPendingAgent = (message) => message?.from === "agent" && Boolean(message?.pending);
const sourceMeta = (source) => formatSourceMeta(source);
const graphForMessage = (message) => {
  const graph = message?.graph;
  if (!graph || typeof graph !== "object") return null;
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  if (!nodes.length && !edges.length) return null;
  return { nodes, edges };
};
const graphMetaForMessage = (message) =>
  message?.graphMeta && typeof message.graphMeta === "object" ? message.graphMeta : {};
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
        <div v-if="message.from === 'agent' && !message.pending && reportRequestForMessage(message)" class="analysis-report-preview">
          <div class="analysis-report-title">生成综合报告</div>
          <p class="analysis-report-copy">模块分析结果已完成。它们将作为正式报告的证据与素材输入；下一步仅需选择渲染风格，系统会起草带独立封面、目录和正文结构的正式报告。</p>
          <div class="analysis-report-actions">
            <select v-model="selectedGenerateRenderStyle" class="analysis-report-select" aria-label="报告渲染风格">
              <option
                v-for="style in renderStylesForRequest(reportRequestForMessage(message))"
                :key="style.id"
                :value="style.id"
              >
                {{ style.label || style.id }}
              </option>
            </select>
            <button type="button" class="analysis-report-button" @click="runReportGeneration(message)">生成报告</button>
          </div>
        </div>
        <div v-if="message.from === 'agent' && !message.pending && reportForMessage(message)" class="analysis-report-preview">
          <div class="analysis-report-title">{{ reportForMessage(message).title || "分析报告" }}</div>
          <p class="analysis-report-copy">报告已生成。可先打开完整预览核对封面、目录与编排后的正文结构，再按需下载或仅更换渲染风格重新生成。</p>
          <div class="analysis-report-actions">
            <a
              v-if="reportPreviewUrl(message)"
              class="analysis-report-button is-link"
              :href="reportPreviewUrl(message)"
              target="_blank"
              rel="noreferrer noopener"
            >
              完整预览
            </a>
            <a
              v-for="item in reportDownloadEntries(message)"
              :key="`${message.id}_report_${item.key}`"
              class="analysis-report-button is-link"
              :href="item.url"
              target="_blank"
              rel="noreferrer noopener"
            >
              下载 {{ item.label }}
            </a>
            <select v-model="selectedRegenerateRenderStyle" class="analysis-report-select" aria-label="重新生成风格">
              <option
                v-for="style in renderStylesForReport(reportForMessage(message))"
                :key="style.id"
                :value="style.id"
              >
                {{ style.label || style.id }}
              </option>
            </select>
            <button type="button" class="analysis-report-button" @click="runReportRegeneration(message)">重新生成</button>
          </div>
        </div>
        <KnowledgeGraphPanel
          v-if="message.from === 'agent' && !message.pending && graphForMessage(message)"
          :graph="graphForMessage(message)"
          :graph-meta="graphMetaForMessage(message)"
        />
        <div v-if="message.from === 'agent' && message.noEvidence" class="rag-debug-mini">{{ uiStore.t("ragDebugNoEvidenceFlag") }}</div>
        <div v-if="message.from === 'agent' && !message.pending && memoryInfoForMessage(message)?.memoryUsed" class="memory-context-info">
          <small>💭 {{ uiStore.t("memoryContextUsed") }}{{ memoryInfoForMessage(message).memoryMessageCount }}{{ uiStore.t("memoryContextMessages") }}</small>
        </div>
        <div v-if="message.from === 'agent' && !message.pending && sourcesForMessage(message).length" class="agent-sources-panel">
          <div class="agent-sources-title">{{ uiStore.t("agentTraceCitationsTitle") }}</div>
          <div class="agent-sources-list">
            <component
              :is="source.kind === 'web' && source.url ? 'a' : 'div'"
              v-for="(source, sourceIdx) in sourcesForMessage(message)"
              :key="source.id || `${message.id}_source_${sourceIdx}`"
              class="agent-source-item"
              :class="{ 'is-web': source.kind === 'web' && source.url }"
              v-bind="source.kind === 'web' && source.url ? { href: source.url, target: '_blank', rel: 'noreferrer noopener' } : {}"
            >
              <strong>{{ source.title || source.source || "-" }}</strong>
              <span>{{ sourceMeta(source) }}</span>
            </component>
          </div>
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
        <div v-if="message.from === 'agent' && !message.pending && reportRequestForMessage(message)" class="analysis-report-preview">
          <div class="analysis-report-title">生成综合报告</div>
          <p class="analysis-report-copy">模块分析结果已完成。它们将作为正式报告的证据与素材输入；下一步仅需选择渲染风格，系统会起草带独立封面、目录和正文结构的正式报告。</p>
          <div class="analysis-report-actions">
            <select v-model="selectedGenerateRenderStyle" class="analysis-report-select" aria-label="报告渲染风格">
              <option
                v-for="style in renderStylesForRequest(reportRequestForMessage(message))"
                :key="style.id"
                :value="style.id"
              >
                {{ style.label || style.id }}
              </option>
            </select>
            <button type="button" class="analysis-report-button" @click="runReportGeneration(message)">生成报告</button>
          </div>
        </div>
        <div v-if="message.from === 'agent' && !message.pending && reportForMessage(message)" class="analysis-report-preview">
          <div class="analysis-report-title">{{ reportForMessage(message).title || "分析报告" }}</div>
          <p class="analysis-report-copy">报告已生成。可先打开完整预览核对封面、目录与编排后的正文结构，再按需下载或仅更换渲染风格重新生成。</p>
          <div class="analysis-report-actions">
            <a
              v-if="reportPreviewUrl(message)"
              class="analysis-report-button is-link"
              :href="reportPreviewUrl(message)"
              target="_blank"
              rel="noreferrer noopener"
            >
              完整预览
            </a>
            <a
              v-for="item in reportDownloadEntries(message)"
              :key="`${message.id}_grouped_report_${item.key}`"
              class="analysis-report-button is-link"
              :href="item.url"
              target="_blank"
              rel="noreferrer noopener"
            >
              下载 {{ item.label }}
            </a>
            <select v-model="selectedRegenerateRenderStyle" class="analysis-report-select" aria-label="重新生成风格">
              <option
                v-for="style in renderStylesForReport(reportForMessage(message))"
                :key="style.id"
                :value="style.id"
              >
                {{ style.label || style.id }}
              </option>
            </select>
            <button type="button" class="analysis-report-button" @click="runReportRegeneration(message)">重新生成</button>
          </div>
        </div>
        <KnowledgeGraphPanel
          v-if="message.from === 'agent' && !message.pending && graphForMessage(message)"
          :graph="graphForMessage(message)"
          :graph-meta="graphMetaForMessage(message)"
          compact
        />
        <div v-if="message.from === 'agent' && message.noEvidence" class="rag-debug-mini">{{ uiStore.t("ragDebugNoEvidenceFlag") }}</div>
        <div v-if="message.from === 'agent' && memoryInfoForMessage(message)?.memoryUsed" class="memory-context-info">
          <small>💭 {{ uiStore.t("memoryContextUsed") }}{{ memoryInfoForMessage(message).memoryMessageCount }}{{ uiStore.t("memoryContextMessages") }}</small>
        </div>
        <div v-if="message.from === 'agent' && sourcesForMessage(message).length" class="agent-sources-panel">
          <div class="agent-sources-title">{{ uiStore.t("agentTraceCitationsTitle") }}</div>
          <div class="agent-sources-list">
            <component
              :is="source.kind === 'web' && source.url ? 'a' : 'div'"
              v-for="(source, sourceIdx) in sourcesForMessage(message)"
              :key="source.id || `${message.id}_grouped_source_${sourceIdx}`"
              class="agent-source-item"
              :class="{ 'is-web': source.kind === 'web' && source.url }"
              v-bind="source.kind === 'web' && source.url ? { href: source.url, target: '_blank', rel: 'noreferrer noopener' } : {}"
            >
              <strong>{{ source.title || source.source || "-" }}</strong>
              <span>{{ sourceMeta(source) }}</span>
            </component>
          </div>
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

.analysis-report-preview {
  margin-top: 14px;
  padding-left: 14px;
  border-left: 3px solid rgba(31, 157, 116, 0.45);
}

.analysis-report-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
}

.analysis-report-copy {
  margin: 0;
  color: var(--text-channel);
  font-size: 12px;
  line-height: 1.5;
}

.analysis-report-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.analysis-report-select {
  min-height: 34px;
  max-width: 180px;
  border: 1px solid rgba(47, 107, 255, 0.18);
  border-radius: 6px;
  background: var(--surface-panel);
  color: var(--text);
  font-size: 13px;
  font-weight: 650;
}

.analysis-report-button {
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid rgba(31, 157, 116, 0.24);
  border-radius: 6px;
  background: rgba(31, 157, 116, 0.08);
  font-size: 13px;
  font-weight: 650;
  color: #13795b;
  text-decoration: none;
  cursor: pointer;
}

.analysis-report-button:hover {
  border-color: rgba(31, 157, 116, 0.42);
  background: rgba(31, 157, 116, 0.14);
}

.analysis-report-button.is-link {
  display: inline-flex;
  align-items: center;
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

.memory-context-info {
  margin-top: 10px;
  padding: 6px 12px;
  border-radius: 6px;
  background: rgba(99, 102, 241, 0.08);
  color: rgb(79, 70, 229);
  font-size: 12px;
  line-height: 1.4;
}

.agent-sources-panel {
  margin-top: 12px;
}

.agent-sources-title {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 10px;
}

.agent-sources-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-source-item {
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
  max-width: 100%;
  border: 1px solid rgba(47, 107, 255, 0.12);
  border-radius: 16px;
  padding: 10px 12px;
  background: rgba(47, 107, 255, 0.05);
  text-decoration: none;
}

.agent-source-item strong {
  font-size: 12px;
  color: var(--text);
}

.agent-source-item span {
  font-size: 12px;
  color: var(--text-channel);
}

.agent-source-item.is-web:hover {
  border-color: rgba(47, 107, 255, 0.3);
  background: rgba(47, 107, 255, 0.1);
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
