<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { storeToRefs } from "pinia";

import { useChatSession } from "@/composables/useChatSession";
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
  send,
} = useChatSession();

const sendMessage = async () => {
  const result = await send();
  if (result.noRole) {
    router.push("/app");
  }
};

onMounted(() => {
  if (!ready.value || !selectedRole.value) {
    router.push("/app");
  }
});
</script>

<template>
  <div class="dc-chat-layout">
    <div class="dc-toolbar">
      <span class="ch-hash">#</span>
      <span class="ch-name">{{ channelName }}</span>
      <span class="toolbar-divider"></span>
      <span class="ch-topic">{{ systemPrompt || "-" }}</span>
      <span class="badge-pill">{{ selectedRoleName || "-" }}</span>
    </div>

    <div class="dc-feed">
      <div v-if="!activeSession || !activeSession.messages.length" class="feed-welcome">
        <h2># {{ channelName }}</h2>
        <p>{{ uiStore.t("inputPlaceholder") }}</p>
      </div>

      <article
        v-for="(msg, idx) in activeSession?.messages || []"
        :key="idx"
        class="msg-row"
        :class="{ 'is-first': idx === 0 || activeSession.messages[idx - 1].from !== msg.from }"
      >
        <template v-if="idx === 0 || activeSession.messages[idx - 1].from !== msg.from">
          <div class="msg-avatar" :class="{ 'is-agent': msg.from === 'agent' }">
            {{ msg.from === "user" ? "U" : "AI" }}
          </div>
          <div class="msg-body">
            <div class="msg-meta">
              <span class="msg-author">{{ msg.from === "user" ? "You" : "Agent Studio" }}</span>
              <span class="msg-timestamp">{{ displayTime(msg.time) }}</span>
            </div>
            <div class="msg-content">{{ msg.text }}</div>
          </div>
        </template>
        <template v-else>
          <div class="msg-avatar is-empty"></div>
          <div class="msg-body">
            <div class="msg-content">{{ msg.text }}</div>
          </div>
        </template>
      </article>
    </div>

    <div class="dc-composer">
      <div class="dc-composer-inner">
        <input
          v-model="input"
          type="text"
          :placeholder="uiStore.t('inputPlaceholder')"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <button class="dc-composer-send" :disabled="sending" @click="sendMessage">➤</button>
      </div>
      <div class="msg-err" v-if="chatError">{{ chatError }}</div>
    </div>
  </div>
</template>
