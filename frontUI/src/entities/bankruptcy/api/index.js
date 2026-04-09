import { apiRequest, buildApiUrl } from "@/shared/api/client";
import {
  normalizeBankruptcyRecord,
  normalizeBankruptcyRecordList,
  normalizeBankruptcyResult,
} from "@/entities/bankruptcy/lib/record";

const normalizePlotUrl = (value) => {
  if (typeof value !== "string" || !value.trim()) {
    return "";
  }
  return value.startsWith("/") ? buildApiUrl(value) : value;
};

const normalizeRecordResponse = (record) => {
  const normalized = normalizeBankruptcyRecord(record);
  normalized.plotUrl = normalizePlotUrl(normalized.plotUrl);
  return normalized;
};

export const predictBankruptcy = async ({ workspaceId, file, enterpriseName }) => {
  const formData = new FormData();
  formData.append("workspaceId", String(workspaceId || "default"));
  formData.append("file", file);
  if (typeof enterpriseName === "string" && enterpriseName.trim()) {
    formData.append("enterpriseName", enterpriseName.trim());
  }

  const result = await apiRequest("/api/bankruptcy/predict", {
    method: "POST",
    body: formData,
  });
  if (result.ok && result.data?.data) {
    const normalized = normalizeBankruptcyResult(result.data.data);
    normalized.plotUrl = normalizePlotUrl(normalized.plotUrl);
    result.data.data = normalized;
  }
  return result;
};

export const uploadBankruptcyRecord = async ({ workspaceId, file, enterpriseName }) => {
  const formData = new FormData();
  formData.append("workspaceId", String(workspaceId || "default"));
  formData.append("file", file);
  if (typeof enterpriseName === "string" && enterpriseName.trim()) {
    formData.append("enterpriseName", enterpriseName.trim());
  }

  const result = await apiRequest("/api/bankruptcy/records", {
    method: "POST",
    body: formData,
  });
  if (result.ok && result.data?.data) {
    result.data.data = normalizeRecordResponse(result.data.data);
  }
  return result;
};

export const listBankruptcyRecords = async (workspaceId) => {
  const result = await apiRequest(`/api/bankruptcy/records?workspaceId=${encodeURIComponent(String(workspaceId || "default"))}`);
  if (result.ok && Array.isArray(result.data?.data?.records)) {
    result.data.data.records = normalizeBankruptcyRecordList(result.data.data.records);
  }
  return result;
};

export const getBankruptcyRecord = async (recordId, workspaceId) => {
  const result = await apiRequest(
    `/api/bankruptcy/records/${Number(recordId)}?workspaceId=${encodeURIComponent(String(workspaceId || "default"))}`,
  );
  if (result.ok && result.data?.data) {
    result.data.data = normalizeRecordResponse(result.data.data);
  }
  return result;
};

export const analyzeBankruptcyRecord = async (recordId, workspaceId) => {
  const formData = new FormData();
  formData.append("workspaceId", String(workspaceId || "default"));
  const result = await apiRequest(`/api/bankruptcy/records/${Number(recordId)}/analyze`, {
    method: "POST",
    body: formData,
  });
  if (result.ok && result.data?.data) {
    result.data.data = normalizeRecordResponse(result.data.data);
  }
  return result;
};

export const deleteBankruptcyRecord = (recordId, workspaceId) =>
  apiRequest(`/api/bankruptcy/records/${Number(recordId)}?workspaceId=${encodeURIComponent(String(workspaceId || "default"))}`, {
    method: "DELETE",
  });
