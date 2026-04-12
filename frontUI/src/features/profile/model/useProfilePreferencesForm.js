import { saveProfilePreferencesAction } from "@/features/profile/model/actions";

export const useProfilePreferencesForm = (settings) => {
  const {
    uiStore,
    workspaceStore,
    prefForm,
    prefRole,
    authBgGifUrl,
    syncPrefForm,
    clearPreferencesFeedback,
    setPreferencesSubmitting,
    setPreferencesError,
    setPreferencesSuccess,
  } = settings;

  const savePreferences = async () => {
    clearPreferencesFeedback();
    setPreferencesSuccess("");
    return saveProfilePreferencesAction({
      uiStore,
      workspaceStore,
      prefForm,
      prefRole,
      authBgGifUrl,
      syncPrefForm,
      setPreferencesSubmitting,
      setPreferencesError,
      setPreferencesSuccess,
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
