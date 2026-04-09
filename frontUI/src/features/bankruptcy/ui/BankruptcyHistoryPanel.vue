<script setup>
defineProps({
  uiStore: {
    type: Object,
    required: true,
  },
  records: {
    type: Array,
    default: () => [],
  },
  selectedRecordId: {
    type: Number,
    default: 0,
  },
  loadingRecords: {
    type: Boolean,
    default: false,
  },
  deletingRecordId: {
    type: Number,
    default: 0,
  },
  statusText: {
    type: Function,
    required: true,
  },
  formatTime: {
    type: Function,
    required: true,
  },
});

defineEmits(["select-record", "delete-record"]);
</script>

<template>
  <div class="prompt-box bankruptcy-list-card">
    <div class="bankruptcy-list-head">
      <strong>{{ uiStore.t("bankruptcyHistory") }}</strong>
      <span class="bankruptcy-count">{{ records.length }}</span>
    </div>

    <div v-if="loadingRecords" class="bankruptcy-empty">{{ uiStore.t("loading") }}</div>
    <div v-else-if="!records.length" class="bankruptcy-empty">{{ uiStore.t("bankruptcyNoRecords") }}</div>
    <div v-else class="bankruptcy-record-list">
      <div
        v-for="record in records"
        :key="record.id"
        class="bankruptcy-record-row"
        :class="{ active: selectedRecordId === record.id }"
        tabindex="0"
        @click="$emit('select-record', record.id)"
        @keyup.enter="$emit('select-record', record.id)"
      >
        <div class="bankruptcy-record-main">
          <div class="bankruptcy-record-name">{{ record.companyName || record.sourceName }}</div>
          <div class="bankruptcy-record-meta">
            <span class="bankruptcy-status-chip" :data-status="record.status">{{ statusText(record.status) }}</span>
            <span v-if="record.riskLevel" class="bankruptcy-risk-text">
              {{ record.riskLevel === "high" ? uiStore.t("bankruptcyRiskHigh") : uiStore.t("bankruptcyRiskLow") }}
            </span>
          </div>
          <div class="bankruptcy-record-time">{{ formatTime(record.updatedAt || record.createdAt) }}</div>
        </div>
        <button
          type="button"
          class="bankruptcy-delete-btn"
          :disabled="deletingRecordId === record.id"
          @click.stop="$emit('delete-record', record.id)"
        >
          {{ uiStore.t("bankruptcyDeleteRecord") }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bankruptcy-list-card {
  margin-top: 0;
  min-height: 320px;
}

.bankruptcy-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.bankruptcy-count {
  min-width: 28px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(88, 101, 242, 0.18);
  color: var(--text);
  font-size: 12px;
  text-align: center;
}

.bankruptcy-record-list {
  display: grid;
  gap: 10px;
}

.bankruptcy-record-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;
  text-align: left;
}

.bankruptcy-record-row:hover,
.bankruptcy-record-row.active {
  border-color: rgba(88, 101, 242, 0.55);
  background: rgba(88, 101, 242, 0.12);
}

.bankruptcy-record-main {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.bankruptcy-record-name {
  font-weight: 700;
  line-height: 1.3;
}

.bankruptcy-record-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.bankruptcy-record-time,
.bankruptcy-risk-text {
  font-size: 12px;
  color: var(--text-muted);
}

.bankruptcy-status-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.bankruptcy-status-chip[data-status="uploaded"] {
  background: rgba(99, 102, 241, 0.18);
  color: #c7d2fe;
}

.bankruptcy-status-chip[data-status="analyzed"] {
  background: rgba(34, 197, 94, 0.18);
  color: #86efac;
}

.bankruptcy-status-chip[data-status="failed"] {
  background: rgba(248, 113, 113, 0.18);
  color: #fca5a5;
}

.bankruptcy-delete-btn {
  border: 1px solid rgba(248, 113, 113, 0.25);
  background: transparent;
  color: #fca5a5;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.bankruptcy-delete-btn:hover:not(:disabled) {
  background: rgba(248, 113, 113, 0.12);
  border-color: rgba(248, 113, 113, 0.5);
}

.bankruptcy-delete-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.bankruptcy-empty {
  display: grid;
  place-items: center;
  min-height: 160px;
  text-align: center;
  color: var(--text-muted);
}
</style>
