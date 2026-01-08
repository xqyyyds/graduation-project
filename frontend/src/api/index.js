import axios from "axios";

const instance = axios.create({
  baseURL: "http://localhost:8000",
  timeout: 60000,
});

// 请求拦截器
instance.interceptors.request.use(
  (config) => {
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
instance.interceptors.response.use(
  (response) => {
    return response.data;
  },
  (error) => {
    console.error("API Error:", error);
    return Promise.reject(error);
  }
);

export default {
  // 仪表盘
  getDashboardStats() {
    return instance.get("/api/dashboard/stats");
  },

  // 任务
  createTask(params) {
    return instance.post("/api/tasks", params);
  },

  getTaskStatus(taskId) {
    return instance.get(`/api/tasks/${taskId}`);
  },

  // 报告
  getReports(category = null) {
    const params = category && category !== "全部" ? { category } : {};
    return instance.get("/api/reports", { params });
  },

  getReportContent(filename) {
    return instance.get(`/api/reports/${encodeURIComponent(filename)}`);
  },

  downloadReport(filename) {
    return `http://localhost:8000/api/reports/${encodeURIComponent(
      filename
    )}/download`;
  },

  deleteReport(filename) {
    return instance.delete(`/api/reports/${encodeURIComponent(filename)}`);
  },

  // 配置
  getCategories() {
    return instance.get("/api/categories");
  },

  getForecastRanges() {
    return instance.get("/api/forecast-ranges");
  },

  // LLM 设置
  getLLMSettings() {
    return instance.get("/api/settings/llm");
  },

  updateLLMSettings(settings) {
    return instance.post("/api/settings/llm", settings);
  },

  testLLMConnection() {
    return instance.post("/api/settings/llm/test");
  },
};
