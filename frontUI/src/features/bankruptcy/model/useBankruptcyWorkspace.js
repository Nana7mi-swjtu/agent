import { computed, ref, watch } from "vue";
import { storeToRefs } from "pinia";

import { useBankruptcyStore } from "@/stores/bankruptcy";
import { useUiStore } from "@/stores/ui";
import { useWorkspaceStore } from "@/stores/workspace";

export const useBankruptcyWorkspace = () => {
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
  const fileInputKey = ref(0);
  const success = ref("");

  const resetForm = () => {
    selectedFile.value = null;
    enterpriseName.value = "";
    fileInputKey.value += 1;
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

  return {
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
  };
};
