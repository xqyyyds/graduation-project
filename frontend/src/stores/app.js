import { defineStore } from "pinia";
import { ref, computed, watch } from "vue";
import api from "../api";

// --- 辅助函数：持久化存储 ---
const loadState = (key, defaultValue) => {
  try {
    const saved = localStorage.getItem(key);
    return saved ? JSON.parse(saved) : defaultValue;
  } catch {
    return defaultValue;
  }
};

const saveState = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    console.warn("状态持久化失败:", e);
  }
};

export const useAppStore = defineStore("app", () => {
  // ==========================================
  // 1. 核心状态 (State)
  // ==========================================
  const sidebarCollapsed = ref(loadState("sidebarCollapsed", false)); 
  const currentTask = ref(loadState("currentTask", null));            
  const taskPollingInterval = ref(null);                              

  // 🔥 新增：主题配置状态
  const themeConfig = ref(loadState("themeConfig", {
    primaryColor: "#3b82f6", // 默认主题色
    isDark: false,           // 默认浅色模式
  }));

  // 系统设置
  const settings = ref(
    loadState("appSettings", {
      apiUrl: "http://localhost:8000",
      timeout: 60,
      listDensity: "default",
    })
  );

  // 仪表盘真实数据
  const dashboardStats = ref({
    total_reports: 0,
    reports_today: 0,
    reports_this_week: 0,
    category_distribution: {}, 
    recent_reports: [],        
  });

  // 报告列表数据
  const reports = ref([]);
  const selectedCategory = ref("全部");

  // ==========================================
  // 2. 静态配置 (Config)
  // ==========================================
  const categories = ref(["综合", "社会", "高校", "生活", "科技", "政治", "其他"]);
  const forecastRanges = ref([
    { value: "1w", label: "1周" },
    { value: "2w", label: "2周" },
    { value: "1m", label: "1个月" },
    { value: "2m", label: "2个月" },
  ]);

  // ==========================================
  // 3. 监听器 (Watchers)
  // ==========================================
  watch(sidebarCollapsed, (val) => saveState("sidebarCollapsed", val));
  watch(currentTask, (val) => saveState("currentTask", val), { deep: true });
  watch(settings, (val) => saveState("appSettings", val), { deep: true });
  // 🔥 监听主题变化并自动保存
  watch(themeConfig, (val) => saveState("themeConfig", val), { deep: true });

  // ==========================================
  // 4. 业务动作 (Actions)
  // ==========================================
  
  const toggleSidebar = () => {
    sidebarCollapsed.value = !sidebarCollapsed.value;
  };

  // 🔥 切换主题色
  const setThemeColor = (color) => {
    themeConfig.value.primaryColor = color;
  };

  // 🔥 切换暗黑模式
  const toggleDarkMode = (isDark) => {
    themeConfig.value.isDark = isDark;
  };

  const updateSettings = (newSettings) => {
    Object.assign(settings.value, newSettings);
  };

  const fetchDashboardStats = async () => {
    try {
      const data = await api.getDashboardStats();
      dashboardStats.value = data;
    } catch (error) {
      console.error("Dashboard 数据获取失败:", error);
    }
  };

  const fetchReports = async (category = null) => {
    try {
      const data = await api.getReports(category);
      reports.value = data;
    } catch (error) {
      console.error("报告列表获取失败:", error);
    }
  };

  const createTask = async (params) => {
    try {
      const data = await api.createTask(params);
      currentTask.value = data;
      startTaskPolling(data.task_id);
      return data;
    } catch (error) {
      console.error("任务创建失败:", error);
      throw error;
    }
  };

  const startTaskPolling = (taskId) => {
    if (taskPollingInterval.value) {
      clearInterval(taskPollingInterval.value);
    }
    fetchTaskStatus(taskId);
    taskPollingInterval.value = setInterval(async () => {
      await fetchTaskStatus(taskId);
    }, 2000);
  };

  const fetchTaskStatus = async (taskId) => {
    try {
      const status = await api.getTaskStatus(taskId);
      currentTask.value = status;

      if (status.status === "completed" || status.status === "failed") {
        stopTaskPolling();
        await fetchDashboardStats(); 
        await fetchReports();        
      }
    } catch (error) {
      console.error("轮询状态失败:", error);
      if (error.response?.status === 404) {
        stopTaskPolling();
        if (currentTask.value) {
          currentTask.value = {
            ...currentTask.value,
            status: "unknown",
            message: "任务连接中断 (服务端可能已重启)",
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

  const restoreTaskPolling = () => {
    if (currentTask.value?.status === "running" && currentTask.value?.task_id) {
      startTaskPolling(currentTask.value.task_id);
    }
  };

  const clearCurrentTask = () => {
    stopTaskPolling();
    currentTask.value = null;
  };

  return {
    sidebarCollapsed,
    currentTask,
    dashboardStats,
    reports,
    selectedCategory,
    categories,
    forecastRanges,
    settings,
    themeConfig, // 🔥 导出主题配置
    isTaskRunning: computed(() => currentTask.value?.status === "running"),
    toggleSidebar,
    updateSettings,
    fetchDashboardStats,
    fetchReports,
    createTask,
    startTaskPolling,
    stopTaskPolling,
    restoreTaskPolling,
    clearCurrentTask,
    setThemeColor, // 🔥 导出设置颜色方法
    toggleDarkMode // 🔥 导出设置暗黑方法
  };
});