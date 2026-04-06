import { getCsrfToken } from "@/services/api/csrf";
import { apiRequest, buildApiUrl, notifyUnauthorized } from "@/services/api/client";

const RAG_JSON_ERROR = "rag request failed";

const toErrorResult = (status, error) => ({
  ok: false,
  status,
  data: { ok: false, error: error || RAG_JSON_ERROR },
});

export const uploadRagDocument = ({ workspaceId, file, chunking, onUploadProgress }) =>
  new Promise((resolve) => {
    const formData = new FormData();
    formData.append("workspaceId", String(workspaceId || "default"));
    formData.append("file", file);
    if (chunking && typeof chunking === "object") {
      formData.append("chunking", JSON.stringify(chunking));
      if (typeof chunking.strategy === "string" && chunking.strategy.trim()) {
        formData.append("chunkingStrategy", String(chunking.strategy).trim());
      }
    }

    const xhr = new XMLHttpRequest();
    xhr.open("POST", buildApiUrl("/api/rag/upload"), true);
    xhr.withCredentials = true;

    const csrfToken = getCsrfToken();
    if (csrfToken) {
      xhr.setRequestHeader("X-CSRF-Token", csrfToken);
    }

    if (typeof onUploadProgress === "function") {
      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) return;
        const percent = Math.max(0, Math.min(100, Math.round((event.loaded / event.total) * 100)));
        onUploadProgress(percent, event.loaded, event.total);
      };
    }

    xhr.onerror = () => resolve(toErrorResult(0, "network error"));
    xhr.onabort = () => resolve(toErrorResult(0, "upload aborted"));
    xhr.onload = () => {
      const status = Number(xhr.status) || 0;
      notifyUnauthorized(status);
      let data = {};
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : {};
      } catch {
        data = {};
      }
      resolve({
        ok: status >= 200 && status < 300,
        status,
        data,
      });
    };

    xhr.send(formData);
  });

export const listRagDocuments = (workspaceId) =>
  apiRequest(`/api/rag/documents?workspaceId=${encodeURIComponent(String(workspaceId || "default"))}`);

export const getRagIndexJob = (jobId, workspaceId) =>
  apiRequest(`/api/rag/jobs/${Number(jobId)}?workspaceId=${encodeURIComponent(String(workspaceId || "default"))}`);

export const enqueueRagIndex = (documentId, workspaceId, chunking) =>
  apiRequest("/api/rag/index", {
    method: "POST",
    body: {
      documentId: Number(documentId),
      workspaceId: String(workspaceId || "default"),
      ...(chunking && typeof chunking === "object" ? { chunking } : {}),
    },
  });

export const reindexRagDocument = (documentId, workspaceId, chunking) =>
  apiRequest(`/api/rag/documents/${Number(documentId)}/reindex`, {
    method: "POST",
    body: {
      workspaceId: String(workspaceId || "default"),
      ...(chunking && typeof chunking === "object" ? { chunking } : {}),
    },
  });

export const deleteRagDocument = (documentId, workspaceId) =>
  apiRequest(`/api/rag/documents/${Number(documentId)}?workspaceId=${encodeURIComponent(String(workspaceId || "default"))}`, {
    method: "DELETE",
  });

export const getRagDebugSnapshot = (workspaceId) =>
  apiRequest(`/api/rag/debug?workspaceId=${encodeURIComponent(String(workspaceId || "default"))}`);
