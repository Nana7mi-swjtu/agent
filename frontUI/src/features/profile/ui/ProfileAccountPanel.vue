<script setup>
import FeedbackMessage from "@/shared/ui/FeedbackMessage.vue";

defineProps({
  uiStore: {
    type: Object,
    required: true,
  },
  profile: {
    type: Object,
    required: true,
  },
  form: {
    type: Object,
    required: true,
  },
  avatarPreview: {
    type: String,
    default: "",
  },
  fallbackAvatar: {
    type: String,
    required: true,
  },
  nicknameValid: {
    type: Boolean,
    default: true,
  },
  passwordStrength: {
    type: String,
    default: "",
  },
  submitting: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: "",
  },
  success: {
    type: String,
    default: "",
  },
});

defineEmits(["avatar-change", "pick-preset", "submit"]);
</script>

<template>
  <section class="profile-section-card">
    <header class="profile-section-head">
      <div>
        <span class="profile-section-kicker">{{ uiStore.t("profileSummaryTitle") }}</span>
        <h3>{{ uiStore.t("profileAccountSectionTitle") }}</h3>
        <p>{{ uiStore.t("profileAccountSectionDesc") }}</p>
      </div>
    </header>

    <div class="account-identity-band">
      <div class="account-avatar-frame">
        <img :src="avatarPreview || fallbackAvatar" alt="avatar" class="avatar-img" />
      </div>
      <div class="account-identity-copy">
        <strong>{{ form.nickname || profile.nickname || uiStore.t("profile") }}</strong>
        <span>{{ form.email }}</span>
        <label class="profile-secondary-btn">
          {{ uiStore.t("uploadAvatar") }}
          <input type="file" accept="image/*" class="hidden-input" @change="$emit('avatar-change', $event)" />
        </label>
        <p class="hint-text">{{ uiStore.t("avatarCompressHint") }}</p>
      </div>
    </div>

    <div v-if="profile.defaultAvatars.length" class="profile-subsection">
      <div class="profile-subsection-head">
        <strong>{{ uiStore.t("profilePresetAvatars") }}</strong>
      </div>
      <div class="preset-grid">
        <button
          v-for="url in profile.defaultAvatars"
          :key="url"
          type="button"
          class="preset-item"
          @click="$emit('pick-preset', url)"
        >
          <img :src="url" alt="preset avatar" />
        </button>
      </div>
    </div>

    <form class="profile-form" @submit.prevent="$emit('submit')">
      <div class="profile-subsection">
        <div class="profile-subsection-head">
          <strong>{{ uiStore.t("profileIdentitySectionTitle") }}</strong>
        </div>

        <div class="form-row">
          <label>{{ uiStore.t("nicknameLabel") }}</label>
          <input v-model="form.nickname" type="text" />
          <p class="hint-text" :class="{ 'is-danger': form.nickname && !nicknameValid }">
            {{ uiStore.t("nicknameHint") }}
          </p>
        </div>

        <div class="form-row">
          <label>{{ uiStore.t("registerEmailLabel") }}</label>
          <input :value="form.email" type="email" disabled />
          <p class="hint-text">{{ uiStore.t("profileReadOnlyEmailHint") }}</p>
        </div>
      </div>

      <div class="profile-subsection">
        <div class="profile-subsection-head">
          <strong>{{ uiStore.t("accountSecurity") }}</strong>
          <span>{{ uiStore.t("profileSecurityHint") }}</span>
        </div>

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
      </div>

      <FeedbackMessage :muted="submitting ? uiStore.t('savingAccount') : ''" :error="error" :success="success" />

      <div class="profile-actions">
        <button type="submit" class="start-btn profile-primary-btn" :disabled="submitting">{{ uiStore.t("saveAccountButton") }}</button>
        <p class="hint-text action-hint">{{ uiStore.t("profileAccountActionHint") }}</p>
      </div>
    </form>
  </section>
</template>

<style scoped>
.profile-section-card {
  display: grid;
  gap: 18px;
  border: 1px solid var(--line);
  border-radius: 30px;
  padding: 24px;
  background: linear-gradient(180deg, var(--bg-sidebar), var(--bg-overlay));
  box-shadow: var(--shadow-sm);
}

.profile-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.profile-section-kicker {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.profile-section-head h3 {
  margin: 10px 0 6px;
  font-size: 24px;
  line-height: 1.1;
  color: var(--text);
}

.profile-section-head p {
  margin: 0;
  color: var(--text-muted);
}

.account-identity-band {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 18px;
  border-radius: 24px;
  border: 1px solid var(--line);
  background: var(--bg-overlay);
}

.account-avatar-frame {
  width: 104px;
  height: 104px;
  padding: 4px;
  border-radius: 28px;
  background: linear-gradient(135deg, rgba(47, 107, 255, 0.18), rgba(111, 162, 255, 0.34));
  flex-shrink: 0;
}

.avatar-img {
  width: 100%;
  height: 100%;
  border-radius: 24px;
  object-fit: cover;
  background: var(--bg-sidebar);
}

.account-identity-copy {
  min-width: 0;
  display: grid;
  gap: 8px;
}

.account-identity-copy strong {
  font-size: 20px;
  color: var(--text);
}

.account-identity-copy span {
  color: var(--text-muted);
  word-break: break-word;
}

.profile-secondary-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  padding: 0 16px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-channel);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  overflow: hidden;
}

.hidden-input {
  display: none;
}

.profile-subsection {
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: var(--bg-overlay);
}

.profile-subsection-head {
  display: grid;
  gap: 4px;
  margin-bottom: 14px;
}

.profile-subsection-head strong {
  font-size: 14px;
  color: var(--text);
}

.profile-subsection-head span {
  font-size: 12px;
  color: var(--text-muted);
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(48px, 48px));
  gap: 8px;
}

.preset-item {
  padding: 0;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid transparent;
  background: transparent;
}

.preset-item:hover {
  border-color: rgba(47, 107, 255, 0.24);
  box-shadow: 0 10px 20px rgba(47, 107, 255, 0.12);
}

.preset-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.profile-form {
  display: grid;
  gap: 16px;
}

.form-row {
  margin-bottom: 16px;
}

.form-row:last-child {
  margin-bottom: 0;
}

.form-row label {
  display: block;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.form-row input {
  background: var(--bg-input);
  border: 1px solid var(--line);
  border-radius: 16px;
  color: var(--text);
  font-size: 15px;
  padding: 12px 14px;
  width: 100%;
  outline: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.form-row input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 4px rgba(47, 107, 255, 0.1);
}

.form-row input:disabled {
  opacity: 0.72;
  background: var(--bg-subtle);
}

.hint-text {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 6px;
}

.hint-text.is-danger {
  color: var(--danger);
}

.profile-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.profile-primary-btn {
  min-width: 144px;
}

.action-hint {
  margin: 0;
}

@media (max-width: 700px) {
  .profile-section-card {
    padding: 20px;
    border-radius: 24px;
  }

  .account-identity-band {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
