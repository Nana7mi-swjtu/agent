import { apiRequest } from "@/services/api/client";

export const getWorkspaceContext = () => apiRequest("/api/workspace/context");

export const patchWorkspaceContext = (role) =>
  apiRequest("/api/workspace/context", {
    method: "PATCH",
    body: { role },
  });

export const postWorkspaceChat = (message) =>
  apiRequest("/api/workspace/chat", {
    method: "POST",
    body: { message },
  });
