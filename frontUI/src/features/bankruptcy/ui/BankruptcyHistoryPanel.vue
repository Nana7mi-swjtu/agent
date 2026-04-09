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
  background: var(--accent-soft);
  color: var(--accent);
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
  padding: 14px;
  border: 1px solid rgba(47, 107, 255, 0.08);
  border-radius: 18px;
  background: var(--surface-panel-muted);
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
  text-align: left;
}

.bankruptcy-record-row:hover,
.bankruptcy-record-row.active {
  transform: translateY(-1px);
  border-color: rgba(47, 107, 255, 0.24);
  background: rgba(47, 107, 255, 0.08);
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
  background: var(--accent-soft);
  color: var(--accent);
}

.bankruptcy-status-chip[data-status="analyzed"] {
  background: var(--ok-soft);
  color: var(--ok);
}

.bankruptcy-status-chip[data-status="failed"] {
  background: var(--danger-soft);
  color: var(--danger);
}

.bankruptcy-delete-btn {
  border: 1px solid rgba(217, 92, 92, 0.18);
  background: rgba(217, 92, 92, 0.04);
  color: var(--danger);
  border-radius: 999px;
  padding: 8px 10px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.bankruptcy-delete-btn:hover:not(:disabled) {
  background: rgba(217, 92, 92, 0.1);
  border-color: rgba(217, 92, 92, 0.26);
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
