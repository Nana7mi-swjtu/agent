import { computed, reactive, ref } from "vue";
import { storeToRefs } from "pinia";

import { useAuthStore } from "@/stores/auth";
import { useProfileStore } from "@/stores/profile";
import { useUiStore } from "@/stores/ui";
import { useWorkspaceStore } from "@/stores/workspace";
import { getUserProfile } from "@/services/user";
import { getWorkspaceContext } from "@/services/workspace";

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
  const { loading, submitting, error, success, profile } = storeToRefs(profileStore);

  const avatarFile = ref(null);
  const avatarPreset = ref("");
  const avatarPreview = ref("");
  const prefRole = ref("investor");
  const authBgGifUrl = ref(uiStore.authBgGifUrl);

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

  const loadProfile = async () => {
    profileStore.setLoading(true);
    profileStore.setError("");

    const [profileRes, workspaceRes] = await Promise.all([getUserProfile(), getWorkspaceContext()]);
    if (workspaceRes.ok) {
      workspaceStore.applyContext(workspaceRes.data?.data || {});
      prefRole.value = workspaceRes.data?.data?.selectedRole || workspaceStore.selectedRole || "investor";
    }

    profileStore.setLoading(false);

    if (!profileRes.ok) {
      profileStore.setError(profileRes.status === 401 ? uiStore.t("needLoginFirst") : profileRes.data?.error || uiStore.t("loadFailed"));
      return;
    }

    const payload = profileRes.data?.data || {};
    profileStore.setProfile(payload);
    form.nickname = payload.nickname || "";
    form.email = payload.email || "";
    avatarPreview.value = payload.avatarUrl || "";

    if (payload.preferences) {
      uiStore.setPreferences(payload.preferences);
      syncPrefForm();
    }
    authBgGifUrl.value = uiStore.authBgGifUrl;
  };

  return {
    profileStore,
    uiStore,
    workspaceStore,
    authStore,
    loading,
    submitting,
    error,
    success,
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
    syncPrefForm,
    clearFeedback,
    loadProfile,
  };
};
