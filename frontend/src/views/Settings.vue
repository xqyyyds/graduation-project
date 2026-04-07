<template>
  <div class="settings-container">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">系统设置</h1>
        <div class="breadcrumb">
          <span class="root">首页</span> / <span class="current">系统设置</span>
        </div>
      </div>
      <p class="page-desc">System Environment & Intelligence Configuration</p>
    </div>

    <div class="grid-layout">
      <el-card class="settings-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="header-title">
              <div class="icon-box green">
                <el-icon><Connection /></el-icon>
              </div>
              后端连接配置
            </span>
          </div>
        </template>

        <el-form label-position="top" :model="backendForm" class="content-form">
          <el-form-item label="后端服务地址 (API URL)">
            <el-input v-model="backendForm.url" placeholder="http://localhost:8000">
              <template #prefix><el-icon><Link /></el-icon></template>
            </el-input>
          </el-form-item>

          <el-form-item label="超时时间 (秒)">
            <el-input
              v-model.number="backendForm.timeout"
              type="number"
              min="1"
              placeholder="60"
            >
              <template #prefix><el-icon><Timer /></el-icon></template>
            </el-input>
          </el-form-item>

          <div class="form-tip">
            当前日志连接会自动跟随后端地址派生，无需单独填写 WebSocket 地址。
          </div>

          <div class="connection-preview">
            <div class="preview-row">
              <span class="preview-label">当前 API 地址</span>
              <code>{{ normalizedBackendUrl }}</code>
            </div>
            <div class="preview-row">
              <span class="preview-label">派生日志地址</span>
              <code>{{ websocketPreview }}</code>
            </div>
          </div>

          <div v-if="backendDirty" class="masked-tip">
            你已修改连接设置但尚未保存。测试连接会使用当前表单值；页面里的 API 请求和日志重连将在保存后统一切换。
          </div>

          <div class="form-actions">
            <el-button type="primary" @click="saveBackendSettings">
              保存设置
            </el-button>
            <el-button plain :loading="testingConnection" @click="testConnection">
              测试连接
            </el-button>
          </div>

          <transition name="fade">
            <el-alert
              v-if="connectionResult"
              :type="connectionResult.status === 'ok' ? 'success' : 'error'"
              :title="connectionResult.message"
              :description="connectionResult.description"
              show-icon
              style="margin-top: 12px"
            />
          </transition>
        </el-form>
      </el-card>

      <el-card class="settings-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="header-title">
              <div class="icon-box purple">
                <el-icon><Brush /></el-icon>
              </div>
              界面偏好
            </span>
          </div>
        </template>

        <div class="pref-list">
          <div class="pref-item">
            <span>侧边栏默认折叠</span>
            <el-switch v-model="sidebarFolded" />
          </div>
          <div class="pref-divider"></div>
          <div class="pref-item">
            <span>暗色主题 (Dark Mode)</span>
            <el-switch v-model="isDark" />
          </div>
          <div class="pref-divider"></div>
          <div class="pref-item">
            <span>主题色调 (Theme)</span>
            <div class="theme-switcher">
              <div
                v-for="color in themeColors"
                :key="color.key"
                class="theme-opt"
                :class="[color.key, { active: activeTheme === color.key }]"
                @click="setTheme(color.key)"
              ></div>
            </div>
          </div>
        </div>
      </el-card>

      <el-card class="settings-card llm-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="header-title">
              <div class="icon-box orange">
                <el-icon><Cpu /></el-icon>
              </div>
              大模型配置 (LLM)
            </span>
          </div>
        </template>

        <div class="llm-groups">
          <section class="llm-group">
            <div class="llm-group-header">
              <div>
                <h3>主模型配置</h3>
                <p>当前系统处于单模型模式，所有链路统一复用这一套模型配置。</p>
              </div>
              <el-tag type="success" effect="plain">单模型模式</el-tag>
            </div>

            <el-form label-position="top" :model="llmForm.main" class="content-form">
              <el-form-item label="模型名称 (Model Name)">
                <el-input v-model="llmForm.main.model" placeholder="例如 deepseek-v3-2-251201">
                  <template #prefix><el-icon><Box /></el-icon></template>
                </el-input>
              </el-form-item>

              <el-form-item label="API Base URL">
                <el-input
                  v-model="llmForm.main.baseUrl"
                  placeholder="https://ark.cn-beijing.volces.com/api/v3"
                >
                  <template #prefix><el-icon><Link /></el-icon></template>
                </el-input>
              </el-form-item>

              <el-form-item label="API Key">
                <el-input
                  v-model="llmForm.main.apiKey"
                  type="password"
                  show-password
                  placeholder="输入完整密钥后保存"
                >
                  <template #prefix><el-icon><Key /></el-icon></template>
                </el-input>
                <div v-if="showMaskedHint(llmForm.main.apiKey)" class="masked-tip">
                  当前显示为已保存的掩码密钥；如需替换或测试，请重新输入完整密钥。
                </div>
              </el-form-item>

              <div class="form-actions">
                <el-button type="primary" @click="saveLLMConfig">
                  保存配置
                </el-button>
                <el-button
                  plain
                  :loading="testingLLM"
                  @click="testLLM"
                >
                  测试主模型
                </el-button>
              </div>
            </el-form>
          </section>
        </div>

        <el-alert
          class="runtime-alert"
          type="info"
          show-icon
          :closable="false"
          title="当前配置为运行时保存"
          description="当前为单模型模式：保存后会立即作用于当前服务进程；若后端重启，需重新加载或另做持久化。"
        />

        <transition name="fade">
          <el-alert
            v-if="llmTestResult"
            :type="llmTestResult.status === 'ok' ? 'success' : 'error'"
            :title="llmTestResult.message"
            show-icon
            style="margin-top: 12px"
          />
        </transition>
      </el-card>

      <el-card class="settings-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="header-title">
              <div class="icon-box blue">
                <el-icon><Search /></el-icon>
              </div>
              联网搜索配置
            </span>
          </div>
        </template>

        <section class="llm-group">
          <div class="llm-group-header">
            <div>
              <h3>Tavily 搜索</h3>
              <p>用于深读补背景、历史同期搜索和未来趋势信号检索。</p>
            </div>
            <el-tag type="info" effect="plain">运行时配置</el-tag>
          </div>

          <el-form label-position="top" :model="searchForm" class="content-form">
            <el-form-item label="Tavily API Key">
              <el-input
                v-model="searchForm.tavilyApiKey"
                type="password"
                show-password
                placeholder="输入完整 Tavily API Key"
              >
                <template #prefix><el-icon><Key /></el-icon></template>
              </el-input>
              <div v-if="showMaskedHint(searchForm.tavilyApiKey)" class="masked-tip">
                当前显示为已保存的掩码密钥；如需替换或测试，请重新输入完整密钥。
              </div>
            </el-form-item>

            <div class="form-actions">
              <el-button type="primary" @click="saveSearchConfig">
                保存配置
              </el-button>
              <el-button plain :loading="testingSearch" @click="testSearch">
                测试 Tavily
              </el-button>
            </div>
          </el-form>
        </section>

        <el-alert
          class="runtime-alert"
          type="info"
          show-icon
          :closable="false"
          title="联网搜索配置为运行时保存"
          description="保存后会立即作用于当前服务进程；若后端重启，需重新加载或另做持久化。"
        />

        <transition name="fade">
          <el-alert
            v-if="searchTestResult"
            :type="searchTestResult.status === 'ok' ? 'success' : 'error'"
            :title="searchTestResult.message"
            show-icon
            style="margin-top: 12px"
          />
        </transition>
      </el-card>

      <el-card class="about-card" shadow="never">
        <div class="about-content">
          <div class="logo-circle">
            <el-icon :size="40"><DataAnalysis /></el-icon>
          </div>
          <h3>舆情研判平台 Pro</h3>
          <div class="version">Version 1.0.0 (Build 20260109)</div>

          <div class="desc-container">
            <p class="desc">
              基于 LangGraph 多智能体协作架构，集成热点梳理、风险审查、趋势预警与多格式报告导出的舆情分析系统。
            </p>
          </div>

          <div class="tech-badges">
            <span class="badge">Vue 3</span>
            <span class="badge">FastAPI</span>
            <span class="badge">LangGraph</span>
          </div>

          <div class="copyright">© 2026 Intelligence Systems</div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { reactive, onMounted, computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { useAppStore } from "../stores/app";
import api, {
  deriveWsUrl,
  getBaseUrl,
  notifySettingsUpdated,
} from "../api";
import {
  Connection,
  Link,
  Brush,
  Cpu,
  Box,
  Key,
  DataAnalysis,
  Timer,
  Search,
} from "@element-plus/icons-vue";

const store = useAppStore();

const backendForm = reactive({ url: "http://localhost:8000", timeout: 60 });
const llmForm = reactive({
  main: {
    model: "",
    baseUrl: "",
    apiKey: "",
  },
});
const searchForm = reactive({
  tavilyApiKey: "",
});

const testingConnection = ref(false);
const connectionResult = ref(null);
const testingLLM = ref(false);
const llmTestResult = ref(null);
const testingSearch = ref(false);
const searchTestResult = ref(null);

const themeColors = [
  { key: "blue", val: "#3b82f6" },
  { key: "green", val: "#10b981" },
  { key: "purple", val: "#8b5cf6" },
];

const sidebarFolded = computed({
  get: () => store.sidebarCollapsed,
  set: (val) => {
    store.sidebarCollapsed = val;
  },
});

const isDark = computed({
  get: () => store.themeConfig.isDark,
  set: (val) => {
    store.toggleDarkMode(val);
  },
});

const activeTheme = computed(() => {
  const match = themeColors.find(
    (c) =>
      c.val.toLowerCase() ===
      (store.themeConfig.primaryColor || "").toLowerCase()
  );
  return match ? match.key : "blue";
});

const normalizedBackendUrl = computed(() => {
  const value = (backendForm.url || "").trim();
  return value ? value.replace(/\/$/, "") : getBaseUrl();
});

const websocketPreview = computed(() => deriveWsUrl(normalizedBackendUrl.value));
const backendDirty = computed(
  () =>
    normalizedBackendUrl.value !== getBaseUrl() ||
    Number(backendForm.timeout || 60) !== Number(store.settings.timeout || 60)
);

const showMaskedHint = (value) => value && value.includes("*");

const setTheme = (key) => {
  const colorObj = themeColors.find((c) => c.key === key);
  if (colorObj) {
    store.setThemeColor(colorObj.val);
    ElMessage.success(
      `主题色已切换为: ${
        key === "blue" ? "深海蓝" : key === "green" ? "黑客绿" : "暗夜紫"
      }`
    );
  }
};

const loadBackendSettings = () => {
  backendForm.url = store.settings.apiUrl || "http://localhost:8000";
  backendForm.timeout = Number(store.settings.timeout || 60);
};

const saveBackendSettings = () => {
  const normalizedUrl = normalizedBackendUrl.value;
  const normalizedTimeout = Number(backendForm.timeout) || 60;
  store.updateSettings({
    apiUrl: normalizedUrl || "http://localhost:8000",
    timeout: normalizedTimeout,
  });
  notifySettingsUpdated({
    apiUrl: normalizedUrl || "http://localhost:8000",
    timeout: normalizedTimeout,
  });
  connectionResult.value = null;
  ElMessage.success("后端连接设置已保存");
};

const testConnection = async () => {
  testingConnection.value = true;
  connectionResult.value = null;
  try {
    const result = await api.testBackendConnection({
      url: backendForm.url,
      timeout: backendForm.timeout,
    });
    connectionResult.value = {
      status: "ok",
      message: "后端连接成功",
      description: `延迟 ${result.latency}ms，时间戳 ${result.timestamp}`,
    };
    ElMessage.success(`后端服务连接成功 (${result.latency}ms)`);
  } catch (error) {
    const message =
      error?.response?.data?.detail ||
      error?.message ||
      "无法连接到指定后端服务";
    connectionResult.value = {
      status: "error",
      message: "后端连接失败",
      description: message,
    };
    ElMessage.error("后端连接失败：" + message);
  } finally {
    testingConnection.value = false;
  }
};

const loadLLMSettings = async () => {
  try {
    const data = await api.getLLMSettings();
    if (!data) return;
    llmForm.main.model = data.main?.model || "";
    llmForm.main.baseUrl = data.main?.base_url || "";
    llmForm.main.apiKey = data.main?.api_key || "";
  } catch (error) {
    console.error("加载 LLM 设置失败", error);
  }
};

const loadSearchSettings = async () => {
  try {
    const data = await api.getSearchSettings();
    searchForm.tavilyApiKey = data?.tavily_api_key || "";
  } catch (error) {
    console.error("加载联网搜索设置失败", error);
  }
};

const saveLLMConfig = async () => {
  try {
    const res = await api.updateLLMSettings({
      main: {
        model: llmForm.main.model,
        base_url: llmForm.main.baseUrl,
        api_key: llmForm.main.apiKey,
      },
    });
    ElMessage.success(res?.message || "LLM 配置已保存");
    await loadLLMSettings();
  } catch (error) {
    ElMessage.error("保存失败：" + (error?.message || error));
  }
};

const testLLM = async () => {
  testingLLM.value = true;
  llmTestResult.value = null;

  const payload = {
    model: llmForm.main.model || undefined,
    base_url: llmForm.main.baseUrl || undefined,
  };

  if (llmForm.main.apiKey && !llmForm.main.apiKey.includes("*")) {
    payload.api_key = llmForm.main.apiKey;
  }

  try {
    const res = await api.testLLMConnection(payload);
    llmTestResult.value = res;
    if (res?.status === "ok") {
      ElMessage.success("主模型连通性测试成功");
    }
  } catch (error) {
    llmTestResult.value = {
      status: "error",
      message: error?.message || String(error),
    };
    ElMessage.error("主模型连通性测试失败");
  } finally {
    testingLLM.value = false;
  }
};

const saveSearchConfig = async () => {
  try {
    const res = await api.updateSearchSettings({
      tavily_api_key: searchForm.tavilyApiKey,
    });
    ElMessage.success(res?.message || "联网搜索配置已保存");
    await loadSearchSettings();
  } catch (error) {
    ElMessage.error("保存失败：" + (error?.message || error));
  }
};

const testSearch = async () => {
  testingSearch.value = true;
  searchTestResult.value = null;
  const payload = {};
  if (searchForm.tavilyApiKey && !searchForm.tavilyApiKey.includes("*")) {
    payload.tavily_api_key = searchForm.tavilyApiKey;
  }

  try {
    const res = await api.testSearchConnection(payload);
    searchTestResult.value = res;
    if (res?.status === "ok") {
      ElMessage.success("Tavily 连通性测试成功");
    } else {
      ElMessage.error(res?.message || "Tavily 连通性测试失败");
    }
  } catch (error) {
    searchTestResult.value = {
      status: "error",
      message: error?.message || String(error),
    };
    ElMessage.error("Tavily 连通性测试失败");
  } finally {
    testingSearch.value = false;
  }
};

onMounted(async () => {
  loadBackendSettings();
  await loadLLMSettings();
  await loadSearchSettings();
});
</script>

<style scoped>
.settings-container {
  max-width: 1600px;
  margin: 0 auto;
  padding-bottom: 40px;
}
.page-header {
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}
.page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.header-content {
  display: flex;
  align-items: center;
  gap: 16px;
}
.breadcrumb {
  font-size: 14px;
  color: var(--text-secondary);
  background: var(--bg-card);
  padding: 4px 12px;
  border-radius: 12px;
  border: 1px solid var(--border-color);
}
.breadcrumb .current {
  color: var(--primary-color);
  font-weight: 600;
}
.page-desc {
  color: var(--text-muted);
  font-size: 14px;
  margin-top: 8px;
  opacity: 0.8;
}

.grid-layout {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 24px;
  align-items: stretch;
}
@media (max-width: 992px) {
  .grid-layout {
    grid-template-columns: 1fr;
  }
}

.settings-card,
.about-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}
:deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 24px;
}

.icon-box {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  margin-right: 10px;
}
.icon-box.green {
  background: #10b981;
  box-shadow: 0 4px 10px rgba(16, 185, 129, 0.2);
}
.icon-box.purple {
  background: #8b5cf6;
  box-shadow: 0 4px 10px rgba(139, 92, 246, 0.2);
}
.icon-box.orange {
  background: #f59e0b;
  box-shadow: 0 4px 10px rgba(245, 158, 11, 0.2);
}
.icon-box.blue {
  background: #3b82f6;
  box-shadow: 0 4px 10px rgba(59, 130, 246, 0.2);
}
.card-header {
  display: flex;
  align-items: center;
}
.header-title {
  display: flex;
  align-items: center;
  font-weight: 600;
  font-size: 16px;
  color: var(--text-primary);
}
.content-form {
  display: flex;
  flex-direction: column;
  flex: 1;
}
.form-actions {
  margin-top: auto;
  padding-top: 16px;
  display: flex;
  gap: 12px;
}
.form-tip,
.masked-tip {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.connection-preview {
  margin-top: 14px;
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--bg-body);
  border: 1px solid var(--border-color);
}

.preview-row {
  display: grid;
  gap: 6px;
}

.preview-row + .preview-row {
  margin-top: 10px;
}

.preview-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
}

.connection-preview code {
  display: block;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  font-family: "JetBrains Mono", "Fira Code", Consolas, monospace;
  color: var(--text-primary);
}

.pref-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.pref-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  font-size: 14px;
  color: var(--text-primary);
}
.pref-divider {
  height: 1px;
  background: var(--border-color);
  margin: 12px 0;
  opacity: 0.5;
}
.theme-switcher {
  display: flex;
  gap: 12px;
}
.theme-opt {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s;
}
.theme-opt.blue {
  background: #3b82f6;
}
.theme-opt.green {
  background: #10b981;
}
.theme-opt.purple {
  background: #8b5cf6;
}
.theme-opt.active {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 4px rgba(0, 0, 0, 0.1);
}

.llm-card :deep(.el-card__body) {
  gap: 16px;
}
.llm-groups {
  display: grid;
  gap: 16px;
}
.llm-group {
  border: 1px solid var(--border-color);
  border-radius: 14px;
  padding: 18px 18px 8px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), transparent);
}
.llm-group-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
}
.llm-group-header h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 16px;
}
.llm-group-header p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}
.runtime-alert {
  margin-top: 8px;
}

.about-card {
  background: var(
    --about-bg,
    linear-gradient(145deg, #f8fafc 0%, #ffffff 100%)
  );
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  transition: background 0.3s, color 0.3s;
}
.about-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  width: 100%;
}
.about-content h3 {
  font-size: 22px;
  margin: 0 0 8px 0;
  font-weight: 700;
  color: var(--text-primary);
}
.logo-circle {
  width: 80px;
  height: 80px;
  background: var(--about-logo-bg, rgba(37, 99, 235, 0.05));
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
  border: 1px solid var(--border-color);
  box-shadow: 0 10px 20px rgba(0, 0, 0, 0.05);
  color: var(--primary-color);
}
.version {
  color: var(--text-secondary);
  font-size: 12px;
  margin-bottom: 24px;
  background: var(--bg-body);
  padding: 4px 12px;
  border-radius: 12px;
}
.desc {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
  max-width: 90%;
  margin: 0 auto 32px auto;
}
.tech-badges {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  justify-content: center;
}
.badge {
  background: var(--bg-body);
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
}
.copyright {
  margin-top: auto;
  font-size: 12px;
  color: var(--text-muted);
}

:root {
  --about-bg: linear-gradient(145deg, #ffffff 0%, #f1f5f9 100%);
  --about-logo-bg: rgba(37, 99, 235, 0.08);
}
html.dark {
  --about-bg: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
  --about-logo-bg: rgba(255, 255, 255, 0.05);
}
html.dark .logo-circle {
  color: #ffffff;
}
</style>
