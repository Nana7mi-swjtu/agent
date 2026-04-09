<script setup>
defineProps({
  sessions: {
    type: Array,
    default: () => [],
  },
  activeSessionId: {
    type: String,
    default: "",
  },
  uiStore: {
    type: Object,
    required: true,
  },
});

defineEmits(["select-session", "delete-session", "new-chat"]);
</script>

<template>
  <div class="channel-section-header section-gap"><span class="ch-caret">▾</span>{{ uiStore.t("chatHistory") }}</div>
  <div
    v-for="session in sessions"
    :key="session.id"
    class="channel-row"
    :class="{ active: activeSessionId === session.id }"
    @click="$emit('select-session', session.id)"
  >
    <span class="channel-hash session-hash">🕐</span>
    <span class="channel-row-name">{{ session.title }}</span>
    <button class="session-delete-btn" :title="uiStore.t('deleteChat')" @click.stop="$emit('delete-session', session.id)">
      ×
    </button>
  </div>

  <div class="channel-row channel-row-new" @click="$emit('new-chat')">
    <span class="channel-hash">＋</span>
    <span class="channel-row-name">{{ uiStore.t("newChat") }}</span>
  </div>
</template>

<style scoped>
.section-gap {
  margin-top: 16px;
}

.session-hash {
  font-size: 13px;
}

.channel-row-new {
  color: var(--accent);
  margin-top: 8px;
}
</style>
