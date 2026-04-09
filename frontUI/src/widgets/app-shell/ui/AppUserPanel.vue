<script setup>
defineProps({
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

defineEmits(["go-profile", "logout"]);
</script>

<template>
  <div class="sidebar-user-panel">
    <div class="user-avatar" @click="$emit('go-profile')">
      <img v-if="userAvatarUrl" :src="userAvatarUrl" alt="avatar" />
      <span v-else>{{ userFallbackLetter }}</span>
      <div class="status-dot"></div>
    </div>
    <div class="user-name-block">
      <strong>{{ displayName }}</strong>
      <small>{{ workspaceId }} · {{ activeSessionCount }} {{ uiStore.t("chatHistory") }}</small>
    </div>
    <button class="panel-icon-btn" title="设置" @click="$emit('go-profile')">Me</button>
    <button class="panel-icon-btn" title="退出" @click="$emit('logout')">Out</button>
  </div>
</template>
