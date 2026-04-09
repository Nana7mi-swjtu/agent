<script setup>
import AppUserPanel from "@/widgets/app-shell/ui/AppUserPanel.vue";
import SidebarRoleSection from "@/widgets/app-shell/ui/SidebarRoleSection.vue";
import SidebarSessionList from "@/widgets/app-shell/ui/SidebarSessionList.vue";

defineProps({
  currentPath: {
    type: String,
    required: true,
  },
  roles: {
    type: Array,
    default: () => [],
  },
  selectedRole: {
    type: String,
    default: "",
  },
  sessions: {
    type: Array,
    default: () => [],
  },
  activeSessionId: {
    type: String,
    default: "",
  },
  workspaceGifUrl: {
    type: String,
    default: "",
  },
  displayName: {
    type: String,
    required: true,
  },
  userAvatarUrl: {
    type: String,
    default: "",
  },
  userFallbackLetter: {
    type: String,
    default: "U",
  },
  workspaceId: {
    type: String,
    default: "default",
  },
  activeSessionCount: {
    type: Number,
    default: 0,
  },
  uiStore: {
    type: Object,
    required: true,
  },
});

defineEmits(["go-bankruptcy", "switch-role", "select-session", "delete-session", "new-chat", "go-profile", "logout"]);
</script>

<template>
  <div class="dc-sidebar">
    <div class="sidebar-guild-header">
      <div class="sidebar-guild-title">Agent Studio</div>
      <div class="sidebar-guild-subtitle">{{ workspaceId }}</div>
    </div>
    <div class="sidebar-scroller">
      <SidebarRoleSection
        :current-path="currentPath"
        :roles="roles"
        :selected-role="selectedRole"
        :ui-store="uiStore"
        @go-bankruptcy="$emit('go-bankruptcy')"
        @switch-role="$emit('switch-role', $event)"
      />

      <SidebarSessionList
        :sessions="sessions"
        :active-session-id="activeSessionId"
        :ui-store="uiStore"
        @select-session="$emit('select-session', $event)"
        @delete-session="$emit('delete-session', $event)"
        @new-chat="$emit('new-chat')"
      />

      <div v-if="workspaceGifUrl" class="sidebar-gif-card">
        <img :src="workspaceGifUrl" alt="workspace animation" class="sidebar-gif-preview" />
        <div class="sidebar-gif-label">动态展示</div>
      </div>
    </div>

    <AppUserPanel
      :display-name="displayName"
      :user-avatar-url="userAvatarUrl"
      :user-fallback-letter="userFallbackLetter"
      :workspace-id="workspaceId"
      :active-session-count="activeSessionCount"
      :ui-store="uiStore"
      @go-profile="$emit('go-profile')"
      @logout="$emit('logout')"
    />
  </div>
</template>
