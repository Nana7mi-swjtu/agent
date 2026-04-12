import { computed, ref } from "vue";
import { storeToRefs } from "pinia";

import { useChatStore } from "@/entities/chat/model/store";
import { postWorkspaceChat, postWorkspaceChatStream } from "@/entities/workspace/api";
import { formatMessageTime } from "@/shared/lib/time";
import { useUiStore } from "@/shared/model/ui-store";
import { useWorkspaceStore } from "@/entities/workspace/model/store";

const parseStreamEvents = async (response, onEvent) => {
  if (!response.body || !response.body.getReader) {
    throw new Error("stream body is unavailable");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let newlineIndex = buffer.indexOf("\n");
    while (newlineIndex >= 0) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);
      if (line) {
        onEvent(JSON.parse(line));
      }
      newlineIndex = buffer.indexOf("\n");
    }
    if (done) {
      const tail = buffer.trim();
      if (tail) {
        onEvent(JSON.parse(tail));
      }
      return;
    }
  }
};

export const useChatMessaging = () => {
  const uiStore = useUiStore();
  const chatStore = useChatStore();
  const workspaceStore = useWorkspaceStore();
  const { selectedRole, systemPrompt, workspaceId, chatStreamingEnabled } = storeToRefs(workspaceStore);
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

  const restoreFailedRequest = (pendingMessageId, text, message) => {
    chatStore.removeMessage(pendingMessageId);
    error.value = message;
    input.value = text;
    return { ok: false, error: message };
  };

  const finalizeAssistantMessage = (pendingMessageId, payload = {}) => {
    const trace = payload.trace && typeof payload.trace === "object" ? payload.trace : null;
    let memoryInfo = null;
    if (trace && Array.isArray(trace.steps)) {
      const composeStep = trace.steps.find(
        (step) => step && typeof step === "object" && (step.step_id || step.id) === "compose_answer",
      );
      if (composeStep && typeof composeStep.details === "object") {
        memoryInfo = {
          memoryUsed: Boolean(composeStep.details.memoryUsed),
          memoryMessageCount: Number.isInteger(composeStep.details.memoryMessageCount) ? composeStep.details.memoryMessageCount : 0,
          contextPresent: Boolean(composeStep.details.conversationContextPresent),
        };
      }
    }
    chatStore.replaceMessage(pendingMessageId, {
      from: "agent",
      text: payload.reply || "",
      time: new Date().toISOString(),
      citations: payload.citations || [],
      sources: payload.sources || [],
      noEvidence: Boolean(payload.noEvidence),
      debug: payload.debug || null,
      trace: trace,
      graph: payload.graph || null,
      graphMeta: payload.graphMeta || null,
      memoryInfo: memoryInfo,
      pending: false,
    });
    workspaceStore.systemPrompt = payload.systemPrompt || workspaceStore.systemPrompt;
  };

  const tryStreamReply = async (text, conversationId, pendingMessageId) => {
    const response = await postWorkspaceChatStream(text, workspaceId.value, conversationId);
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      return {
        ok: false,
        fallback: response.status === 404 || response.status === 405 || !response.body,
        error: errorPayload?.error || "",
      };
    }

    const finalPayload = {
      reply: "",
      citations: [],
      sources: [],
      noEvidence: false,
      debug: null,
      trace: null,
      graph: null,
      graphMeta: null,
      systemPrompt: "",
    };
    let streamError = "";

    await parseStreamEvents(response, (event) => {
      if (!event || typeof event !== "object") {
        return;
      }
      if (event.type === "delta") {
        const nextText = `${chatStore.activeSession?.messages.find((item) => item.id === pendingMessageId)?.text || ""}${String(event.text || "")}`;
        chatStore.patchMessage(pendingMessageId, {
          from: "agent",
          text: nextText,
          pending: true,
          pendingStage: uiStore.t("assistantWorking"),
        });
        return;
      }
      if (event.type === "meta") {
        finalPayload.reply = String(
          chatStore.activeSession?.messages.find((item) => item.id === pendingMessageId)?.text || "",
        );
        finalPayload.citations = Array.isArray(event.citations) ? event.citations : [];
        finalPayload.sources = Array.isArray(event.sources) ? event.sources : [];
        finalPayload.noEvidence = Boolean(event.noEvidence);
        finalPayload.debug = event.debug && typeof event.debug === "object" ? event.debug : null;
        finalPayload.trace = event.trace && typeof event.trace === "object" ? event.trace : null;
        finalPayload.graph = event.graph && typeof event.graph === "object" ? event.graph : null;
        finalPayload.graphMeta = event.graphMeta && typeof event.graphMeta === "object" ? event.graphMeta : null;
        finalPayload.systemPrompt = String(event.systemPrompt || "");
        return;
      }
      if (event.type === "error") {
        streamError = String(event.error || uiStore.t("sendFailed"));
      }
    });

    if (streamError) {
      return { ok: false, fallback: false, error: streamError };
    }

    return { ok: true, payload: finalPayload };
  };

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
    try {
      if (chatStreamingEnabled.value) {
        const streamResult = await tryStreamReply(text, current.conversationId, pendingMessageId);
        if (streamResult.ok) {
          finalizeAssistantMessage(pendingMessageId, streamResult.payload);
          return { ok: true, data: { data: streamResult.payload } };
        }
        if (!streamResult.fallback) {
          return restoreFailedRequest(pendingMessageId, text, streamResult.error || uiStore.t("sendFailed"));
        }
      }

      const result = await postWorkspaceChat(text, workspaceId.value, current.conversationId);
      if (!result.ok) {
        return restoreFailedRequest(pendingMessageId, text, result.data?.error || uiStore.t("sendFailed"));
      }
      finalizeAssistantMessage(pendingMessageId, result.data?.data || {});
      return result;
    } catch (requestError) {
      return restoreFailedRequest(
        pendingMessageId,
        text,
        requestError instanceof Error ? requestError.message : uiStore.t("sendFailed"),
      );
    } finally {
      sending.value = false;
    }
  };

  return {
    input,
    selectedRole,
    sessions,
    activeSessionId,
    selectedRoleName,
    systemPrompt,
    chatStreamingEnabled,
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
