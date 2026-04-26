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
assert.match(messageItemSource, /const reportPreviewUrl = \(message\) => resolveReportDownloadUrl\(reportForMessage\(message\)\?\.previewUrl\)/);
assert.match(messageItemSource, /完整预览/);
assert.match(messageItemSource, /下载 \{\{ item\.label \}\}/);
assert.match(messageItemSource, /\{ key: "pdf", label: "PDF", url: resolveReportDownloadUrl\(urls\.pdf\) \}/);
assert.match(messageItemSource, /filter\(\(item\) => item\.url\)/);
assert.doesNotMatch(messageItemSource, /analysisReportRequest|runReportGeneration|runReportRegeneration|重新生成/);
assert.doesNotMatch(messageItemSource, /report type|reportType|structureOptions|sectionOptions|moduleSubset|tableOfContents/i);

const workspaceApiSource = read("src/entities/workspace/api/index.js");
assert.match(workspaceApiSource, /import \{ apiRequest, buildApiUrl, streamApiRequest \} from "@\/shared\/api\/client"/);
assert.match(workspaceApiSource, /postWorkspaceReport = \(payload = \{\}\) =>/);
assert.match(workspaceApiSource, /buildAnalysisReportDownloadUrl = \(reportId, format = "pdf", workspaceId = "default"\)/);
assert.match(workspaceApiSource, /buildAnalysisReportPreviewUrl = \(reportId, format = "pdf", workspaceId = "default"\)/);
assert.doesNotMatch(workspaceApiSource, /postAnalysisReportGeneration =/);
assert.doesNotMatch(workspaceApiSource, /postAnalysisReportRegeneration =/);
assert.match(workspaceApiSource, /buildAnalysisReportDownloadUrl[\s\S]*buildApiUrl/);
assert.match(workspaceApiSource, /buildAnalysisReportAssetDownloadUrl[\s\S]*buildApiUrl/);

const messagingSource = read("src/features/chat/model/useChatMessaging.js");
assert.match(messagingSource, /analysisModuleArtifacts/);
assert.doesNotMatch(messagingSource, /analysisReportRequest|runReportAction = async|全部分析模块已完成。请选择渲染风格后生成综合报告。/);

const sessionSource = read("src/entities/chat/lib/session.js");
assert.match(sessionSource, /bundleSchemaVersion: String\(raw\.bundleSchemaVersion \|\| ""\)/);
assert.match(sessionSource, /renderProfile: raw\.renderProfile && typeof raw\.renderProfile === "object" \? raw\.renderProfile : null/);
assert.match(sessionSource, /exportManifest: raw\.exportManifest && typeof raw\.exportManifest === "object" \? raw\.exportManifest : null/);
assert.match(sessionSource, /pageCount: Number\.isInteger\(raw\.pageCount\) \? raw\.pageCount : 0/);
assert.doesNotMatch(sessionSource, /analysisReportRequest/);

const markdownSource = read("src/shared/lib/markdown.js");
assert.match(markdownSource, /import \{ buildApiUrl \} from "@\/shared\/api\/client"/);
assert.match(markdownSource, /const resolveBackendRelativeUrl = \(value\) =>/);
assert.match(markdownSource, /clean\.startsWith\("\/api\/"\) \? buildApiUrl\(clean\) : clean/);
assert.match(markdownSource, /token\.attrSet\("href", resolveBackendRelativeUrl\(token\.attrGet\("href"\)\)\)/);
assert.match(markdownSource, /token\.attrSet\("src", resolveBackendRelativeUrl\(token\.attrGet\("src"\)\)\)/);

console.log("report preview download frontend verification passed");
