import { patchUserPreferences } from "@/services/user";
import { patchWorkspaceContext } from "@/services/workspace";

export const useProfilePreferencesForm = (settings) => {
  const {
    profileStore,
    uiStore,
    workspaceStore,
    prefForm,
    prefRole,
    authBgGifUrl,
    syncPrefForm,
    clearFeedback,
  } = settings;

  const savePreferences = async () => {
    clearFeedback();

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
    prefForm,
    prefRole,
    authBgGifUrl,
    savePreferences,
    clearAuthBg,
  };
};
