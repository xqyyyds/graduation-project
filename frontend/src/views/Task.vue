<template>
  <div class="task-container">
    <div class="page-header">
      <h1 class="page-title">研判任务控制台</h1>
      <p class="page-desc">Task Execution & Monitoring Center</p>
    </div>

    <el-row
      :gutter="24"
      class="main-content-row"
      style="display: flex; align-items: stretch; flex-wrap: wrap"
    >
      <el-col :xs="24" :lg="9" class="left-col">
        <el-card class="create-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span class="header-title">
                <el-icon class="icon-box blue"><Plus /></el-icon> 新建任务
              </span>
            </div>
          </template>

          <el-form
            ref="formRef"
            :model="taskForm"
            :rules="rules"
            label-position="top"
            class="task-form"
          >
            <el-form-item label="分析类别 (Category)" prop="category">
              <el-select
                v-model="taskForm.category"
                placeholder="选择分析维度"
                style="width: 100%"
                size="large"
              >
                <template #prefix
                  ><el-icon><Menu /></el-icon
                ></template>
                <el-option
                  v-for="cat in categories"
                  :key="cat"
                  :label="cat"
                  :value="cat"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="时间范围 (Time Range)">
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item
                    prop="startDate"
                    label="开始日期"
                    label-width="0"
                  >
                    <el-date-picker
                      v-model="taskForm.startDate"
                      type="date"
                      placeholder="开始日期"
                      style="width: 100%"
                      size="large"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item prop="endDate" label="结束日期" label-width="0">
                    <el-date-picker
                      v-model="taskForm.endDate"
                      type="date"
                      placeholder="结束日期"
                      style="width: 100%"
                      size="large"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form-item>

            <el-form-item label="预测周期 (Forecast)" prop="forecast_range">
              <el-radio-group
                v-model="taskForm.forecast_range"
                class="forecast-group"
                size="large"
              >
                <el-radio-button
                  v-for="range in forecastRanges"
                  :key="range.value"
                  :label="range.value"
                >
                  {{ range.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>

            <div class="form-footer">
              <el-button
                type="primary"
                class="submit-btn"
                :loading="isSubmitting"
                :disabled="isTaskRunning"
                @click="submitTask"
              >
                <el-icon class="el-icon--left"><VideoPlay /></el-icon>
                {{ isTaskRunning ? "引擎占用中..." : "启动智能研判" }}
              </el-button>
            </div>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="15" class="right-col">
        <el-card class="monitor-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span class="header-title">
                <el-icon class="icon-box green"><Monitor /></el-icon>
                实时监控面板
              </span>
              <el-tag
                v-if="currentTask"
                :type="getStatusType(currentTask.status)"
                effect="dark"
                round
              >
                {{ getStatusText(currentTask.status) }}
              </el-tag>
            </div>
          </template>

          <div v-if="!currentTask" class="empty-state">
            <div class="empty-bg-circle">
              <el-icon><Cpu /></el-icon>
            </div>
            <h3>等待任务指令</h3>
            <p>Ready for Intelligence Processing</p>
          </div>

          <div v-else class="active-monitor">
            <div class="monitor-info-row">
              <div class="info-pill">
                <span class="label">ID</span>
                <span class="val code">{{
                  currentTask.task_id.slice(0, 8)
                }}</span>
              </div>
              <div class="info-pill">
                <span class="label">Target</span>
                <span class="val">{{
                  currentTask.category || taskForm.category
                }}</span>
              </div>
            </div>

            <div class="timer-section">
              <div class="timer-label">TASK DURATION</div>
              <div class="timer-display">
                {{ formatDuration(elapsedTime) }}
              </div>
            </div>

            <div class="progress-section">
              <div class="progress-header">
                <span class="p-label"
                  >Current Phase: {{ currentTask.current_step }}</span
                >
                <span class="p-val">{{ currentTask.progress }}%</span>
              </div>
              <el-progress
                :percentage="currentTask.progress"
                :stroke-width="12"
                :status="getProgressStatus(currentTask.status)"
                striped
                striped-flow
                :duration="15"
                :show-text="false"
              />
            </div>

            <div
              class="result-actions"
              v-if="['completed', 'failed'].includes(currentTask.status)"
            >
              <el-button
                type="success"
                v-if="currentTask.status === 'completed'"
                @click="viewReport"
                class="action-btn"
              >
                <el-icon><DocumentChecked /></el-icon> 查看报告
              </el-button>
              <el-button @click="resetTask" class="action-btn">
                <el-icon><RefreshRight /></el-icon> 重置
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <div class="workflow-section">
      <div class="section-title">INTELLIGENCE PROCESSING PIPELINE</div>
      <div class="pipeline-container">
        <div class="pipeline-line"></div>

        <div
          class="pipeline-node"
          v-for="(step, idx) in workflowSteps"
          :key="idx"
          :class="{
            'is-active': isStepActive(step),
            'is-done': isStepCompleted(step),
          }"
        >
          <div class="node-circle">
            <el-icon v-if="isStepCompleted(step)"><Check /></el-icon>
            <el-icon v-else-if="isStepActive(step)" class="is-loading"
              ><Loading
            /></el-icon>
            <span v-else>{{ idx + 1 }}</span>
          </div>
          <div class="node-content">
            <span class="node-title">{{ step }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { storeToRefs } from "pinia";
import { ref, computed, reactive, onMounted, onUnmounted, watch } from "vue";
import { useRouter } from "vue-router";
import { useAppStore } from "../stores/app";
import { ElMessage } from "element-plus";
import dayjs from "dayjs";

const router = useRouter();
const store = useAppStore();
const formRef = ref(null);
const isSubmitting = ref(false);

const categories = computed(() => store.categories);
const forecastRanges = computed(() => store.forecastRanges);
// 直接使用 store 中的 ref，这样在脚本中访问时可以用 currentTask.value 获取真实对象
const { currentTask, taskStartTime } = storeToRefs(store);
const isTaskRunning = computed(() => store.isTaskRunning);

// ==========================================
// 🔥🔥🔥 核心修改：计时器逻辑彻底修复 🔥🔥🔥
// ==========================================
const elapsedTime = ref(0);
let timerInterval = null;

// 更新时间的核心函数
const updateElapsedTime = () => {
  // 优先使用后端返回的 start_time/end_time（毫秒），兜底使用本地的 taskStartTime
  const start =
    (currentTask.value && currentTask.value.start_time) ||
    taskStartTime.value ||
    0;
  if (!start || start <= 0) {
    elapsedTime.value = 0;
    return;
  }

  // 如果后端有结束时间且任务已完成/失败，使用结束时间冻结显示
  const end = currentTask.value && currentTask.value.end_time;
  if (
    currentTask.value &&
    (currentTask.value.status === "completed" ||
      currentTask.value.status === "failed") &&
    end &&
    end > 0
  ) {
    elapsedTime.value = end - start;
  } else {
    const now = Date.now();
    elapsedTime.value = now - start;
  }
};

const startTimer = () => {
  if (timerInterval) clearInterval(timerInterval);
  updateElapsedTime(); // 立即执行一次，防止UI跳变
  timerInterval = setInterval(updateElapsedTime, 1000);
};

const stopTimer = () => {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
};

// 监听任务状态自动启停计时器
watch(
  () => currentTask.value?.status,
  (newStatus) => {
    if (newStatus === "running") {
      // 只要状态是运行中，就开启计时（updateElapsedTime 会自动去 store 拿正确的时间戳）
      startTimer();
    } else if (newStatus === "completed" || newStatus === "failed") {
      stopTimer();
      updateElapsedTime(); // 结束时最后校准一次时间
    } else {
      stopTimer();
      elapsedTime.value = 0;
    }
  },
  { immediate: true } // 立即执行，确保刷新页面后能从 localStorage 恢复计时
);

onUnmounted(() => stopTimer());

// ==========================================
// 下面是常规业务逻辑，无需修改
// ==========================================

const formatDuration = (ms) => {
  if (ms < 0) ms = 0;
  const totalSeconds = Math.floor(ms / 1000);
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(
    s
  ).padStart(2, "0")}`;
};

const taskForm = reactive({
  category: "综合",
  startDate: null,
  endDate: null,
  forecast_range: "1m",
});

const workflowSteps = [
  "数据分类",
  "数据准备",
  "观点分析",
  "合规审查",
  "质量评估",
  "趋势预测",
  "报告生成",
];

const rules = {
  category: [{ required: true, message: "请选择类别", trigger: "change" }],
  startDate: [
    { required: true, message: "请选择开始日期", trigger: "change" },
    {
      validator: (rule, value, callback) => {
        if (!value) return callback();
        const today = new Date();
        today.setHours(23, 59, 59, 999);
        if (new Date(value) > today)
          callback(new Error("开始日期不能晚于今天"));
        else callback();
      },
      trigger: "change",
    },
  ],
  endDate: [
    { required: true, message: "请选择结束日期", trigger: "change" },
    {
      validator: (rule, value, callback) => {
        if (!value) return callback();
        const today = new Date();
        today.setHours(23, 59, 59, 999);
        if (new Date(value) > today)
          return callback(new Error("结束日期不能晚于今天"));
        if (!taskForm.startDate) return callback();
        if (new Date(taskForm.startDate) > new Date(value)) {
          return callback(new Error("结束日期不能早于开始日期"));
        }
        callback();
      },
      trigger: "change",
    },
  ],
};

const submitTask = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (valid) {
      isSubmitting.value = true;
      try {
        await store.createTask({
          category: taskForm.category,
          forecast_range: taskForm.forecast_range,
          start_date: dayjs(taskForm.startDate).format("YYYY-MM-DD"),
          end_date: dayjs(taskForm.endDate).format("YYYY-MM-DD"),
        });
        ElMessage.success("指令已下发，任务开始执行");
      } catch (e) {
        ElMessage.error("启动失败: " + e.message);
      } finally {
        isSubmitting.value = false;
      }
    }
  });
};

const getStatusType = (s) =>
  ({ running: "primary", completed: "success", failed: "danger" }[s] || "info");
const getStatusText = (s) =>
  ({ running: "运行中", completed: "已完成", failed: "执行失败" }[s] ||
  "等待中");
const getProgressStatus = (s) =>
  ({ completed: "success", failed: "exception" }[s] || "");

const getStepIndex = (stepName) => workflowSteps.indexOf(stepName);
const currentStepIndex = computed(() =>
  currentTask.value ? getStepIndex(currentTask.value.current_step) : -1
);

const isStepActive = (step) =>
  currentTask.value?.status === "running" &&
  currentTask.value.current_step === step;
const isStepCompleted = (step) => {
  if (!currentTask.value) return false;
  if (currentTask.value.status === "completed") return true;
  const idx = getStepIndex(step);
  return idx !== -1 && idx < currentStepIndex.value;
};

const viewReport = () => router.push("/reports");
const resetTask = () => {
  store.clearCurrentTask(); // 这会同时重置 store.taskStartTime
  elapsedTime.value = 0;
  stopTimer();
};

onMounted(() => store.restoreTaskPolling());
</script>

<style scoped>
/* 1. 基础容器 */
.task-container {
  max-width: 1600px;
  margin: 0 auto;
}
.page-header {
  margin-bottom: 32px;
}
.page-title {
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.5px;
}
.page-desc {
  color: var(--text-muted);
  font-size: 14px;
  margin-top: 4px;
  font-family: "Inter", sans-serif;
}

.main-content-row {
  margin-bottom: 32px;
}

/* 2. 通用卡片 */
.create-card,
.monitor-card {
  height: 100%;
  border: none;
  display: flex;
  flex-direction: column;
}
:deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-title {
  font-weight: 700;
  font-size: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
}

.icon-box {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}
.icon-box.blue {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
}
.icon-box.green {
  background: linear-gradient(135deg, #10b981, #059669);
}

/* 3. 左侧表单 */
.task-form {
  display: flex;
  flex-direction: column;
  flex: 1;
}
.forecast-group {
  width: 100%;
  display: flex;
}
:deep(.el-radio-button) {
  flex: 1;
}
:deep(.el-radio-button__inner) {
  width: 100%;
}

.form-footer {
  margin-top: auto;
  padding-top: 32px;
}
.submit-btn {
  width: 100%;
  height: 56px;
  font-size: 16px;
  font-weight: 700;
  border-radius: 12px;
  transition: all 0.3s;
}
.submit-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.3);
}

/* 4. 右侧监控 - 计时器风格 */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}
.empty-bg-circle {
  width: 120px;
  height: 120px;
  background: var(--bg-body);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 56px;
  color: var(--text-light);
  margin-bottom: 24px;
  border: 4px solid var(--bg-card);
  box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.05);
}

.active-monitor {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between; /* 上下撑开 */
}

/* 顶部信息行 */
.monitor-info-row {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}
.info-pill {
  background: var(--bg-body);
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
}
.info-pill .val {
  font-weight: 700;
  color: var(--text-primary);
}
.info-pill .code {
  font-family: monospace;
}

/* 🔥🔥 核心：数字时钟区域 🔥🔥 */
.timer-section {
  flex: 1; /* 占据中间所有空白 */
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--bg-body);
  border-radius: 16px;
  margin-bottom: 24px;
  padding: 32px 0;
  border: 1px solid var(--border-color);
  position: relative;
  overflow: hidden;
}
/* 装饰性背景光效 */
.timer-section::after {
  content: "";
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(
    circle,
    rgba(37, 99, 235, 0.03) 0%,
    rgba(0, 0, 0, 0) 70%
  );
  pointer-events: none;
}

.timer-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--text-muted);
  margin-bottom: 12px;
}
.timer-display {
  font-family: "Courier New", Courier, monospace; /* 模拟电子表字体 */
  font-size: 64px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 4px;
  line-height: 1;
  margin-bottom: 0; /* 居中显示，不留额外下边距 */
  text-shadow: 0 0 20px rgba(37, 99, 235, 0.1);
  font-variant-numeric: tabular-nums; /* 数字等宽，防止跳动 */
}

/* 3列次级指标 */
.timer-sub-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  width: 100%;
  padding: 0 24px;
  gap: 24px;
}
.sub-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.sub-label {
  font-size: 12px;
  color: var(--text-muted);
}
.sub-val {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.speed-text {
  color: var(--success-color);
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 进度条沉底 */
.progress-section {
  margin-top: auto;
}
.progress-header {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-weight: 500;
}
.p-val {
  color: var(--primary-color);
  font-weight: 700;
}

.result-actions {
  display: flex;
  gap: 16px;
  margin-top: 24px;
}
.action-btn {
  flex: 1;
  height: 48px;
}

/* 5. 底部工作流图示 */
.workflow-section {
  background: var(--bg-card);
  border-radius: 16px;
  border: 1px solid var(--border-color);
  padding: 32px;
  box-shadow: var(--shadow-sm);
}
.section-title {
  text-align: center;
  font-size: 12px;
  font-weight: 800;
  color: var(--text-muted);
  letter-spacing: 2px;
  margin-bottom: 40px;
}

.pipeline-container {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  position: relative;
  max-width: 1200px;
  margin: 0 auto;
}

/* 贯穿线 */
.pipeline-line {
  position: absolute;
  top: 24px;
  left: 40px;
  right: 40px;
  height: 2px;
  background: var(--border-color);
  z-index: 0;
}

.pipeline-node {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 120px;
  text-align: center;
}

/* 圆圈节点 */
.node-circle {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--bg-card);
  border: 2px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-muted);
  margin-bottom: 16px;
  transition: all 0.3s;
}

.node-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.node-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  transition: color 0.3s;
}

/* 激活状态 */
.pipeline-node.is-active .node-circle {
  border-color: var(--primary-color);
  background: var(--bg-card);
  color: var(--primary-color);
  box-shadow: 0 0 0 6px rgba(37, 99, 235, 0.1);
  transform: scale(1.1);
}
.pipeline-node.is-active .node-title {
  color: var(--primary-color);
}

/* 完成状态 */
.pipeline-node.is-done .node-circle {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: white;
}
.pipeline-node.is-done .node-title {
  color: var(--text-primary);
}
</style>
