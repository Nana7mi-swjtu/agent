export const normalizeEnabledAnalysisModules = (value) => {
  if (!Array.isArray(value)) return [];
  const result = [];
  value.forEach((item) => {
    const moduleId = String(item || "").trim();
    if (moduleId && !result.includes(moduleId)) {
      result.push(moduleId);
    }
  });
  return result;
};

export const buildWorkspaceChatRequestBody = (message, workspaceId, conversationId, options = {}) => {
  const enabledAnalysisModules = normalizeEnabledAnalysisModules(options.enabledAnalysisModules);
  const body = {
    message,
    workspaceId: workspaceId || "default",
    conversationId: conversationId || "",
    entity: typeof options.entity === "string" ? options.entity : "",
    intent: typeof options.intent === "string" ? options.intent : "",
  };
  if (enabledAnalysisModules.length) {
    body.enabledAnalysisModules = enabledAnalysisModules;
  }
  return body;
};
