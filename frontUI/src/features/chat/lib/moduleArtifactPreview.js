const sliceObjects = (value, limit) =>
  Array.isArray(value) ? value.filter((item) => item && typeof item === "object").slice(0, limit) : [];

export const getModuleArtifact = (message) =>
  message?.analysisModuleArtifact && typeof message.analysisModuleArtifact === "object"
    ? message.analysisModuleArtifact
    : null;

export const getModuleEvidence = (message, limit = 5) => sliceObjects(getModuleArtifact(message)?.evidenceReferences, limit);

export const getModuleTables = (message, limit = 3) => sliceObjects(getModuleArtifact(message)?.factTables, limit);

export const getModuleChartCandidates = (message, limit = 3) =>
  sliceObjects(getModuleArtifact(message)?.chartCandidates, limit);

export const getModuleRenderedAssets = (message, limit = 3) =>
  sliceObjects(getModuleArtifact(message)?.renderedAssets, limit);

export const getModuleRenderedAssetSrc = (asset) => {
  const payload = asset?.renderPayload && typeof asset.renderPayload === "object" ? asset.renderPayload : {};
  const dataUrl = String(payload.dataUrl || payload.src || "").trim();
  if (dataUrl) return dataUrl;
  const inlineContent = String(asset?.inlineContent || "").trim();
  const contentType = String(asset?.contentType || "image/png").trim() || "image/png";
  if (!inlineContent) return "";
  return /^data:/i.test(inlineContent) ? inlineContent : `data:${contentType};base64,${inlineContent}`;
};

export const getModuleRenderableAssets = (message, limit = 3) =>
  getModuleRenderedAssets(message, limit).filter((item) => getModuleRenderedAssetSrc(item));

export const getModuleFallbackCharts = (message, limit = 3) => {
  const renderedChartIds = new Set(
    getModuleRenderedAssets(message, limit)
      .map((item) => String(item?.chartId || "").trim())
      .filter(Boolean),
  );
  const candidates = getModuleChartCandidates(message, limit).filter(
    (item) => !renderedChartIds.has(String(item?.chartId || "").trim()),
  );
  if (candidates.length) return candidates;
  return sliceObjects(getModuleArtifact(message)?.visualSummaries, limit);
};

export const getModuleHeadline = (message) => {
  const artifact = getModuleArtifact(message);
  if (!artifact) return "";
  return String(artifact?.executiveSummary?.headline || artifact?.readerPacket?.executiveSummary?.headline || "").trim();
};

export const getModuleTableColumns = (table, limit = 6) =>
  Array.isArray(table?.columns) ? table.columns.filter((item) => item && typeof item === "object").slice(0, limit) : [];

export const getModuleTableRows = (table, limit = 5) =>
  Array.isArray(table?.rows) ? table.rows.filter((item) => item && typeof item === "object").slice(0, limit) : [];

export const getModuleTableCellText = (row, key) => {
  const cells = row?.cells && typeof row.cells === "object" ? row.cells : {};
  const value = cells?.[key];
  if (value === 0) return "0";
  return String(value || "-").trim() || "-";
};

export const hasModuleArtifactContext = (message) =>
  Boolean(getModuleArtifact(message))
  && (
    Boolean(getModuleHeadline(message))
    || getModuleEvidence(message).length > 0
    || getModuleTables(message).length > 0
    || getModuleRenderableAssets(message).length > 0
    || getModuleFallbackCharts(message).length > 0
  );
