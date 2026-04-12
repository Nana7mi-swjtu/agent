<script setup>
import { onMounted } from "vue";
import { RouterView } from "vue-router";

import { useAppShell } from "@/widgets/app-shell/model/useAppShell";
import AppServerBar from "@/widgets/app-shell/ui/AppServerBar.vue";
import AppSidebar from "@/widgets/app-shell/ui/AppSidebar.vue";
import { useUiStore } from "@/shared/model/ui-store";

const uiStore = useUiStore();
const {
  currentPath,
  roles,
  selectedRole,
  sessions,
  activeSessionId,
  workspaceId,
  workspaceGifUrl,
  displayName,
  userAvatarUrl,
  userFallbackLetter,
  activeSessionCount,
  initialize,
  openSession,
  newChat,
  quickSwitchRole,
  removeSession,
  goHome,
  goBankruptcy,
  goProfile,
  logout,
} = useAppShell();

onMounted(initialize);
</script>

<template>
  <div class="dc-chrome">
    <AppServerBar
      :current-path="currentPath"
      :roles="roles"
      :selected-role="selectedRole"
      :ui-store="uiStore"
      @go-home="goHome"
      @go-bankruptcy="goBankruptcy"
      @switch-role="quickSwitchRole"
    />

    <AppSidebar
      :current-path="currentPath"
      :roles="roles"
      :selected-role="selectedRole"
      :sessions="sessions"
      :active-session-id="activeSessionId"
      :workspace-gif-url="workspaceGifUrl"
      :display-name="displayName"
      :user-avatar-url="userAvatarUrl"
      :user-fallback-letter="userFallbackLetter"
      :workspace-id="workspaceId"
      :active-session-count="activeSessionCount"
      :ui-store="uiStore"
      @go-bankruptcy="goBankruptcy"
      @switch-role="quickSwitchRole"
      @select-session="openSession"
      @delete-session="removeSession"
      @new-chat="newChat"
      @go-profile="goProfile"
      @logout="logout"
    />

    <div class="dc-main">
      <div class="dc-main-scroll">
      <RouterView />
      </div>
    </div>
  </div>
</template>
