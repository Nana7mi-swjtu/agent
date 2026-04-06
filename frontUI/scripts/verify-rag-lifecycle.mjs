import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { canDeleteRagDocument, getRagDocumentActionType } from "../src/utils/rag.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const servicesPath = path.resolve(__dirname, "../src/services/rag.js");
const composablePath = path.resolve(__dirname, "../src/composables/useChatSession.js");
const viewPath = path.resolve(__dirname, "../src/views/app/AppChatView.vue");

assert.equal(getRagDocumentActionType({ status: "uploaded" }), "start");
assert.equal(getRagDocumentActionType({ status: "failed" }), "retry");
assert.equal(getRagDocumentActionType({ status: "indexed" }), "reindex");
assert.equal(getRagDocumentActionType({ status: "indexing" }), "");

assert.equal(canDeleteRagDocument({ status: "uploaded" }), true);
assert.equal(canDeleteRagDocument({ status: "failed" }), true);
assert.equal(canDeleteRagDocument({ status: "indexed" }), true);
assert.equal(canDeleteRagDocument({ status: "indexing" }), false);

const servicesSource = fs.readFileSync(servicesPath, "utf-8");
assert.match(servicesSource, /export const reindexRagDocument =/);
assert.match(servicesSource, /export const deleteRagDocument =/);

const composableSource = fs.readFileSync(composablePath, "utf-8");
assert.match(composableSource, /const startDocumentIndex = async/);
assert.match(composableSource, /const removeDocument = async/);
assert.match(composableSource, /ragActionDocumentId/);

const viewSource = fs.readFileSync(viewPath, "utf-8");
assert.match(viewSource, /ragDocumentStartIndexing/);
assert.match(viewSource, /ragDocumentRetry/);
assert.match(viewSource, /ragDocumentReindex/);
assert.match(viewSource, /ragDocumentDelete/);
assert.match(viewSource, /canDeleteRagDocument\(doc\)/);

console.log("rag lifecycle frontend verification passed");
