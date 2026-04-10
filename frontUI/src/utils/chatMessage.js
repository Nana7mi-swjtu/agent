export const getMessageTraceSteps = (message) => {
  const steps = message?.trace?.steps;
  if (!Array.isArray(steps)) return [];
  return steps.filter((item) => item && typeof item === "object");
};

export const getMessageRagDebug = (message) => {
  const rag = message?.debug?.rag;
  return rag && typeof rag === "object" ? rag : null;
};

export const formatTraceDetailValue = (value) => {
  if (value == null) return "-";
  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : "-";
  }
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) return "-";
    return entries
      .map(([key, nested]) => `${key}=${formatTraceDetailValue(nested)}`)
      .join("; ");
  }
  const text = String(value).trim();
  return text || "-";
};
