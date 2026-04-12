<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { storeToRefs } from "pinia";

import { useWorkspaceContext } from "@/features/workspace-context/model/useWorkspaceContext";
import { useWorkspaceStore } from "@/entities/workspace/model/store";
import ContentSection from "@/shared/ui/ContentSection.vue";
import FeedbackMessage from "@/shared/ui/FeedbackMessage.vue";
import { useUiStore } from "@/shared/model/ui-store";

const router = useRouter();
const uiStore = useUiStore();
const workspaceStore = useWorkspaceStore();
const { roles, selectedRole, ready } = storeToRefs(workspaceStore);
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
