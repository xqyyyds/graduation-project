import assert from "node:assert/strict";
import {
  WORKFLOW_STEPS,
  getCurrentStepIndex,
  getStepIndex,
  isStepActive,
  isStepCompleted,
} from "./taskProgress.js";

assert.equal(WORKFLOW_STEPS.length, 6);
assert.equal(getStepIndex("prepare"), 0);
assert.equal(getStepIndex("report"), 4);
assert.equal(getStepIndex("unknown"), -1);

const runningTask = { status: "running", stage_id: "compliance" };
assert.equal(getCurrentStepIndex(runningTask), 2);
assert.equal(isStepActive(runningTask, WORKFLOW_STEPS[2]), true);
assert.equal(isStepActive(runningTask, WORKFLOW_STEPS[1]), false);
assert.equal(isStepCompleted(runningTask, WORKFLOW_STEPS[0]), true);
assert.equal(isStepCompleted(runningTask, WORKFLOW_STEPS[1]), true);
assert.equal(isStepCompleted(runningTask, WORKFLOW_STEPS[2]), false);

const completedTask = { status: "completed", stage_id: "done" };
for (const step of WORKFLOW_STEPS) {
  assert.equal(isStepCompleted(completedTask, step), true);
}

console.log("taskProgress tests passed");
