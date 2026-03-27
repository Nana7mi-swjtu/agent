import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";

import { CHAT_SESSIONS_KEY } from "@/constants/storage";
import { safeJsonParse } from "@/utils/json";

const buildConversationId = () => `c_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

const normalizeMessage = (raw) => ({
  from: raw?.from === "agent" ? "agent" : "user",
  text: String(raw?.text || ""),
  time: typeof raw?.time === "string" ? raw.time : new Date().toISOString(),
  citations: Array.isArray(raw?.citations) ? raw.citations : [],
  noEvidence: Boolean(raw?.noEvidence),
  debug: raw?.debug && typeof raw.debug === "object" ? raw.debug : null,
});

const normalizeSession = (raw) => ({
  id: String(raw?.id || `s_${Date.now()}`),
  conversationId: String(raw?.conversationId || raw?.id || buildConversationId()),
  workspaceId: String(raw?.workspaceId || "default"),
  role: typeof raw?.role === "string" ? raw.role : "",
  title: String(raw?.title || "新对话"),
  messages: Array.isArray(raw?.messages) ? raw.messages.map(normalizeMessage) : [],
  updatedAt: typeof raw?.updatedAt === "string" ? raw.updatedAt : new Date().toISOString(),
});

const loadSessions = () => {
  const raw = safeJsonParse(localStorage.getItem(CHAT_SESSIONS_KEY) || "[]", []);
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeSession);
};

export const useChatStore = defineStore("chat", () => {
  const sessions = ref(loadSessions());
  const activeSessionId = ref(sessions.value[0]?.id || "");
  const sending = ref(false);
  const error = ref("");

  const activeSession = computed(
    () => sessions.value.find((session) => session.id === activeSessionId.value) || null,
  );

  const setActiveSession = (sessionId) => {
    activeSessionId.value = sessionId;
  };

  const createSession = (role, roleNameResolver, workspaceId = "default") => {
    const id = `s_${Date.now()}`;
    const roleTitle = role ? roleNameResolver(role) : "新对话";
    const record = normalizeSession({
      id,
      conversationId: buildConversationId(),
      workspaceId: String(workspaceId || "default"),
      role,
      title: role ? `${roleTitle} 对话` : "新对话",
      messages: [],
      updatedAt: new Date().toISOString(),
    });
    sessions.value.unshift(record);
    activeSessionId.value = record.id;
    return record;
  };

  const ensureSession = (role, roleNameResolver, workspaceId = "default") => {
    if (activeSession.value) return activeSession.value;
    return createSession(role, roleNameResolver, workspaceId);
  };

  const appendMessage = (message) => {
    if (!activeSession.value) return;
    activeSession.value.messages.push(normalizeMessage(message));
    activeSession.value.updatedAt = new Date().toISOString();
  };

  const setSessionScope = ({ workspaceId, role }) => {
    if (!activeSession.value) return;
    if (workspaceId) {
      activeSession.value.workspaceId = String(workspaceId);
    }
    if (typeof role === "string") {
      activeSession.value.role = role;
    }
    if (!activeSession.value.conversationId) {
      activeSession.value.conversationId = buildConversationId();
    }
    activeSession.value.updatedAt = new Date().toISOString();
  };

  const deleteSession = (sessionId) => {
    const normalizedId = String(sessionId || "");
    const index = sessions.value.findIndex((session) => session.id === normalizedId);
    if (index < 0) return false;
    sessions.value.splice(index, 1);

    if (activeSessionId.value === normalizedId) {
      activeSessionId.value = sessions.value[0]?.id || "";
    }
    return true;
  };

  const setSending = (value) => {
    sending.value = Boolean(value);
  };

  const setError = (value = "") => {
    error.value = String(value || "");
  };

  const clearState = () => {
    sending.value = false;
    error.value = "";
    activeSessionId.value = sessions.value[0]?.id || "";
  };

  const normalizePersistedSessions = () => {
    sessions.value = loadSessions();
    if (!activeSessionId.value && sessions.value.length) {
      activeSessionId.value = sessions.value[0].id;
    }
  };

  watch(
    sessions,
    (next) => {
      localStorage.setItem(CHAT_SESSIONS_KEY, JSON.stringify(next));
    },
    { deep: true },
  );

  return {
    sessions,
    activeSessionId,
    activeSession,
    sending,
    error,
    setActiveSession,
    createSession,
    ensureSession,
    appendMessage,
    setSessionScope,
    deleteSession,
    setSending,
    setError,
    clearState,
    normalizePersistedSessions,
  };
});
