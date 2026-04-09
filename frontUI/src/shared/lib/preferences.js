import { COPY } from "@/shared/i18n";
import { PREFERENCES_KEY } from "@/shared/config/storage";
import { safeJsonParse } from "@/shared/lib/json";

export const DEFAULT_PREFERENCES = {
  theme: "light",
  language: "zh-CN",
  notifications: {
    agentRun: true,
    emailPush: false,
  },
};

export const normalizePreferences = (raw = {}) => ({
  theme: raw.theme === "dark" ? "dark" : "light",
  language: raw.language === "en-US" ? "en-US" : "zh-CN",
  notifications: {
    agentRun:
      typeof raw.notifications?.agentRun === "boolean"
        ? raw.notifications.agentRun
        : DEFAULT_PREFERENCES.notifications.agentRun,
    emailPush:
      typeof raw.notifications?.emailPush === "boolean"
        ? raw.notifications.emailPush
        : DEFAULT_PREFERENCES.notifications.emailPush,
  },
});

export const loadPreferencesFromLocal = () =>
  normalizePreferences(safeJsonParse(localStorage.getItem(PREFERENCES_KEY) || "{}", {}));

export const persistPreferences = (preferences) => {
  localStorage.setItem(PREFERENCES_KEY, JSON.stringify(normalizePreferences(preferences)));
};

export const roleDisplayName = (roleKey, language) => {
  const names = {
    "zh-CN": {
      investor: "投资者",
      enterprise_manager: "企业管理者",
      regulator: "监管机构",
    },
    "en-US": {
      investor: "Investor",
      enterprise_manager: "Enterprise Manager",
      regulator: "Regulator",
    },
  };
  return names[language]?.[roleKey] || names["zh-CN"][roleKey] || roleKey;
};

export const translate = (language, key) => COPY[language]?.[key] || COPY["zh-CN"]?.[key] || key;
