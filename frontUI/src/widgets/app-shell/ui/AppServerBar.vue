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
    <div class="server-icon icon-home" :class="{ active: currentPath === '/app' }" title="主页" @click="$emit('go-home')">⚡</div>
    <div class="server-icon" :class="{ active: currentPath === '/bankruptcy-analysis' }" :title="uiStore.t('bankruptcyAnalysis')" @click="$emit('go-bankruptcy')">📊</div>
    <div class="server-sep"></div>
    <div
      v-for="role in roles"
      :key="role.key"
      class="server-icon"
      :class="{ active: selectedRole === role.key && currentPath === '/chat' }"
      :title="role.name"
      @click="$emit('switch-role', role.key)"
    >
      {{ role.name.slice(0, 1).toUpperCase() }}
    </div>
  </nav>
</template>
