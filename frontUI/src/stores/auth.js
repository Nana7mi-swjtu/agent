import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { clearCsrfToken, setCsrfToken } from "@/services/api/csrf";
import { apiRequest } from "@/services/api/client";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";

export const useAuthStore = defineStore("auth", () => {
  const ready = ref(false);
  const authenticated = ref(false);
  const user = ref(null);

  const userId = computed(() => user.value?.id ?? null);

  const bootstrapSession = async () => {
    const sessionResult = await apiRequest("/auth/session");
    if (!sessionResult.ok) {
      clearSession();
      ready.value = true;
      return false;
    }

    const meResult = await apiRequest("/auth/me");
    if (!meResult.ok) {
      clearSession();
      ready.value = true;
      return false;
    }

    authenticated.value = true;
    user.value = meResult.data?.user || null;
    if (typeof meResult.data?.csrfToken === "string") {
      setCsrfToken(meResult.data.csrfToken);
    }
    ready.value = true;
    return true;
  };

  const login = async (payload) => {
    const result = await apiRequest("/auth/login", { method: "POST", body: payload });
    if (!result.ok) {
      return result;
    }

    authenticated.value = true;
    user.value = result.data?.user || null;
    if (typeof result.data?.csrfToken === "string") {
      setCsrfToken(result.data.csrfToken);
    }
    ready.value = true;
    return result;
  };

  const logout = async () => {
    await apiRequest("/auth/logout", { method: "POST" });
    clearSession();
  };

  const clearSession = () => {
    const chatStore = useChatStore();
    const workspaceStore = useWorkspaceStore();
    authenticated.value = false;
    user.value = null;
    ready.value = true;
    chatStore.clearState();
    workspaceStore.clearWorkspaceState();
    clearCsrfToken();
  };

  return {
    ready,
    authenticated,
    user,
    userId,
    bootstrapSession,
    login,
    logout,
    clearSession,
  };
});
