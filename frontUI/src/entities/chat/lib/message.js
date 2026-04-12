export const getMessageTraceSteps = (message) => {
  const steps = message?.trace?.steps;
  if (!Array.isArray(steps)) return [];
  return steps.filter((item) => item && typeof item === "object");
};

export const deriveSourcesFromCitations = (citations = []) => {
  const grouped = new Map();
  citations.forEach((citation) => {
    if (!citation || typeof citation !== "object") {
      return;
    }
    const source = String(citation.source || "").trim();
    if (!source) {
      return;
    }
    if (!grouped.has(source)) {
      grouped.set(source, {
        id: `rag:${source}`,
        kind: "rag",
        title: source,
        source,
        pages: [],
        sections: [],
        chunkIds: [],
        citationCount: 0,
      });
    }
    const entry = grouped.get(source);
    if (Number.isInteger(citation.page) && !entry.pages.includes(citation.page)) {
      entry.pages.push(citation.page);
    }
    const section = String(citation.section || "").trim();
    if (section && !entry.sections.includes(section)) {
      entry.sections.push(section);
    }
    const chunkId = String(citation.chunk_id || "").trim();
    if (chunkId && !entry.chunkIds.includes(chunkId)) {
      entry.chunkIds.push(chunkId);
    }
    entry.citationCount += 1;
  });
  return Array.from(grouped.values()).sort((left, right) => left.title.localeCompare(right.title));
};

export const getMessageSources = (message) => {
  if (Array.isArray(message?.sources) && message.sources.length) {
    return message.sources;
  }
  if (Array.isArray(message?.citations) && message.citations.length) {
    return deriveSourcesFromCitations(message.citations);
  }
  return [];
};

export const getMessageRagDebug = (message) => {
  const rag = message?.debug?.rag;
  return rag && typeof rag === "object" ? rag : null;
};

export const getMessageMemoryInfo = (message) => {
  const trace = message?.trace;
  if (!trace || typeof trace !== "object") return null;
  const steps = Array.isArray(trace.steps) ? trace.steps : [];
  const composeStep = steps.find(
    (step) => step && typeof step === "object" && (step.step_id || step.id) === "compose_answer",
  );
  if (!composeStep || typeof composeStep.details !== "object") return null;
  return {
    memoryUsed: Boolean(composeStep.details.memoryUsed),
    memoryMessageCount: Number.isInteger(composeStep.details.memoryMessageCount) ? composeStep.details.memoryMessageCount : 0,
    contextPresent: Boolean(composeStep.details.conversationContextPresent),
  };
};

export const formatSourceMeta = (source) => {
  if (!source || typeof source !== "object") return "-";
  if (source.kind === "web") {
    return String(source.domain || source.url || "-");
  }
  const parts = [];
  if (Array.isArray(source.pages) && source.pages.length) {
    parts.push(`p.${source.pages.join(", ")}`);
  }
  if (Array.isArray(source.sections) && source.sections.length) {
    parts.push(source.sections.join(" / "));
  }
  return parts.join(" · ") || "-";
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
