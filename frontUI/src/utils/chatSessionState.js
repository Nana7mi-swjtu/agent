export const buildConversationId = () => `c_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

const normalizeTrace = (raw) => (raw && typeof raw === "object" ? raw : null);

const normalizeGraphPayload = (graph, graphMeta) => {
  if (!graph || typeof graph !== "object") {
    return { graph: null, graphMeta: null };
  }
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  if (nodes.length === 0 && edges.length === 0) {
    return { graph: null, graphMeta: null };
  }
  if (!graphMeta || typeof graphMeta !== "object") {
    return { graph: null, graphMeta: null };
  }
  const source = String(graphMeta.source || "").trim();
  const contextSize = Number(graphMeta.contextSize || 0);
  if (source !== "knowledge_graph" || contextSize <= 0) {
    return { graph: null, graphMeta: null };
  }
  return { graph, graphMeta };
};

export const normalizeChatMessage = (raw) => {
  const normalizedGraph = normalizeGraphPayload(raw?.graph, raw?.graphMeta);
  return {
    from: raw?.from === "agent" ? "agent" : "user",
    text: String(raw?.text || ""),
    time: typeof raw?.time === "string" ? raw.time : new Date().toISOString(),
    citations: Array.isArray(raw?.citations) ? raw.citations : [],
    noEvidence: Boolean(raw?.noEvidence),
    debug: raw?.debug && typeof raw.debug === "object" ? raw.debug : null,
    trace: normalizeTrace(raw?.trace),
    graph: normalizedGraph.graph,
    graphMeta: normalizedGraph.graphMeta,
  };
};

export const normalizeChatSession = (raw) => ({
  id: String(raw?.id || `s_${Date.now()}`),
  conversationId: String(raw?.conversationId || raw?.id || buildConversationId()),
  workspaceId: String(raw?.workspaceId || "default"),
  role: typeof raw?.role === "string" ? raw.role : "",
  title: String(raw?.title || "新对话"),
  messages: Array.isArray(raw?.messages) ? raw.messages.map(normalizeChatMessage) : [],
  updatedAt: typeof raw?.updatedAt === "string" ? raw.updatedAt : new Date().toISOString(),
});
