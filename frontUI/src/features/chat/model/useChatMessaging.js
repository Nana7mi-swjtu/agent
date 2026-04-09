import { computed, ref } from "vue";
import { storeToRefs } from "pinia";

import { postWorkspaceChat } from "@/services/workspace";
import { useChatStore } from "@/stores/chat";
import { useUiStore } from "@/stores/ui";
import { useWorkspaceStore } from "@/stores/workspace";
import { formatMessageTime } from "@/shared/lib/time";

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

    sending.value = true;
    const result = await postWorkspaceChat(text, workspaceId.value, current.conversationId);
    sending.value = false;

    if (!result.ok) {
      error.value = result.data?.error || uiStore.t("sendFailed");
      return result;
    }

    chatStore.appendMessage({
      from: "agent",
      text: result.data?.data?.reply || "",
      time: new Date().toISOString(),
      citations: result.data?.data?.citations || [],
      noEvidence: Boolean(result.data?.data?.noEvidence),
      debug: result.data?.data?.debug || null,
      trace: result.data?.data?.trace || null,
    });
    workspaceStore.systemPrompt = result.data?.data?.systemPrompt || workspaceStore.systemPrompt;

    if (!result.empty) {
      input.value = "";
    }
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
