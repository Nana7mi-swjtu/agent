import { useChatMessaging } from "@/features/chat/model/useChatMessaging";
import { useWorkspaceRag } from "@/features/rag/model/useWorkspaceRag";

export const useChatWorkspace = () => ({
  ...useChatMessaging(),
  ...useWorkspaceRag(),
});
