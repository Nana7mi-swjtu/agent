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
  <section class="profile-card">
    <div class="avatar-row">
      <img :src="avatarPreview || fallbackAvatar" alt="avatar" class="avatar-img" />
      <div>
        <label class="avatar-upload-btn">
          {{ uiStore.t("uploadAvatar") }}
          <input type="file" accept="image/*" class="hidden-input" @change="$emit('avatar-change', $event)" />
        </label>
        <p class="hint-text">{{ uiStore.t("avatarCompressHint") }}</p>
      </div>
    </div>

    <div v-if="profile.defaultAvatars.length" class="preset-grid">
      <div v-for="url in profile.defaultAvatars" :key="url" class="preset-item" @click="$emit('pick-preset', url)">
        <img :src="url" alt="preset" />
      </div>
    </div>

    <form @submit.prevent="$emit('submit')">
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

      <hr class="profile-divider" />
      <h3 class="profile-section-title">{{ uiStore.t("accountSecurity") }}</h3>

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
  </section>
</template>

<style scoped>
.profile-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.03);
}

.avatar-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.avatar-img {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  object-fit: cover;
  border: 4px solid var(--bg-overlay);
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

.hidden-input {
  display: none;
}

.preset-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.preset-item {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
}

.preset-item:hover {
  border-color: var(--accent);
}

.preset-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.profile-divider {
  margin: 20px 0;
  border: none;
  border-top: 1px solid var(--line);
}

.profile-section-title {
  margin: 0 0 12px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  font-weight: 700;
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

.form-row input {
  background: var(--bg-server-bar);
  border: 1px solid var(--line);
  border-radius: 3px;
  color: var(--text);
  font-size: 15px;
  padding: 10px;
  width: 100%;
  outline: none;
}

.form-row input:focus {
  border-color: var(--accent);
}

.form-row input:disabled {
  opacity: 0.5;
}

.hint-text {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 6px;
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

.save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
