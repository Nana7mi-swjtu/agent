import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { normalizeChatMessage } from "../src/entities/chat/lib/session.js";
import { resolveModuleDisplayMarkdown } from "../src/features/chat/lib/moduleArtifactPreview.js";

const root = resolve(import.meta.dirname, "..");
const read = (path) => readFileSync(resolve(root, path), "utf8");

const message = normalizeChatMessage({
  id: "m_robotics_preview",
  from: "agent",
  text: "模块结果",
  analysisModuleArtifact: {
    artifactId: "artifact_robotics_001",
    moduleId: "robotics_risk",
    markdownBody: [
      "# 机器人行业风险机会分析",
      "",
      "## 机会判断",
      "",
      "政策与订单是当前主线。",
      "",
      "{{table:opportunity_themes}}",
      "",
      "{{asset:asset_theme_001}}",
    ].join("\n"),
    factTables: [
      {
        tableId: "opportunity_themes",
        title: "机会主题",
        columns: [
          { key: "theme", label: "主题" },
          { key: "impactScore", label: "影响分" },
        ],
        rows: [
          {
            rowId: "opp_001",
            cells: { theme: "政策与设备更新", impactScore: 88 },
          },
        ],
      },
    ],
    renderedAssets: [
      {
        assetId: "asset_theme_001",
        chartId: "chart_theme_001",
        title: "机会主题强度分布",
        caption: "比较当前机会主线的相对强弱。",
        interpretationBoundary: "图中分值仅用于相对排序。",
        contentType: "image/png",
        renderPayload: { dataUrl: "data:image/png;base64,ZmFrZQ==" },
      },
    ],
  },
});

const resolvedMarkdown = resolveModuleDisplayMarkdown(message);

assert.match(resolvedMarkdown, /政策与订单是当前主线。/);
assert.match(resolvedMarkdown, /\*\*机会主题\*\*/);
assert.match(resolvedMarkdown, /\| 主题 \| 影响分 \|/);
assert.match(resolvedMarkdown, /\| 政策与设备更新 \| 88 \|/);
assert.match(resolvedMarkdown, /!\[机会主题强度分布\]\(data:image\/png;base64,ZmFrZQ==\)/);
assert.match(resolvedMarkdown, /解读边界：图中分值仅用于相对排序。/);
assert.doesNotMatch(resolvedMarkdown, /\{\{table:/);
assert.doesNotMatch(resolvedMarkdown, /\{\{asset:/);

const fallbackAssetMessage = normalizeChatMessage({
  id: "m_robotics_asset_fallback",
  from: "agent",
  analysisModuleArtifact: {
    artifactId: "artifact_robotics_002",
    moduleId: "robotics_risk",
    markdownBody: "## 风险判断\n\n{{asset:asset_risk_001}}",
    factTables: [
      {
        tableId: "risk_themes",
        title: "风险主题",
        columns: [{ key: "theme", label: "主题" }],
        rows: [{ rowId: "risk_001", cells: { theme: "监管与标准门槛" } }],
      },
    ],
    renderedAssets: [
      {
        assetId: "asset_risk_001",
        title: "风险主题强度分布",
        caption: "当前未生成图片资产，回退到关联表格。",
        sourceTableId: "risk_themes",
        fallbackTableId: "risk_themes",
      },
    ],
  },
});

const fallbackResolvedMarkdown = resolveModuleDisplayMarkdown(fallbackAssetMessage);
assert.match(fallbackResolvedMarkdown, /\*\*风险主题\*\*/);
assert.match(fallbackResolvedMarkdown, /\| 主题 \|/);
assert.match(fallbackResolvedMarkdown, /\| 监管与标准门槛 \|/);

const componentSource = read("src/features/chat/ui/ChatMessageItem.vue");
assert.doesNotMatch(componentSource, /module-reader-panel/);
assert.doesNotMatch(componentSource, /结构化表格/);
assert.doesNotMatch(componentSource, /图表预览/);

console.log("Robotics module rendering verified on the single markdown path.");
