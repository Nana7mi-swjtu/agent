<script setup>
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
  uiStore: {
    type: Object,
    required: true,
  },
});

defineEmits(["go-home", "go-bankruptcy", "switch-role"]);
</script>

<template>
  <nav class="dc-server-bar">
    <button type="button" class="server-icon icon-home" :class="{ active: currentPath === '/app' }" title="主页" @click="$emit('go-home')">
      <span class="server-icon-badge">AI</span>
      <span class="server-icon-label">Agent</span>
    </button>
    <button
      type="button"
      class="server-icon"
      :class="{ active: currentPath === '/bankruptcy-analysis' }"
      :title="uiStore.t('bankruptcyAnalysis')"
      @click="$emit('go-bankruptcy')"
    >
      <span class="server-icon-badge">WF</span>
      <span class="server-icon-label">{{ uiStore.t("bankruptcyAnalysis") }}</span>
    </button>
    <div class="server-sep"></div>
    <button
      v-for="role in roles"
      :key="role.key"
      type="button"
      class="server-icon"
      :class="{ active: selectedRole === role.key && currentPath === '/chat' }"
      :title="role.name"
      @click="$emit('switch-role', role.key)"
    >
      <span class="server-icon-badge">{{ role.name.slice(0, 1).toUpperCase() }}</span>
      <span class="server-icon-label">{{ role.name }}</span>
    </button>
  </nav>
</template>
