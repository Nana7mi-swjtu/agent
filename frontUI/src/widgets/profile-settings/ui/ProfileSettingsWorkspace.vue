<script setup>
import { computed, onMounted } from "vue";
import { storeToRefs } from "pinia";

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
const { workspaceId } = storeToRefs(settings.workspaceStore);

const {
  uiStore,
  loading,
  error,
  profile,
  form,
  prefForm,
  prefRole,
  accountSubmitting,
  accountError,
  accountSuccess,
  preferencesSubmitting,
  preferencesError,
  preferencesSuccess,
  loadProfile,
} = settings;
const { avatarPreview, nicknameValid, passwordStrength, onAvatarChange, pickPreset, saveProfile } = account;
const { authBgGifUrl, savePreferences, clearAuthBg } = preferences;

const summaryAvatar = computed(() => avatarPreview.value || profile.value.avatarUrl || fallbackAvatar.value);
const summaryName = computed(() => form.nickname || profile.value.nickname || uiStore.t("profile"));
const summaryRole = computed(() => uiStore.getRoleDisplayName(prefRole.value));
const summaryTheme = computed(() => uiStore.t(prefForm.theme));
const summaryLanguage = computed(() => uiStore.t(prefForm.language === "en-US" ? "english" : "chinese"));

onMounted(loadProfile);
</script>

<template>
  <div class="profile-workspace">
    <FeedbackMessage :muted="loading ? uiStore.t('loading') : ''" :error="error" />

    <div v-if="!loading && !error" class="profile-workspace-shell">
      <section class="profile-summary-card">
        <div class="profile-summary-main">
          <div class="profile-summary-avatar-wrap">
            <img :src="summaryAvatar" alt="profile avatar" class="profile-summary-avatar" />
          </div>
          <div class="profile-summary-copy">
            <span class="profile-summary-kicker">{{ uiStore.t("profileSummaryTitle") }}</span>
            <h2>{{ summaryName }}</h2>
            <p>{{ uiStore.t("profileSummaryDesc") }}</p>
            <div class="profile-summary-email">{{ form.email }}</div>
          </div>
        </div>

        <div class="profile-summary-metrics">
          <div class="profile-metric-card">
            <span>{{ uiStore.t("profileCurrentWorkspace") }}</span>
            <strong>{{ workspaceId }}</strong>
          </div>
          <div class="profile-metric-card">
            <span>{{ uiStore.t("profileCurrentRole") }}</span>
            <strong>{{ summaryRole }}</strong>
          </div>
          <div class="profile-metric-card">
            <span>{{ uiStore.t("profileCurrentTheme") }}</span>
            <strong>{{ summaryTheme }}</strong>
          </div>
          <div class="profile-metric-card">
            <span>{{ uiStore.t("profileCurrentLanguage") }}</span>
            <strong>{{ summaryLanguage }}</strong>
          </div>
        </div>
      </section>

      <div class="profile-panels-grid">
        <ProfileAccountPanel
          :ui-store="uiStore"
          :profile="profile"
          :form="form"
          :avatar-preview="avatarPreview"
          :fallback-avatar="fallbackAvatar"
          :nickname-valid="nicknameValid"
          :password-strength="passwordStrength"
          :submitting="accountSubmitting"
          :error="accountError"
          :success="accountSuccess"
          @avatar-change="onAvatarChange"
          @pick-preset="pickPreset"
          @submit="saveProfile"
        />

        <ProfilePreferencesPanel
          :ui-store="uiStore"
          :pref-form="prefForm"
          :pref-role="prefRole"
          :auth-bg-gif-url="authBgGifUrl"
          :submitting="preferencesSubmitting"
          :error="preferencesError"
          :success="preferencesSuccess"
          @update:pref-role="prefRole = $event"
          @update:auth-bg-gif-url="authBgGifUrl = $event"
          @clear-auth-bg="clearAuthBg"
          @submit="savePreferences"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-workspace {
  display: grid;
  gap: 20px;
}

.profile-workspace-shell {
  display: grid;
  gap: 20px;
}

.profile-summary-card {
  display: grid;
  gap: 18px;
  padding: 24px;
  border: 1px solid var(--line);
  border-radius: 30px;
  background:
    radial-gradient(circle at top right, var(--accent-soft), transparent 28%),
    linear-gradient(180deg, var(--bg-sidebar), var(--bg-overlay));
  box-shadow: var(--shadow-sm);
}

.profile-summary-main {
  display: flex;
  align-items: center;
  gap: 18px;
}

.profile-summary-avatar-wrap {
  display: grid;
  place-items: center;
  width: 92px;
  height: 92px;
  padding: 4px;
  border-radius: 28px;
  background: linear-gradient(135deg, rgba(47, 107, 255, 0.22), rgba(111, 162, 255, 0.38));
  box-shadow: 0 18px 36px rgba(47, 107, 255, 0.14);
  flex-shrink: 0;
}

.profile-summary-avatar {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 24px;
  object-fit: cover;
  background: var(--bg-sidebar);
}

.profile-summary-copy {
  min-width: 0;
}

.profile-summary-kicker {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.profile-summary-copy h2 {
  margin: 12px 0 6px;
  font-size: 30px;
  line-height: 1.08;
  color: var(--text);
}

.profile-summary-copy p {
  margin: 0;
  max-width: 60ch;
  color: var(--text-muted);
}

.profile-summary-email {
  margin-top: 12px;
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-channel);
  font-size: 13px;
  font-weight: 600;
}

.profile-summary-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.profile-metric-card {
  display: grid;
  gap: 6px;
  padding: 16px;
  border-radius: 20px;
  border: 1px solid var(--line);
  background: var(--bg-overlay);
}

.profile-metric-card span {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.profile-metric-card strong {
  color: var(--text);
  font-size: 15px;
}

.profile-panels-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr);
  gap: 20px;
  align-items: start;
}

@media (max-width: 1100px) {
  .profile-panels-grid,
  .profile-summary-metrics {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 840px) {
  .profile-summary-main {
    align-items: flex-start;
    flex-direction: column;
  }

  .profile-panels-grid,
  .profile-summary-metrics {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .profile-summary-card {
    padding: 20px;
    border-radius: 24px;
  }

  .profile-summary-copy h2 {
    font-size: 26px;
  }
}
</style>
