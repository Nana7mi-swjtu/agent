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
assert.match(messageItemSource, /const reportRequestForMessage = \(message\) =>/);
assert.match(messageItemSource, /renderStylesForRequest\(reportRequestForMessage\(message\)\)/);
assert.match(messageItemSource, /runReportGeneration\(message\)/);
assert.match(messageItemSource, /runReportRegeneration\(message\)/);
assert.match(messageItemSource, /完整预览/);
assert.match(messageItemSource, /下载 \{\{ item\.label \}\}/);
assert.match(messageItemSource, /重新生成/);
assert.match(messageItemSource, /\{ key: "pdf", label: "PDF", url: resolveReportDownloadUrl\(urls\.pdf\) \}/);
assert.match(messageItemSource, /filter\(\(item\) => item\.url\)/);
assert.doesNotMatch(messageItemSource, /report type|reportType|structureOptions|sectionOptions|moduleSubset|tableOfContents/i);

const workspaceApiSource = read("src/entities/workspace/api/index.js");
assert.match(workspaceApiSource, /import \{ apiRequest, buildApiUrl, streamApiRequest \} from "@\/shared\/api\/client"/);
assert.match(workspaceApiSource, /buildAnalysisReportDownloadUrl = \(reportId, format = "pdf", workspaceId = "default"\)/);
assert.match(workspaceApiSource, /buildAnalysisReportPreviewUrl = \(reportId, format = "pdf", workspaceId = "default"\)/);
assert.match(workspaceApiSource, /postAnalysisReportGeneration =/);
assert.match(workspaceApiSource, /postAnalysisReportRegeneration =/);
assert.match(workspaceApiSource, /buildAnalysisReportDownloadUrl[\s\S]*buildApiUrl/);
assert.match(workspaceApiSource, /buildAnalysisReportAssetDownloadUrl[\s\S]*buildApiUrl/);

const messagingSource = read("src/features/chat/model/useChatMessaging.js");
assert.match(messagingSource, /analysisModuleArtifacts/);
assert.match(messagingSource, /reportGenerationRequest/);
assert.match(messagingSource, /全部分析模块已完成。请选择渲染风格后生成综合报告。/);

const markdownSource = read("src/shared/lib/markdown.js");
assert.match(markdownSource, /import \{ buildApiUrl \} from "@\/shared\/api\/client"/);
assert.match(markdownSource, /const resolveBackendRelativeUrl = \(value\) =>/);
assert.match(markdownSource, /clean\.startsWith\("\/api\/"\) \? buildApiUrl\(clean\) : clean/);
assert.match(markdownSource, /token\.attrSet\("href", resolveBackendRelativeUrl\(token\.attrGet\("href"\)\)\)/);
assert.match(markdownSource, /token\.attrSet\("src", resolveBackendRelativeUrl\(token\.attrGet\("src"\)\)\)/);

console.log("report preview download frontend verification passed");
