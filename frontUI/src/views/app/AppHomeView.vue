<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { storeToRefs } from "pinia";

import ContentSection from "@/components/shared/ContentSection.vue";
import FeedbackMessage from "@/components/shared/FeedbackMessage.vue";
import { useWorkspaceContext } from "@/composables/useWorkspaceContext";
import { useUiStore } from "@/stores/ui";
import { useWorkspaceStore } from "@/stores/workspace";

const router = useRouter();
const uiStore = useUiStore();
const workspaceStore = useWorkspaceStore();
const { roles, selectedRole, systemPrompt, ready } = storeToRefs(workspaceStore);
const { loadContext, selectRole } = useWorkspaceContext();
const error = ref("");

const toChat = () => {
  if (!selectedRole.value) {
    error.value = uiStore.t("noRole");
    return;
  }
  router.push("/chat");
};

const toBankruptcyAnalysis = () => {
  router.push("/bankruptcy-analysis");
};

const onSelectRole = async (roleKey) => {
  error.value = "";
  const result = await selectRole(roleKey);
  if (!result.ok) {
    error.value = result.error;
  }
};

onMounted(async () => {
  if (!ready.value) {
    await loadContext();
  }
});
</script>

<template>
  <ContentSection :title="uiStore.t('roleSelection')" :subtitle="uiStore.t('roleSelectionDesc')">
    <FeedbackMessage :muted="!ready ? uiStore.t('loading') : ''" />

    <template v-if="ready">
      <div class="role-grid">
        <button
          v-for="role in roles"
          :key="role.key"
          type="button"
          class="role-card"
          :class="{ active: selectedRole === role.key }"
          @click="onSelectRole(role.key)"
        >
          <strong>{{ role.name }}</strong>
          <span>{{ role.description }}</span>
        </button>
      </div>

      <div class="prompt-box" v-if="systemPrompt">
        <strong>{{ uiStore.t("promptLabel") }}</strong>
        <p style="margin: 8px 0 0; font-size: 13px; white-space: pre-wrap; word-break: break-word">{{ systemPrompt }}</p>
      </div>

      <FeedbackMessage :error="error" />

      <button type="button" class="start-btn" style="margin-top: 20px" :disabled="!selectedRole" @click="toChat">
        {{ uiStore.t("startChat") }}
      </button>
      <button type="button" class="start-btn" style="margin-top: 12px" @click="toBankruptcyAnalysis">
        {{ uiStore.t("bankruptcyAnalysis") }}
      </button>
    </template>
  </ContentSection>
</template>
