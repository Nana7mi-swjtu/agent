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
  gap: 18px;
  min-height: 0;
}

.bankruptcy-sidebar {
  display: grid;
  gap: 16px;
  align-content: start;
}

@media (max-width: 1024px) {
  .bankruptcy-shell {
    grid-template-columns: 1fr;
  }
}
</style>
