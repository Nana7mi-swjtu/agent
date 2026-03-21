<script setup>
import { computed, onMounted } from "vue";

import ContentSection from "@/components/shared/ContentSection.vue";
import FeedbackMessage from "@/components/shared/FeedbackMessage.vue";
import { useProfileForm } from "@/composables/useProfileForm";
import { useUiStore } from "@/stores/ui";

const uiStore = useUiStore();
const {
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
  nicknameValid,
  passwordStrength,
  loadProfile,
  onAvatarChange,
  pickPreset,
  saveProfile,
  savePreferences,
  clearAuthBg,
} = useProfileForm();

const fallbackAvatar = computed(() => "https://api.dicebear.com/9.x/fun-emoji/svg?seed=default-profile");

onMounted(loadProfile);
</script>

<template>
  <ContentSection :title="uiStore.t('profile')" subtitle="Account, avatar and role preferences.">
    <FeedbackMessage :muted="loading ? uiStore.t('loading') : ''" />

    <div v-if="!loading" class="profile-section">
      <div class="avatar-row">
        <img :src="avatarPreview || fallbackAvatar" alt="avatar" class="avatar-img" />
        <div>
          <label class="avatar-upload-btn">
            {{ uiStore.t("uploadAvatar") }}
            <input type="file" accept="image/*" style="display: none" @change="onAvatarChange" />
          </label>
          <p class="hint-text">{{ uiStore.t("avatarCompressHint") }}</p>
        </div>
      </div>

      <div class="preset-grid" v-if="profile.defaultAvatars.length">
        <div v-for="url in profile.defaultAvatars" :key="url" class="preset-item" @click="pickPreset(url)">
          <img :src="url" alt="preset" />
        </div>
      </div>

      <form @submit.prevent="saveProfile">
        <div class="form-row">
          <label>{{ uiStore.t("nicknameLabel") }}</label>
          <input v-model="form.nickname" type="text" />
          <p class="hint-text" :style="form.nickname && !nicknameValid ? 'color:#f8716d' : ''">
            {{ uiStore.t("nicknameHint") }}
          </p>
        </div>
        <div class="form-row">
          <label>{{ uiStore.t("registerEmailLabel") }}</label>
          <input :value="form.email" type="email" disabled />
        </div>

        <hr style="margin: 20px 0" />
        <h3 style="margin: 0 0 12px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); font-weight: 700">
          {{ uiStore.t("accountSecurity") }}
        </h3>
        <div class="form-row">
          <label>{{ uiStore.t("oldPasswordLabel") }}</label>
          <input v-model="form.old_password" type="password" autocomplete="current-password" />
        </div>
        <div class="form-row">
          <label>{{ uiStore.t("newPasswordLabel") }}</label>
          <input v-model="form.new_password" type="password" autocomplete="new-password" />
        </div>
        <div class="form-row">
          <label>{{ uiStore.t("confirmNewPasswordLabel") }}</label>
          <input v-model="form.confirm_password" type="password" autocomplete="new-password" />
        </div>
        <p class="hint-text">{{ uiStore.t("passwordStrengthLabel") }}：{{ passwordStrength }}</p>
        <FeedbackMessage :error="error" :success="success" />
        <button type="submit" class="save-btn" :disabled="submitting">{{ uiStore.t("saveAccountButton") }}</button>
      </form>

      <hr style="margin: 28px 0 20px" />
      <h3 style="margin: 0 0 12px; font-size: 15px; font-weight: 600">{{ uiStore.t("preferences") }}</h3>
      <form @submit.prevent="savePreferences">
        <div class="form-row">
          <label>{{ uiStore.t("theme") }}</label>
          <select v-model="prefForm.theme">
            <option value="light">{{ uiStore.t("light") }}</option>
            <option value="dark">{{ uiStore.t("dark") }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>{{ uiStore.t("language") }}</label>
          <select v-model="prefForm.language">
            <option value="zh-CN">{{ uiStore.t("chinese") }}</option>
            <option value="en-US">{{ uiStore.t("english") }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>{{ uiStore.t("authBgGifUrlLabel") }}</label>
          <input v-model="authBgGifUrl" type="url" placeholder="https://example.com/bg.gif" />
          <p class="hint-text">{{ uiStore.t("authBgGifUrlHint") }}</p>
          <button
            type="button"
            class="avatar-upload-btn"
            @click="clearAuthBg"
            style="margin-top: 8px"
          >
            {{ uiStore.t("clearAuthBg") }}
          </button>
        </div>
        <div class="switch-row">
          <input v-model="prefForm.notifications.agentRun" type="checkbox" />
          <span>{{ uiStore.t("notifyAgent") }}</span>
        </div>
        <div class="switch-row">
          <input v-model="prefForm.notifications.emailPush" type="checkbox" />
          <span>{{ uiStore.t("notifyEmail") }}</span>
        </div>
        <div class="form-row">
          <label>{{ uiStore.t("profileRole") }}</label>
          <select v-model="prefRole">
            <option value="investor">{{ uiStore.getRoleDisplayName("investor") }}</option>
            <option value="enterprise_manager">{{ uiStore.getRoleDisplayName("enterprise_manager") }}</option>
            <option value="regulator">{{ uiStore.getRoleDisplayName("regulator") }}</option>
          </select>
          <p class="hint-text">{{ uiStore.t("profileRoleHint") }}</p>
        </div>
        <button type="submit" class="save-btn">{{ uiStore.t("savePreferences") }}</button>
      </form>
    </div>
  </ContentSection>
</template>
