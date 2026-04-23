<script setup>
import { nextTick, onMounted, ref, watch } from "vue";

import ChatMessageItem from "@/features/chat/ui/ChatMessageItem.vue";

const props = defineProps({
  activeSession: {
    type: Object,
    default: null,
  },
  channelName: {
    type: String,
    default: "",
  },
  displayTime: {
    type: Function,
    required: true,
  },
  agentTraceEnabled: {
    type: Boolean,
    default: false,
  },
  traceDetailsVisible: {
    type: Boolean,
    default: false,
  },
  ragDebugEnabled: {
    type: Boolean,
    default: false,
  },
  ragDebugDetailsVisible: {
    type: Boolean,
    default: false,
  },
  traceTitle: {
    type: Function,
    required: true,
  },
  traceStatus: {
    type: Function,
    required: true,
  },
  traceDetailsEntries: {
    type: Function,
    required: true,
  },
  uiStore: {
    type: Object,
    required: true,
  },
  generateReport: {
    type: Function,
    default: () => {},
  },
  regenerateReport: {
    type: Function,
    default: () => {},
  },
});

const isGroupedMessage = (index, messageList) =>
  index > 0
  && !messageList[index - 1]?.pending
  && !messageList[index]?.pending
  && messageList[index - 1]?.from === messageList[index]?.from;

const feedElement = ref(null);
const autoFollow = ref(true);

const isNearBottom = () => {
  const element = feedElement.value;
  if (!element) return true;
  return element.scrollHeight - element.scrollTop - element.clientHeight < 72;
};

const scrollToBottom = async (force = false) => {
  await nextTick();
  const element = feedElement.value;
  if (!element || (!force && !autoFollow.value)) return;
  element.scrollTop = element.scrollHeight;
};

const handleScroll = () => {
  autoFollow.value = isNearBottom();
};

const jumpToLatest = async () => {
  autoFollow.value = true;
  await scrollToBottom(true);
};

watch(
  () => props.activeSession?.id,
  async () => {
    autoFollow.value = true;
    await scrollToBottom(true);
  },
  { immediate: true },
);

watch(
  () => props.activeSession?.messages?.length || 0,
  async () => {
    await scrollToBottom();
  },
);

watch(
  () => props.activeSession?.messages?.at(-1)?.text || "",
  async () => {
    await scrollToBottom();
  },
);

onMounted(async () => {
  await scrollToBottom(true);
});
</script>

<template>
  <div ref="feedElement" class="dc-feed" @scroll="handleScroll">
    <div v-if="!activeSession || !activeSession.messages.length" class="feed-welcome">
      <h2># {{ channelName }}</h2>
      <p>{{ uiStore.t("inputPlaceholder") }}</p>
    </div>

    <ChatMessageItem
      v-for="(message, index) in activeSession?.messages || []"
      :key="message.id || index"
      :message="message"
      :is-grouped="isGroupedMessage(index, activeSession.messages)"
      :display-time="displayTime"
      :agent-trace-enabled="agentTraceEnabled"
      :trace-details-visible="traceDetailsVisible"
      :rag-debug-enabled="ragDebugEnabled"
      :rag-debug-details-visible="ragDebugDetailsVisible"
      :trace-title="traceTitle"
      :trace-status="traceStatus"
      :trace-details-entries="traceDetailsEntries"
      :generate-report="generateReport"
      :regenerate-report="regenerateReport"
    />

    <button
      v-if="activeSession?.messages?.length && !autoFollow"
      type="button"
      class="jump-latest-btn"
      @click="jumpToLatest"
    >
      {{ uiStore.t("chatJumpLatest") }}
    </button>
  </div>
</template>

<style scoped>
.dc-feed {
  position: relative;
  flex: 1;
  overflow-y: auto;
  padding: 18px 0 6px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.feed-welcome {
  padding: 18px 24px 26px;
  margin-top: auto;
  border-top: 1px solid var(--line);
}

.feed-welcome h2 {
  margin: 0 0 8px;
  font-size: 34px;
  font-weight: 700;
  color: var(--text);
}

.feed-welcome p {
  margin: 0;
  color: var(--text-muted);
  font-size: 15px;
}

.jump-latest-btn {
  position: sticky;
  align-self: flex-end;
  right: 24px;
  bottom: 16px;
  margin: auto 24px 12px auto;
  min-height: 38px;
  padding: 0 14px;
  border: 1px solid rgba(47, 107, 255, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.94);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
}
</style>
