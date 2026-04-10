import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { normalizeChatMessage } from "../src/entities/chat/lib/session.js";
import {
  formatTraceDetailValue,
  getMessageRagDebug,
  getMessageTraceSteps,
  getMessageSources,
} from "../src/entities/chat/lib/message.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const legacyMessage = normalizeChatMessage({
  from: "agent",
  text: "legacy",
});
assert.equal(legacyMessage.trace, null);
assert.equal(legacyMessage.debug, null);
assert.deepEqual(legacyMessage.citations, []);
assert.deepEqual(legacyMessage.sources, []);
assert.equal(legacyMessage.noEvidence, false);

const tracedMessage = normalizeChatMessage({
  from: "agent",
  text: "answer",
  noEvidence: true,
  citations: [{ source: "doc-a", chunk_id: "chunk-1" }],
  trace: { steps: [{ id: "planner", status: "done" }] },
  debug: {
    rag: {
      retrieval: {
        rawCount: 1,
      },
    },
  },
  sources: [{ id: "rag:doc-a", kind: "rag", title: "doc-a", source: "doc-a", pages: [1] }],
});
assert.equal(getMessageTraceSteps(tracedMessage).length, 1);
assert.equal(getMessageRagDebug(tracedMessage)?.retrieval?.rawCount, 1);
assert.equal(getMessageSources(tracedMessage).length, 1);
assert.equal(formatTraceDetailValue(["a", "b"]), "a, b");
assert.match(formatTraceDetailValue({ strategy: "private_first", count: 2 }), /strategy=private_first/);

const tracePanelSource = fs.readFileSync(path.resolve(__dirname, "../src/features/chat/ui/AgentTracePanel.vue"), "utf8");
assert.match(tracePanelSource, /agent-trace-node/);
assert.match(tracePanelSource, /fitView/);
assert.match(tracePanelSource, /beginPan/);
assert.match(tracePanelSource, /border-radius:\s*999px/);
assert.doesNotMatch(tracePanelSource, /\}\}\s*steps/);
assert.match(tracePanelSource, /surface-panel-elevated/);

console.log("agent trace frontend verification passed");
