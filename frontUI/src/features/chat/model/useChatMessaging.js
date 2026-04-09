import { computed, ref } from "vue";
import { storeToRefs } from "pinia";

import { useChatStore } from "@/entities/chat/model/store";
import { postWorkspaceChat } from "@/entities/workspace/api";
import { formatMessageTime } from "@/shared/lib/time";
import { useUiStore } from "@/shared/model/ui-store";
import { useWorkspaceStore } from "@/entities/workspace/model/store";

export const useChatMessaging = () => {
  const uiStore = useUiStore();
  const chatStore = useChatStore();
  const workspaceStore = useWorkspaceStore();
  const { selectedRole, systemPrompt, workspaceId } = storeToRefs(workspaceStore);
  const { sessions, activeSessionId, sending, error, activeSession } = storeToRefs(chatStore);
  const input = ref("");

  const selectedRoleName = computed(() =>
    selectedRole.value ? uiStore.getRoleDisplayName(selectedRole.value) : "",
  );

  const channelName = computed(() => {
    const title = activeSession.value?.title?.trim();
    if (title) {
      return title.toLowerCase().replace(/\s+/g, "-");
    }
    return selectedRoleName.value || "analysis-room";
  });

  const displayTime = (value) => formatMessageTime(value, uiStore.language);

  const send = async () => {
    error.value = "";
    if (!selectedRole.value) {
      error.value = uiStore.t("noRole");
      return { ok: false, noRole: true };
    }

    const text = String(input.value || "").trim();
    if (!text) {
      return { ok: false, empty: true };
    }

    const current = chatStore.ensureSession(selectedRole.value, uiStore.getRoleDisplayName, workspaceId.value);
    chatStore.setSessionScope({ workspaceId: workspaceId.value, role: selectedRole.value });
    chatStore.appendMessage({ from: "user", text, time: new Date().toISOString() });
    if (current.messages.length === 1) {
      current.title = text.slice(0, 20) || current.title;
    }
    input.value = "";
    const pendingMessageId = chatStore.appendPendingAssistantMessage(uiStore.t("assistantWorking"));

    sending.value = true;
    let result;
    try {
      result = await postWorkspaceChat(text, workspaceId.value, current.conversationId);
    } catch (requestError) {
      sending.value = false;
      chatStore.removeMessage(pendingMessageId);
      error.value = requestError instanceof Error ? requestError.message : uiStore.t("sendFailed");
      input.value = text;
      return { ok: false, error: error.value };
    }
    sending.value = false;

    if (!result.ok) {
      chatStore.removeMessage(pendingMessageId);
      error.value = result.data?.error || uiStore.t("sendFailed");
      input.value = text;
      return result;
    }

    chatStore.replaceMessage(pendingMessageId, {
      from: "agent",
      text: result.data?.data?.reply || "",
      time: new Date().toISOString(),
      citations: result.data?.data?.citations || [],
      noEvidence: Boolean(result.data?.data?.noEvidence),
      debug: result.data?.data?.debug || null,
      trace: result.data?.data?.trace || null,
    });
    workspaceStore.systemPrompt = result.data?.data?.systemPrompt || workspaceStore.systemPrompt;
    return result;
  };

  return {
    input,
    selectedRole,
    sessions,
    activeSessionId,
    selectedRoleName,
    systemPrompt,
    sending,
    workspaceId,
    chatError: error,
    activeSession,
    channelName,
    displayTime,
    send,
    setActiveSession: chatStore.setActiveSession,
    createSession: () => chatStore.createSession(selectedRole.value, uiStore.getRoleDisplayName, workspaceId.value),
  };
};
