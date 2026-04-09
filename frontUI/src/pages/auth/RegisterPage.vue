<script setup>
import { useRegisterForm } from "@/features/auth/model/useRegisterForm";
import { useUiStore } from "@/shared/model/ui-store";
import PublicAuthLayout from "@/widgets/auth-shell/ui/PublicAuthLayout.vue";

const uiStore = useUiStore();
const { form, error, cooldown, sendCode, verifyCode } = useRegisterForm();

const onSendCode = async () => {
  await sendCode();
};

const onVerifyCode = async () => {
  const result = await verifyCode();
  if (!result.ok) {
    return;
  }
  window.alert(uiStore.t("registerSuccess"));
};
</script>

<template>
  <PublicAuthLayout>
    <h1>{{ uiStore.t("register") }}</h1>
    <p class="auth-sub">{{ uiStore.t("joinAgentStudio") }}</p>
    <form @submit.prevent="onSendCode">
      <div class="field">
        <label>{{ uiStore.t("emailLabel") }}</label>
        <input v-model="form.email" type="email" autocomplete="email" />
      </div>
      <div class="field">
        <label>{{ uiStore.t("passwordLabel") }}</label>
        <input v-model="form.password" type="password" autocomplete="new-password" />
      </div>
      <div class="field">
        <label>{{ uiStore.t("confirmPasswordLabel") }}</label>
        <input v-model="form.confirm_password" type="password" autocomplete="new-password" />
      </div>
      <button type="submit" class="btn-primary" :disabled="cooldown > 0">
        {{ uiStore.t("sendCode") }}<span v-if="cooldown > 0"> ({{ cooldown }}s)</span>
      </button>
    </form>
    <form @submit.prevent="onVerifyCode" style="margin-top: 16px">
      <div class="field">
        <label>{{ uiStore.t("codeLabel") }}</label>
        <input v-model="form.code" type="text" maxlength="6" placeholder="6位验证码" />
      </div>
      <button type="submit" class="btn-primary">{{ uiStore.t("completeRegister") }}</button>
    </form>
    <div class="err-text" v-if="error">{{ error }}</div>
    <p class="auth-links" style="margin-top: 16px">
      {{ uiStore.t("alreadyHaveAccount") }}<router-link to="/login">{{ uiStore.t("login") }}</router-link>
    </p>
  </PublicAuthLayout>
</template>
