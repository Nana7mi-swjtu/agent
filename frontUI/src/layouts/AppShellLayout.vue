<script setup>
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { storeToRefs } from "pinia";

import { RouterView } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import { useUiStore } from "@/stores/ui";
import { useWorkspaceStore } from "@/stores/workspace";
import { patchWorkspaceContext } from "@/services/workspace";

const router = useRouter();
const authStore = useAuthStore();
const chatStore = useChatStore();
const uiStore = useUiStore();
const workspaceStore = useWorkspaceStore();

const { sessions, activeSessionId } = storeToRefs(chatStore);
const { roles, selectedRole, workspaceId } = storeToRefs(workspaceStore);

const workspaceGifUrl = computed(() => uiStore.authBgGifUrl);
const displayName = computed(() => authStore.user?.nickname || authStore.user?.email || "User");
const userAvatarUrl = computed(() => authStore.user?.avatarUrl || "");
const userFallbackLetter = computed(() => {
  const source = displayName.value.trim();
  return source ? source.charAt(0).toUpperCase() : "U";
});
const activeSessionCount = computed(() => sessions.value.length);

const setActiveSession = (id) => {
  chatStore.setActiveSession(id);
  if (router.currentRoute.value.path !== "/chat") {
    router.push("/chat");
  }
};

const newChat = () => {
  chatStore.createSession(selectedRole.value, uiStore.getRoleDisplayName, workspaceId.value);
  router.push("/chat");
};

const quickSwitchRole = async (roleKey) => {
  const result = await patchWorkspaceContext(roleKey);
  if (!result.ok) return;
  workspaceStore.applyContext(result.data?.data || {});
  chatStore.createSession(roleKey, uiStore.getRoleDisplayName, workspaceId.value);
  if (router.currentRoute.value.path !== "/chat") {
    router.push("/chat");
  }
};

const removeSession = (sessionId) => {
  chatStore.deleteSession(sessionId);
};

const goHome = () => router.push("/app");
const goProfile = () => router.push("/profile");
const onLogout = async () => {
  await authStore.logout();
  router.push("/login");
};

onMounted(async () => {
  await authStore.refreshUserProfile();
});
</script>

<template>
  <div class="dc-chrome">
    <nav class="dc-server-bar">
      <div class="server-icon icon-home" :class="{ active: $route.path === '/app' }" @click="goHome" title="主页">⚡</div>
      <div class="server-sep"></div>
      <div
        v-for="role in roles"
        :key="role.key"
        class="server-icon"
        :class="{ active: selectedRole === role.key && $route.path === '/chat' }"
        :title="role.name"
        @click="quickSwitchRole(role.key)"
      >
        {{ role.name.slice(0, 1).toUpperCase() }}
      </div>
    </nav>

    <div class="dc-sidebar">
      <div class="sidebar-guild-header">Agent Studio</div>
      <div class="sidebar-scroller">
        <div class="channel-section-header"><span class="ch-caret">▾</span>{{ uiStore.t("switchRole") }}</div>
        <div
          v-for="role in roles"
          :key="role.key"
          class="channel-row"
          :class="{ active: selectedRole === role.key && $route.path === '/chat' }"
          @click="quickSwitchRole(role.key)"
        >
          <span class="channel-hash">#</span>
          <span class="channel-row-name">{{ role.name }}</span>
        </div>

        <div class="channel-section-header" style="margin-top: 16px"><span class="ch-caret">▾</span>{{ uiStore.t("chatHistory") }}</div>
        <div
          v-for="s in sessions"
          :key="s.id"
          class="channel-row"
          :class="{ active: activeSessionId === s.id }"
          @click="setActiveSession(s.id)"
        >
          <span class="channel-hash" style="font-size: 13px">🕐</span>
          <span class="channel-row-name">{{ s.title }}</span>
          <button
            class="session-delete-btn"
            :title="uiStore.t('deleteChat')"
            @click.stop="removeSession(s.id)"
          >
            ×
          </button>
        </div>

        <div class="channel-row" style="color: var(--accent); margin-top: 8px" @click="newChat">
          <span class="channel-hash">＋</span>
          <span class="channel-row-name">{{ uiStore.t("newChat") }}</span>
        </div>

        <div v-if="workspaceGifUrl" class="sidebar-gif-card">
          <img :src="workspaceGifUrl" alt="workspace animation" class="sidebar-gif-preview" />
          <div class="sidebar-gif-label">动态展示</div>
        </div>
      </div>

      <div class="sidebar-user-panel">
        <div class="user-avatar" @click="goProfile">
          <img v-if="userAvatarUrl" :src="userAvatarUrl" alt="avatar" />
          <span v-else>{{ userFallbackLetter }}</span>
          <div class="status-dot"></div>
        </div>
        <div class="user-name-block">
          <strong>{{ displayName }}</strong>
          <small>{{ workspaceId }} · {{ activeSessionCount }} {{ uiStore.t("chatHistory") }}</small>
        </div>
        <button class="panel-icon-btn" title="设置" @click="goProfile">⚙</button>
        <button class="panel-icon-btn" title="退出" @click="onLogout">⏻</button>
      </div>
    </div>

    <div class="dc-main">
      <RouterView />
    </div>
  </div>
</template>
