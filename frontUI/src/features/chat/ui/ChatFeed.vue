<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";

import { ANALYSIS_MODULE_DEFINITIONS } from "@/entities/analysis-module/model/registry";
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
  selectedAnalysisModules: {
    type: Array,
    default: () => [],
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
  index > 0
  && !messageList[index - 1]?.pending
  && !messageList[index]?.pending
  && messageList[index - 1]?.from === messageList[index]?.from;

const feedElement = ref(null);
const autoFollow = ref(true);

const selectedModuleLabels = computed(() =>
  ANALYSIS_MODULE_DEFINITIONS
    .filter((module) => props.selectedAnalysisModules.includes(module.id))
    .map((module) => props.uiStore.t(module.labelKey)),
);

const welcomeGuidance = computed(() => {
  const count = props.selectedAnalysisModules.length;
  if (count > 1) {
    return {
      title: props.uiStore.t("analysisEmptyStateMultiTitle"),
      body: props.uiStore.t("analysisEmptyStateMultiBody"),
      steps: [
        props.uiStore.t("analysisEmptyStateStepSelect"),
        props.uiStore.t("analysisEmptyStateStepShared"),
        props.uiStore.t("analysisEmptyStateStepStage"),
      ],
    };
  }
  if (count === 1) {
    return {
      title: props.uiStore.t("analysisEmptyStateSingleTitle"),
      body: props.uiStore.t("analysisEmptyStateSingleBody"),
      steps: [
        props.uiStore.t("analysisEmptyStateStepSingleInput"),
        props.uiStore.t("analysisEmptyStateStepFollowUp"),
        props.uiStore.t("analysisEmptyStateStepStage"),
      ],
    };
  }
  return {
    title: props.uiStore.t("analysisEmptyStateTitle"),
    body: props.uiStore.t("analysisEmptyStateBody"),
    steps: [
      props.uiStore.t("analysisEmptyStateStepSelect"),
      props.uiStore.t("analysisEmptyStateStepShared"),
      props.uiStore.t("analysisEmptyStateStepStage"),
    ],
  };
});

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
      <p>{{ welcomeGuidance.title }}</p>
      <div v-if="selectedModuleLabels.length" class="feed-module-chips">
        <span v-for="label in selectedModuleLabels" :key="label" class="feed-module-chip">{{ label }}</span>
      </div>
      <p class="feed-welcome-body">{{ welcomeGuidance.body }}</p>
      <ul class="feed-welcome-steps">
        <li v-for="step in welcomeGuidance.steps" :key="step">{{ step }}</li>
      </ul>
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

.feed-welcome-body {
  margin-top: 12px !important;
}

.feed-module-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.feed-module-chip {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(47, 107, 255, 0.08);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}

.feed-welcome-steps {
  margin: 14px 0 0;
  padding-left: 20px;
  color: var(--text-channel);
}

.feed-welcome-steps li {
  margin: 0 0 8px 0;
  line-height: 1.5;
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
