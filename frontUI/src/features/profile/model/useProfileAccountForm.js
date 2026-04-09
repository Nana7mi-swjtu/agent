import { compressImage } from "@/shared/lib/image";
import { saveProfileAccountAction } from "@/features/profile/model/actions";

export const useProfileAccountForm = (settings) => {
  const {
    profileStore,
    uiStore,
    authStore,
    profile,
    form,
    avatarFile,
    avatarPreset,
    avatarPreview,
    nicknameValid,
    emailValid,
    passwordStrength,
    clearFeedback,
  } = settings;

  const onAvatarChange = async (event) => {
    const [rawFile] = event.target.files || [];
    if (!rawFile) return;
    clearFeedback();
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
    clearFeedback();

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

    return saveProfileAccountAction({
      payload,
      profileStore,
      uiStore,
      authStore,
      profile,
      avatarPreview,
      form,
    });
  };

  return {
    avatarPreview,
    form,
    profile,
    nicknameValid,
    passwordStrength,
    onAvatarChange,
    pickPreset,
    saveProfile,
  };
};
