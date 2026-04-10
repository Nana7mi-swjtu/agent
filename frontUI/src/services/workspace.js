import { apiRequest } from "@/services/api/client";

export const getWorkspaceContext = () => apiRequest("/api/workspace/context");

export const patchWorkspaceContext = (role) =>
  apiRequest("/api/workspace/context", {
    method: "PATCH",
    body: { role },
  });

export const postWorkspaceChat = (message, workspaceId, conversationId) =>
  postWorkspaceChatWithContext({
    message,
    workspaceId,
    conversationId,
  });

export const postWorkspaceChatWithContext = ({
  message,
  workspaceId,
  conversationId,
  entity,
  intent,
}) =>
  apiRequest("/api/workspace/chat", {
    method: "POST",
    body: {
      message,
      workspaceId: workspaceId || "default",
      conversationId: conversationId || "",
      entity: entity || "",
      intent: intent || "",
    },
  });
