<script setup>

import { useForgotPasswordForm } from "@/composables/useForgotPasswordForm";
import PublicAuthLayout from "@/layouts/PublicAuthLayout.vue";
import { useUiStore } from "@/stores/ui";

const uiStore = useUiStore();
const { form, error, cooldown, sendCode, resetPassword } = useForgotPasswordForm();

const onSendCode = async () => {
  await sendCode();
};

const onResetPassword = async () => {
  const result = await resetPassword();
  if (!result.ok) {
    return;
  }
  window.alert(uiStore.t("resetSuccess"));
};
</script>

<template>
  <PublicAuthLayout>
    <h1>{{ uiStore.t("forgotPassword") }}</h1>
    <p class="auth-sub">{{ uiStore.t("resetByEmail") }}</p>
    <form @submit.prevent="onSendCode">
      <div class="field">
        <label>{{ uiStore.t("emailLabel") }}</label>
        <input v-model="form.email" type="email" autocomplete="email" />
      </div>
      <button type="submit" class="btn-primary" :disabled="cooldown > 0">
        {{ uiStore.t("sendCode") }}<span v-if="cooldown > 0"> ({{ cooldown }}s)</span>
      </button>
    </form>
    <form @submit.prevent="onResetPassword" style="margin-top: 16px">
      <div class="field">
        <label>{{ uiStore.t("codeLabel") }}</label>
        <input v-model="form.code" type="text" maxlength="6" placeholder="6位验证码" />
      </div>
      <div class="field">
        <label>{{ uiStore.t("passwordLabel") }}</label>
        <input v-model="form.new_password" type="password" autocomplete="new-password" />
      </div>
      <div class="field">
        <label>{{ uiStore.t("confirmPasswordLabel") }}</label>
        <input v-model="form.confirm_password" type="password" autocomplete="new-password" />
      </div>
      <button type="submit" class="btn-primary">{{ uiStore.t("resetPasswordButton") }}</button>
    </form>
    <div class="err-text" v-if="error">{{ error }}</div>
    <p class="auth-links" style="margin-top: 16px">
      <router-link to="/login">{{ uiStore.t("login") }}</router-link>
    </p>
  </PublicAuthLayout>
</template>
