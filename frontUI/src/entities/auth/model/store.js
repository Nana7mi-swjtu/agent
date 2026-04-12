import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { clearCsrfToken, setCsrfToken } from "@/shared/api/csrf";
import { apiRequest } from "@/shared/api/client";
import { getUserProfile } from "@/entities/profile/api";

export const useAuthStore = defineStore("auth", () => {
  const ready = ref(false);
  const authenticated = ref(false);
  const user = ref(null);

  const userId = computed(() => user.value?.id ?? null);

  const applyAuthenticatedSession = (nextUser, csrfToken = "") => {
    authenticated.value = true;
    user.value = nextUser || null;
    if (typeof csrfToken === "string") {
      setCsrfToken(csrfToken);
    }
    ready.value = true;
  };

  const clearSessionState = () => {
    authenticated.value = false;
    user.value = null;
    ready.value = true;
    clearCsrfToken();
  };

  const restoreSession = async () => {
    const sessionResult = await apiRequest("/auth/session");
    if (!sessionResult.ok) {
      clearSessionState();
      return false;
    }

    const meResult = await apiRequest("/auth/me");
    if (!meResult.ok) {
      clearSessionState();
      return false;
    }

    applyAuthenticatedSession(meResult.data?.user || null, meResult.data?.csrfToken || "");
    return true;
  };

  const login = async (payload) => {
    const result = await apiRequest("/auth/login", { method: "POST", body: payload });
    if (!result.ok) {
      return result;
    }

    applyAuthenticatedSession(result.data?.user || null, result.data?.csrfToken || "");
    return result;
  };

  const refreshUserProfile = async () => {
    if (!authenticated.value) {
      return { ok: false, status: 401, data: { error: "authentication required" } };
    }
    const result = await getUserProfile();
    if (!result.ok) return result;
    const profile = result.data?.data || {};
    user.value = {
      ...(user.value || {}),
      nickname: profile.nickname || "",
      avatarUrl: profile.avatarUrl || "",
      email: profile.email || user.value?.email || "",
    };
    return result;
  };

  const requestLogout = async () => {
    return apiRequest("/auth/logout", { method: "POST" });
  };

  const bootstrapSession = async () => restoreSession();

  const clearSession = () => {
    clearSessionState();
  };

  const logout = async () => {
    const result = await requestLogout();
    clearSessionState();
    return result;
  };

  return {
    ready,
    authenticated,
    user,
    userId,
    applyAuthenticatedSession,
    clearSessionState,
    restoreSession,
    requestLogout,
    bootstrapSession,
    login,
    logout,
    refreshUserProfile,
    clearSession,
  };
});
