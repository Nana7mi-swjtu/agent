export const normalizeTopFeatures = (raw) =>
  Array.isArray(raw)
    ? raw
        .filter((item) => item && typeof item === "object")
        .map((item) => ({
          name: String(item.name || ""),
          shapValue: Number(item.shapValue || 0),
          absoluteValue: Number(item.absoluteValue || Math.abs(Number(item.shapValue || 0))),
          direction: item.direction === "increase_risk" ? "increase_risk" : "decrease_risk",
        }))
    : [];

const normalizeInputSummary = (raw) =>
  raw && typeof raw === "object"
    ? {
        rowCount: Number(raw.rowCount || 0),
        featureCount: Number(raw.featureCount || 0),
      }
    : { rowCount: 0, featureCount: 0 };

const normalizeDate = (value) => (typeof value === "string" && value.trim() ? value : "");

export const normalizeBankruptcyRecord = (raw) => ({
  id: Number(raw?.id || 0),
  workspaceId: String(raw?.workspaceId || "default"),
  companyName: String(raw?.companyName || ""),
  sourceName: String(raw?.sourceName || ""),
  fileName: String(raw?.fileName || ""),
  fileExtension: String(raw?.fileExtension || ""),
  status: ["uploaded", "analyzed", "failed"].includes(raw?.status) ? raw.status : "uploaded",
  enterpriseName: String(raw?.enterpriseName || ""),
  errorMessage: String(raw?.errorMessage || ""),
  probability: raw?.probability == null ? null : Number(raw.probability),
  threshold: raw?.threshold == null ? null : Number(raw.threshold),
  riskLevel: raw?.riskLevel === "high" ? "high" : raw?.riskLevel === "low" ? "low" : "",
  plotUrl: typeof raw?.plotUrl === "string" ? raw.plotUrl : "",
  topFeatures: normalizeTopFeatures(raw?.topFeatures),
  inputSummary: normalizeInputSummary(raw?.inputSummary),
  createdAt: normalizeDate(raw?.createdAt),
  updatedAt: normalizeDate(raw?.updatedAt),
  analyzedAt: normalizeDate(raw?.analyzedAt),
});

export const normalizeBankruptcyRecordList = (raw) =>
  Array.isArray(raw) ? raw.map((item) => normalizeBankruptcyRecord(item)).filter((item) => item.id > 0) : [];

export const normalizeBankruptcyResult = (raw) => normalizeBankruptcyRecord(raw);
