import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { normalizeChatMessage } from "../src/entities/chat/lib/session.js";
import {
  getModuleEvidence,
  getModuleFallbackCharts,
  getModuleHeadline,
  getModuleRenderableAssets,
  getModuleRenderedAssetSrc,
  getModuleTableCellText,
  getModuleTableColumns,
  getModuleTableRows,
  getModuleTables,
  hasModuleArtifactContext,
} from "../src/features/chat/lib/moduleArtifactPreview.js";

const root = resolve(import.meta.dirname, "..");
const read = (path) => readFileSync(resolve(root, path), "utf8");

const message = normalizeChatMessage({
  id: "m_robotics_preview",
  from: "agent",
  text: "模块结果",
  analysisModuleArtifact: {
    artifactId: "artifact_robotics_001",
    moduleId: "robotics_risk",
    executiveSummary: { headline: "政策与订单是当前主线。" },
    evidenceReferences: [
      { id: "evidence_001", title: "公开政策文件", readerSummary: "该政策用于支撑机会侧判断。" },
    ],
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
      {
        tableId: "risk_themes",
        title: "风险主题",
        columns: [{ key: "theme", label: "主题" }],
        rows: [{ rowId: "risk_001", cells: { theme: "监管与标准门槛" } }],
      },
      {
        tableId: "source_composition",
        title: "证据来源构成",
        columns: [{ key: "sourceType", label: "来源类型" }],
        rows: [{ rowId: "src_001", cells: { sourceType: "政策" } }],
      },
      {
        tableId: "event_timeline",
        title: "事件时间线",
        columns: [{ key: "publishedAt", label: "日期" }],
        rows: [{ rowId: "evt_001", cells: { publishedAt: "2026-04-24" } }],
      },
    ],
    chartCandidates: [
      {
        chartId: "chart_theme_001",
        title: "机会主题强度分布",
        caption: "比较当前机会主线的相对强弱。",
      },
      {
        chartId: "chart_source_001",
        title: "证据来源构成",
        caption: "当前未生成图片资产，保留候选与表格回退。",
      },
    ],
    renderedAssets: [
      {
        assetId: "asset_theme_001",
        chartId: "chart_theme_001",
        title: "机会主题强度分布",
        contentType: "image/png",
        renderPayload: { dataUrl: "data:image/png;base64,ZmFrZQ==" },
      },
      {
        assetId: "asset_empty_001",
        chartId: "chart_unused_001",
        title: "空图像",
      },
    ],
    visualSummaries: [
      {
        id: "visual_source_001",
        title: "证据来源构成",
        caption: "来源构成仍可通过说明卡片回退展示。",
      },
    ],
  },
});

assert.equal(getModuleHeadline(message), "政策与订单是当前主线。");
assert.equal(getModuleEvidence(message).length, 1);
assert.equal(getModuleTables(message).length, 3);
assert.equal(getModuleTableColumns(getModuleTables(message)[0]).length, 2);
assert.equal(getModuleTableRows(getModuleTables(message)[0]).length, 1);
assert.equal(getModuleTableCellText(getModuleTableRows(getModuleTables(message)[0])[0], "impactScore"), "88");
assert.equal(getModuleRenderableAssets(message).length, 1);
assert.equal(getModuleRenderedAssetSrc(getModuleRenderableAssets(message)[0]), "data:image/png;base64,ZmFrZQ==");
assert.equal(getModuleFallbackCharts(message).length, 1);
assert.equal(getModuleFallbackCharts(message)[0].chartId, "chart_source_001");
assert.equal(hasModuleArtifactContext(message), true);

const fallbackOnlyMessage = normalizeChatMessage({
  id: "m_robotics_fallback",
  from: "agent",
  text: "模块结果",
  analysisModuleArtifact: {
    artifactId: "artifact_robotics_002",
    moduleId: "robotics_risk",
    visualSummaries: [{ id: "visual_001", title: "图表摘要", caption: "回退说明卡片。" }],
  },
});

assert.equal(getModuleRenderableAssets(fallbackOnlyMessage).length, 0);
assert.equal(getModuleFallbackCharts(fallbackOnlyMessage)[0].id, "visual_001");

const componentSource = read("src/features/chat/ui/ChatMessageItem.vue");
assert.match(componentSource, /module-reader-table/);
assert.match(componentSource, /module-reader-image/);
assert.match(componentSource, /结构化表格/);
assert.match(componentSource, /图表预览/);

console.log("Robotics module table and visual rendering verified.");
