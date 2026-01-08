<template>
  <div class="task-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">任务管理</h1>
      <p class="page-desc">创建并管理舆情研判任务</p>
    </div>

    <el-row :gutter="24">
      <!-- 左侧：创建任务 -->
      <el-col :xs="24" :lg="10">
        <el-card class="create-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20" color="#10b981"><Plus /></el-icon>
              <span>创建新任务</span>
            </div>
          </template>

          <el-form
            ref="formRef"
            :model="taskForm"
            :rules="rules"
            label-position="top"
            class="task-form"
          >
            <el-form-item label="分析类别" prop="category">
              <el-select
                v-model="taskForm.category"
                placeholder="选择类别"
                style="width: 100%"
              >
                <el-option
                  v-for="cat in categories"
                  :key="cat"
                  :label="cat"
                  :value="cat"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="时间范围" prop="dateRange">
              <div style="display: flex; gap: 8px; align-items: center">
                <el-date-picker
                  ref="startPickerRef"
                  v-model="pickerStart"
                  type="date"
                  placeholder="开始日期"
                  clearable
                  editable
                  value-format="YYYY-MM-DD"
                  style="width: 48%"
                  @change="onStartChange"
                />

                <el-date-picker
                  ref="endPickerRef"
                  v-model="pickerEnd"
                  type="date"
                  placeholder="结束日期"
                  clearable
                  editable
                  value-format="YYYY-MM-DD"
                  style="width: 48%"
                  @change="onEndChange"
                />
              </div>

              <div class="date-tip">
                <el-icon size="14" color="#909399" style="margin-right: 4px">
                  <InfoFilled />
                </el-icon>
                <span>支持手动输入 (YYYY-MM-DD)，请点击"保存"生效。</span>
              </div>

              <div v-if="showSaveButton" class="picker-actions">
                <el-button size="small" type="primary" @click="applyPicker"
                  >保存</el-button
                >
                <el-button size="small" @click="clearPickers">清除</el-button>
              </div>
            </el-form-item>

            <el-form-item label="预测周期" prop="forecast_range">
              <el-radio-group v-model="taskForm.forecast_range">
                <el-radio-button
                  v-for="range in forecastRanges"
                  :key="range.value"
                  :value="range.value"
                >
                  {{ range.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                size="large"
                :loading="isSubmitting"
                :disabled="isTaskRunning"
                class="submit-btn"
                @click="submitTask"
              >
                <el-icon><CaretRight /></el-icon>
                {{ isTaskRunning ? "任务运行中..." : "启动研判任务" }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右侧：任务状态 -->
      <el-col :xs="24" :lg="14">
        <el-card class="status-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20" color="#3b82f6"><Monitor /></el-icon>
              <span>任务监控</span>
            </div>
          </template>

          <!-- 无任务状态 -->
          <div v-if="!currentTask" class="empty-state">
            <el-icon :size="64" color="#d1d5db"><Tickets /></el-icon>
            <p>暂无运行中的任务</p>
            <span>创建新任务后，将在此处显示进度</span>
          </div>

          <!-- 有任务状态 -->
          <div v-else class="task-monitor">
            <!-- 任务信息 -->
            <div class="task-info">
              <div class="info-row">
                <span class="info-label">任务ID</span>
                <span class="info-value">{{ currentTask.task_id }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">状态</span>
                <el-tag :type="getStatusType(currentTask.status)" size="large">
                  {{ getStatusText(currentTask.status) }}
                </el-tag>
              </div>
            </div>

            <!-- 进度条 -->
            <div class="progress-section">
              <div class="progress-header">
                <span>执行进度</span>
                <span>{{ currentTask.progress }}%</span>
              </div>
              <el-progress
                :percentage="currentTask.progress"
                :status="getProgressStatus(currentTask.status)"
                :stroke-width="12"
              />
            </div>

            <!-- 当前步骤 -->
            <div class="step-section">
              <div class="step-header">
                <el-icon
                  v-if="currentTask.status === 'running'"
                  class="is-loading"
                >
                  <Loading />
                </el-icon>
                <el-icon
                  v-else-if="currentTask.status === 'completed'"
                  color="#10b981"
                >
                  <CircleCheck />
                </el-icon>
                <el-icon v-else color="#ef4444">
                  <CircleClose />
                </el-icon>
                <span>{{ currentTask.current_step }}</span>
              </div>
              <p class="step-message">{{ currentTask.message }}</p>
            </div>

            <!-- 操作按钮 -->
            <div
              v-if="
                currentTask.status === 'completed' ||
                currentTask.status === 'failed' ||
                currentTask.status === 'unknown'
              "
              class="action-section"
            >
              <el-button
                v-if="currentTask.status === 'completed'"
                type="primary"
                @click="viewLatestReport"
              >
                <el-icon><View /></el-icon>
                查看报告
              </el-button>
              <el-button @click="clearTask">
                <el-icon><RefreshRight /></el-icon>
                新建任务
              </el-button>
            </div>
          </div>
        </el-card>

        <!-- 工作流说明 -->
        <el-card class="workflow-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20" color="#8b5cf6"><InfoFilled /></el-icon>
              <span>工作流说明</span>
            </div>
          </template>

          <el-steps :active="getActiveStep()" align-center>
            <el-step title="数据采集" description="热搜聚类" />
            <el-step title="热度统计" description="Agent A" />
            <el-step title="观点分析" description="Agent B" />
            <el-step title="合规审查" description="Agent C" />
            <el-step title="趋势预测" description="Agent D" />
            <el-step title="报告生成" description="Agent E" />
          </el-steps>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useAppStore } from "../stores/app";
import { ElMessage } from "element-plus";

const router = useRouter();
const store = useAppStore();

const formRef = ref(null);
const isSubmitting = ref(false);

const categories = computed(() => store.categories);
const forecastRanges = computed(() => store.forecastRanges);
const currentTask = computed(() => store.currentTask);
const isTaskRunning = computed(() => store.isTaskRunning);

// 页面加载时恢复任务轮询
onMounted(() => {
  store.restoreTaskPolling();
});

onUnmounted(() => {
  // 不停止轮询，让状态在后台继续更新
});

// 表单数据
const taskForm = reactive({
  category: "综合",
  dateRange: null,
  forecast_range: "1m",
});

// 表单验证
const rules = {
  category: [{ required: true, message: "请选择分析类别", trigger: "change" }],
};

// 日期选择器
const pickerStart = ref(null);
const pickerEnd = ref(null);
const startPickerRef = ref(null);
const endPickerRef = ref(null);

// 显示保存按钮的条件
const showSaveButton = computed(() => {
  if (!pickerStart.value && !pickerEnd.value) return false;
  const current = JSON.stringify([pickerStart.value, pickerEnd.value]);
  const saved = JSON.stringify(taskForm.dateRange);
  return current !== saved;
});

// 同步初始值
watch(
  () => taskForm.dateRange,
  (v) => {
    pickerStart.value = v?.[0] || null;
    pickerEnd.value = v?.[1] || null;
  },
  { immediate: true }
);

// 验证日期字符串
const isValidDateStr = (s) => {
  if (!s || typeof s !== "string") return false;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const [y, m, d] = s.split("-").map((x) => parseInt(x, 10));
  const dt = new Date(y, m - 1, d);
  return (
    dt.getFullYear() === y && dt.getMonth() + 1 === m && dt.getDate() === d
  );
};

// 保存日期
const applyPicker = () => {
  const s = pickerStart.value ? String(pickerStart.value).trim() : null;
  const e = pickerEnd.value ? String(pickerEnd.value).trim() : null;

  if (!s || !e) {
    ElMessage.error("请同时选择开始与结束日期。");
    return;
  }

  if (!isValidDateStr(s)) {
    ElMessage.error("开始日期格式不正确，请输入 YYYY-MM-DD。");
    return;
  }
  if (!isValidDateStr(e)) {
    ElMessage.error("结束日期格式不正确，请输入 YYYY-MM-DD。");
    return;
  }

  if (s > e) {
    ElMessage.error("结束日期不得早于开始日期。");
    return;
  }

  taskForm.dateRange = [s, e];
  ElMessage.success("日期已保存");
};

const clearPickers = () => {
  pickerStart.value = null;
  pickerEnd.value = null;
  taskForm.dateRange = null;
};

const onStartChange = (v) => {
  const s = v ? String(v).trim() : null;
  if (s && !isValidDateStr(s)) {
    ElMessage.error("开始日期格式不正确。");
  }
};

const onEndChange = (v) => {
  const e = v ? String(v).trim() : null;
  if (e && !isValidDateStr(e)) {
    ElMessage.error("结束日期格式不正确。");
  }
};

// 提交任务
const submitTask = async () => {
  try {
    await formRef.value.validate();

    const s = taskForm.dateRange?.[0];
    const e = taskForm.dateRange?.[1];

    if (!s || !e) {
      ElMessage.error("请先保存开始与结束日期。");
      return;
    }

    if (!isValidDateStr(s) || !isValidDateStr(e)) {
      ElMessage.error("日期格式不正确，请输入 YYYY-MM-DD。");
      return;
    }

    if (s > e) {
      ElMessage.error("结束日期不得早于开始日期。");
      return;
    }

    isSubmitting.value = true;

    const params = {
      category: taskForm.category,
      forecast_range: taskForm.forecast_range,
      start_date: s,
      end_date: e,
    };

    await store.createTask(params);
    ElMessage.success("任务创建成功，开始执行...");
  } catch (error) {
    if (error !== false) {
      ElMessage.error("任务创建失败: " + (error.message || "未知错误"));
    }
  } finally {
    isSubmitting.value = false;
  }
};

// 辅助函数
const getStatusType = (status) => {
  const map = {
    running: "warning",
    completed: "success",
    failed: "danger",
    unknown: "info",
  };
  return map[status] || "info";
};

const getStatusText = (status) => {
  const map = {
    running: "运行中",
    completed: "已完成",
    failed: "失败",
    unknown: "状态丢失",
  };
  return map[status] || status;
};

const getProgressStatus = (status) => {
  if (status === "failed") return "exception";
  if (status === "completed") return "success";
  return "";
};

const getActiveStep = () => {
  if (!currentTask.value) return 0;
  const step = currentTask.value.current_step;
  const stepMap = {
    初始化: 0,
    数据采集: 0,
    热度统计: 1,
    观点分析: 2,
    合规审查: 3,
    趋势预测: 4,
    报告生成: 5,
    完成: 6,
  };
  return stepMap[step] || 0;
};

const viewLatestReport = () => {
  router.push("/reports");
};

const clearTask = () => {
  store.clearCurrentTask();
};
</script>

<style scoped>
.task-page {
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 28px;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  color: #1f2937;
  margin: 0 0 8px 0;
}

.page-desc {
  font-size: 14px;
  color: #6b7280;
  margin: 0;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 15px;
}

/* 创建任务卡片 */
.create-card {
  margin-bottom: 24px;
  border-radius: 12px;
  border: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.task-form {
  padding: 8px 0;
}

.task-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: #374151;
}

.submit-btn {
  width: 100%;
  height: 52px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 10px;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  border: none;
  transition: all 0.3s;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.35);
}

/* 任务状态卡片 */
.status-card {
  margin-bottom: 24px;
  border-radius: 12px;
  border: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 56px 0;
  color: #9ca3af;
}

.empty-state p {
  margin: 20px 0 8px;
  font-size: 16px;
  font-weight: 500;
  color: #6b7280;
}

.empty-state span {
  font-size: 14px;
  color: #9ca3af;
}

.task-monitor {
  padding: 8px 0;
}

.task-info {
  display: flex;
  gap: 40px;
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid #f3f4f6;
}

.info-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-label {
  font-size: 12px;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 500;
}

.info-value {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  font-family: "SF Mono", Monaco, monospace;
}

.progress-section {
  margin-bottom: 24px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 500;
  color: #374151;
}

.progress-header span:last-child {
  color: #10b981;
  font-weight: 600;
}

.step-section {
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border-radius: 10px;
  padding: 18px 20px;
  margin-bottom: 24px;
  border: 1px solid #d1fae5;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
}

.step-message {
  margin: 0;
  font-size: 14px;
  color: #6b7280;
  line-height: 1.5;
}

.action-section {
  display: flex;
  gap: 12px;
}

.action-section .el-button {
  flex: 1;
  height: 44px;
  font-weight: 500;
}

/* 工作流卡片 */
.workflow-card {
  margin-bottom: 24px;
  border-radius: 12px;
  border: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

:deep(.el-step__title) {
  font-size: 13px;
  font-weight: 500;
}

:deep(.el-step__description) {
  font-size: 12px;
}

:deep(.el-step__head.is-process) {
  color: #10b981;
  border-color: #10b981;
}

:deep(.el-step__title.is-process) {
  color: #10b981;
  font-weight: 600;
}

.date-tip {
  margin-top: 10px;
  font-size: 12px;
  color: #9ca3af;
  display: flex;
  align-items: center;
}

.picker-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

.picker-actions .el-button {
  font-weight: 500;
}
</style>
