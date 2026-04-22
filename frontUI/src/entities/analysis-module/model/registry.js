export const ANALYSIS_MODULE_DEFINITIONS = [
  {
    id: "robotics_risk",
    labelKey: "analysisModuleRoboticsRisk",
  },
];

export const SUPPORTED_ANALYSIS_MODULE_IDS = ANALYSIS_MODULE_DEFINITIONS.map((module) => module.id);

const SUPPORTED_ANALYSIS_MODULE_ID_SET = new Set(SUPPORTED_ANALYSIS_MODULE_IDS);

export const normalizeAnalysisModuleIds = (raw) => {
  if (!Array.isArray(raw)) return [];
  const result = [];
  raw.forEach((item) => {
    const moduleId = String(item || "").trim();
    if (SUPPORTED_ANALYSIS_MODULE_ID_SET.has(moduleId) && !result.includes(moduleId)) {
      result.push(moduleId);
    }
  });
  return result;
};
