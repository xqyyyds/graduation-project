import axios from "axios";

// 1. 创建实例 (不再写死 baseURL，而在拦截器中动态处理)
const instance = axios.create({
  timeout: 60000, // 60秒超时
});

// 辅助函数：获取当前配置的 Base URL
const getBaseUrl = () => {
  try {
    // 从 localStorage 读取我们在 Settings.vue/Store 中保存的配置
    const settings = localStorage.getItem("appSettings");
    if (settings) {
      const parsed = JSON.parse(settings);
      // 如果有配置且不为空，使用配置的地址；去掉末尾可能的斜杠
      if (parsed.apiUrl) return parsed.apiUrl.replace(/\/$/, "");
    }
  } catch (e) {
    console.warn("读取 API 配置失败，使用默认地址");
  }
  return "http://localhost:8000"; // 默认兜底地址
};

// 2. 请求拦截器：动态注入 Base URL
instance.interceptors.request.use(
  (config) => {
    // 每次请求前动态设置 baseURL
    config.baseURL = getBaseUrl();
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 3. 响应拦截器
instance.interceptors.response.use(
  (response) => {
    return response.data;
  },
  (error) => {
    console.error("API Error:", error);
    // 可以统一处理 HTTP 错误状态，比如 401 跳转登录等
    return Promise.reject(error);
  }
);

export default {
  // --- 仪表盘 ---
  getDashboardStats() {
    return instance.get("/api/dashboard/stats");
  },

  // --- 任务 ---
  createTask(params) {
    return instance.post("/api/tasks", params);
  },

  getTaskStatus(taskId) {
    return instance.get(`/api/tasks/${taskId}`);
  },

  // --- 报告 ---
  getReports(category = null) {
    const params = category && category !== "全部" ? { category } : {};
    return instance.get("/api/reports", { params });
  },

  getReportContent(filename) {
    return instance.get(`/api/reports/${encodeURIComponent(filename)}`);
  },

  // 修正：下载链接也需要动态拼接 Base URL
  downloadReport(filename) {
    const baseUrl = getBaseUrl();
    return `${baseUrl}/api/reports/${encodeURIComponent(filename)}/download`;
  },

  deleteReport(filename) {
    return instance.delete(`/api/reports/${encodeURIComponent(filename)}`);
  },

  // --- 配置 ---
  getCategories() {
    return instance.get("/api/categories");
  },

  getForecastRanges() {
    return instance.get("/api/forecast-ranges");
  },

  // --- LLM 设置 ---
  getLLMSettings() {
    return instance.get("/api/settings/llm");
  },

  updateLLMSettings(settings) {
    return instance.post("/api/settings/llm", settings);
  },

  testLLMConnection(payload = {}) {
    return instance.post("/api/settings/llm/test", payload);
  },
};
