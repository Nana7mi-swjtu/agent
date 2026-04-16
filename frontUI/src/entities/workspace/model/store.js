import { defineStore } from "pinia";
import { ref } from "vue";

const parseBool = (value, fallback = false) => {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(normalized)) return true;
    if (["0", "false", "no", "off"].includes(normalized)) return false;
  }
  return fallback;
};

export const useWorkspaceStore = defineStore("workspace", () => {
  const ready = ref(false);
  const roles = ref([]);
  const selectedRole = ref("");
  const systemPrompt = ref("");
  const workspaceId = ref("default");
  const ragDebugEnabled = ref(parseBool(import.meta.env.VITE_RAG_DEBUG_VISUALIZATION_ENABLED, false));
  const agentTraceEnabled = ref(parseBool(import.meta.env.VITE_AGENT_TRACE_VISUALIZATION_ENABLED, false));
  const agentTraceDebugDetailsEnabled = ref(
    parseBool(import.meta.env.VITE_AGENT_TRACE_DEBUG_DETAILS_ENABLED, false),
  );
  const chatStreamingEnabled = ref(parseBool(import.meta.env.VITE_WORKSPACE_CHAT_STREAMING_ENABLED, false));
  const agentChatJobsEnabled = ref(parseBool(import.meta.env.VITE_AGENT_CHAT_JOBS_ENABLED, true));

  const applyContext = (data = {}) => {
    roles.value = Array.isArray(data.roles) ? data.roles : [];
    selectedRole.value = data.selectedRole || "";
    systemPrompt.value = data.systemPrompt || "";
    workspaceId.value = String(data.workspaceId || "default");
    ragDebugEnabled.value = parseBool(data.ragDebugVisualizationEnabled, ragDebugEnabled.value);
    agentTraceEnabled.value = parseBool(data.agentTraceVisualizationEnabled, agentTraceEnabled.value);
    agentTraceDebugDetailsEnabled.value = parseBool(
      data.agentTraceDebugDetailsEnabled,
      agentTraceDebugDetailsEnabled.value,
    );
    chatStreamingEnabled.value = parseBool(data.chatStreamingEnabled, chatStreamingEnabled.value);
    agentChatJobsEnabled.value = parseBool(data.agentChatJobsEnabled, agentChatJobsEnabled.value);
    ready.value = true;
  };

  const setContextReady = () => {
    ready.value = true;
  };

  const setActiveSession = (sessionId) => {
    return sessionId;
  };

  const clearWorkspaceState = () => {
    ready.value = false;
    roles.value = [];
    selectedRole.value = "";
    systemPrompt.value = "";
    workspaceId.value = "default";
    ragDebugEnabled.value = parseBool(import.meta.env.VITE_RAG_DEBUG_VISUALIZATION_ENABLED, false);
    agentTraceEnabled.value = parseBool(import.meta.env.VITE_AGENT_TRACE_VISUALIZATION_ENABLED, false);
    agentTraceDebugDetailsEnabled.value = parseBool(
      import.meta.env.VITE_AGENT_TRACE_DEBUG_DETAILS_ENABLED,
      false,
    );
    chatStreamingEnabled.value = parseBool(import.meta.env.VITE_WORKSPACE_CHAT_STREAMING_ENABLED, false);
    agentChatJobsEnabled.value = parseBool(import.meta.env.VITE_AGENT_CHAT_JOBS_ENABLED, true);
  };

  return {
    ready,
    roles,
    selectedRole,
    systemPrompt,
    workspaceId,
    ragDebugEnabled,
    agentTraceEnabled,
    agentTraceDebugDetailsEnabled,
    chatStreamingEnabled,
    agentChatJobsEnabled,
    applyContext,
    setContextReady,
    setActiveSession,
    clearWorkspaceState,
  };
});
