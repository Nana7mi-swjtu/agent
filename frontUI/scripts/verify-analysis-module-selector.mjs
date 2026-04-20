import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { normalizeChatSession, serializeChatSession } from "../src/entities/chat/lib/session.js";
import {
  buildWorkspaceChatRequestBody,
  normalizeEnabledAnalysisModules,
} from "../src/entities/workspace/api/chatPayload.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) => fs.readFileSync(path.resolve(__dirname, "..", relativePath), "utf8");

assert.deepEqual(normalizeEnabledAnalysisModules(["robotics_risk", "robotics_risk", "", null]), ["robotics_risk"]);
assert.deepEqual(normalizeEnabledAnalysisModules("robotics_risk"), []);

const ordinaryBody = buildWorkspaceChatRequestBody("hello", "ws-1", "c-1");
assert.equal(Object.hasOwn(ordinaryBody, "enabledAnalysisModules"), false);

const moduleBody = buildWorkspaceChatRequestBody("分析石头科技", "ws-1", "c-1", {
  enabledAnalysisModules: ["robotics_risk"],
});
assert.deepEqual(moduleBody.enabledAnalysisModules, ["robotics_risk"]);

const legacySession = normalizeChatSession({
  id: "s_legacy",
  conversationId: "c_legacy",
  messages: [],
});
assert.deepEqual(legacySession.selectedAnalysisModules, []);

const moduleSession = normalizeChatSession({
  id: "s_module",
  conversationId: "c_module",
  selectedAnalysisModules: ["robotics_risk", "unknown"],
  messages: [],
});
assert.deepEqual(moduleSession.selectedAnalysisModules, ["robotics_risk"]);
assert.deepEqual(serializeChatSession(moduleSession).selectedAnalysisModules, ["robotics_risk"]);

const messagingSource = read("src/features/chat/model/useChatMessaging.js");
assert.match(messagingSource, /selectedAnalysisModule/);
assert.match(messagingSource, /requestOptionsForModules/);
assert.match(messagingSource, /agentChatJobsEnabled\.value && !hasSelectedAnalysisModules/);
assert.match(messagingSource, /postWorkspaceChatStream\(text, workspaceId\.value, conversationId, options\)/);
assert.match(messagingSource, /postWorkspaceChat\(text, workspaceId\.value, current\.conversationId, requestOptions\)/);

const composerSource = read("src/features/chat/ui/ChatComposer.vue");
assert.match(composerSource, /analysisModuleValue/);
assert.match(composerSource, /dc-composer-toolbar/);
assert.match(composerSource, /dc-module-select/);
assert.match(composerSource, /aria-label/);

const workspaceSource = read("src/widgets/chat-workspace/ui/ChatWorkspace.vue");
assert.match(workspaceSource, /v-model:analysis-module-value/);
assert.match(workspaceSource, /analysisModuleRoboticsRisk/);

console.log("analysis module selector frontend verification passed");
