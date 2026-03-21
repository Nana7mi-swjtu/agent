import { defineStore } from "pinia";
import { ref } from "vue";

export const useWorkspaceStore = defineStore("workspace", () => {
  const ready = ref(false);
  const roles = ref([]);
  const selectedRole = ref("");
  const systemPrompt = ref("");

  const applyContext = (data = {}) => {
    roles.value = Array.isArray(data.roles) ? data.roles : [];
    selectedRole.value = data.selectedRole || "";
    systemPrompt.value = data.systemPrompt || "";
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
  };

  return {
    ready,
    roles,
    selectedRole,
    systemPrompt,
    applyContext,
    setContextReady,
    setActiveSession,
    clearWorkspaceState,
  };
});
