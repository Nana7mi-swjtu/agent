import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) => fs.readFileSync(path.resolve(__dirname, "..", relativePath), "utf8");

const messageItemSource = read("src/features/chat/ui/ChatMessageItem.vue");
assert.match(messageItemSource, /import \{ buildApiUrl \} from "@\/shared\/api\/client"/);
assert.match(messageItemSource, /const resolveReportDownloadUrl = \(url\) =>/);
assert.match(messageItemSource, /cleanUrl\.startsWith\("\/api\/"\) \? buildApiUrl\(cleanUrl\) : cleanUrl/);
assert.match(messageItemSource, /reportForMessage\(message\)\.preview/);
assert.match(messageItemSource, /reportDownloadEntries\(message\)\.length/);
assert.match(messageItemSource, /filter\(\(item\) => item\.url\)/);

const workspaceApiSource = read("src/entities/workspace/api/index.js");
assert.match(workspaceApiSource, /import \{ apiRequest, buildApiUrl, streamApiRequest \} from "@\/shared\/api\/client"/);
assert.match(workspaceApiSource, /buildAnalysisReportDownloadUrl[\s\S]*buildApiUrl/);
assert.match(workspaceApiSource, /buildAnalysisReportAssetDownloadUrl[\s\S]*buildApiUrl/);

console.log("report preview download frontend verification passed");
