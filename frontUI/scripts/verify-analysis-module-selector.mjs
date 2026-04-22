import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  ANALYSIS_MODULE_DEFINITIONS,
  normalizeAnalysisModuleIds,
} from "../src/entities/analysis-module/model/registry.js";
import { normalizeChatSession, serializeChatSession } from "../src/entities/chat/lib/session.js";
import {
  buildWorkspaceChatRequestBody,
  normalizeEnabledAnalysisModules,
} from "../src/entities/workspace/api/chatPayload.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) => fs.readFileSync(path.resolve(__dirname, "..", relativePath), "utf8");

assert.deepEqual(
  ANALYSIS_MODULE_DEFINITIONS.map((module) => module.id),
  ["robotics_risk"],
);
assert.deepEqual(normalizeAnalysisModuleIds(["robotics_risk", "robotics_risk", "unknown", "", null]), ["robotics_risk"]);
assert.deepEqual(normalizeAnalysisModuleIds("robotics_risk"), []);
assert.deepEqual(
  normalizeEnabledAnalysisModules(["robotics_risk", "enterprise_operations", "robotics_risk", "", null]),
  ["robotics_risk", "enterprise_operations"],
);
assert.deepEqual(normalizeEnabledAnalysisModules("robotics_risk"), []);

const ordinaryBody = buildWorkspaceChatRequestBody("hello", "ws-1", "c-1");
assert.equal(Object.hasOwn(ordinaryBody, "enabledAnalysisModules"), false);

const moduleBody = buildWorkspaceChatRequestBody("分析石头科技", "ws-1", "c-1", {
  enabledAnalysisModules: ["robotics_risk", "enterprise_operations", "robotics_risk"],
});
assert.deepEqual(moduleBody.enabledAnalysisModules, ["robotics_risk", "enterprise_operations"]);

const legacySession = normalizeChatSession({
  id: "s_legacy",
  conversationId: "c_legacy",
  messages: [],
});
assert.deepEqual(legacySession.selectedAnalysisModules, []);

const moduleSession = normalizeChatSession({
  id: "s_module",
  conversationId: "c_module",
  selectedAnalysisModules: ["robotics_risk", "robotics_risk", "unknown"],
  messages: [],
});
assert.deepEqual(moduleSession.selectedAnalysisModules, ["robotics_risk"]);
assert.deepEqual(serializeChatSession(moduleSession).selectedAnalysisModules, ["robotics_risk"]);

const messagingSource = read("src/features/chat/model/useChatMessaging.js");
assert.match(messagingSource, /selectedAnalysisModules/);
assert.match(messagingSource, /requestOptionsForModules/);
assert.match(messagingSource, /normalizeSelectedAnalysisModules\(current\.selectedAnalysisModules\)/);
assert.doesNotMatch(messagingSource, /activeAnalysisModules\.value\[0\]/);
assert.match(messagingSource, /agentChatJobsEnabled\.value && !hasSelectedAnalysisModules/);
assert.match(messagingSource, /postWorkspaceChatStream\(text, workspaceId\.value, conversationId, options\)/);
assert.match(messagingSource, /postWorkspaceChat\(text, workspaceId\.value, current\.conversationId, requestOptions\)/);

const composerSource = read("src/features/chat/ui/ChatComposer.vue");
assert.match(composerSource, /analysisModuleValues/);
assert.match(composerSource, /update:analysisModuleValues/);
assert.match(composerSource, /type="checkbox"/);
assert.match(composerSource, /dc-composer-toolbar/);
assert.match(composerSource, /dc-module-select/);
assert.match(composerSource, /dc-module-trigger/);
assert.match(composerSource, /dc-module-menu/);
assert.match(composerSource, /dc-module-option/);
assert.match(composerSource, /aria-label/);
assert.match(composerSource, /aria-expanded/);
assert.match(composerSource, /isModuleMenuOpen/);
assert.match(composerSource, /closeModuleMenu/);
assert.doesNotMatch(composerSource, /<select\b/);
assert.doesNotMatch(composerSource, /analysisModuleValue:/);
assert.doesNotMatch(composerSource, /moduleSummary/);
assert.doesNotMatch(composerSource, /selectedModuleLabels/);
assert.doesNotMatch(composerSource, /noAnalysisModuleLabel/);

const workspaceSource = read("src/widgets/chat-workspace/ui/ChatWorkspace.vue");
assert.match(workspaceSource, /v-model:analysis-module-values/);
assert.match(workspaceSource, /ANALYSIS_MODULE_DEFINITIONS/);
assert.doesNotMatch(workspaceSource, /no-analysis-module-label/);

console.log("analysis module selector frontend verification passed");
