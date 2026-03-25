import { computed, ref, watch } from "vue";
import { storeToRefs } from "pinia";

import { postWorkspaceChat } from "@/services/workspace";
import { listRagDocuments, uploadRagDocument, getRagIndexJob, enqueueRagIndex } from "@/services/rag";
import { useChatStore } from "@/stores/chat";
import { useUiStore } from "@/stores/ui";
import { useWorkspaceStore } from "@/stores/workspace";
import { formatMessageTime } from "@/utils/time";

export const useChatSession = () => {
  const uiStore = useUiStore();
  const chatStore = useChatStore();
  const workspaceStore = useWorkspaceStore();
  const { selectedRole, systemPrompt, workspaceId } = storeToRefs(workspaceStore);
  const { sessions, activeSessionId, sending, error, activeSession } = storeToRefs(chatStore);
  const input = ref("");
  const ragUploading = ref(false);
  const uploadPercent = ref(0);
  const ragStageText = ref("");
  const ragError = ref("");
  const ragDocuments = ref([]);
  const activeJobId = ref(null);

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

  const stopPollingJob = () => {
    activeJobId.value = null;
  };

  const loadDocuments = async () => {
    const result = await listRagDocuments(workspaceId.value);
    if (result.ok) {
      ragDocuments.value = Array.isArray(result.data?.data?.documents) ? result.data.data.documents : [];
      return { ok: true };
    }
    return { ok: false, error: result.data?.error || uiStore.t("loadFailed") };
  };

  const pollJobUntilDone = async (jobId) => {
    activeJobId.value = Number(jobId);
    let attempts = 0;
    while (activeJobId.value === Number(jobId) && attempts < 120) {
      attempts += 1;
      const result = await getRagIndexJob(jobId, workspaceId.value);
      if (!result.ok) {
        ragStageText.value = uiStore.t("ragIndexUnknown");
        ragError.value = result.data?.error || uiStore.t("loadFailed");
        return { ok: false };
      }
      const status = String(result.data?.data?.status || "");
      if (status === "pending") {
        ragStageText.value = uiStore.t("ragIndexPending");
      } else if (status === "running") {
        ragStageText.value = uiStore.t("ragIndexRunning");
      } else if (status === "done") {
        ragStageText.value = uiStore.t("ragIndexDone");
        await loadDocuments();
        return { ok: true };
      } else if (status === "failed") {
        ragStageText.value = uiStore.t("ragIndexFailed");
        ragError.value = result.data?.data?.errorMessage || uiStore.t("sendFailed");
        await loadDocuments();
        return { ok: false };
      }
      await new Promise((resolve) => {
        setTimeout(resolve, 1000);
      });
    }
    ragStageText.value = uiStore.t("ragIndexUnknown");
    return { ok: false };
  };

  const uploadDocument = async (file) => {
    ragError.value = "";
    ragUploading.value = true;
    uploadPercent.value = 0;
    ragStageText.value = uiStore.t("ragUploadPreparing");
    const uploadResult = await uploadRagDocument({
      workspaceId: workspaceId.value,
      file,
      onUploadProgress: (percent) => {
        uploadPercent.value = percent;
        ragStageText.value = `${uiStore.t("ragUploadProgress")} ${percent}%`;
      },
    });

    if (!uploadResult.ok) {
      ragUploading.value = false;
      ragError.value = uploadResult.data?.error || uiStore.t("sendFailed");
      ragStageText.value = uiStore.t("ragUploadFailed");
      return { ok: false };
    }

    uploadPercent.value = 100;
    const documentId = uploadResult.data?.data?.id;
    if (typeof documentId !== "number" || documentId <= 0) {
      ragUploading.value = false;
      ragStageText.value = uiStore.t("ragIndexUnknown");
      await loadDocuments();
      return { ok: true };
    }

    ragStageText.value = uiStore.t("ragIndexPending");
    let jobId = uploadResult.data?.data?.jobId;
    if (!(typeof jobId === "number" && jobId > 0)) {
      const indexResult = await enqueueRagIndex(documentId, workspaceId.value);
      if (indexResult.ok && typeof indexResult.data?.data?.jobId === "number") {
        jobId = indexResult.data.data.jobId;
      }
    }

    if (typeof jobId === "number" && jobId > 0) {
      await pollJobUntilDone(jobId);
      ragUploading.value = false;
      return { ok: true };
    }

    await loadDocuments();
    ragUploading.value = false;
    ragStageText.value = uiStore.t("ragUploadDone");
    return { ok: true };
  };

  const onWorkspaceScopeChanged = async () => {
    stopPollingJob();
    ragUploading.value = false;
    uploadPercent.value = 0;
    ragStageText.value = "";
    ragError.value = "";
    await loadDocuments();
  };

  watch(workspaceId, async () => {
    await onWorkspaceScopeChanged();
  });

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
    ragUploading,
    uploadPercent,
    ragStageText,
    ragError,
    ragDocuments,
    loadDocuments,
    uploadDocument,
    send,
    setActiveSession: chatStore.setActiveSession,
    createSession: () => chatStore.createSession(selectedRole.value, uiStore.getRoleDisplayName, workspaceId.value),
  };
};
