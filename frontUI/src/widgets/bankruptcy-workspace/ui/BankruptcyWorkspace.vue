<script setup>
import FeedbackMessage from "@/shared/ui/FeedbackMessage.vue";
import { useBankruptcyWorkspace } from "@/features/bankruptcy/model/useBankruptcyWorkspace";
import BankruptcyDetailPanel from "@/features/bankruptcy/ui/BankruptcyDetailPanel.vue";
import BankruptcyHistoryPanel from "@/features/bankruptcy/ui/BankruptcyHistoryPanel.vue";
import BankruptcyUploadPanel from "@/features/bankruptcy/ui/BankruptcyUploadPanel.vue";

const {
  uiStore,
  workspaceId,
  records,
  selectedRecordId,
  selectedRecord,
  loadingRecords,
  loadingDetail,
  uploading,
  analyzing,
  deletingRecordId,
  error,
  success,
  enterpriseName,
  fileInputKey,
  detailActionLabel,
  showAnalyzedResult,
  onFileChange,
  onUpload,
  selectRecord,
  analyzeSelected,
  deleteRecord,
  statusText,
  percentText,
  formatTime,
} = useBankruptcyWorkspace();
</script>

<template>
  <div>
    <FeedbackMessage
      :error="error"
      :success="success"
      :muted="uploading || analyzing ? uiStore.t('bankruptcyRunning') : ''"
    />

    <div class="bankruptcy-lab-banner">
      <span class="bankruptcy-lab-badge">Workflow validation</span>
      <p>Bankruptcy analysis is staged here for agent workflow verification before it moves into the main conversation workspace.</p>
    </div>

    <div class="bankruptcy-shell">
      <aside class="bankruptcy-sidebar">
        <BankruptcyUploadPanel
          :ui-store="uiStore"
          :workspace-id="workspaceId"
          :enterprise-name="enterpriseName"
          :uploading="uploading"
          :file-input-key="fileInputKey"
          @update:enterprise-name="enterpriseName = $event"
          @select-file="onFileChange"
          @submit="onUpload"
        />

        <BankruptcyHistoryPanel
          :ui-store="uiStore"
          :records="records"
          :selected-record-id="selectedRecordId"
          :loading-records="loadingRecords"
          :deleting-record-id="deletingRecordId"
          :status-text="statusText"
          :format-time="formatTime"
          @select-record="selectRecord"
          @delete-record="deleteRecord"
        />
      </aside>

      <BankruptcyDetailPanel
        :ui-store="uiStore"
        :selected-record="selectedRecord"
        :loading-detail="loadingDetail"
        :analyzing="analyzing"
        :deleting-record-id="deletingRecordId"
        :detail-action-label="detailActionLabel"
        :show-analyzed-result="showAnalyzedResult"
        :status-text="statusText"
        :format-time="formatTime"
        :percent-text="percentText"
        @analyze-selected="analyzeSelected"
        @delete-record="deleteRecord"
      />
    </div>
  </div>
</template>

<style scoped>
.bankruptcy-shell {
  display: grid;
  grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
  gap: 20px;
  min-height: 0;
}

.bankruptcy-sidebar {
  display: grid;
  gap: 16px;
  align-content: start;
}

.bankruptcy-lab-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 18px;
  padding: 14px 16px;
  border: 1px solid rgba(47, 107, 255, 0.14);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(244, 249, 255, 0.94), rgba(255, 255, 255, 0.92));
  box-shadow: var(--shadow-sm);
}

.bankruptcy-lab-banner p {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}

.bankruptcy-lab-badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

@media (max-width: 1024px) {
  .bankruptcy-shell {
    grid-template-columns: 1fr;
  }
}
</style>
