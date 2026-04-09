import { computed, reactive, ref } from "vue";
import { storeToRefs } from "pinia";

import { useAuthStore } from "@/entities/auth/model/store";
import { useProfileStore } from "@/entities/profile/model/store";
import { useWorkspaceStore } from "@/entities/workspace/model/store";
import { loadProfileSettingsAction } from "@/features/profile/model/actions";
import { useUiStore } from "@/shared/model/ui-store";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const NICKNAME_RE = /^[\w\u4e00-\u9fff\-\s]{2,32}$/;

const getPasswordStrength = (password, language) => {
  let score = 0;
  if (password.length >= 8) score += 1;
  if (/[A-Z]/.test(password)) score += 1;
  if (/[a-z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[^A-Za-z0-9]/.test(password)) score += 1;
  if (score <= 2) return language === "en-US" ? "Weak" : "弱";
  if (score <= 4) return language === "en-US" ? "Medium" : "中";
  return language === "en-US" ? "Strong" : "强";
};

export const useProfileSettings = () => {
  const profileStore = useProfileStore();
  const uiStore = useUiStore();
  const workspaceStore = useWorkspaceStore();
  const authStore = useAuthStore();
  const { loading, error, profile } = storeToRefs(profileStore);

  const avatarFile = ref(null);
  const avatarPreset = ref("");
  const avatarPreview = ref("");
  const prefRole = ref("investor");
  const authBgGifUrl = ref(uiStore.authBgGifUrl);
  const accountSubmitting = ref(false);
  const accountError = ref("");
  const accountSuccess = ref("");
  const preferencesSubmitting = ref(false);
  const preferencesError = ref("");
  const preferencesSuccess = ref("");

  const form = reactive({
    nickname: "",
    email: "",
    old_password: "",
    new_password: "",
    confirm_password: "",
  });

  const prefForm = reactive({
    theme: uiStore.preferences.theme,
    language: uiStore.preferences.language,
    notifications: {
      agentRun: uiStore.preferences.notifications.agentRun,
      emailPush: uiStore.preferences.notifications.emailPush,
    },
  });

  const nicknameValid = computed(() => NICKNAME_RE.test(form.nickname || ""));
  const emailValid = computed(() => EMAIL_RE.test(form.email || ""));
  const passwordStrength = computed(() => getPasswordStrength(form.new_password || "", uiStore.language));

  const syncPrefForm = () => {
    prefForm.theme = uiStore.preferences.theme;
    prefForm.language = uiStore.preferences.language;
    prefForm.notifications.agentRun = uiStore.preferences.notifications.agentRun;
    prefForm.notifications.emailPush = uiStore.preferences.notifications.emailPush;
  };

  const clearFeedback = () => {
    profileStore.clearFeedback();
  };

  const clearAccountFeedback = () => {
    accountError.value = "";
    accountSuccess.value = "";
  };

  const setAccountError = (message = "") => {
    accountError.value = String(message || "");
    if (accountError.value) {
      accountSuccess.value = "";
    }
  };

  const setAccountSuccess = (message = "") => {
    accountSuccess.value = String(message || "");
    if (accountSuccess.value) {
      accountError.value = "";
    }
  };

  const setAccountSubmitting = (value) => {
    accountSubmitting.value = Boolean(value);
  };

  const clearPreferencesFeedback = () => {
    preferencesError.value = "";
    preferencesSuccess.value = "";
  };

  const setPreferencesError = (message = "") => {
    preferencesError.value = String(message || "");
    if (preferencesError.value) {
      preferencesSuccess.value = "";
    }
  };

  const setPreferencesSuccess = (message = "") => {
    preferencesSuccess.value = String(message || "");
    if (preferencesSuccess.value) {
      preferencesError.value = "";
    }
  };

  const setPreferencesSubmitting = (value) => {
    preferencesSubmitting.value = Boolean(value);
  };

  const loadProfile = async () =>
    loadProfileSettingsAction({
      profileStore,
      uiStore,
      workspaceStore,
      form,
      avatarPreview,
      prefRole,
      authBgGifUrl,
      syncPrefForm,
    });

  return {
    profileStore,
    uiStore,
    workspaceStore,
    authStore,
    loading,
    error,
    profile,
    form,
    prefForm,
    prefRole,
    authBgGifUrl,
    avatarFile,
    avatarPreset,
    avatarPreview,
    nicknameValid,
    emailValid,
    passwordStrength,
    accountSubmitting,
    accountError,
    accountSuccess,
    preferencesSubmitting,
    preferencesError,
    preferencesSuccess,
    syncPrefForm,
    clearFeedback,
    clearAccountFeedback,
    setAccountError,
    setAccountSuccess,
    setAccountSubmitting,
    clearPreferencesFeedback,
    setPreferencesError,
    setPreferencesSuccess,
    setPreferencesSubmitting,
    loadProfile,
  };
};
