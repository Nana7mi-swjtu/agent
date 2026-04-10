import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";

import { CHAT_SESSIONS_KEY } from "@/shared/config/storage";
import { safeJsonParse } from "@/shared/lib/json";
import {
  buildConversationId,
  buildMessageId,
  normalizeChatMessage,
  normalizeChatSession,
  serializeChatSession,
} from "@/entities/chat/lib/session";

const loadSessions = () => {
  const raw = safeJsonParse(localStorage.getItem(CHAT_SESSIONS_KEY) || "[]", []);
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeChatSession);
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
    const record = normalizeChatSession({
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
    activeSession.value.messages.push(normalizeChatMessage(message));
    activeSession.value.updatedAt = new Date().toISOString();
  };

  const replaceMessage = (messageId, message) => {
    if (!activeSession.value) return false;
    const targetId = String(messageId || "");
    const index = activeSession.value.messages.findIndex((item) => item.id === targetId);
    if (index < 0) return false;
    activeSession.value.messages.splice(index, 1, normalizeChatMessage({ ...message, id: targetId }));
    activeSession.value.updatedAt = new Date().toISOString();
    return true;
  };

  const patchMessage = (messageId, patch) => {
    if (!activeSession.value) return false;
    const targetId = String(messageId || "");
    const message = activeSession.value.messages.find((item) => item.id === targetId);
    if (!message) return false;
    Object.assign(message, normalizeChatMessage({ ...message, ...patch, id: targetId }));
    activeSession.value.updatedAt = new Date().toISOString();
    return true;
  };

  const removeMessage = (messageId) => {
    if (!activeSession.value) return false;
    const targetId = String(messageId || "");
    const index = activeSession.value.messages.findIndex((item) => item.id === targetId);
    if (index < 0) return false;
    activeSession.value.messages.splice(index, 1);
    activeSession.value.updatedAt = new Date().toISOString();
    return true;
  };

  const appendPendingAssistantMessage = (pendingStage = "") => {
    const id = buildMessageId();
    appendMessage({
      id,
      from: "agent",
      text: "",
      time: new Date().toISOString(),
      pending: true,
      pendingStage,
    });
    return id;
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

  const clearRuntimeState = () => {
    sending.value = false;
    error.value = "";
    activeSessionId.value = sessions.value[0]?.id || "";
  };

  const clearState = () => {
    clearRuntimeState();
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
      localStorage.setItem(CHAT_SESSIONS_KEY, JSON.stringify(next.map(serializeChatSession)));
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
    replaceMessage,
    patchMessage,
    removeMessage,
    appendPendingAssistantMessage,
    setSessionScope,
    deleteSession,
    setSending,
    setError,
    clearRuntimeState,
    clearState,
    normalizePersistedSessions,
  };
});
