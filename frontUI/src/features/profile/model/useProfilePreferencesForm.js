import { saveProfilePreferencesAction } from "@/features/profile/model/actions";

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
    return saveProfilePreferencesAction({
      profileStore,
      uiStore,
      workspaceStore,
      prefForm,
      prefRole,
      authBgGifUrl,
      syncPrefForm,
    });
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
