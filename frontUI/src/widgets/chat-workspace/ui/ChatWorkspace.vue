<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { storeToRefs } from "pinia";

import { useChatWorkspace } from "@/features/chat/model/useChatWorkspace";
import ChatComposer from "@/features/chat/ui/ChatComposer.vue";
import ChatFeed from "@/features/chat/ui/ChatFeed.vue";
import RagWorkspacePanel from "@/features/rag/ui/RagWorkspacePanel.vue";
import { useWorkspaceStore } from "@/stores/workspace";
import { useUiStore } from "@/stores/ui";

const router = useRouter();
const uiStore = useUiStore();
const workspaceStore = useWorkspaceStore();
const { ready } = storeToRefs(workspaceStore);
const {
  input,
  selectedRole,
  selectedRoleName,
  systemPrompt,
  sending,
  chatError,
  activeSession,
  channelName,
  displayTime,
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
  send,
} = useChatWorkspace();

const sendMessage = async () => {
  const result = await send();
  if (result.noRole) {
    router.push("/app");
  }
};

onMounted(() => {
  if (!ready.value || !selectedRole.value) {
    router.push("/app");
    return;
  }
  loadDocuments();
});

const onChooseDocument = async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  await uploadDocument(file);
  event.target.value = "";
};

const onRunDocumentAction = async (document) => {
  await startDocumentIndex(document?.id);
};

const onDeleteDocument = async (document) => {
  await removeDocument(document?.id);
};

const traceTitleMap = {
  planner: "agentTraceStepPlanner",
  clarify: "agentTraceStepClarify",
  search_subagent: "agentTraceStepSearchSubagent",
  rag_lookup: "agentTraceStepRagLookup",
  web_lookup: "agentTraceStepWebLookup",
  merge_results: "agentTraceStepMergeResults",
  mcp_subagent: "agentTraceStepMcpSubagent",
  compose_answer: "agentTraceStepComposeAnswer",
  citations: "agentTraceStepCitations",
};

const traceTitle = (step) => {
  const key = traceTitleMap[String(step?.id || "").trim()];
  return key ? uiStore.t(key) : step?.title || step?.id || "-";
};

const traceStatus = (step) => String(step?.status || "done").replaceAll("_", " ");

const traceDetailsEntries = (step) =>
  step?.details && typeof step.details === "object" ? Object.entries(step.details) : [];
</script>

<template>
  <div class="dc-chat-layout">
    <RagWorkspacePanel
      :channel-name="channelName"
      :system-prompt="systemPrompt"
      :selected-role-name="selectedRoleName"
      :rag-uploading="ragUploading"
      :upload-percent="uploadPercent"
      :rag-stage-text="ragStageText"
      :rag-error="ragError"
      :rag-documents="ragDocuments"
      :rag-debug-enabled="ragDebugEnabled"
      :rag-debug-snapshot="ragDebugSnapshot"
      :chunking-strategy="chunkingStrategy"
      :chunking-applied-text="chunkingAppliedText"
      :rag-action-document-id="ragActionDocumentId"
      @update:chunking-strategy="chunkingStrategy = $event"
      @choose-document="onChooseDocument"
      @load-documents="loadDocuments"
      @run-document-action="onRunDocumentAction"
      @delete-document="onDeleteDocument"
      @load-rag-debug-snapshot="loadRagDebugSnapshot"
    />

    <ChatFeed
      :active-session="activeSession"
      :channel-name="channelName"
      :display-time="displayTime"
      :agent-trace-enabled="agentTraceEnabled"
      :rag-debug-enabled="ragDebugEnabled"
      :trace-title="traceTitle"
      :trace-status="traceStatus"
      :trace-details-entries="traceDetailsEntries"
      :ui-store="uiStore"
    />

    <ChatComposer
      v-model="input"
      :sending="sending"
      :error="chatError"
      :placeholder="uiStore.t('inputPlaceholder')"
      @submit="sendMessage"
    />
  </div>
</template>

<style scoped>
.dc-chat-layout {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
</style>
