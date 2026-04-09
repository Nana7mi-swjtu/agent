import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { AUTH_BG_GIF_KEY, DEFAULT_AUTH_BG_GIF_URL } from "@/shared/config/storage";
import {
  loadPreferencesFromLocal,
  normalizePreferences,
  persistPreferences,
  roleDisplayName,
  translate,
} from "@/shared/lib/preferences";

export const useUiStore = defineStore("ui", () => {
  const preferences = ref(loadPreferencesFromLocal());
  const authBgGifUrl = ref(localStorage.getItem(AUTH_BG_GIF_KEY)?.trim() || DEFAULT_AUTH_BG_GIF_URL);

  const language = computed(() => preferences.value.language);
  const hasAuthBgGif = computed(() => Boolean(authBgGifUrl.value));
  const authStageStyle = computed(() => {
    if (!authBgGifUrl.value) {
      return {};
    }
    return { "--auth-gif": `url('${authBgGifUrl.value}')` };
  });

  const applyTheme = (theme) => {
    document.documentElement.setAttribute("data-theme", theme === "dark" ? "dark" : "light");
  };

  const t = (key) => translate(language.value, key);

  const getRoleDisplayName = (roleKey) => roleDisplayName(roleKey, language.value);

  const setPreferences = (next) => {
    const normalized = normalizePreferences(next);
    preferences.value = normalized;
    persistPreferences(normalized);
    applyTheme(normalized.theme);
  };

  const mergePreferences = (patch) => {
    setPreferences({
      ...preferences.value,
      ...patch,
      notifications: {
        ...preferences.value.notifications,
        ...(patch.notifications || {}),
      },
    });
  };

  const setAuthBgGifUrl = (url) => {
    const value = String(url || "").trim();
    if (!value) {
      authBgGifUrl.value = DEFAULT_AUTH_BG_GIF_URL;
      localStorage.removeItem(AUTH_BG_GIF_KEY);
      return;
    }
    authBgGifUrl.value = value;
    localStorage.setItem(AUTH_BG_GIF_KEY, value);
  };

  applyTheme(preferences.value.theme);

  return {
    preferences,
    language,
    authBgGifUrl,
    hasAuthBgGif,
    authStageStyle,
    t,
    getRoleDisplayName,
    setPreferences,
    mergePreferences,
    setAuthBgGifUrl,
  };
});
