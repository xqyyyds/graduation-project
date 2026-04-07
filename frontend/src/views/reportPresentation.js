const joinSegments = (segments) =>
  segments
    .map((item) => (item || "").trim())
    .filter(Boolean)
    .join("");

export const buildForecastTopicSummary = (topic = {}) => {
  const pieces = [];

  if (topic.background) {
    pieces.push(topic.background.trim());
  }

  const audience = (topic.audience || "").trim();
  const scene = (topic.scene_opening || "").trim();

  if (audience || scene) {
    const detailParts = [];
    if (audience) detailParts.push(`涉及人群以${audience}为主`);
    if (scene) detailParts.push(`典型发酵场景会出现在${scene}`);
    pieces.push(`${detailParts.join("，")}。`);
  }

  return joinSegments(pieces);
};

export const buildForecastParagraph = (point = {}) => {
  if (point.summary_paragraph?.trim()) {
    return point.summary_paragraph.trim();
  }

  const sentences = [];

  if (point.content?.trim()) {
    sentences.push(point.content.trim());
  }

  const trigger = (point.trigger || "").trim();
  const spreadPath = (point.spread_path || "").trim();
  const offlineScene = (point.offline_scene || "").trim();
  const onlineScene = (point.online_scene || "").trim();
  const likelihood = (point.likelihood || "").trim();
  const evidence = Array.isArray(point.evidence_basis)
    ? point.evidence_basis.filter(Boolean).join("、")
    : (point.evidence_basis || "").trim();

  if (trigger || spreadPath) {
    const sequence = [];
    if (trigger) sequence.push(`一旦出现${trigger}`);
    if (spreadPath) sequence.push(`讨论通常会沿着${spreadPath}持续外溢`);
    sentences.push(`${sequence.join("，")}。`);
  }

  if (offlineScene || onlineScene) {
    const sceneParts = [];
    if (offlineScene) sceneParts.push(`线下常见于${offlineScene}`);
    if (onlineScene) sceneParts.push(`线上则多在${onlineScene}被放大`);
    sentences.push(`${sceneParts.join("，")}。`);
  }

  if (likelihood || evidence) {
    const tailParts = [];
    if (likelihood) tailParts.push(`综合判断其发生可能性为${likelihood}`);
    if (evidence) tailParts.push(`这一判断主要基于${evidence}`);
    sentences.push(`${tailParts.join("，")}。`);
  }

  return joinSegments(sentences);
};
