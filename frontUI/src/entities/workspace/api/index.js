import { apiRequest, buildApiUrl, streamApiRequest } from "@/shared/api/client";
import { buildWorkspaceChatRequestBody } from "@/entities/workspace/api/chatPayload";

export { buildWorkspaceChatRequestBody, normalizeEnabledAnalysisModules } from "@/entities/workspace/api/chatPayload";

export const getWorkspaceContext = () => apiRequest("/api/workspace/context");

export const patchWorkspaceContext = (role) =>
  apiRequest("/api/workspace/context", {
    method: "PATCH",
    body: { role },
  });

export const postWorkspaceChat = (message, workspaceId, conversationId, options = {}) =>
  apiRequest("/api/workspace/chat", {
    method: "POST",
    body: buildWorkspaceChatRequestBody(message, workspaceId, conversationId, options),
  });

export const postWorkspaceChatStream = (message, workspaceId, conversationId, options = {}) =>
  streamApiRequest("/api/workspace/chat/stream", {
    method: "POST",
    body: buildWorkspaceChatRequestBody(message, workspaceId, conversationId, options),
  });

export const postWorkspaceChatJob = (message, workspaceId, conversationId, options = {}) =>
  apiRequest("/api/workspace/chat/jobs", {
    method: "POST",
    body: {
      message,
      workspaceId: workspaceId || "default",
      conversationId: conversationId || "",
      entity: typeof options.entity === "string" ? options.entity : "",
      intent: typeof options.intent === "string" ? options.intent : "",
    },
  });

export const getWorkspaceChatJob = (jobId, workspaceId) =>
  apiRequest(`/api/workspace/chat/jobs/${encodeURIComponent(jobId)}?workspaceId=${encodeURIComponent(workspaceId || "default")}`);

export const listWorkspaceChatJobs = (workspaceId, conversationId) =>
  apiRequest(
    `/api/workspace/chat/jobs?workspaceId=${encodeURIComponent(workspaceId || "default")}&conversationId=${encodeURIComponent(conversationId || "")}`,
  );

export const getAnalysisReport = (reportId, workspaceId) =>
  apiRequest(`/api/workspace/reports/${encodeURIComponent(reportId)}?workspaceId=${encodeURIComponent(workspaceId || "default")}`);

export const buildAnalysisReportDownloadUrl = (reportId, format = "pdf", workspaceId = "default") =>
  buildApiUrl(
    `/api/workspace/reports/${encodeURIComponent(reportId)}/download?format=${encodeURIComponent(format)}&workspaceId=${encodeURIComponent(workspaceId || "default")}`,
  );

export const buildAnalysisReportAssetDownloadUrl = (reportId, assetId, workspaceId = "default") =>
  buildApiUrl(
    `/api/workspace/reports/${encodeURIComponent(reportId)}/assets/${encodeURIComponent(assetId)}/download?workspaceId=${encodeURIComponent(workspaceId || "default")}`,
  );
