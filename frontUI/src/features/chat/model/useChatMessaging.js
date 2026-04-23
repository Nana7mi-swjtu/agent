import { computed, onMounted, ref, watch } from "vue";
import { storeToRefs } from "pinia";

import { useChatStore } from "@/entities/chat/model/store";
import { normalizeSelectedAnalysisModules } from "@/entities/chat/lib/session";
import {
  getWorkspaceChatJob,
  listWorkspaceChatJobs,
  postAnalysisReportGeneration,
  postAnalysisReportRegeneration,
  postWorkspaceChat,
  postWorkspaceChatJob,
  postWorkspaceChatStream,
} from "@/entities/workspace/api";
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

const activeJobPolls = new Map();
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const isActiveJobStatus = (status) => ["pending", "running"].includes(String(status || "").toLowerCase());

export const useChatMessaging = () => {
  const uiStore = useUiStore();
  const chatStore = useChatStore();
  const workspaceStore = useWorkspaceStore();
  const { selectedRole, systemPrompt, workspaceId, chatStreamingEnabled, agentChatJobsEnabled } = storeToRefs(workspaceStore);
  const { sessions, activeSessionId, sending, error, activeSession } = storeToRefs(chatStore);
  const input = ref("");

  const selectedRoleName = computed(() =>
    selectedRole.value ? uiStore.getRoleDisplayName(selectedRole.value) : "",
  );

  const activeAnalysisModules = computed(() =>
    normalizeSelectedAnalysisModules(activeSession.value?.selectedAnalysisModules),
  );

  const selectedAnalysisModules = computed({
    get: () => activeAnalysisModules.value,
    set: (moduleIds) => {
      if (!activeSession.value && selectedRole.value) {
        chatStore.createSession(selectedRole.value, uiStore.getRoleDisplayName, workspaceId.value);
      }
      chatStore.setActiveSessionAnalysisModules(normalizeSelectedAnalysisModules(moduleIds));
    },
  });

  const channelName = computed(() => {
    const title = activeSession.value?.title?.trim();
    if (title) {
      return title.toLowerCase().replace(/\s+/g, "-");
    }
    return selectedRoleName.value || "analysis-room";
  });

  const displayTime = (value) => formatMessageTime(value, uiStore.language);

  const appendAgentMessage = (message, sessionId = "") => {
    if (sessionId) {
      return chatStore.appendMessageToSession(sessionId, message);
    }
    return chatStore.appendMessage(message);
  };

  const applyAssistantMessage = (pendingMessageId, message, sessionId = "") => {
    const replaced = sessionId
      ? chatStore.replaceMessageInSession(sessionId, pendingMessageId, message)
      : chatStore.replaceMessage(pendingMessageId, message);
    if (!replaced) {
      appendAgentMessage(message, sessionId);
    }
    return replaced;
  };

  const restoreFailedRequest = (pendingMessageId, text, message, sessionId = "") => {
    if (pendingMessageId) {
      if (sessionId) {
        chatStore.removeMessageFromSession(sessionId, pendingMessageId);
      } else {
        chatStore.removeMessage(pendingMessageId);
      }
    }
    error.value = message;
    input.value = text;
    return { ok: false, error: message };
  };

  const finalizeAssistantMessage = (pendingMessageId, payload = {}, sessionId = "", jobId = "") => {
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
    const baseMessage = {
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
      analysisReport: payload.analysisReport || null,
      memoryInfo: memoryInfo,
      jobId: jobId ? String(jobId) : "",
      jobStatus: "succeeded",
      pending: false,
    };
    const moduleArtifacts = Array.isArray(payload.analysisModuleArtifacts)
      ? payload.analysisModuleArtifacts.filter((item) => item && typeof item === "object")
      : [];
    if (moduleArtifacts.length) {
      moduleArtifacts.forEach((artifact, index) => {
        const artifactMessage = {
          ...baseMessage,
          text: String(artifact.markdownBody || ""),
          analysisModuleArtifact: artifact,
          analysisReport: null,
          reportGenerationRequest: null,
        };
        if (index === 0) {
          applyAssistantMessage(pendingMessageId, artifactMessage, sessionId);
        } else {
          appendAgentMessage(artifactMessage, sessionId);
        }
      });
      if (payload.analysisReportRequest && typeof payload.analysisReportRequest === "object") {
        appendAgentMessage(
          {
            ...baseMessage,
            text: "全部分析模块已完成。请选择渲染风格后生成综合报告。",
            analysisModuleArtifact: null,
            analysisReport: null,
            reportGenerationRequest: payload.analysisReportRequest,
          },
          sessionId,
        );
      }
    } else {
      applyAssistantMessage(pendingMessageId, baseMessage, sessionId);
    }
    workspaceStore.systemPrompt = payload.systemPrompt || workspaceStore.systemPrompt;
  };

  const markAssistantJobFailed = (pendingMessageId, message, sessionId = "", jobId = "", submittedText = "") => {
    const errorText = String(message || uiStore.t("sendFailed"));
    const patch = {
      from: "agent",
      text: errorText,
      time: new Date().toISOString(),
      pending: false,
      pendingStage: "",
      jobId: jobId ? String(jobId) : "",
      jobStatus: "failed",
      submittedText,
      error: errorText,
    };
    const patched = sessionId
      ? chatStore.patchMessageInSession(sessionId, pendingMessageId, patch)
      : chatStore.patchMessage(pendingMessageId, patch);
    if (!patched && sessionId) {
      chatStore.appendMessageToSession(sessionId, patch);
    }
    error.value = errorText;
  };

  const findJobMessage = (session, jobId) =>
    session?.messages?.find((message) => String(message?.jobId || "") === String(jobId || ""));

  const conversationHasActiveJob = (session) =>
    Boolean(session?.messages?.some((message) => message?.from === "agent" && message?.jobId && message?.pending));

  const applyJobSnapshot = (job, sessionId, fallbackMessageId = "") => {
    if (!job || typeof job !== "object") return;
    const session = chatStore.findSession(sessionId);
    if (!session) return;
    const jobId = String(job.jobId || "");
    if (!jobId) return;
    const existing = findJobMessage(session, jobId);
    const messageId = existing?.id || fallbackMessageId;
    if (isActiveJobStatus(job.status)) {
      if (!existing) {
        chatStore.appendMessageToSession(sessionId, {
          from: "agent",
          text: "",
          time: job.createdAt || new Date().toISOString(),
          pending: true,
          pendingStage: uiStore.t("assistantWorking"),
          jobId,
          jobStatus: job.status,
          submittedText: job.message || "",
        });
      } else {
        chatStore.patchMessageInSession(sessionId, existing.id, {
          pending: true,
          pendingStage: uiStore.t("assistantWorking"),
          jobStatus: job.status,
        });
      }
      return;
    }
    if (job.status === "succeeded" && job.result && typeof job.result === "object") {
      finalizeAssistantMessage(messageId || `job_${jobId}`, job.result, sessionId, jobId);
      return;
    }
    if (job.status === "failed") {
      markAssistantJobFailed(messageId || `job_${jobId}`, job.error || uiStore.t("sendFailed"), sessionId, jobId, job.message || "");
    }
  };

  const pollJobUntilTerminal = async (jobId, sessionId, messageId) => {
    const key = `${sessionId}:${jobId}`;
    if (activeJobPolls.has(key)) return;
    activeJobPolls.set(key, true);
    try {
      for (let attempt = 0; attempt < 180; attempt += 1) {
        const response = await getWorkspaceChatJob(jobId, workspaceId.value);
        if (!response.ok) {
          markAssistantJobFailed(messageId, response.data?.error || uiStore.t("sendFailed"), sessionId, jobId);
          return;
        }
        const job = response.data?.data;
        applyJobSnapshot(job, sessionId, messageId);
        if (!isActiveJobStatus(job?.status)) {
          return;
        }
        await sleep(2000);
      }
      markAssistantJobFailed(messageId, uiStore.t("sendFailed"), sessionId, jobId);
    } catch (pollError) {
      markAssistantJobFailed(
        messageId,
        pollError instanceof Error ? pollError.message : uiStore.t("sendFailed"),
        sessionId,
        jobId,
      );
    } finally {
      activeJobPolls.delete(key);
    }
  };

  const hydrateConversationJobs = async () => {
    const session = activeSession.value;
    if (!session?.conversationId || !agentChatJobsEnabled.value) return;
    const response = await listWorkspaceChatJobs(workspaceId.value, session.conversationId).catch(() => null);
    if (!response?.ok) return;
    const jobs = Array.isArray(response.data?.data?.jobs) ? response.data.data.jobs : [];
    jobs.reverse().forEach((job) => {
      applyJobSnapshot(job, session.id);
      if (isActiveJobStatus(job?.status)) {
        const message = findJobMessage(session, job.jobId);
        if (message) {
          void pollJobUntilTerminal(job.jobId, session.id, message.id);
        }
      }
    });
  };

  const requestOptionsForModules = (moduleIds = []) => {
    const enabledAnalysisModules = normalizeSelectedAnalysisModules(moduleIds);
    return enabledAnalysisModules.length ? { enabledAnalysisModules } : {};
  };

  const tryStreamReply = async (text, conversationId, pendingMessageId, options = {}) => {
    const response = await postWorkspaceChatStream(text, workspaceId.value, conversationId, options);
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
      analysisModuleArtifacts: [],
      analysisReportRequest: null,
      analysisReport: null,
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
        finalPayload.analysisModuleArtifacts = Array.isArray(event.analysisModuleArtifacts) ? event.analysisModuleArtifacts : [];
        finalPayload.analysisReportRequest = event.analysisReportRequest && typeof event.analysisReportRequest === "object" ? event.analysisReportRequest : null;
        finalPayload.analysisReport = event.analysisReport && typeof event.analysisReport === "object" ? event.analysisReport : null;
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
    const selectedModules = normalizeSelectedAnalysisModules(current.selectedAnalysisModules);
    const hasSelectedAnalysisModules = selectedModules.length > 0;
    const requestOptions = requestOptionsForModules(selectedModules);
    if (agentChatJobsEnabled.value && conversationHasActiveJob(current)) {
      error.value = uiStore.t("assistantWorking");
      return { ok: false, activeJob: true };
    }
    chatStore.appendMessage({ from: "user", text, time: new Date().toISOString() });
    if (current.messages.length === 1) {
      current.title = text.slice(0, 20) || current.title;
    }
    input.value = "";
    const pendingMessageId = chatStore.appendPendingAssistantMessage(uiStore.t("assistantWorking"));

    sending.value = true;
    try {
      if (agentChatJobsEnabled.value && !hasSelectedAnalysisModules) {
        const jobResult = await postWorkspaceChatJob(text, workspaceId.value, current.conversationId);
        if (!jobResult.ok) {
          return restoreFailedRequest(pendingMessageId, text, jobResult.data?.error || uiStore.t("sendFailed"), current.id);
        }
        const job = jobResult.data?.data || {};
        chatStore.patchMessageInSession(current.id, pendingMessageId, {
          jobId: String(job.jobId || ""),
          jobStatus: String(job.status || "pending"),
          submittedText: text,
          pending: true,
          pendingStage: uiStore.t("assistantWorking"),
        });
        void pollJobUntilTerminal(job.jobId, current.id, pendingMessageId);
        return jobResult;
      }

      if (chatStreamingEnabled.value) {
        const streamResult = await tryStreamReply(text, current.conversationId, pendingMessageId, requestOptions);
        if (streamResult.ok) {
          finalizeAssistantMessage(pendingMessageId, streamResult.payload);
          return { ok: true, data: { data: streamResult.payload } };
        }
        if (!streamResult.fallback) {
          return restoreFailedRequest(pendingMessageId, text, streamResult.error || uiStore.t("sendFailed"));
        }
      }

      const result = await postWorkspaceChat(text, workspaceId.value, current.conversationId, requestOptions);
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

  const appendReportMessage = (analysisReport, text = "综合报告已生成。") => {
    appendAgentMessage({
      from: "agent",
      text,
      time: new Date().toISOString(),
      analysisReport,
      pending: false,
    });
  };

  const generateReport = async (requestPayload, renderStyle = "professional") => {
    const moduleArtifactIds = Array.isArray(requestPayload?.moduleArtifactIds)
      ? requestPayload.moduleArtifactIds
      : [];
    if (!moduleArtifactIds.length) {
      error.value = uiStore.t("sendFailed");
      return { ok: false, error: error.value };
    }
    const session = activeSession.value;
    sending.value = true;
    error.value = "";
    try {
      const result = await postAnalysisReportGeneration({
        moduleArtifactIds,
        renderStyle,
        workspaceId: workspaceId.value,
        conversationId: session?.conversationId || "",
      });
      if (!result.ok) {
        error.value = result.data?.error || uiStore.t("sendFailed");
        return { ok: false, error: error.value };
      }
      const analysisReport = result.data?.data?.analysisReport || result.data?.analysisReport || null;
      if (analysisReport) {
        appendReportMessage(analysisReport);
      }
      return result;
    } catch (requestError) {
      error.value = requestError instanceof Error ? requestError.message : uiStore.t("sendFailed");
      return { ok: false, error: error.value };
    } finally {
      sending.value = false;
    }
  };

  const regenerateReport = async (report, renderStyle = "professional") => {
    const reportId = String(report?.reportId || "").trim();
    if (!reportId) {
      error.value = uiStore.t("sendFailed");
      return { ok: false, error: error.value };
    }
    const session = activeSession.value;
    sending.value = true;
    error.value = "";
    try {
      const result = await postAnalysisReportRegeneration(reportId, {
        renderStyle,
        workspaceId: workspaceId.value,
        conversationId: session?.conversationId || "",
      });
      if (!result.ok) {
        error.value = result.data?.error || uiStore.t("sendFailed");
        return { ok: false, error: error.value };
      }
      const analysisReport = result.data?.data?.analysisReport || result.data?.analysisReport || null;
      if (analysisReport) {
        appendReportMessage(analysisReport, "综合报告已重新生成。");
      }
      return result;
    } catch (requestError) {
      error.value = requestError instanceof Error ? requestError.message : uiStore.t("sendFailed");
      return { ok: false, error: error.value };
    } finally {
      sending.value = false;
    }
  };

  onMounted(() => {
    void hydrateConversationJobs();
  });

  watch([activeSessionId, workspaceId], () => {
    void hydrateConversationJobs();
  });

  return {
    input,
    selectedRole,
    sessions,
    activeSessionId,
    activeAnalysisModules,
    selectedAnalysisModules,
    selectedRoleName,
    systemPrompt,
    chatStreamingEnabled,
    agentChatJobsEnabled,
    sending,
    workspaceId,
    chatError: error,
    activeSession,
    channelName,
    displayTime,
    send,
    generateReport,
    regenerateReport,
    hydrateConversationJobs,
    clearActiveAnalysisModules: chatStore.clearActiveSessionAnalysisModules,
    setActiveSession: chatStore.setActiveSession,
    createSession: () => chatStore.createSession(selectedRole.value, uiStore.getRoleDisplayName, workspaceId.value),
  };
};
