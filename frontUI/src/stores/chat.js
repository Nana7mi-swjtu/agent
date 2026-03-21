import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";

import { CHAT_SESSIONS_KEY } from "@/constants/storage";
import { safeJsonParse } from "@/utils/json";

const normalizeMessage = (raw) => ({
  from: raw?.from === "agent" ? "agent" : "user",
  text: String(raw?.text || ""),
  time: typeof raw?.time === "string" ? raw.time : new Date().toISOString(),
});

const normalizeSession = (raw) => ({
  id: String(raw?.id || `s_${Date.now()}`),
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

  const createSession = (role, roleNameResolver) => {
    const id = `s_${Date.now()}`;
    const roleTitle = role ? roleNameResolver(role) : "新对话";
    const record = normalizeSession({
      id,
      role,
      title: role ? `${roleTitle} 对话` : "新对话",
      messages: [],
      updatedAt: new Date().toISOString(),
    });
    sessions.value.unshift(record);
    activeSessionId.value = record.id;
    return record;
  };

  const ensureSession = (role, roleNameResolver) => {
    if (activeSession.value) return activeSession.value;
    return createSession(role, roleNameResolver);
  };

  const appendMessage = (message) => {
    if (!activeSession.value) return;
    activeSession.value.messages.push(normalizeMessage(message));
    activeSession.value.updatedAt = new Date().toISOString();
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
    setSending,
    setError,
    clearState,
    normalizePersistedSessions,
  };
});
