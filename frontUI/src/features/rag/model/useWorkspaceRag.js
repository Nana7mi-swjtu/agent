import { ref, watch } from "vue";
import { storeToRefs } from "pinia";

import {
  deleteRagDocument,
  listRagDocuments,
  uploadRagDocument,
  getRagIndexJob,
  enqueueRagIndex,
  getRagDebugSnapshot,
  reindexRagDocument,
} from "@/features/rag/api";
import { useUiStore } from "@/shared/model/ui-store";
import { useWorkspaceStore } from "@/entities/workspace/model/store";

const SUPPORTED_RAG_EXTENSIONS = [".pdf", ".docx", ".md", ".txt"];

const isSupportedRagFile = (file) => {
  const name = String(file?.name || "").trim().toLowerCase();
  return SUPPORTED_RAG_EXTENSIONS.some((extension) => name.endsWith(extension));
};

export const useWorkspaceRag = () => {
  const uiStore = useUiStore();
  const workspaceStore = useWorkspaceStore();
  const { workspaceId, ragDebugEnabled, agentTraceEnabled } = storeToRefs(workspaceStore);
  const ragUploading = ref(false);
  const uploadPercent = ref(0);
  const ragStageText = ref("");
  const ragError = ref("");
  const ragDocuments = ref([]);
  const ragDebugSnapshot = ref(null);
  const chunkingStrategy = ref("paragraph");
  const chunkingAppliedText = ref("");
  const activeJobId = ref(null);
  const ragActionDocumentId = ref(null);

  const stopPollingJob = () => {
    activeJobId.value = null;
  };

  const loadRagDebugSnapshot = async () => {
    if (!ragDebugEnabled.value) {
      ragDebugSnapshot.value = null;
      return { ok: false, disabled: true };
    }
    const result = await getRagDebugSnapshot(workspaceId.value);
    if (!result.ok) {
      ragDebugSnapshot.value = null;
      return { ok: false, error: result.data?.error || uiStore.t("loadFailed") };
    }
    ragDebugSnapshot.value = result.data?.data || null;
    return { ok: true };
  };

  const loadDocuments = async () => {
    const result = await listRagDocuments(workspaceId.value);
    if (result.ok) {
      ragDocuments.value = Array.isArray(result.data?.data?.documents) ? result.data.data.documents : [];
      const first = ragDocuments.value[0];
      const applied = first?.chunkingApplied;
      if (applied?.strategy) {
        const fallback = applied?.fallbackUsed ? ` (${uiStore.t("ragChunkFallback")})` : "";
        chunkingAppliedText.value = `${uiStore.t("ragChunkAppliedPrefix")}: ${applied.strategy}${fallback}`;
      } else {
        chunkingAppliedText.value = "";
      }
      await loadRagDebugSnapshot();
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
        const applied = result.data?.data?.chunkingApplied;
        if (applied?.strategy) {
          const fallback = applied?.fallbackUsed ? ` (${uiStore.t("ragChunkFallback")})` : "";
          chunkingAppliedText.value = `${uiStore.t("ragChunkAppliedPrefix")}: ${applied.strategy}${fallback}`;
        }
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
    if (!isSupportedRagFile(file)) {
      ragStageText.value = uiStore.t("ragUploadFailed");
      ragError.value = uiStore.t("ragUnsupportedFormat");
      return { ok: false };
    }
    ragUploading.value = true;
    uploadPercent.value = 0;
    ragStageText.value = uiStore.t("ragUploadPreparing");
    const uploadResult = await uploadRagDocument({
      workspaceId: workspaceId.value,
      file,
      chunking: {
        strategy: chunkingStrategy.value,
      },
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
      const indexResult = await enqueueRagIndex(documentId, workspaceId.value, {
        strategy: chunkingStrategy.value,
      });
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

  const startDocumentIndex = async (documentId) => {
    ragError.value = "";
    ragActionDocumentId.value = Number(documentId);
    ragStageText.value = uiStore.t("ragIndexPending");

    const indexResult = await reindexRagDocument(documentId, workspaceId.value, {
      strategy: chunkingStrategy.value,
    });
    if (!indexResult.ok) {
      ragError.value = indexResult.data?.error || uiStore.t("sendFailed");
      ragStageText.value = uiStore.t("ragIndexFailed");
      await loadDocuments();
      ragActionDocumentId.value = null;
      return { ok: false };
    }

    const jobId = indexResult.data?.data?.jobId;
    if (typeof jobId === "number" && jobId > 0) {
      await pollJobUntilDone(jobId);
    } else {
      await loadDocuments();
      ragStageText.value = uiStore.t("ragIndexUnknown");
    }
    ragActionDocumentId.value = null;
    return { ok: true };
  };

  const removeDocument = async (documentId) => {
    ragError.value = "";
    ragActionDocumentId.value = Number(documentId);
    ragStageText.value = uiStore.t("ragDeleteRunning");

    const result = await deleteRagDocument(documentId, workspaceId.value);
    if (!result.ok) {
      ragError.value = result.data?.error || uiStore.t("sendFailed");
      ragStageText.value = uiStore.t("ragDeleteFailed");
      await loadDocuments();
      ragActionDocumentId.value = null;
      return { ok: false };
    }

    await loadDocuments();
    ragStageText.value = uiStore.t("ragDeleteDone");
    ragActionDocumentId.value = null;
    return { ok: true };
  };

  const onWorkspaceScopeChanged = async () => {
    stopPollingJob();
    ragUploading.value = false;
    uploadPercent.value = 0;
    ragStageText.value = "";
    ragError.value = "";
    chunkingAppliedText.value = "";
    ragDebugSnapshot.value = null;
    ragActionDocumentId.value = null;
    await loadDocuments();
  };

  watch(workspaceId, async () => {
    await onWorkspaceScopeChanged();
  });

  return {
    ragUploading,
    uploadPercent,
    ragStageText,
    ragError,
    ragDocuments,
    ragDebugEnabled,
    agentTraceEnabled,
    ragDebugSnapshot,
    chunkingStrategy,
    chunkingAppliedText,
    ragActionDocumentId,
    loadDocuments,
    uploadDocument,
    startDocumentIndex,
    removeDocument,
    loadRagDebugSnapshot,
  };
};
