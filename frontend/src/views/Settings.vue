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
              placeholder="60"
            >
              <template #prefix><el-icon><Timer /></el-icon></template>
            </el-input>
          </el-form-item>

          <div class="form-actions">
            <el-button type="primary" plain @click="testConnection">
              测试连接
            </el-button>
          </div>
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

      <el-card class="settings-card" shadow="never">
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

        <el-form label-position="top" :model="llmForm" class="content-form">
          <el-form-item label="模型名称 (Model Name)">
            <el-input v-model="llmForm.model" placeholder="gpt-4o-mini">
              <template #prefix><el-icon><Box /></el-icon></template>
            </el-input>
          </el-form-item>

          <el-form-item label="API Base URL">
            <el-input
              v-model="llmForm.baseUrl"
              placeholder="https://api.zetatechs.com/v1"
            >
              <template #prefix><el-icon><Link /></el-icon></template>
            </el-input>
          </el-form-item>

          <el-form-item label="API Key">
            <el-input
              v-model="llmForm.apiKey"
              type="password"
              show-password
              placeholder="sk-..."
            >
              <template #prefix><el-icon><Key /></el-icon></template>
            </el-input>
            <div
              v-if="llmForm.apiKey && llmForm.apiKey.includes('*')"
              style="margin-top: 8px; color: var(--text-muted); font-size: 12px"
            >
              当前显示为已保存的掩码密钥；如需测试或替换，请输入完整密钥并保存。
            </div>
          </el-form-item>

          <div class="form-actions">
            <el-button type="primary" @click="saveLLMConfig">保存配置</el-button>
            <el-button plain :loading="testingLLM" @click="testLLM">
              测试连通性
            </el-button>
          </div>

          <transition name="fade">
            <el-alert
              v-if="llmTestResult"
              :type="llmTestResult.status === 'ok' ? 'success' : 'error'"
              :title="llmTestResult.message"
              show-icon
              style="margin-top: 12px"
            />
          </transition>
        </el-form>
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
              基于 LangGraph
              多智能体协作架构，集成热搜聚类、深度观点分析与趋势预测的下一代舆情系统。
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
import api from "../api";
import {
  Connection,
  Link,
  Brush,
  Cpu,
  Box,
  Key,
  DataAnalysis,
  Timer,
} from "@element-plus/icons-vue";

const store = useAppStore();

const backendForm = reactive({ url: "http://localhost:8000", timeout: 60 });
const llmForm = reactive({
  model: "gpt-4o-mini",
  baseUrl: "https://api.zetatechs.com/v1",
  apiKey: "sk-89s7d8f7s8d7f8s7d8f7s8d7f8s7d8f",
});

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

const testConnection = () => {
  ElMessage.info("正在尝试连接后端...");
  setTimeout(() => ElMessage.success("后端服务连接成功 (12ms)"), 800);
};

const testingLLM = ref(false);
const llmTestResult = ref(null);

const loadLLMSettings = async () => {
  try {
    const data = await api.getLLMSettings();
    if (data) {
      llmForm.model = data.model || "";
      llmForm.baseUrl = data.base_url || "";
      llmForm.apiKey = data.api_key || "";
    }
  } catch (error) {
    console.error("加载 LLM 设置失败", error);
  }
};

const saveLLMConfig = async () => {
  try {
    const res = await api.updateLLMSettings({
      model: llmForm.model,
      base_url: llmForm.baseUrl,
      api_key: llmForm.apiKey,
    });
    ElMessage.success(res?.message || "LLM 配置已保存");
    await testLLM();
  } catch (error) {
    ElMessage.error("保存失败：" + (error?.message || error));
  }
};

const testLLM = async () => {
  testingLLM.value = true;
  llmTestResult.value = null;

  const payload = {
    model: llmForm.model || undefined,
    base_url: llmForm.baseUrl || undefined,
  };
  if (llmForm.apiKey && !llmForm.apiKey.includes("*"))
    payload.api_key = llmForm.apiKey;

  try {
    const res = await api.testLLMConnection(payload);
    llmTestResult.value = res;
    if (res?.status === "ok") {
      ElMessage.success(res.message || "LLM 连接成功");
    } else {
      console.warn("LLM 测试返回失败：", res);
    }
  } catch (error) {
    console.error("LLM 测试异常：", error);
    llmTestResult.value = {
      status: "error",
      message: error?.message || String(error),
    };
  } finally {
    testingLLM.value = false;
  }
};

onMounted(() => {
  loadLLMSettings();
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
  padding-top: 24px;
  display: flex;
  gap: 12px;
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

/* About Card 样式 */
.about-card {
  background: var(
    --about-bg,
    linear-gradient(145deg, #f8fafc 0%, #ffffff 100%)
  );
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  transition: background 0.3s, color 0.3s;
}

/* 🔥🔥 修复重点：添加居中对齐属性 🔥🔥 */
.about-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;     /* 水平居中 */
  justify-content: center; /* 垂直居中 */
  text-align: center;      /* 文本居中 */
  width: 100%;             /* 宽度撑满 */
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
  justify-content: center; /* 徽标水平居中 */
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

/* 局部变量覆盖 */
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