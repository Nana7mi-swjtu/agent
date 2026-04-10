export const buildConversationId = () => `c_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
export const buildMessageId = () => `m_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

const normalizeTrace = (raw) => (raw && typeof raw === "object" ? raw : null);
const normalizeSources = (raw) => (Array.isArray(raw) ? raw.filter((item) => item && typeof item === "object") : []);

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

export const serializeChatSession = (session) => ({
  id: String(session?.id || `s_${Date.now()}`),
  conversationId: String(session?.conversationId || session?.id || buildConversationId()),
  workspaceId: String(session?.workspaceId || "default"),
  role: typeof session?.role === "string" ? session.role : "",
  title: String(session?.title || "新对话"),
  messages: Array.isArray(session?.messages)
    ? session.messages.filter((message) => !message?.pending).map(serializeChatMessage)
    : [],
  updatedAt: typeof session?.updatedAt === "string" ? session.updatedAt : new Date().toISOString(),
});
