<script setup>
import { computed, ref, watch } from "vue";
import { storeToRefs } from "pinia";

import ContentSection from "@/components/shared/ContentSection.vue";
import FeedbackMessage from "@/components/shared/FeedbackMessage.vue";
import { useBankruptcyStore } from "@/stores/bankruptcy";
import { useUiStore } from "@/stores/ui";
import { useWorkspaceStore } from "@/stores/workspace";

const uiStore = useUiStore();
const workspaceStore = useWorkspaceStore();
const bankruptcyStore = useBankruptcyStore();

const { workspaceId } = storeToRefs(workspaceStore);
const {
  records,
  selectedRecordId,
  selectedRecord,
  loadingRecords,
  loadingDetail,
  uploading,
  analyzing,
  deletingRecordId,
  error,
} = storeToRefs(bankruptcyStore);

const enterpriseName = ref("");
const selectedFile = ref(null);
const fileInput = ref(null);
const success = ref("");

const resetForm = () => {
  selectedFile.value = null;
  enterpriseName.value = "";
  if (fileInput.value) {
    fileInput.value.value = "";
  }
};

watch(
  workspaceId,
  async () => {
    resetForm();
    success.value = "";
    bankruptcyStore.reset();
    await bankruptcyStore.loadRecords(workspaceId.value);
  },
  { immediate: true },
);

const onFileChange = (event) => {
  selectedFile.value = event?.target?.files?.[0] || null;
  success.value = "";
  bankruptcyStore.clearMessages();
};

const onUpload = async () => {
  success.value = "";
  bankruptcyStore.clearMessages();
  if (!selectedFile.value) {
    bankruptcyStore.error = uiStore.t("bankruptcyNeedFile");
    return;
  }
  const result = await bankruptcyStore.saveRecord(workspaceId.value, selectedFile.value, enterpriseName.value);
  if (!result.ok) return;
  success.value = uiStore.t("bankruptcyUploadSaved");
  resetForm();
};

const selectRecord = async (recordId) => {
  success.value = "";
  await bankruptcyStore.loadRecordDetail(workspaceId.value, recordId);
};

const analyzeSelected = async () => {
  if (!selectedRecord.value?.id) return;
  success.value = "";
  const result = await bankruptcyStore.runAnalysis(workspaceId.value, selectedRecord.value.id);
  if (result.ok) {
    success.value = uiStore.t("bankruptcyResult");
  }
};

const deleteRecord = async (recordId) => {
  if (!recordId) return;
  if (!window.confirm(uiStore.t("bankruptcyDeleteConfirm"))) return;
  success.value = "";
  const result = await bankruptcyStore.removeRecord(workspaceId.value, recordId);
  if (result.ok) {
    success.value = uiStore.t("bankruptcyDeleteRecord");
  }
};

const statusText = (status) => {
  if (status === "analyzed") return uiStore.t("bankruptcyStatusAnalyzed");
  if (status === "failed") return uiStore.t("bankruptcyStatusFailed");
  return uiStore.t("bankruptcyStatusUploaded");
};

const percentText = (value) => (value == null ? "--" : `${(Number(value || 0) * 100).toFixed(2)}%`);

const formatTime = (value) => {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "--";
  return parsed.toLocaleString(uiStore.language === "zh-CN" ? "zh-CN" : "en-US", {
    hour12: false,
  });
};

const detailActionLabel = computed(() =>
  selectedRecord.value?.status === "analyzed" ? uiStore.t("bankruptcyRetryAnalysis") : uiStore.t("bankruptcyAnalyzeSaved"),
);

const showAnalyzedResult = computed(() => selectedRecord.value?.status === "analyzed");
</script>

<template>
  <ContentSection :title="uiStore.t('bankruptcyAnalysis')" :subtitle="uiStore.t('bankruptcyAnalysisDesc')">
    <FeedbackMessage :error="error" :success="success" :muted="uploading || analyzing ? uiStore.t('bankruptcyRunning') : ''" />

    <div class="bankruptcy-shell">
      <aside class="bankruptcy-sidebar">
        <div class="prompt-box">
          <strong>{{ uiStore.t("bankruptcyWorkspaceScope") }}</strong>
          <p class="scope-text">{{ workspaceId }}</p>
        </div>

        <div class="prompt-box" style="margin-top: 16px">
          <strong>{{ uiStore.t("bankruptcySaveUpload") }}</strong>
          <input
            ref="fileInput"
            type="file"
            accept=".csv,text/csv"
            class="bankruptcy-file-input"
            @change="onFileChange"
          />

          <div class="bankruptcy-form-row">
            <label class="bankruptcy-label">{{ uiStore.t("bankruptcyEnterpriseName") }}</label>
            <input
              v-model="enterpriseName"
              type="text"
              :placeholder="uiStore.t('bankruptcyEnterpriseName')"
              class="bankruptcy-input"
            />
            <p class="bankruptcy-hint">{{ uiStore.t("bankruptcyEnterpriseNameHint") }}</p>
          </div>

          <button type="button" class="start-btn" :disabled="uploading" @click="onUpload">
            {{ uploading ? uiStore.t("bankruptcyRunning") : uiStore.t("bankruptcySaveUpload") }}
          </button>
        </div>

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
              @click="selectRecord(record.id)"
              @keyup.enter="selectRecord(record.id)"
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
                @click.stop="deleteRecord(record.id)"
              >
                {{ uiStore.t("bankruptcyDeleteRecord") }}
              </button>
            </div>
          </div>
        </div>
      </aside>

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
              <button
                type="button"
                class="start-btn"
                :disabled="analyzing"
                @click="analyzeSelected"
              >
                {{ analyzing ? uiStore.t("bankruptcyRunning") : detailActionLabel }}
              </button>
              <button
                type="button"
                class="bankruptcy-delete-btn detail-delete"
                :disabled="deletingRecordId === selectedRecord.id"
                @click="deleteRecord(selectedRecord.id)"
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
                <div
                  v-for="feature in selectedRecord.topFeatures"
                  :key="feature.name"
                  class="bankruptcy-feature-row"
                >
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
    </div>
  </ContentSection>
</template>

<style scoped>
.scope-text {
  margin: 8px 0 0;
  font-size: 13px;
}

.bankruptcy-shell {
  display: grid;
  grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
  gap: 18px;
  min-height: 0;
}

.bankruptcy-sidebar {
  display: grid;
  gap: 0;
  align-content: start;
}

.bankruptcy-file-input {
  display: block;
  width: 100%;
  margin-top: 12px;
}

.bankruptcy-form-row {
  margin-top: 16px;
}

.bankruptcy-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.bankruptcy-input {
  width: 100%;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--line);
  background: var(--bg-server-bar);
  color: var(--text);
  outline: none;
}

.bankruptcy-input:focus {
  border-color: var(--accent);
}

.bankruptcy-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.bankruptcy-list-card {
  margin-top: 16px;
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

.detail-delete {
  min-width: 112px;
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
  .bankruptcy-shell {
    grid-template-columns: 1fr;
  }

  .bankruptcy-detail-head {
    flex-direction: column;
  }

  .bankruptcy-detail-actions {
    justify-content: flex-start;
  }
}
</style>
