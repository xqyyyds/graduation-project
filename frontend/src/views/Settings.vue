<template>
  <div class="settings-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">系统设置</h1>
      <p class="page-desc">配置系统参数和偏好设置</p>
    </div>

    <el-row :gutter="24">
      <el-col :xs="24" :lg="12">
        <!-- API 设置 -->
        <el-card class="settings-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20" color="#10b981"><Connection /></el-icon>
              <span>API 配置</span>
            </div>
          </template>

          <el-form label-position="top" class="settings-form">
            <el-form-item label="后端地址">
              <el-input
                v-model="localSettings.apiUrl"
                placeholder="http://localhost:8000"
                @change="saveSettings"
              >
                <template #prefix>
                  <el-icon><Link /></el-icon>
                </template>
              </el-input>
            </el-form-item>

            <el-form-item label="请求超时（秒）">
              <el-input-number
                v-model="localSettings.timeout"
                :min="10"
                :max="300"
                :step="10"
                style="width: 100%"
                @change="saveSettings"
              />
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                :loading="testing"
                @click="testConnection"
              >
                <el-icon><Connection /></el-icon>
                测试连接
              </el-button>
              <el-tag
                v-if="connectionStatus !== null"
                :type="connectionStatus ? 'success' : 'danger'"
                style="margin-left: 12px"
              >
                {{ connectionStatus ? "连接成功" : "连接失败" }}
              </el-tag>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- LLM 设置 -->
        <el-card class="settings-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20" color="#f59e0b"><Cpu /></el-icon>
              <span>LLM 模型配置</span>
            </div>
          </template>

          <el-form label-position="top" class="settings-form">
            <el-form-item label="模型名称">
              <el-input v-model="llmSettings.model" placeholder="gpt-4o-mini">
                <template #prefix>
                  <el-icon><Box /></el-icon>
                </template>
              </el-input>
              <div class="form-tip">
                支持 OpenAI 兼容的模型，如 gpt-4o-mini、glm-4-flash 等
              </div>
            </el-form-item>

            <el-form-item label="API Base URL">
              <el-input
                v-model="llmSettings.base_url"
                placeholder="https://api.openai.com/v1"
              >
                <template #prefix>
                  <el-icon><Link /></el-icon>
                </template>
              </el-input>
            </el-form-item>

            <el-form-item label="API Key">
              <el-input
                v-model="llmSettings.api_key"
                type="password"
                show-password
                placeholder="sk-..."
              >
                <template #prefix>
                  <el-icon><Key /></el-icon>
                </template>
              </el-input>
              <div class="form-tip">修改 API Key 后需要点击保存按钮</div>
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                @click="saveLLMSettings"
                :loading="savingLLM"
              >
                <el-icon><Check /></el-icon>
                保存设置
              </el-button>
              <el-button @click="testLLMConnection" :loading="testingLLM">
                <el-icon><Connection /></el-icon>
                测试连接
              </el-button>
            </el-form-item>

            <el-alert
              v-if="llmTestResult"
              :type="llmTestResult.status === 'ok' ? 'success' : 'error'"
              :title="llmTestResult.message"
              :closable="true"
              show-icon
              style="margin-top: 12px"
            />
          </el-form>
        </el-card>

        <!-- 外观设置 -->
        <el-card class="settings-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20" color="#8b5cf6"><Brush /></el-icon>
              <span>外观设置</span>
            </div>
          </template>

          <el-form label-position="top" class="settings-form">
            <el-form-item label="侧边栏状态">
              <el-switch
                v-model="sidebarCollapsed"
                active-text="折叠"
                inactive-text="展开"
                @change="toggleSidebar"
              />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <!-- 关于系统 -->
        <el-card class="settings-card about-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20" color="#3b82f6"><InfoFilled /></el-icon>
              <span>关于系统</span>
            </div>
          </template>

          <div class="about-section">
            <div class="about-logo">
              <div class="logo-wrapper">
                <el-icon :size="48" color="#10b981"><DataAnalysis /></el-icon>
              </div>
            </div>
            <h3 class="about-title">舆情研判平台</h3>
            <p class="about-version">版本 1.0.0</p>
            <p class="about-desc">
              基于 LangGraph 多智能体协作的社交媒体舆情分析系统，
              集成热搜聚类、观点分析、合规审查、趋势预测等功能。
            </p>

            <el-divider />

            <div class="tech-stack">
              <h4>技术栈</h4>
              <div class="tech-tags">
                <el-tag type="success">Vue 3</el-tag>
                <el-tag type="success">Element Plus</el-tag>
                <el-tag type="warning">FastAPI</el-tag>
                <el-tag type="warning">LangGraph</el-tag>
                <el-tag type="info">MongoDB</el-tag>
                <el-tag type="info">ChromaDB</el-tag>
              </div>
            </div>
          </div>
        </el-card>

        <!-- 系统功能介绍 -->
        <el-card class="settings-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20" color="#10b981"><Guide /></el-icon>
              <span>功能介绍</span>
            </div>
          </template>

          <div class="features-list">
            <div class="feature-item">
              <div
                class="feature-icon"
                style="
                  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                "
              >
                <el-icon><DataAnalysis /></el-icon>
              </div>
              <div class="feature-content">
                <h5>智能研判</h5>
                <p>多智能体协作，自动完成热搜聚类、观点分析、合规审查</p>
              </div>
            </div>

            <div class="feature-item">
              <div
                class="feature-icon"
                style="
                  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
                "
              >
                <el-icon><TrendCharts /></el-icon>
              </div>
              <div class="feature-content">
                <h5>趋势预测</h5>
                <p>基于历史数据，预测舆情走势和风险点</p>
              </div>
            </div>

            <div class="feature-item">
              <div
                class="feature-icon"
                style="
                  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
                "
              >
                <el-icon><Document /></el-icon>
              </div>
              <div class="feature-content">
                <h5>报告生成</h5>
                <p>一键生成专业研判报告，支持导出和分享</p>
              </div>
            </div>

            <div class="feature-item">
              <div
                class="feature-icon"
                style="
                  background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
                "
              >
                <el-icon><Timer /></el-icon>
              </div>
              <div class="feature-content">
                <h5>断点续传</h5>
                <p>任务中断后可继续执行，状态自动保存</p>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from "vue";
import { useAppStore } from "../stores/app";
import { ElMessage } from "element-plus";
import api from "../api";

const store = useAppStore();

const sidebarCollapsed = computed({
  get: () => store.sidebarCollapsed,
  set: () => {},
});

const toggleSidebar = () => {
  store.toggleSidebar();
};

// 本地设置（与 store 同步）
const localSettings = reactive({
  apiUrl: store.settings.apiUrl,
  timeout: store.settings.timeout,
});

// LLM 设置
const llmSettings = reactive({
  model: "",
  base_url: "",
  api_key: "",
});

// 状态
const testing = ref(false);
const connectionStatus = ref(null);
const testingLLM = ref(false);
const savingLLM = ref(false);
const llmTestResult = ref(null);

// 保存设置到 store
const saveSettings = () => {
  store.updateSettings(localSettings);
  ElMessage.success("设置已保存");
};

// 测试后端连接
const testConnection = async () => {
  testing.value = true;
  connectionStatus.value = null;

  const apiUrl = localSettings.apiUrl || "http://localhost:8000";

  try {
    // 使用实际输入的 URL 进行测试
    const response = await fetch(`${apiUrl}/api/health`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(5000), // 5秒超时
    });

    if (response.ok) {
      const data = await response.json();
      if (data.status === "ok") {
        connectionStatus.value = true;
        ElMessage.success("后端连接成功");
      } else {
        connectionStatus.value = false;
        ElMessage.error("后端响应异常");
      }
    } else {
      connectionStatus.value = false;
      ElMessage.error(`连接失败: HTTP ${response.status}`);
    }
  } catch (error) {
    connectionStatus.value = false;
    if (error.name === "TimeoutError") {
      ElMessage.error("连接超时，请检查地址是否正确");
    } else if (error.name === "TypeError") {
      ElMessage.error("无法连接到服务器，请检查地址和端口");
    } else {
      ElMessage.error("连接失败: " + (error.message || "网络错误"));
    }
  } finally {
    testing.value = false;
  }
};

// 加载 LLM 设置
const loadLLMSettings = async () => {
  try {
    const data = await api.getLLMSettings();
    llmSettings.model = data.model || "";
    llmSettings.base_url = data.base_url || "";
    llmSettings.api_key = data.api_key || "";
  } catch (error) {
    console.error("加载 LLM 设置失败:", error);
  }
};

// 保存 LLM 设置
const saveLLMSettings = async () => {
  savingLLM.value = true;
  try {
    await api.updateLLMSettings(llmSettings);
    ElMessage.success("LLM 设置已保存");
  } catch (error) {
    ElMessage.error("保存失败: " + (error.message || "未知错误"));
  } finally {
    savingLLM.value = false;
  }
};

// 测试 LLM 连接
const testLLMConnection = async () => {
  testingLLM.value = true;
  llmTestResult.value = null;
  try {
    const result = await api.testLLMConnection();
    llmTestResult.value = result;
    if (result.status === "ok") {
      ElMessage.success("LLM 连接成功");
    } else {
      ElMessage.error(result.message);
    }
  } catch (error) {
    llmTestResult.value = {
      status: "error",
      message: "连接失败: " + (error.message || "网络错误"),
    };
    ElMessage.error("LLM 连接测试失败");
  } finally {
    testingLLM.value = false;
  }
};

onMounted(() => {
  loadLLMSettings();
});
</script>

<style scoped>
.settings-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 8px 0;
}

.page-desc {
  font-size: 14px;
  color: #6b7280;
  margin: 0;
}

.settings-card {
  margin-bottom: 20px;
  border-radius: 12px;
}

/* 让同一行的卡片高度相等 */
:deep(.el-row) {
  align-items: stretch;
}

:deep(.el-col) {
  display: flex;
  flex-direction: column;
}

/* 卡片铺满列高度 */
.settings-card {
  flex: 1;
  display: flex;
  flex-direction: column;
}

:deep(.el-card__body) {
  flex: 1;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.settings-form {
  padding: 8px 0;
}

.form-tip {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 4px;
}

/* 关于系统 */
.about-section {
  text-align: center;
  padding: 20px 0;
}

.about-logo {
  margin-bottom: 16px;
}

.logo-wrapper {
  width: 80px;
  height: 80px;
  margin: 0 auto;
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.about-title {
  font-size: 22px;
  font-weight: 700;
  color: #1f2937;
  margin: 0 0 8px 0;
}

.about-version {
  font-size: 14px;
  color: #10b981;
  margin: 0 0 16px 0;
}

.about-desc {
  font-size: 14px;
  color: #6b7280;
  line-height: 1.6;
  max-width: 400px;
  margin: 0 auto;
}

.tech-stack h4 {
  font-size: 14px;
  color: #6b7280;
  margin: 0 0 12px 0;
}

.tech-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

/* 功能介绍 */
.features-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.feature-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 12px;
  background: #f9fafb;
  border-radius: 10px;
  transition: all 0.2s;
}

.feature-item:hover {
  background: #f3f4f6;
}

.feature-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #fff;
}

.feature-icon .el-icon {
  font-size: 20px;
}

.feature-content h5 {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 4px 0;
}

.feature-content p {
  font-size: 13px;
  color: #6b7280;
  margin: 0;
  line-height: 1.5;
}
</style>
