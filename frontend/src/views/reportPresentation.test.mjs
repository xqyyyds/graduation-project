import assert from "node:assert/strict";
import {
  buildForecastParagraph,
  buildForecastTopicSummary,
} from "./reportPresentation.js";

const summary = buildForecastTopicSummary({
  background: "3月形成的查分与分数线焦虑仍在持续。",
  audience: "考研考生、毕业生、家长",
  scene_opening: "查分夜、调剂群和宿舍夜谈",
});

assert.equal(
  summary,
  "3月形成的查分与分数线焦虑仍在持续。涉及人群以考研考生、毕业生、家长为主，典型发酵场景会出现在查分夜、调剂群和宿舍夜谈。"
);

assert.equal(
  buildForecastParagraph({
    summary_paragraph:
      "二手截图和口径不清的通知一旦叠加，争论就会迅速从求证滑向制度质疑。",
  }),
  "二手截图和口径不清的通知一旦叠加，争论就会迅速从求证滑向制度质疑。"
);

const paragraph = buildForecastParagraph({
  content: "围绕调剂信息和院校名额的二手截图仍会频繁出现。",
  trigger: "复试线、调剂名额、院校通知流出",
  spread_path: "群聊截图扩散到短视频平台和评论区",
  offline_scene: "宿舍、考研自习室、家长群讨论",
  online_scene: "热搜评论区、考研博主账号、信息汇总帖",
  evidence_basis: ["当前查分焦虑持续", "节点信息仍不透明"],
  likelihood: "High",
});

assert.ok(paragraph.includes("围绕调剂信息和院校名额的二手截图仍会频繁出现。"));
assert.ok(paragraph.includes("一旦出现复试线、调剂名额、院校通知流出"));
assert.ok(paragraph.includes("讨论通常会沿着群聊截图扩散到短视频平台和评论区持续外溢"));
assert.ok(paragraph.includes("线下常见于宿舍、考研自习室、家长群讨论"));
assert.ok(paragraph.includes("线上则多在热搜评论区、考研博主账号、信息汇总帖被放大"));
assert.ok(paragraph.includes("综合判断其发生可能性为High"));
assert.ok(paragraph.includes("这一判断主要基于当前查分焦虑持续、节点信息仍不透明"));

console.log("reportPresentation tests passed");
