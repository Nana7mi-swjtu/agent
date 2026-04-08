const ACTIONS_BY_STATUS = {
  uploaded: "start",
  failed: "retry",
  indexed: "reindex",
};

export const getRagDocumentActionType = (document) => {
  const status = String(document?.status || "").trim().toLowerCase();
  return ACTIONS_BY_STATUS[status] || "";
};

export const canDeleteRagDocument = (document) => {
  const status = String(document?.status || "").trim().toLowerCase();
  return ["uploaded", "failed", "indexed"].includes(status);
};
