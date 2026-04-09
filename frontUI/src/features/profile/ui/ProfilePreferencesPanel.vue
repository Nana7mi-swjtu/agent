<script setup>
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
});

defineEmits(["update:prefRole", "update:authBgGifUrl", "clear-auth-bg", "submit"]);
</script>

<template>
  <section class="profile-card">
    <h3 class="profile-heading">{{ uiStore.t("preferences") }}</h3>

    <form @submit.prevent="$emit('submit')">
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
        <input :value="authBgGifUrl" type="url" placeholder="https://example.com/bg.gif" @input="$emit('update:authBgGifUrl', $event.target.value)" />
        <p class="hint-text">{{ uiStore.t("authBgGifUrlHint") }}</p>
        <button type="button" class="avatar-upload-btn clear-btn" @click="$emit('clear-auth-bg')">
          {{ uiStore.t("clearAuthBg") }}
        </button>
      </div>

      <label class="switch-row">
        <input v-model="prefForm.notifications.agentRun" type="checkbox" />
        <span>{{ uiStore.t("notifyAgent") }}</span>
      </label>

      <label class="switch-row">
        <input v-model="prefForm.notifications.emailPush" type="checkbox" />
        <span>{{ uiStore.t("notifyEmail") }}</span>
      </label>

      <div class="form-row">
        <label>{{ uiStore.t("profileRole") }}</label>
        <select :value="prefRole" @change="$emit('update:prefRole', $event.target.value)">
          <option value="investor">{{ uiStore.getRoleDisplayName("investor") }}</option>
          <option value="enterprise_manager">{{ uiStore.getRoleDisplayName("enterprise_manager") }}</option>
          <option value="regulator">{{ uiStore.getRoleDisplayName("regulator") }}</option>
        </select>
        <p class="hint-text">{{ uiStore.t("profileRoleHint") }}</p>
      </div>

      <button type="submit" class="save-btn">{{ uiStore.t("savePreferences") }}</button>
    </form>
  </section>
</template>

<style scoped>
.profile-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.03);
}

.profile-heading {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
}

.form-row {
  margin-bottom: 16px;
}

.form-row label {
  display: block;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.form-row input,
.form-row select {
  background: var(--bg-server-bar);
  border: 1px solid var(--line);
  border-radius: 3px;
  color: var(--text);
  font-size: 15px;
  padding: 10px;
  width: 100%;
  outline: none;
}

.form-row input:focus,
.form-row select:focus {
  border-color: var(--accent);
}

.hint-text {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 6px;
}

.avatar-upload-btn {
  display: inline-block;
  background: var(--bg-overlay);
  border: 1px solid var(--line);
  border-radius: 3px;
  color: var(--text);
  font-size: 14px;
  padding: 8px 14px;
  cursor: pointer;
}

.clear-btn {
  margin-top: 8px;
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  font-size: 15px;
  color: var(--text);
}

.switch-row input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--accent);
}

.save-btn {
  background: var(--accent);
  border: none;
  border-radius: 3px;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  padding: 10px 20px;
  cursor: pointer;
  transition: background 0.15s;
}

.save-btn:hover:not(:disabled) {
  background: #4752c4;
}
</style>
