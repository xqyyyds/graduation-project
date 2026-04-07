export const WORKFLOW_STEPS = [
  { id: "prepare", label: "数据准备" },
  { id: "deep_read", label: "深读分析" },
  { id: "compliance", label: "违规审核" },
  { id: "forecast", label: "趋势预测" },
  { id: "report", label: "报告组装" },
  { id: "done", label: "导出完成" },
];

export const getStepIndex = (stepId) =>
  WORKFLOW_STEPS.findIndex((item) => item.id === stepId);

export const getCurrentStepIndex = (task) =>
  task?.stage_id ? getStepIndex(task.stage_id) : -1;

export const isStepActive = (task, step) =>
  task?.status === "running" && task?.stage_id === step.id;

export const isStepCompleted = (task, step) => {
  if (!task) return false;
  if (task.status === "completed") return true;
  const idx = getStepIndex(step.id);
  const currentIdx = getCurrentStepIndex(task);
  return idx !== -1 && idx < currentIdx;
};
