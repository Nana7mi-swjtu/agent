import { getUserProfile, patchUserPreferences, updateUserProfile } from "@/entities/profile/api";
import { getWorkspaceContext, patchWorkspaceContext } from "@/entities/workspace/api";

export const loadProfileSettingsAction = async ({
  profileStore,
  uiStore,
  workspaceStore,
  form,
  avatarPreview,
  prefRole,
  authBgGifUrl,
  syncPrefForm,
}) => {
  profileStore.setLoading(true);
  profileStore.setError("");

  const [profileRes, workspaceRes] = await Promise.all([getUserProfile(), getWorkspaceContext()]);
  if (workspaceRes.ok) {
    workspaceStore.applyContext(workspaceRes.data?.data || {});
    prefRole.value = workspaceRes.data?.data?.selectedRole || workspaceStore.selectedRole || "investor";
  }

  profileStore.setLoading(false);

  if (!profileRes.ok) {
    profileStore.setError(
      profileRes.status === 401 ? uiStore.t("needLoginFirst") : profileRes.data?.error || uiStore.t("loadFailed"),
    );
    return profileRes;
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
  return profileRes;
};

export const saveProfileAccountAction = async ({
  payload,
  profileStore,
  uiStore,
  authStore,
  profile,
  avatarPreview,
  form,
}) => {
  profileStore.setSubmitting(true);
  const result = await updateUserProfile(payload);
  profileStore.setSubmitting(false);

  if (!result.ok) {
    profileStore.setError(result.data?.error || uiStore.t("profileSaveFailed"));
    return result;
  }

  const updated = result.data?.data || {};
  avatarPreview.value = updated.avatarUrl || avatarPreview.value;
  profile.value.nickname = updated.nickname || profile.value.nickname;
  profile.value.avatarUrl = updated.avatarUrl || profile.value.avatarUrl;
  form.old_password = "";
  form.new_password = "";
  form.confirm_password = "";
  profileStore.setSuccess(uiStore.t("profileSaveSuccess"));
  await authStore.refreshUserProfile();
  return result;
};

export const saveProfilePreferencesAction = async ({
  profileStore,
  uiStore,
  workspaceStore,
  prefForm,
  prefRole,
  authBgGifUrl,
  syncPrefForm,
}) => {
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
    return prefRes;
  }
  if (!roleRes.ok) {
    profileStore.setError(roleRes.data?.error || uiStore.t("roleSaveFailed"));
    return roleRes;
  }

  if (prefRes.data?.data?.preferences) {
    uiStore.setPreferences(prefRes.data.data.preferences);
    syncPrefForm();
  }
  if (roleRes.data?.data) {
    workspaceStore.applyContext(roleRes.data.data);
  }

  profileStore.setSuccess(uiStore.t("savePreferencesSuccess"));
  return {
    ok: true,
    preferenceResult: prefRes,
    roleResult: roleRes,
  };
};
