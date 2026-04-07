import axios from "axios";

export const SETTINGS_UPDATED_EVENT = "app-settings-updated";

// 1. 创建实例 (不再写死 baseURL，而在拦截器中动态处理)
const instance = axios.create({
  timeout: 60000,
});

export const getStoredSettings = () => {
  try {
    const settings = localStorage.getItem("appSettings");
    if (settings) {
      return JSON.parse(settings);
    }
  } catch (e) {
    console.warn("读取应用设置失败，使用默认值");
  }
  return {
    apiUrl: "http://localhost:8000",
    timeout: 60,
    listDensity: "default",
  };
};

export const normalizeBaseUrl = (value) =>
  (value || "http://localhost:8000").trim().replace(/\/$/, "");

export const getBaseUrl = () => {
  const { apiUrl } = getStoredSettings();
  return normalizeBaseUrl(apiUrl);
};

export const getTimeout = () => {
  const { timeout } = getStoredSettings();
  const parsedTimeout = Number(timeout);
  return Number.isFinite(parsedTimeout) && parsedTimeout > 0 ? parsedTimeout : 60;
};

export const deriveWsUrl = (baseUrl) =>
  normalizeBaseUrl(baseUrl).replace(/^http/i, "ws") + "/ws/logs";

export const getWsUrl = () => deriveWsUrl(getBaseUrl());

export const notifySettingsUpdated = (nextSettings = {}) => {
  window.dispatchEvent(
    new CustomEvent(SETTINGS_UPDATED_EVENT, {
      detail: {
        ...getStoredSettings(),
        ...nextSettings,
      },
    })
  );
};

// 2. 请求拦截器：动态注入 Base URL
instance.interceptors.request.use(
  (config) => {
    config.baseURL = getBaseUrl();
    config.timeout = getTimeout() * 1000;
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
  async testBackendConnection(payload = {}) {
    const startedAt = performance.now();
    const baseUrl = normalizeBaseUrl(payload.url || getBaseUrl());
    const timeout = Number(payload.timeout || getTimeout()) * 1000;
    const response = await axios.get(`${baseUrl}/api/health`, { timeout });
    return {
      ...response.data,
      latency: Math.round(performance.now() - startedAt),
    };
  },

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

  getReportJson(filename) {
    return instance.get(`/api/reports/${encodeURIComponent(filename)}/json`);
  },

  getReportArtifacts(filename) {
    return instance.get(`/api/reports/${encodeURIComponent(filename)}/artifacts`);
  },

  // 修正：下载链接也需要动态拼接 Base URL
  downloadReport(filename, format = "md") {
    const baseUrl = getBaseUrl();
    return `${baseUrl}/api/reports/${encodeURIComponent(
      filename
    )}/download?format=${encodeURIComponent(format)}`;
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

  getSearchSettings() {
    return instance.get("/api/settings/search");
  },

  updateSearchSettings(settings) {
    return instance.post("/api/settings/search", settings);
  },

  testSearchConnection(payload = {}) {
    return instance.post("/api/settings/search/test", payload);
  },
};
