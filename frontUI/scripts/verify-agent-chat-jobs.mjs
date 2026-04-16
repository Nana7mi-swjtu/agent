import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = (path) => readFileSync(resolve(root, path), "utf8");
const assertIncludes = (content, needle, label) => {
  if (!content.includes(needle)) {
    throw new Error(`${label} missing: ${needle}`);
  }
};

const workspaceApi = read("src/entities/workspace/api/index.js");
assertIncludes(workspaceApi, "postWorkspaceChatJob", "workspace API");
assertIncludes(workspaceApi, '"/api/workspace/chat/jobs"', "workspace API");
assertIncludes(workspaceApi, "getWorkspaceChatJob", "workspace API");
assertIncludes(workspaceApi, "listWorkspaceChatJobs", "workspace API");

const workspaceStore = read("src/entities/workspace/model/store.js");
assertIncludes(workspaceStore, "agentChatJobsEnabled", "workspace store");
assertIncludes(workspaceStore, "data.agentChatJobsEnabled", "workspace context application");

const sessionLib = read("src/entities/chat/lib/session.js");
assertIncludes(sessionLib, "jobId", "chat message normalization");
assertIncludes(sessionLib, "jobStatus", "chat message normalization");
assertIncludes(sessionLib, "submittedText", "chat message normalization");
assertIncludes(sessionLib, "!message?.pending || message?.jobId", "job placeholder persistence");

const chatStore = read("src/entities/chat/model/store.js");
assertIncludes(chatStore, "replaceMessageInSession", "chat store");
assertIncludes(chatStore, "patchMessageInSession", "chat store");
assertIncludes(chatStore, "appendMessageToSession", "chat store");

const messaging = read("src/features/chat/model/useChatMessaging.js");
assertIncludes(messaging, "postWorkspaceChatJob", "chat messaging");
assertIncludes(messaging, "pollJobUntilTerminal", "chat messaging");
assertIncludes(messaging, "hydrateConversationJobs", "chat messaging");
assertIncludes(messaging, "conversationHasActiveJob", "chat messaging");
assertIncludes(messaging, "finalizeAssistantMessage", "chat messaging");
assertIncludes(messaging, "markAssistantJobFailed", "chat messaging");

console.log("Agent chat job frontend contract verified.");
