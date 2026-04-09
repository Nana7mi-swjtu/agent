<script setup>
import ChatMessageItem from "@/features/chat/ui/ChatMessageItem.vue";

defineProps({
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
});

const isGroupedMessage = (index, messageList) =>
  index > 0 && messageList[index - 1]?.from === messageList[index]?.from;
</script>

<template>
  <div class="dc-feed">
    <div v-if="!activeSession || !activeSession.messages.length" class="feed-welcome">
      <h2># {{ channelName }}</h2>
      <p>{{ uiStore.t("inputPlaceholder") }}</p>
    </div>

    <ChatMessageItem
      v-for="(message, index) in activeSession?.messages || []"
      :key="index"
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
    />
  </div>
</template>

<style scoped>
.dc-feed {
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
</style>
