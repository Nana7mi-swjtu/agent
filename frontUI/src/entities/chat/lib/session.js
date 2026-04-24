import {
  SUPPORTED_ANALYSIS_MODULE_IDS,
  normalizeAnalysisModuleIds,
} from "../../analysis-module/model/registry.js";

export const buildConversationId = () => `c_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
export const buildMessageId = () => `m_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
export { SUPPORTED_ANALYSIS_MODULE_IDS };

const normalizeTrace = (raw) => (raw && typeof raw === "object" ? raw : null);
const normalizeSources = (raw) => (Array.isArray(raw) ? raw.filter((item) => item && typeof item === "object") : []);
const normalizeGraph = (raw) => {
  if (!raw || typeof raw !== "object") return null;
  const nodes = Array.isArray(raw.nodes) ? raw.nodes.filter((item) => item && typeof item === "object") : [];
  const edges = Array.isArray(raw.edges) ? raw.edges.filter((item) => item && typeof item === "object") : [];
  if (!nodes.length && !edges.length) return null;
  return { nodes, edges };
};
const normalizeGraphMeta = (raw) => (raw && typeof raw === "object" ? raw : null);
export const normalizeSelectedAnalysisModules = (raw) => normalizeAnalysisModuleIds(raw);
const normalizeModuleArtifactArray = (raw) =>
  Array.isArray(raw) ? raw.filter((item) => item && typeof item === "object") : [];
const normalizeRenderStyles = (raw) =>
  Array.isArray(raw)
    ? raw
        .filter((item) => item && typeof item === "object")
        .map((item) => ({
          id: String(item.id || "").trim(),
          label: String(item.label || item.id || "").trim(),
        }))
        .filter((item) => item.id)
    : [];
const normalizeReportRegeneration = (raw) => {
  if (!raw || typeof raw !== "object") return null;
  return {
    allowed: raw.allowed !== false,
    reportId: String(raw.reportId || "").trim(),
    renderStyles: normalizeRenderStyles(raw.renderStyles),
    defaultRenderStyle: String(raw.defaultRenderStyle || "professional").trim() || "professional",
  };
};
const normalizeAnalysisReport = (raw) => {
  if (!raw || typeof raw !== "object") return null;
  const reportId = String(raw.reportId || "").trim();
  if (!reportId) return null;
  const downloadUrls = raw.downloadUrls && typeof raw.downloadUrls === "object" ? raw.downloadUrls : {};
  return {
    reportId,
    title: String(raw.title || ""),
    status: String(raw.status || ""),
    preview: String(raw.preview || ""),
    availableFormats: Array.isArray(raw.availableFormats) ? raw.availableFormats.map((item) => String(item)) : [],
    downloadUrls: {
      pdf: String(downloadUrls.pdf || ""),
    },
    previewUrl: String(raw.previewUrl || ""),
    renderStyle: String(raw.renderStyle || "professional"),
    regeneration: normalizeReportRegeneration(raw.regeneration),
    limitations: Array.isArray(raw.limitations) ? raw.limitations.filter((item) => item && typeof item === "object") : [],
  };
};
const normalizeAnalysisModuleArtifact = (raw) => {
  if (!raw || typeof raw !== "object") return null;
  const artifactId = String(raw.artifactId || "").trim();
  if (!artifactId) return null;
  return {
    artifactId,
    moduleId: String(raw.moduleId || "").trim(),
    moduleRunId: String(raw.moduleRunId || "").trim(),
    title: String(raw.title || "模块分析结果"),
    status: String(raw.status || ""),
    contentType: String(raw.contentType || "text/markdown"),
    markdownBody: String(raw.markdownBody || ""),
    displayComposition: raw.displayComposition && typeof raw.displayComposition === "object" ? raw.displayComposition : null,
    executiveSummary: raw.executiveSummary && typeof raw.executiveSummary === "object" ? raw.executiveSummary : null,
    readerPacket: raw.readerPacket && typeof raw.readerPacket === "object" ? raw.readerPacket : null,
    evidenceReferences: normalizeModuleArtifactArray(raw.evidenceReferences),
    factTables: normalizeModuleArtifactArray(raw.factTables),
    chartCandidates: normalizeModuleArtifactArray(raw.chartCandidates),
    renderedAssets: normalizeModuleArtifactArray(raw.renderedAssets),
    visualSummaries: normalizeModuleArtifactArray(raw.visualSummaries),
    analysisSession: raw.analysisSession && typeof raw.analysisSession === "object" ? raw.analysisSession : null,
    metadata: raw.metadata && typeof raw.metadata === "object" ? raw.metadata : null,
  };
};
const normalizeReportGenerationRequest = (raw) => {
  if (!raw || typeof raw !== "object") return null;
  const moduleArtifactIds = Array.isArray(raw.moduleArtifactIds)
    ? raw.moduleArtifactIds.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  if (!moduleArtifactIds.length) return null;
  return {
    requestId: String(raw.requestId || ""),
    analysisSessionId: String(raw.analysisSessionId || ""),
    analysisSessionRevision: Number.isInteger(raw.analysisSessionRevision) ? raw.analysisSessionRevision : 0,
    moduleArtifactIds,
    renderStyles: normalizeRenderStyles(raw.renderStyles),
    defaultRenderStyle: String(raw.defaultRenderStyle || "professional").trim() || "professional",
  };
};

export const normalizeChatMessage = (raw) => ({
  id: String(raw?.id || buildMessageId()),
  from: raw?.from === "agent" ? "agent" : "user",
  text: String(raw?.text || ""),
  time: typeof raw?.time === "string" ? raw.time : new Date().toISOString(),
  citations: Array.isArray(raw?.citations) ? raw.citations : [],
  sources: normalizeSources(raw?.sources),
  noEvidence: Boolean(raw?.noEvidence),
  debug: raw?.debug && typeof raw.debug === "object" ? raw.debug : null,
  trace: normalizeTrace(raw?.trace),
  graph: normalizeGraph(raw?.graph),
  graphMeta: normalizeGraphMeta(raw?.graphMeta),
  analysisModuleArtifact: normalizeAnalysisModuleArtifact(raw?.analysisModuleArtifact),
  reportGenerationRequest: normalizeReportGenerationRequest(raw?.reportGenerationRequest),
  analysisReport: normalizeAnalysisReport(raw?.analysisReport),
  memoryInfo: raw?.memoryInfo && typeof raw.memoryInfo === "object" ? raw.memoryInfo : null,
  jobId: raw?.jobId ? String(raw.jobId) : "",
  jobStatus: typeof raw?.jobStatus === "string" ? raw.jobStatus : "",
  submittedText: typeof raw?.submittedText === "string" ? raw.submittedText : "",
  error: typeof raw?.error === "string" ? raw.error : "",
  pending: Boolean(raw?.pending),
  pendingStage: typeof raw?.pendingStage === "string" ? raw.pendingStage : "",
});

export const serializeChatMessage = (message) => ({
  id: String(message?.id || buildMessageId()),
  from: message?.from === "agent" ? "agent" : "user",
  text: String(message?.text || ""),
  time: typeof message?.time === "string" ? message.time : new Date().toISOString(),
  citations: Array.isArray(message?.citations) ? message.citations : [],
  sources: normalizeSources(message?.sources),
  noEvidence: Boolean(message?.noEvidence),
  debug: message?.debug && typeof message.debug === "object" ? message.debug : null,
  trace: normalizeTrace(message?.trace),
  graph: normalizeGraph(message?.graph),
  graphMeta: normalizeGraphMeta(message?.graphMeta),
  analysisModuleArtifact: normalizeAnalysisModuleArtifact(message?.analysisModuleArtifact),
  reportGenerationRequest: normalizeReportGenerationRequest(message?.reportGenerationRequest),
  analysisReport: normalizeAnalysisReport(message?.analysisReport),
  memoryInfo: message?.memoryInfo && typeof message.memoryInfo === "object" ? message.memoryInfo : null,
  jobId: message?.jobId ? String(message.jobId) : "",
  jobStatus: typeof message?.jobStatus === "string" ? message.jobStatus : "",
  submittedText: typeof message?.submittedText === "string" ? message.submittedText : "",
  error: typeof message?.error === "string" ? message.error : "",
  pending: Boolean(message?.pending),
  pendingStage: typeof message?.pendingStage === "string" ? message.pendingStage : "",
});

export const normalizeChatSession = (raw) => ({
  id: String(raw?.id || `s_${Date.now()}`),
  conversationId: String(raw?.conversationId || raw?.id || buildConversationId()),
  workspaceId: String(raw?.workspaceId || "default"),
  role: typeof raw?.role === "string" ? raw.role : "",
  title: String(raw?.title || "新对话"),
  messages: Array.isArray(raw?.messages) ? raw.messages.map(normalizeChatMessage) : [],
  selectedAnalysisModules: normalizeSelectedAnalysisModules(raw?.selectedAnalysisModules),
  updatedAt: typeof raw?.updatedAt === "string" ? raw.updatedAt : new Date().toISOString(),
});

export const serializeChatSession = (session) => ({
  id: String(session?.id || `s_${Date.now()}`),
  conversationId: String(session?.conversationId || session?.id || buildConversationId()),
  workspaceId: String(session?.workspaceId || "default"),
  role: typeof session?.role === "string" ? session.role : "",
  title: String(session?.title || "新对话"),
  messages: Array.isArray(session?.messages)
    ? session.messages.filter((message) => !message?.pending || message?.jobId).map(serializeChatMessage)
    : [],
  selectedAnalysisModules: normalizeSelectedAnalysisModules(session?.selectedAnalysisModules),
  updatedAt: typeof session?.updatedAt === "string" ? session.updatedAt : new Date().toISOString(),
});
