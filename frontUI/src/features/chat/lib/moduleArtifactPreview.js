const PLACEHOLDER_PATTERN = /\{\{(table|asset):([A-Za-z0-9._-]+)\}\}/g;

const sliceObjects = (value, limit) =>
  Array.isArray(value) ? value.filter((item) => item && typeof item === "object").slice(0, limit) : [];

const escapeMarkdownCell = (value) => {
  const text = String(value ?? "-").trim() || "-";
  return text.replaceAll("|", "\\|").replaceAll("\n", "<br>");
};

export const getModuleArtifact = (message) =>
  message?.analysisModuleArtifact && typeof message.analysisModuleArtifact === "object"
    ? message.analysisModuleArtifact
    : null;

const getModuleTables = (message, limit = Number.MAX_SAFE_INTEGER) =>
  sliceObjects(getModuleArtifact(message)?.factTables, limit);

const getModuleRenderedAssets = (message, limit = Number.MAX_SAFE_INTEGER) =>
  sliceObjects(getModuleArtifact(message)?.renderedAssets, limit);

const getModuleRenderedAssetSrc = (asset) => {
  const payload = asset?.renderPayload && typeof asset.renderPayload === "object" ? asset.renderPayload : {};
  const dataUrl = String(payload.dataUrl || payload.src || "").trim();
  if (dataUrl) return dataUrl;
  const inlineContent = String(asset?.inlineContent || "").trim();
  const contentType = String(asset?.contentType || "image/png").trim() || "image/png";
  if (!inlineContent) return "";
  return /^data:/i.test(inlineContent) ? inlineContent : `data:${contentType};base64,${inlineContent}`;
};

const getModuleTableColumns = (table, limit = 8) =>
  Array.isArray(table?.columns) ? table.columns.filter((item) => item && typeof item === "object").slice(0, limit) : [];

const getModuleTableRows = (table, limit = 8) =>
  Array.isArray(table?.rows) ? table.rows.filter((item) => item && typeof item === "object").slice(0, limit) : [];

const getModuleTableCellText = (row, key) => {
  const cells = row?.cells && typeof row.cells === "object" ? row.cells : {};
  const value = cells?.[key];
  if (value === 0) return "0";
  return String(value || "-").trim() || "-";
};

const tableMarkdown = (table) => {
  const columns = getModuleTableColumns(table);
  if (!columns.length) return "";
  const rows = getModuleTableRows(table);
  const title = String(table?.title || table?.tableId || "表格").trim() || "表格";
  const header = `| ${columns.map((column) => escapeMarkdownCell(column.label || column.key)).join(" | ")} |`;
  const separator = `| ${columns.map(() => "---").join(" | ")} |`;
  const body = rows.map((row) => `| ${columns.map((column) => escapeMarkdownCell(getModuleTableCellText(row, column.key))).join(" | ")} |`);
  const lines = [`**${title}**`, "", header, separator, ...body];
  if (!rows.length && String(table?.emptyText || "").trim()) {
    lines.push(String(table.emptyText).trim());
  }
  return lines.join("\n");
};

const assetMarkdown = (asset, artifact) => {
  const src = getModuleRenderedAssetSrc(asset);
  const title = String(asset?.title || asset?.assetId || "图表").trim() || "图表";
  const alt = String(asset?.altText || title).trim() || title;
  const caption = String(asset?.caption || "").trim();
  const boundary = String(asset?.interpretationBoundary || "").trim();
  if (src) {
    const lines = [`![${alt}](${src})`];
    if (caption) lines.push(`*${caption}*`);
    if (boundary) lines.push(`> 解读边界：${boundary}`);
    return lines.join("\n\n");
  }
  const tableId = String(asset?.sourceTableId || asset?.fallbackTableId || "").trim();
  if (tableId) {
    const fallbackTable = getModuleTables({ analysisModuleArtifact: artifact }).find(
      (item) => String(item?.tableId || "").trim() === tableId,
    );
    if (fallbackTable) {
      const lines = [tableMarkdown(fallbackTable)];
      if (caption) lines.push(`*${caption}*`);
      if (boundary) lines.push(`> 解读边界：${boundary}`);
      return lines.filter(Boolean).join("\n\n");
    }
  }
  const fallbackText = [caption, boundary].filter(Boolean).join(" ");
  return fallbackText ? `> ${fallbackText}` : "";
};

export const resolveModuleDisplayMarkdown = (message) => {
  const artifact = getModuleArtifact(message);
  if (!artifact) return String(message?.text || "");
  const base = String(artifact?.markdownBody || message?.text || "").trim();
  if (!base) return "";
  PLACEHOLDER_PATTERN.lastIndex = 0;
  if (!PLACEHOLDER_PATTERN.test(base)) return base;
  PLACEHOLDER_PATTERN.lastIndex = 0;
  const tableById = new Map(
    getModuleTables(message).map((item) => [String(item?.tableId || "").trim(), item]),
  );
  const assetById = new Map(
    getModuleRenderedAssets(message).map((item) => [String(item?.assetId || "").trim(), item]),
  );
  return base.replace(PLACEHOLDER_PATTERN, (_, kind, identifier) => {
    if (kind === "table") {
      const table = tableById.get(String(identifier || "").trim());
      return table ? `\n\n${tableMarkdown(table)}\n\n` : "";
    }
    const asset = assetById.get(String(identifier || "").trim());
    return asset ? `\n\n${assetMarkdown(asset, artifact)}\n\n` : "";
  });
};
