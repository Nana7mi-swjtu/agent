import { apiRequest, streamApiRequest } from "@/shared/api/client";

export const getWorkspaceContext = () => apiRequest("/api/workspace/context");

export const patchWorkspaceContext = (role) =>
  apiRequest("/api/workspace/context", {
    method: "PATCH",
    body: { role },
  });

export const postWorkspaceChat = (message, workspaceId, conversationId) =>
  apiRequest("/api/workspace/chat", {
    method: "POST",
    body: {
      message,
      workspaceId: workspaceId || "default",
      conversationId: conversationId || "",
    },
  });

export const postWorkspaceChatStream = (message, workspaceId, conversationId) =>
  streamApiRequest("/api/workspace/chat/stream", {
    method: "POST",
    body: {
      message,
      workspaceId: workspaceId || "default",
      conversationId: conversationId || "",
    },
  });
