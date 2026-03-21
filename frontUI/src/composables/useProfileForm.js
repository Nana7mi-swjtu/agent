import { computed, reactive, ref } from "vue";
import { storeToRefs } from "pinia";

import { useProfileStore } from "@/stores/profile";
import { useUiStore } from "@/stores/ui";
import { useWorkspaceStore } from "@/stores/workspace";
import { getUserProfile, patchUserPreferences, updateUserProfile } from "@/services/user";
import { getWorkspaceContext, patchWorkspaceContext } from "@/services/workspace";
import { compressImage } from "@/utils/image";

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

export const useProfileForm = () => {
  const profileStore = useProfileStore();
  const uiStore = useUiStore();
  const workspaceStore = useWorkspaceStore();
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

  const onAvatarChange = async (event) => {
    const [rawFile] = event.target.files || [];
    if (!rawFile) return;
    profileStore.clearFeedback();
    try {
      const compressed = await compressImage(rawFile);
      avatarFile.value = compressed;
      avatarPreset.value = "";
      avatarPreview.value = URL.createObjectURL(compressed);
    } catch (err) {
      profileStore.setError(err?.message || uiStore.t("avatarProcessFailed"));
    }
  };

  const pickPreset = (url) => {
    avatarPreset.value = url;
    avatarFile.value = null;
    avatarPreview.value = url;
  };

  const saveProfile = async () => {
    profileStore.clearFeedback();

    if (!nicknameValid.value) {
      profileStore.setError(uiStore.t("nicknameInvalidError"));
      return;
    }
    if (!emailValid.value) {
      profileStore.setError(uiStore.t("emailFormatInvalid"));
      return;
    }

    const hasPasswordInput = form.old_password || form.new_password || form.confirm_password;
    if (hasPasswordInput) {
      if (!form.old_password || !form.new_password) {
        profileStore.setError(uiStore.t("passwordOldNewRequired"));
        return;
      }
      if (form.new_password !== form.confirm_password) {
        profileStore.setError(uiStore.t("passwordNotMatch"));
        return;
      }
      if (form.new_password.length < 8) {
        profileStore.setError(uiStore.t("passwordTooShortClient"));
        return;
      }
    }

    const payload = new FormData();
    payload.append("nickname", form.nickname);
    if (form.old_password) payload.append("old_password", form.old_password);
    if (form.new_password) payload.append("new_password", form.new_password);
    if (avatarFile.value) payload.append("avatar", avatarFile.value);
    else if (avatarPreset.value) payload.append("avatar_preset", avatarPreset.value);

    profileStore.setSubmitting(true);
    const result = await updateUserProfile(payload);
    profileStore.setSubmitting(false);

    if (!result.ok) {
      profileStore.setError(result.data?.error || uiStore.t("profileSaveFailed"));
      return;
    }

    const updated = result.data?.data || {};
    avatarPreview.value = updated.avatarUrl || avatarPreview.value;
    profile.value.nickname = updated.nickname || profile.value.nickname;
    profile.value.avatarUrl = updated.avatarUrl || profile.value.avatarUrl;
    form.old_password = "";
    form.new_password = "";
    form.confirm_password = "";
    profileStore.setSuccess(uiStore.t("profileSaveSuccess"));
  };

  const savePreferences = async () => {
    profileStore.clearFeedback();

    uiStore.setAuthBgGifUrl(authBgGifUrl.value);
    uiStore.mergePreferences(prefForm);

    const [prefRes, roleRes] = await Promise.all([
      patchUserPreferences({
        theme: prefForm.theme,
        language: prefForm.language,
        notifications: {
          agentRun: prefForm.notifications.agentRun,
          emailPush: prefForm.notifications.emailPush,
        },
      }),
      patchWorkspaceContext(prefRole.value),
    ]);

    if (!prefRes.ok) {
      profileStore.setError(prefRes.data?.error || uiStore.t("preferencesSaveFailed"));
      return;
    }
    if (!roleRes.ok) {
      profileStore.setError(roleRes.data?.error || uiStore.t("roleSaveFailed"));
      return;
    }

    if (prefRes.data?.data?.preferences) {
      uiStore.setPreferences(prefRes.data.data.preferences);
      syncPrefForm();
    }
    if (roleRes.data?.data) {
      workspaceStore.applyContext(roleRes.data.data);
    }

    profileStore.setSuccess(uiStore.t("savePreferencesSuccess"));
  };

  const clearAuthBg = () => {
    authBgGifUrl.value = "";
    uiStore.setAuthBgGifUrl("");
  };

  return {
    loading,
    submitting,
    error,
    success,
    profile,
    form,
    prefForm,
    prefRole,
    authBgGifUrl,
    avatarPreview,
    avatarFile,
    nicknameValid,
    emailValid,
    passwordStrength,
    loadProfile,
    onAvatarChange,
    pickPreset,
    saveProfile,
    savePreferences,
    clearAuthBg,
  };
};
