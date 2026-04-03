import assert from "node:assert/strict";

import {
  normalizeBankruptcyRecord,
  normalizeBankruptcyRecordList,
  normalizeBankruptcyResult,
  normalizeTopFeatures,
} from "../src/utils/bankruptcy.js";

const features = normalizeTopFeatures([
  { name: "Debt ratio %", shapValue: 0.5, direction: "increase_risk" },
  { name: "Cash Flow to Liability", shapValue: -0.2, direction: "decrease_risk" },
]);
assert.equal(features.length, 2);
assert.equal(features[0].absoluteValue, 0.5);
assert.equal(features[1].direction, "decrease_risk");

const result = normalizeBankruptcyResult({
  id: 12,
  workspaceId: "ws-risk",
  companyName: "Example Corp",
  sourceName: "example.csv",
  fileName: "example.csv",
  status: "analyzed",
  probability: 0.72,
  threshold: 0.63,
  riskLevel: "high",
  plotUrl: "/api/bankruptcy/records/12/plot?workspaceId=ws-risk",
  topFeatures: features,
  inputSummary: { rowCount: 1, featureCount: 95 },
});
assert.equal(result.id, 12);
assert.equal(result.companyName, "Example Corp");
assert.equal(result.riskLevel, "high");
assert.equal(result.topFeatures.length, 2);
assert.equal(result.inputSummary.featureCount, 95);

const list = normalizeBankruptcyRecordList([
  { id: 12, workspaceId: "ws-risk", companyName: "Example Corp", status: "uploaded" },
  { id: 13, workspaceId: "ws-risk", companyName: "Beta Corp", status: "failed" },
]);
assert.equal(list.length, 2);
assert.equal(list[1].status, "failed");

const uploaded = normalizeBankruptcyRecord({
  id: 99,
  workspaceId: "ws-risk",
  companyName: "Queued Corp",
  fileName: "queued.csv",
  status: "uploaded",
});
assert.equal(uploaded.plotUrl, "");
assert.equal(uploaded.fileName, "queued.csv");

console.log("bankruptcy analysis frontend verification passed");
