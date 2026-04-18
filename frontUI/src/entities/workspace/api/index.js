import { apiRequest, streamApiRequest } from "@/shared/api/client";

export const getWorkspaceContext = () => apiRequest("/api/workspace/context");

export const patchWorkspaceContext = (role) =>
  apiRequest("/api/workspace/context", {
    method: "PATCH",
    body: { role },
  });

export const postWorkspaceChat = (message, workspaceId, conversationId, options = {}) =>
  apiRequest("/api/workspace/chat", {
    method: "POST",
    body: {
      message,
      workspaceId: workspaceId || "default",
      conversationId: conversationId || "",
      entity: typeof options.entity === "string" ? options.entity : "",
      intent: typeof options.intent === "string" ? options.intent : "",
    },
  });

export const postWorkspaceChatStream = (message, workspaceId, conversationId, options = {}) =>
  streamApiRequest("/api/workspace/chat/stream", {
    method: "POST",
    body: {
      message,
      workspaceId: workspaceId || "default",
      conversationId: conversationId || "",
      entity: typeof options.entity === "string" ? options.entity : "",
      intent: typeof options.intent === "string" ? options.intent : "",
    },
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
