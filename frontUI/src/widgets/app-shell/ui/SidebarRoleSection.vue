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

defineEmits(["go-bankruptcy", "switch-role"]);
</script>

<template>
  <div class="channel-section-header"><span class="ch-caret">▾</span>{{ uiStore.t("switchRole") }}</div>
  <div class="channel-row" :class="{ active: currentPath === '/bankruptcy-analysis' }" @click="$emit('go-bankruptcy')">
    <span class="channel-hash">#</span>
    <span class="channel-row-name">{{ uiStore.t("bankruptcyAnalysis") }}</span>
  </div>
  <div
    v-for="role in roles"
    :key="role.key"
    class="channel-row"
    :class="{ active: selectedRole === role.key && currentPath === '/chat' }"
    @click="$emit('switch-role', role.key)"
  >
    <span class="channel-hash">#</span>
    <span class="channel-row-name">{{ role.name }}</span>
  </div>
</template>
