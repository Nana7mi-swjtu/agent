<script setup>
import { computed, onMounted } from "vue";

import FeedbackMessage from "@/shared/ui/FeedbackMessage.vue";
import { useProfileAccountForm } from "@/features/profile/model/useProfileAccountForm";
import { useProfilePreferencesForm } from "@/features/profile/model/useProfilePreferencesForm";
import { useProfileSettings } from "@/features/profile/model/useProfileSettings";
import ProfileAccountPanel from "@/features/profile/ui/ProfileAccountPanel.vue";
import ProfilePreferencesPanel from "@/features/profile/ui/ProfilePreferencesPanel.vue";

const settings = useProfileSettings();
const account = useProfileAccountForm(settings);
const preferences = useProfilePreferencesForm(settings);
const fallbackAvatar = computed(() => "https://api.dicebear.com/9.x/fun-emoji/svg?seed=default-profile");

const {
  uiStore,
  loading,
  submitting,
  error,
  success,
  profile,
  loadProfile,
} = settings;
const { form, avatarPreview, nicknameValid, passwordStrength, onAvatarChange, pickPreset, saveProfile } = account;
const { prefForm, prefRole, authBgGifUrl, savePreferences, clearAuthBg } = preferences;

onMounted(loadProfile);
</script>

<template>
  <div>
    <FeedbackMessage :muted="loading ? uiStore.t('loading') : ''" />

    <div v-if="!loading" class="profile-workspace">
      <ProfileAccountPanel
        :ui-store="uiStore"
        :profile="profile"
        :form="form"
        :avatar-preview="avatarPreview"
        :fallback-avatar="fallbackAvatar"
        :nickname-valid="nicknameValid"
        :password-strength="passwordStrength"
        :submitting="submitting"
        :error="error"
        :success="success"
        @avatar-change="onAvatarChange"
        @pick-preset="pickPreset"
        @submit="saveProfile"
      />

      <ProfilePreferencesPanel
        :ui-store="uiStore"
        :pref-form="prefForm"
        :pref-role="prefRole"
        :auth-bg-gif-url="authBgGifUrl"
        @update:pref-role="prefRole = $event"
        @update:auth-bg-gif-url="authBgGifUrl = $event"
        @clear-auth-bg="clearAuthBg"
        @submit="savePreferences"
      />
    </div>
  </div>
</template>

<style scoped>
.profile-workspace {
  display: grid;
  gap: 20px;
  max-width: 760px;
}
</style>
