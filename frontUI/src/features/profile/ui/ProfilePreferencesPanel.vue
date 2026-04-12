<script setup>
import FeedbackMessage from "@/shared/ui/FeedbackMessage.vue";

defineProps({
  uiStore: {
    type: Object,
    required: true,
  },
  prefForm: {
    type: Object,
    required: true,
  },
  prefRole: {
    type: String,
    default: "investor",
  },
  authBgGifUrl: {
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

defineEmits(["update:prefRole", "update:authBgGifUrl", "clear-auth-bg", "submit"]);
</script>

<template>
  <section class="profile-section-card">
    <header class="profile-section-head">
      <div>
        <span class="profile-section-kicker">{{ uiStore.t("preferences") }}</span>
        <h3>{{ uiStore.t("preferences") }}</h3>
        <p>{{ uiStore.t("profilePreferencesSectionDesc") }}</p>
      </div>
    </header>

    <form class="profile-form" @submit.prevent="$emit('submit')">
      <div class="profile-subsection">
        <div class="profile-subsection-head">
          <strong>{{ uiStore.t("profileAppearance") }}</strong>
          <span>{{ uiStore.t("profileAppearanceHint") }}</span>
        </div>

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
          <input
            :value="authBgGifUrl"
            type="url"
            placeholder="https://example.com/bg.gif"
            @input="$emit('update:authBgGifUrl', $event.target.value)"
          />
          <p class="hint-text">{{ uiStore.t("authBgGifUrlHint") }}</p>
          <button type="button" class="profile-secondary-btn" @click="$emit('clear-auth-bg')">
            {{ uiStore.t("clearAuthBg") }}
          </button>
        </div>
      </div>

      <div class="profile-subsection">
        <div class="profile-subsection-head">
          <strong>{{ uiStore.t("profileNotifications") }}</strong>
        </div>

        <label class="profile-toggle-row">
          <span class="profile-toggle-copy">
            <strong>{{ uiStore.t("notifyAgent") }}</strong>
          </span>
          <span class="profile-toggle">
            <input v-model="prefForm.notifications.agentRun" type="checkbox" />
            <span class="profile-toggle-slider"></span>
          </span>
        </label>

        <label class="profile-toggle-row">
          <span class="profile-toggle-copy">
            <strong>{{ uiStore.t("notifyEmail") }}</strong>
          </span>
          <span class="profile-toggle">
            <input v-model="prefForm.notifications.emailPush" type="checkbox" />
            <span class="profile-toggle-slider"></span>
          </span>
        </label>
      </div>

      <div class="profile-subsection">
        <div class="profile-subsection-head">
          <strong>{{ uiStore.t("profileWorkspaceDefaults") }}</strong>
          <span>{{ uiStore.t("profileRoleHint") }}</span>
        </div>

        <div class="form-row">
          <label>{{ uiStore.t("profileRole") }}</label>
          <select :value="prefRole" @change="$emit('update:prefRole', $event.target.value)">
            <option value="investor">{{ uiStore.getRoleDisplayName("investor") }}</option>
            <option value="enterprise_manager">{{ uiStore.getRoleDisplayName("enterprise_manager") }}</option>
            <option value="regulator">{{ uiStore.getRoleDisplayName("regulator") }}</option>
          </select>
        </div>
      </div>

      <FeedbackMessage :muted="submitting ? uiStore.t('savingPreferences') : ''" :error="error" :success="success" />

      <div class="profile-actions">
        <button type="submit" class="start-btn profile-primary-btn" :disabled="submitting">{{ uiStore.t("savePreferences") }}</button>
        <p class="hint-text action-hint">{{ uiStore.t("profilePreferencesActionHint") }}</p>
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

.profile-form {
  display: grid;
  gap: 16px;
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

.form-row input,
.form-row select {
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

.form-row input:focus,
.form-row select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 4px rgba(47, 107, 255, 0.1);
}

.hint-text {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 6px;
}

.profile-secondary-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 0 16px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-channel);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.profile-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 0;
  border-top: 1px solid rgba(47, 107, 255, 0.08);
}

.profile-toggle-row:first-of-type {
  padding-top: 0;
  border-top: none;
}

.profile-toggle-copy {
  min-width: 0;
}

.profile-toggle-copy strong {
  display: block;
  color: var(--text);
  font-size: 14px;
  line-height: 1.4;
}

.profile-toggle {
  position: relative;
  width: 52px;
  height: 32px;
  flex-shrink: 0;
}

.profile-toggle input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
  margin: 0;
}

.profile-toggle-slider {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: rgba(96, 114, 143, 0.24);
  transition: background 0.18s ease;
}

.profile-toggle-slider::after {
  content: "";
  position: absolute;
  top: 4px;
  left: 4px;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: #fff;
  box-shadow: 0 4px 12px rgba(20, 32, 51, 0.14);
  transition: transform 0.18s ease;
}

.profile-toggle input:checked + .profile-toggle-slider {
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
}

.profile-toggle input:checked + .profile-toggle-slider::after {
  transform: translateX(20px);
}

.profile-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.profile-primary-btn {
  min-width: 164px;
}

.action-hint {
  margin: 0;
}

@media (max-width: 700px) {
  .profile-section-card {
    padding: 20px;
    border-radius: 24px;
  }
}
</style>
