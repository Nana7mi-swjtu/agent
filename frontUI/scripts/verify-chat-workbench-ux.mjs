import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { normalizeChatMessage, normalizeChatSession, serializeChatSession } from "../src/entities/chat/lib/session.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const pendingMessage = normalizeChatMessage({
  from: "agent",
  text: "",
  pending: true,
  pendingStage: "working",
});
assert.equal(pendingMessage.pending, true);
assert.equal(pendingMessage.pendingStage, "working");
assert.match(pendingMessage.id, /^m_/);

const normalizedSession = normalizeChatSession({
  id: "s_demo",
  conversationId: "c_demo",
  workspaceId: "default",
  role: "investor",
  title: "demo",
  messages: [
    { id: "m_user", from: "user", text: "hello" },
    { id: "m_pending", from: "agent", text: "", pending: true },
  ],
});
const serializedSession = serializeChatSession(normalizedSession);
assert.equal(serializedSession.messages.length, 1);
assert.equal(serializedSession.messages[0].id, "m_user");
assert.equal(serializedSession.messages[0].from, "user");

const sourcedMessage = normalizeChatMessage({
  from: "agent",
  text: "answer",
  sources: [{ id: "web:https://example.com", kind: "web", title: "Example", url: "https://example.com" }],
});
assert.equal(sourcedMessage.sources.length, 1);
assert.equal(sourcedMessage.sources[0].kind, "web");

const graphedMessage = normalizeChatMessage({
  from: "agent",
  text: "graph answer",
  graph: {
    nodes: [{ id: "node-1", label: "京东方", type: "company" }],
    edges: [],
  },
  graphMeta: {
    source: "knowledge_graph",
    contextSize: 1,
  },
});
assert.equal(graphedMessage.graph.nodes[0].label, "京东方");
assert.equal(graphedMessage.graphMeta.source, "knowledge_graph");

const graphSession = normalizeChatSession({
  id: "s_graph",
  conversationId: "c_graph",
  workspaceId: "default",
  role: "investor",
  title: "graph",
  messages: [graphedMessage],
});
assert.equal(serializeChatSession(graphSession).messages[0].graphMeta.contextSize, 1);

const markdownLibSource = fs.readFileSync(path.resolve(__dirname, "../src/shared/lib/markdown.js"), "utf8");
assert.match(markdownLibSource, /MarkdownIt/);
assert.match(markdownLibSource, /DOMPurify/);

const messageItemSource = fs.readFileSync(path.resolve(__dirname, "../src/features/chat/ui/ChatMessageItem.vue"), "utf8");
assert.match(messageItemSource, /MarkdownContent/);
assert.match(messageItemSource, /KnowledgeGraphPanel/);
assert.match(messageItemSource, /assistantWorkingHint/);
assert.match(messageItemSource, /msg-pending-card/);
assert.match(messageItemSource, /agent-sources-panel/);
assert.match(messageItemSource, /独立封面、目录和正文页面/);

const knowledgeGraphSource = fs.readFileSync(path.resolve(__dirname, "../src/features/chat/ui/KnowledgeGraphPanel.vue"), "utf8");
assert.match(knowledgeGraphSource, /kg-viewport/);
assert.match(knowledgeGraphSource, /适配视图/);
assert.match(knowledgeGraphSource, /graphMeta/);

const feedSource = fs.readFileSync(path.resolve(__dirname, "../src/features/chat/ui/ChatFeed.vue"), "utf8");
assert.match(feedSource, /jumpToLatest/);
assert.match(feedSource, /handleScroll/);
assert.match(feedSource, /analysisEmptyStateMultiTitle/);
assert.match(feedSource, /feed-module-chip/);

const tracePanelSource = fs.readFileSync(path.resolve(__dirname, "../src/features/chat/ui/AgentTracePanel.vue"), "utf8");
assert.match(tracePanelSource, /agentTraceFitView/);
assert.match(tracePanelSource, /agent-trace-viewport/);
assert.match(tracePanelSource, /beginNodeDrag/);

const messagingSource = fs.readFileSync(path.resolve(__dirname, "../src/features/chat/model/useChatMessaging.js"), "utf8");
assert.match(messagingSource, /input\.value = ""/);
assert.match(messagingSource, /appendPendingAssistantMessage/);
assert.match(messagingSource, /postWorkspaceChatStream/);
assert.match(messagingSource, /chatStore\.patchMessage/);
assert.match(messagingSource, /chatStore\.replaceMessage/);
assert.match(messagingSource, /input\.value = text/);

const workspaceSource = fs.readFileSync(path.resolve(__dirname, "../src/widgets/chat-workspace/ui/ChatWorkspace.vue"), "utf8");
assert.match(workspaceSource, /analysisComposerGuidance/);
assert.match(workspaceSource, /analysisGuidanceMultiPlaceholder/);

const composerSource = fs.readFileSync(path.resolve(__dirname, "../src/features/chat/ui/ChatComposer.vue"), "utf8");
assert.match(composerSource, /dc-composer-guidance/);
assert.match(composerSource, /analysisGuidance/);

console.log("chat workbench UX frontend verification passed");
