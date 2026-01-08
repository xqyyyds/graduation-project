import { defineStore } from "pinia";
import { ref, computed, watch } from "vue";
import api from "../api";

// 从 localStorage 恢复状态
const loadState = (key, defaultValue) => {
  try {
    const saved = localStorage.getItem(key);
    return saved ? JSON.parse(saved) : defaultValue;
  } catch {
    return defaultValue;
  }
};

// 保存状态到 localStorage
const saveState = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    console.warn("保存状态失败:", e);
  }
};

export const useAppStore = defineStore("app", () => {
  // 状态（从 localStorage 恢复）
  const sidebarCollapsed = ref(loadState("sidebarCollapsed", false));
  const currentTask = ref(loadState("currentTask", null));
  const taskPollingInterval = ref(null);

  // 系统设置（持久化）
  const settings = ref(
    loadState("appSettings", {
      apiUrl: "http://localhost:8000",
      timeout: 60,
      listDensity: "default",
    })
  );

  // 仪表盘数据
  const dashboardStats = ref({
    total_reports: 0,
    reports_today: 0,
    reports_this_week: 0,
    category_distribution: {},
    recent_reports: [],
  });

  // 报告列表
  const reports = ref([]);
  const selectedCategory = ref("全部");

  // 配置选项
  const categories = ref([
    "综合",
    "社会",
    "高校",
    "生活",
    "科技",
    "政治",
    "其他",
  ]);
  const forecastRanges = ref([
    { value: "1w", label: "1周" },
    { value: "2w", label: "2周" },
    { value: "1m", label: "1个月" },
    { value: "2m", label: "2个月" },
  ]);

  // 监听状态变化并持久化
  watch(sidebarCollapsed, (val) => saveState("sidebarCollapsed", val));
  watch(currentTask, (val) => saveState("currentTask", val), { deep: true });
  watch(settings, (val) => saveState("appSettings", val), { deep: true });

  // Actions
  const toggleSidebar = () => {
    sidebarCollapsed.value = !sidebarCollapsed.value;
  };

  const updateSettings = (newSettings) => {
    Object.assign(settings.value, newSettings);
  };

  const fetchDashboardStats = async () => {
    try {
      const data = await api.getDashboardStats();
      dashboardStats.value = data;
    } catch (error) {
      console.error("获取仪表盘数据失败:", error);
    }
  };

  const fetchReports = async (category = null) => {
    try {
      const data = await api.getReports(category);
      reports.value = data;
    } catch (error) {
      console.error("获取报告列表失败:", error);
    }
  };

  const createTask = async (params) => {
    try {
      const data = await api.createTask(params);
      currentTask.value = data;
      startTaskPolling(data.task_id);
      return data;
    } catch (error) {
      console.error("创建任务失败:", error);
      throw error;
    }
  };

  const startTaskPolling = (taskId) => {
    if (taskPollingInterval.value) {
      clearInterval(taskPollingInterval.value);
    }

    // 立即获取一次状态
    fetchTaskStatus(taskId);

    taskPollingInterval.value = setInterval(async () => {
      await fetchTaskStatus(taskId);
    }, 2000); // 缩短轮询间隔到 2 秒
  };

  const fetchTaskStatus = async (taskId) => {
    try {
      const status = await api.getTaskStatus(taskId);
      currentTask.value = status;

      if (status.status === "completed" || status.status === "failed") {
        stopTaskPolling();
        // 刷新数据
        await fetchDashboardStats();
        await fetchReports();
      }
    } catch (error) {
      console.error("获取任务状态失败:", error);
      // 如果任务不存在（后端重启等原因），清除本地任务状态
      if (error.response?.status === 404) {
        console.warn("任务不存在，可能后端已重启，清除本地状态");
        stopTaskPolling();
        // 保留任务信息但标记为未知状态
        if (currentTask.value) {
          currentTask.value = {
            ...currentTask.value,
            status: "unknown",
            message: "任务状态丢失（后端可能已重启），请重新创建任务",
          };
        }
      }
    }
  };

  const stopTaskPolling = () => {
    if (taskPollingInterval.value) {
      clearInterval(taskPollingInterval.value);
      taskPollingInterval.value = null;
    }
  };

  // 页面加载时恢复轮询（如果有运行中的任务）
  const restoreTaskPolling = () => {
    if (currentTask.value?.status === "running" && currentTask.value?.task_id) {
      startTaskPolling(currentTask.value.task_id);
    }
  };

  // 清除当前任务
  const clearCurrentTask = () => {
    stopTaskPolling();
    currentTask.value = null;
  };

  return {
    // 状态
    sidebarCollapsed,
    currentTask,
    dashboardStats,
    reports,
    selectedCategory,
    categories,
    forecastRanges,
    settings,

    // 计算属性
    isTaskRunning: computed(() => currentTask.value?.status === "running"),

    // Actions
    toggleSidebar,
    updateSettings,
    fetchDashboardStats,
    fetchReports,
    createTask,
    startTaskPolling,
    stopTaskPolling,
    restoreTaskPolling,
    clearCurrentTask,
  };
});
