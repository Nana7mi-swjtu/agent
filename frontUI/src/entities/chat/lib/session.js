export const buildConversationId = () => `c_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
export const buildMessageId = () => `m_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

export const SUPPORTED_ANALYSIS_MODULE_IDS = ["robotics_risk"];
const SUPPORTED_ANALYSIS_MODULE_ID_SET = new Set(SUPPORTED_ANALYSIS_MODULE_IDS);

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
export const normalizeSelectedAnalysisModules = (raw) => {
  if (!Array.isArray(raw)) return [];
  const result = [];
  raw.forEach((item) => {
    const moduleId = String(item || "").trim();
    if (SUPPORTED_ANALYSIS_MODULE_ID_SET.has(moduleId) && !result.includes(moduleId)) {
      result.push(moduleId);
    }
  });
  return result;
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
