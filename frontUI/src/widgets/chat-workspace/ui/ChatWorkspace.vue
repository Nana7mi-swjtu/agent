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
const { ready, agentTraceDebugDetailsEnabled } = storeToRefs(workspaceStore);
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
    <section class="workbench-stage">
      <header class="workbench-header">
        <div class="workbench-heading">
          <span class="workbench-kicker">{{ selectedRoleName || uiStore.t("startChat") }}</span>
          <h1>{{ channelName }}</h1>
          <p>{{ systemPrompt ? selectedRoleName : uiStore.t("roleSelectionDesc") }}</p>
        </div>
        <div class="workbench-status">
          <span class="workbench-pill">{{ selectedRoleName || "-" }}</span>
          <span class="workbench-pill">{{ ragDocuments.length }} {{ uiStore.t("ragUploadedFiles") }}</span>
        </div>
      </header>

      <ChatFeed
        :active-session="activeSession"
        :channel-name="channelName"
        :display-time="displayTime"
        :agent-trace-enabled="agentTraceEnabled"
        :rag-debug-enabled="ragDebugEnabled"
        :trace-details-visible="agentTraceDebugDetailsEnabled"
        :rag-debug-details-visible="agentTraceDebugDetailsEnabled"
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
    </section>

    <aside class="workbench-context">
      <RagWorkspacePanel
        :channel-name="channelName"
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
    </aside>
  </div>
</template>

<style scoped>
.dc-chat-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 20px;
  flex: 1;
  min-height: 0;
}

.workbench-stage,
.workbench-context {
  min-height: 0;
}

.workbench-stage {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 30px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(245, 249, 255, 0.95));
  box-shadow: var(--shadow-sm);
}

.workbench-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 24px 24px 18px;
  border-bottom: 1px solid var(--line);
  background:
    radial-gradient(circle at top right, rgba(111, 162, 255, 0.14), transparent 28%),
    linear-gradient(180deg, rgba(248, 251, 255, 0.98), rgba(243, 248, 255, 0.9));
}

.workbench-heading h1 {
  margin: 6px 0 8px;
  font-size: 32px;
  line-height: 1.05;
  text-transform: lowercase;
}

.workbench-heading p {
  margin: 0;
  color: var(--text-muted);
  font-size: 14px;
}

.workbench-kicker {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.workbench-status {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.workbench-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.84);
  color: var(--text-channel);
  font-size: 12px;
  font-weight: 700;
}

.workbench-context {
  overflow: hidden;
}

@media (max-width: 1200px) {
  .dc-chat-layout {
    grid-template-columns: 1fr;
  }

  .workbench-header {
    flex-direction: column;
  }

  .workbench-status {
    justify-content: flex-start;
  }
}
</style>
