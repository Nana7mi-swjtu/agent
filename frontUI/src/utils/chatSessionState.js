export const buildConversationId = () => `c_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

const normalizeTrace = (raw) => (raw && typeof raw === "object" ? raw : null);

export const normalizeChatMessage = (raw) => ({
  from: raw?.from === "agent" ? "agent" : "user",
  text: String(raw?.text || ""),
  time: typeof raw?.time === "string" ? raw.time : new Date().toISOString(),
  citations: Array.isArray(raw?.citations) ? raw.citations : [],
  noEvidence: Boolean(raw?.noEvidence),
  debug: raw?.debug && typeof raw.debug === "object" ? raw.debug : null,
  trace: normalizeTrace(raw?.trace),
  graph: raw?.graph && typeof raw.graph === "object" ? raw.graph : null,
  graphMeta: raw?.graphMeta && typeof raw.graphMeta === "object" ? raw.graphMeta : null,
});

export const normalizeChatSession = (raw) => ({
  id: String(raw?.id || `s_${Date.now()}`),
  conversationId: String(raw?.conversationId || raw?.id || buildConversationId()),
  workspaceId: String(raw?.workspaceId || "default"),
  role: typeof raw?.role === "string" ? raw.role : "",
  title: String(raw?.title || "新对话"),
  messages: Array.isArray(raw?.messages) ? raw.messages.map(normalizeChatMessage) : [],
  updatedAt: typeof raw?.updatedAt === "string" ? raw.updatedAt : new Date().toISOString(),
});
