import { useProfileAccountForm } from "@/features/profile/model/useProfileAccountForm";
import { useProfilePreferencesForm } from "@/features/profile/model/useProfilePreferencesForm";
import { useProfileSettings } from "@/features/profile/model/useProfileSettings";

export const useProfileForm = () => {
  const settings = useProfileSettings();
  const account = useProfileAccountForm(settings);
  const preferences = useProfilePreferencesForm(settings);

  return {
    loading: settings.loading,
    submitting: settings.submitting,
    error: settings.error,
    success: settings.success,
    profile: settings.profile,
    form: settings.form,
    prefForm: settings.prefForm,
    prefRole: preferences.prefRole,
    authBgGifUrl: preferences.authBgGifUrl,
    avatarPreview: account.avatarPreview,
    avatarFile: settings.avatarFile,
    nicknameValid: account.nicknameValid,
    emailValid: settings.emailValid,
    passwordStrength: account.passwordStrength,
    loadProfile: settings.loadProfile,
    onAvatarChange: account.onAvatarChange,
    pickPreset: account.pickPreset,
    saveProfile: account.saveProfile,
    savePreferences: preferences.savePreferences,
    clearAuthBg: preferences.clearAuthBg,
  };
};
