import assert from "node:assert/strict";

import { normalizeChatMessage } from "../src/utils/chatSessionState.js";
import { formatTraceDetailValue, getMessageRagDebug, getMessageTraceSteps } from "../src/utils/chatMessage.js";

const legacyMessage = normalizeChatMessage({
  from: "agent",
  text: "legacy",
});
assert.equal(legacyMessage.trace, null);
assert.equal(legacyMessage.debug, null);
assert.deepEqual(legacyMessage.citations, []);
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
});
assert.equal(getMessageTraceSteps(tracedMessage).length, 1);
assert.equal(getMessageRagDebug(tracedMessage)?.retrieval?.rawCount, 1);
assert.equal(formatTraceDetailValue(["a", "b"]), "a, b");
assert.match(formatTraceDetailValue({ strategy: "private_first", count: 2 }), /strategy=private_first/);

console.log("agent trace frontend verification passed");
