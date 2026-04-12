<script setup>
import { useRoute, useRouter } from "vue-router";

import { useLoginForm } from "@/features/auth/model/useLoginForm";
import { useUiStore } from "@/shared/model/ui-store";
import PublicAuthLayout from "@/widgets/auth-shell/ui/PublicAuthLayout.vue";

const router = useRouter();
const route = useRoute();
const uiStore = useUiStore();
const { form, error, submit } = useLoginForm();

const onSubmit = async () => {
  const result = await submit();
  if (!result.ok) return;

  const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/app";
  router.push(redirect);
};
</script>

<template>
  <PublicAuthLayout>
    <h1>Agent Studio</h1>
    <p class="auth-sub">{{ uiStore.t("authWelcomeBack") }}</p>
    <form @submit.prevent="onSubmit">
      <div class="field">
        <label>{{ uiStore.t("emailLabel") }}</label>
        <input v-model="form.email" type="email" autocomplete="email" />
      </div>
      <div class="field">
        <label>{{ uiStore.t("passwordLabel") }}</label>
        <input v-model="form.password" type="password" autocomplete="current-password" />
      </div>
      <div class="err-text" v-if="error">{{ error }}</div>
      <button type="submit" class="btn-primary">{{ uiStore.t("login") }}</button>
    </form>
    <p class="auth-links" style="margin-top: 16px">
      {{ uiStore.t("needAccount") }}<router-link to="/register">{{ uiStore.t("createAccount") }}</router-link>
      &nbsp;路&nbsp;
      <router-link to="/forgot-password">{{ uiStore.t("forgotPassword") }}</router-link>
    </p>
  </PublicAuthLayout>
</template>
