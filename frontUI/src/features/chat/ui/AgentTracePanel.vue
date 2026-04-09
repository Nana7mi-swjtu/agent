<script setup>
import { formatTraceDetailValue } from "@/entities/chat/lib/message";
import { useUiStore } from "@/shared/model/ui-store";

defineProps({
  steps: {
    type: Array,
    default: () => [],
  },
  detailsVisible: {
    type: Boolean,
    default: false,
  },
  titleResolver: {
    type: Function,
    required: true,
  },
  statusResolver: {
    type: Function,
    required: true,
  },
  detailEntriesResolver: {
    type: Function,
    required: true,
  },
  summaryOnly: {
    type: Boolean,
    default: false,
  },
});

const uiStore = useUiStore();
</script>

<template>
  <div class="agent-trace-panel">
    <div class="agent-trace-title">{{ uiStore.t("agentTracePanelTitle") }}</div>
    <div class="agent-trace-list">
      <div v-for="step in steps" :key="step.id" class="agent-trace-step">
        <div class="agent-trace-head">
          <strong>{{ titleResolver(step) }}</strong>
          <span class="agent-trace-status">{{ statusResolver(step) }}</span>
        </div>
        <div class="agent-trace-summary">{{ step.summary }}</div>
        <template v-if="!summaryOnly">
          <div v-if="Array.isArray(step.children) && step.children.length" class="agent-trace-children">
            <div v-for="child in step.children" :key="child.id" class="agent-trace-child">
              <div class="agent-trace-head">
                <strong>{{ titleResolver(child) }}</strong>
                <span class="agent-trace-status">{{ statusResolver(child) }}</span>
              </div>
              <div class="agent-trace-summary">{{ child.summary }}</div>
            </div>
          </div>
          <div v-if="detailEntriesResolver(step).length" class="agent-trace-details">
            <template v-if="detailsVisible">
              <div class="rag-debug-mini">{{ uiStore.t("agentTraceDetailsLabel") }}</div>
              <div
                v-for="[key, value] in detailEntriesResolver(step)"
                :key="`${step.id}_${key}`"
                class="agent-trace-detail-row"
              >
                <span>{{ key }}</span>
                <span>{{ formatTraceDetailValue(value) }}</span>
              </div>
            </template>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-trace-panel {
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(47, 107, 255, 0.12);
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(244, 249, 255, 0.96), rgba(255, 255, 255, 0.94));
}

.agent-trace-title {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

.agent-trace-list {
  display: grid;
  gap: 10px;
}

.agent-trace-step,
.agent-trace-child {
  padding-left: 14px;
  border-left: 2px solid rgba(47, 107, 255, 0.18);
}

.agent-trace-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.agent-trace-status {
  font-size: 11px;
  color: var(--accent);
  text-transform: uppercase;
  font-weight: 700;
}

.agent-trace-summary {
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-channel);
  white-space: pre-wrap;
  word-break: break-word;
}

.agent-trace-details {
  margin-top: 8px;
  display: grid;
  gap: 4px;
}

.agent-trace-detail-row {
  display: grid;
  grid-template-columns: minmax(120px, 180px) minmax(0, 1fr);
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.agent-trace-children {
  margin-top: 8px;
  display: grid;
  gap: 6px;
}
</style>
