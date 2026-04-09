<script setup>
defineProps({
  uiStore: {
    type: Object,
    required: true,
  },
  selectedRecord: {
    type: Object,
    default: null,
  },
  loadingDetail: {
    type: Boolean,
    default: false,
  },
  analyzing: {
    type: Boolean,
    default: false,
  },
  deletingRecordId: {
    type: Number,
    default: 0,
  },
  detailActionLabel: {
    type: String,
    default: "",
  },
  showAnalyzedResult: {
    type: Boolean,
    default: false,
  },
  statusText: {
    type: Function,
    required: true,
  },
  formatTime: {
    type: Function,
    required: true,
  },
  percentText: {
    type: Function,
    required: true,
  },
});

defineEmits(["analyze-selected", "delete-record"]);
</script>

<template>
  <section class="bankruptcy-detail prompt-box">
    <template v-if="loadingDetail">
      <div class="bankruptcy-empty">{{ uiStore.t("loading") }}</div>
    </template>

    <template v-else-if="!selectedRecord">
      <div class="bankruptcy-empty">
        <strong>{{ uiStore.t("bankruptcySelectRecord") }}</strong>
        <p>{{ uiStore.t("bankruptcyEmptyDetail") }}</p>
      </div>
    </template>

    <template v-else>
      <div class="bankruptcy-detail-head">
        <div>
          <h2>{{ selectedRecord.companyName || selectedRecord.sourceName }}</h2>
          <p>{{ selectedRecord.fileName }}</p>
        </div>
        <div class="bankruptcy-detail-actions">
          <button type="button" class="start-btn" :disabled="analyzing" @click="$emit('analyze-selected')">
            {{ analyzing ? uiStore.t("bankruptcyRunning") : detailActionLabel }}
          </button>
          <button
            type="button"
            class="bankruptcy-delete-btn detail-delete"
            :disabled="deletingRecordId === selectedRecord.id"
            @click="$emit('delete-record', selectedRecord.id)"
          >
            {{ uiStore.t("bankruptcyDeleteRecord") }}
          </button>
        </div>
      </div>

      <div class="bankruptcy-meta-grid">
        <div class="bankruptcy-meta-item">
          <span>{{ uiStore.t("bankruptcyStatus") }}</span>
          <strong>{{ statusText(selectedRecord.status) }}</strong>
        </div>
        <div class="bankruptcy-meta-item">
          <span>{{ uiStore.t("bankruptcyFileName") }}</span>
          <strong>{{ selectedRecord.fileName }}</strong>
        </div>
        <div class="bankruptcy-meta-item">
          <span>{{ uiStore.t("bankruptcyCreatedAt") }}</span>
          <strong>{{ formatTime(selectedRecord.createdAt) }}</strong>
        </div>
        <div class="bankruptcy-meta-item">
          <span>{{ uiStore.t("bankruptcyUpdatedAt") }}</span>
          <strong>{{ formatTime(selectedRecord.updatedAt) }}</strong>
        </div>
      </div>

      <div v-if="selectedRecord.status === 'uploaded'" class="bankruptcy-empty detail-empty">
        <strong>{{ uiStore.t("bankruptcyAnalyzeSaved") }}</strong>
        <p>{{ uiStore.t("bankruptcySavedForLater") }}</p>
      </div>

      <div v-else-if="selectedRecord.status === 'failed'" class="bankruptcy-empty detail-empty">
        <strong>{{ uiStore.t("bankruptcyStatusFailed") }}</strong>
        <p>{{ selectedRecord.errorMessage || uiStore.t("sendFailed") }}</p>
      </div>

      <template v-else-if="showAnalyzedResult">
        <div class="bankruptcy-result-grid">
          <div class="bankruptcy-result-card">
            <span>{{ uiStore.t("bankruptcyProbability") }}</span>
            <strong>{{ percentText(selectedRecord.probability) }}</strong>
          </div>
          <div class="bankruptcy-result-card">
            <span>{{ uiStore.t("bankruptcyThreshold") }}</span>
            <strong>{{ percentText(selectedRecord.threshold) }}</strong>
          </div>
          <div class="bankruptcy-result-card">
            <span>{{ uiStore.t("bankruptcyRiskLevel") }}</span>
            <strong>
              {{ selectedRecord.riskLevel === "high" ? uiStore.t("bankruptcyRiskHigh") : uiStore.t("bankruptcyRiskLow") }}
            </strong>
          </div>
          <div class="bankruptcy-result-card">
            <span>{{ uiStore.t("bankruptcyWorkspaceScope") }}</span>
            <strong>{{ selectedRecord.workspaceId }}</strong>
          </div>
        </div>

        <div class="bankruptcy-detail-section">
          <strong>{{ uiStore.t("bankruptcyTopFeatures") }}</strong>
          <div v-if="selectedRecord.topFeatures.length" class="bankruptcy-feature-list">
            <div v-for="feature in selectedRecord.topFeatures" :key="feature.name" class="bankruptcy-feature-row">
              <span>{{ feature.name }}</span>
              <span>{{ feature.shapValue.toFixed(4) }}</span>
            </div>
          </div>
        </div>

        <div v-if="selectedRecord.plotUrl" class="bankruptcy-detail-section">
          <strong>{{ uiStore.t("bankruptcyPlot") }}</strong>
          <div class="bankruptcy-plot-card">
            <img :src="selectedRecord.plotUrl" :alt="uiStore.t('bankruptcyPlot')" class="bankruptcy-plot" />
          </div>
        </div>
      </template>
    </template>
  </section>
</template>

<style scoped>
.bankruptcy-detail {
  min-height: 560px;
}

.bankruptcy-detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--line);
}

.bankruptcy-detail-head h2 {
  margin: 0;
  font-size: 24px;
  line-height: 1.2;
  color: var(--text);
}

.bankruptcy-detail-head p {
  margin: 6px 0 0;
  color: var(--text-muted);
}

.bankruptcy-detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-end;
}

.detail-delete,
.bankruptcy-delete-btn {
  min-width: 112px;
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

.bankruptcy-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.bankruptcy-meta-item,
.bankruptcy-result-card {
  display: grid;
  gap: 6px;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.02);
}

.bankruptcy-meta-item span,
.bankruptcy-result-card span {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.bankruptcy-meta-item strong,
.bankruptcy-result-card strong {
  color: var(--text);
  font-size: 15px;
}

.bankruptcy-empty {
  display: grid;
  place-items: center;
  min-height: 160px;
  text-align: center;
  color: var(--text-muted);
}

.bankruptcy-empty strong {
  color: var(--text);
}

.detail-empty {
  margin-top: 18px;
  border: 1px dashed var(--line);
  border-radius: 12px;
}

.bankruptcy-result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.bankruptcy-detail-section {
  margin-top: 20px;
}

.bankruptcy-feature-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.bankruptcy-feature-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--line);
  font-variant-numeric: tabular-nums;
}

.bankruptcy-plot-card {
  margin-top: 12px;
  border-radius: 14px;
  overflow: hidden;
  background: #fff;
  padding: 10px;
}

.bankruptcy-plot {
  display: block;
  width: 100%;
  height: auto;
}

@media (max-width: 1024px) {
  .bankruptcy-detail-head {
    flex-direction: column;
  }

  .bankruptcy-detail-actions {
    justify-content: flex-start;
  }
}
</style>
