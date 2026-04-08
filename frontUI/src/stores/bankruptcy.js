import { defineStore } from "pinia";
import { ref } from "vue";

import {
  analyzeBankruptcyRecord,
  deleteBankruptcyRecord,
  getBankruptcyRecord,
  listBankruptcyRecords,
  uploadBankruptcyRecord,
} from "@/services/bankruptcy";

export const useBankruptcyStore = defineStore("bankruptcy", () => {
  const records = ref([]);
  const selectedRecordId = ref(0);
  const selectedRecord = ref(null);
  const loadingRecords = ref(false);
  const loadingDetail = ref(false);
  const uploading = ref(false);
  const analyzing = ref(false);
  const deletingRecordId = ref(0);
  const error = ref("");
  const success = ref("");

  const clearMessages = () => {
    error.value = "";
    success.value = "";
  };

  const reset = () => {
    records.value = [];
    selectedRecordId.value = 0;
    selectedRecord.value = null;
    loadingRecords.value = false;
    loadingDetail.value = false;
    uploading.value = false;
    analyzing.value = false;
    deletingRecordId.value = 0;
    clearMessages();
  };

  const syncRecordSummary = (detail) => {
    if (!detail || typeof detail !== "object") return;
    const nextSummary = {
      id: detail.id,
      workspaceId: detail.workspaceId,
      companyName: detail.companyName,
      sourceName: detail.sourceName,
      fileName: detail.fileName,
      status: detail.status,
      probability: detail.probability,
      riskLevel: detail.riskLevel,
      createdAt: detail.createdAt,
      updatedAt: detail.updatedAt,
      analyzedAt: detail.analyzedAt,
    };
    const index = records.value.findIndex((item) => item.id === nextSummary.id);
    if (index >= 0) {
      records.value.splice(index, 1, nextSummary);
    } else {
      records.value.unshift(nextSummary);
    }
  };

  const loadRecordDetail = async (workspaceId, recordId) => {
    if (!recordId) {
      selectedRecordId.value = 0;
      selectedRecord.value = null;
      return { ok: true, empty: true };
    }
    loadingDetail.value = true;
    clearMessages();
    const result = await getBankruptcyRecord(recordId, workspaceId);
    loadingDetail.value = false;
    if (!result.ok) {
      error.value = result.data?.error || "Load failed";
      return result;
    }
    selectedRecordId.value = Number(recordId);
    selectedRecord.value = result.data?.data || null;
    syncRecordSummary(selectedRecord.value);
    return result;
  };

  const loadRecords = async (workspaceId, preferredRecordId = 0) => {
    loadingRecords.value = true;
    clearMessages();
    const result = await listBankruptcyRecords(workspaceId);
    loadingRecords.value = false;
    if (!result.ok) {
      records.value = [];
      selectedRecordId.value = 0;
      selectedRecord.value = null;
      error.value = result.data?.error || "Load failed";
      return result;
    }

    records.value = Array.isArray(result.data?.data?.records) ? result.data.data.records : [];
    const nextId =
      Number(preferredRecordId || 0) ||
      (records.value.some((item) => item.id === selectedRecordId.value) ? selectedRecordId.value : records.value[0]?.id || 0);

    if (!nextId) {
      selectedRecordId.value = 0;
      selectedRecord.value = null;
      return result;
    }
    return loadRecordDetail(workspaceId, nextId);
  };

  const saveRecord = async (workspaceId, file, enterpriseName) => {
    uploading.value = true;
    clearMessages();
    const result = await uploadBankruptcyRecord({ workspaceId, file, enterpriseName });
    uploading.value = false;
    if (!result.ok) {
      error.value = result.data?.error || "Upload failed";
      return result;
    }
    selectedRecord.value = result.data?.data || null;
    selectedRecordId.value = Number(selectedRecord.value?.id || 0);
    syncRecordSummary(selectedRecord.value);
    return result;
  };

  const runAnalysis = async (workspaceId, recordId) => {
    analyzing.value = true;
    clearMessages();
    const result = await analyzeBankruptcyRecord(recordId, workspaceId);
    analyzing.value = false;
    if (!result.ok) {
      error.value = result.data?.error || "Analysis failed";
      return result;
    }
    selectedRecord.value = result.data?.data || null;
    selectedRecordId.value = Number(selectedRecord.value?.id || recordId || 0);
    syncRecordSummary(selectedRecord.value);
    return result;
  };

  const removeRecord = async (workspaceId, recordId) => {
    deletingRecordId.value = Number(recordId || 0);
    clearMessages();
    const result = await deleteBankruptcyRecord(recordId, workspaceId);
    deletingRecordId.value = 0;
    if (!result.ok) {
      error.value = result.data?.error || "Delete failed";
      return result;
    }

    records.value = records.value.filter((item) => item.id !== Number(recordId));
    if (selectedRecordId.value === Number(recordId)) {
      const next = records.value[0] || null;
      selectedRecordId.value = Number(next?.id || 0);
      selectedRecord.value = null;
      if (next?.id) {
        return loadRecordDetail(workspaceId, next.id);
      }
    }
    return result;
  };

  return {
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
    clearMessages,
    reset,
    loadRecords,
    loadRecordDetail,
    saveRecord,
    runAnalysis,
    removeRecord,
  };
});
