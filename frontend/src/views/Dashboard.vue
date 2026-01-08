<template>
  <div class="dashboard">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">舆情研判驾驶舱</h1>
      <p class="page-desc">全面概览平台核心数据与关键指标</p>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div
            class="stat-icon"
            style="
              background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            "
          >
            <el-icon :size="24"><Document /></el-icon>
          </div>
          <div class="stat-info">
            <span class="stat-label">报告总数</span>
            <span class="stat-value">{{ stats.total_reports }}</span>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div
            class="stat-icon"
            style="
              background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
            "
          >
            <el-icon :size="24"><Calendar /></el-icon>
          </div>
          <div class="stat-info">
            <span class="stat-label">今日生成</span>
            <span class="stat-value">{{ stats.reports_today }}</span>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div
            class="stat-icon"
            style="
              background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
            "
          >
            <el-icon :size="24"><TrendCharts /></el-icon>
          </div>
          <div class="stat-info">
            <span class="stat-label">本周生成</span>
            <span class="stat-value">{{ stats.reports_this_week }}</span>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div
            class="stat-icon"
            style="
              background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
            "
          >
            <el-icon :size="24"><Folder /></el-icon>
          </div>
          <div class="stat-info">
            <span class="stat-label">分类数量</span>
            <span class="stat-value">{{
              Object.keys(stats.category_distribution).length
            }}</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 主要内容区 -->
    <el-row :gutter="20" class="content-row">
      <!-- 快速操作 -->
      <el-col :xs="24" :lg="8">
        <el-card class="action-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span>快速操作</span>
            </div>
          </template>

          <div class="quick-actions">
            <el-button
              type="primary"
              size="large"
              class="action-btn"
              @click="goToTask"
            >
              <el-icon><Plus /></el-icon>
              新建研判任务
            </el-button>

            <el-button size="large" class="action-btn" @click="goToReports">
              <el-icon><FolderOpened /></el-icon>
              查看所有报告
            </el-button>

            <el-button size="large" class="action-btn" @click="goToSettings">
              <el-icon><Setting /></el-icon>
              系统设置
            </el-button>
          </div>

          <!-- 任务状态提示 -->
          <div v-if="currentTask" class="task-status-card">
            <div class="task-status-header">
              <span class="task-status-title">当前任务</span>
              <el-tag
                :type="getTaskStatusType(currentTask.status)"
                size="small"
              >
                {{ getTaskStatusText(currentTask.status) }}
              </el-tag>
            </div>
            <div class="task-progress">
              <el-progress
                :percentage="currentTask.progress"
                :status="currentTask.status === 'failed' ? 'exception' : ''"
              />
            </div>
            <p class="task-message">{{ currentTask.message }}</p>
          </div>

          <!-- 系统状态 -->
          <div v-if="!currentTask" class="system-status">
            <div class="status-item">
              <el-icon color="#10b981"><CircleCheck /></el-icon>
              <span>后端服务正常</span>
            </div>
            <div class="status-item">
              <el-icon color="#10b981"><CircleCheck /></el-icon>
              <span>数据库已连接</span>
            </div>
            <div class="status-item">
              <el-icon color="#10b981"><CircleCheck /></el-icon>
              <span>LLM 模型就绪</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 最近报告 -->
      <el-col :xs="24" :lg="16">
        <el-card class="reports-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span>最近报告</span>
              <el-button type="primary" link @click="goToReports">
                查看全部
                <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </template>

          <el-table
            :data="stats.recent_reports"
            style="width: 100%"
            :show-header="true"
            max-height="400"
          >
            <el-table-column label="报告标题" min-width="200">
              <template #default="{ row }">
                <div class="report-title-cell">
                  <el-icon class="report-icon"><Document /></el-icon>
                  <span class="report-title">{{ row.title }}</span>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="分类" width="100">
              <template #default="{ row }">
                <el-tag :type="getCategoryType(row.category)" size="small">
                  {{ row.category }}
                </el-tag>
              </template>
            </el-table-column>

            <el-table-column prop="created_at" label="生成时间" width="160" />

            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button
                  type="primary"
                  link
                  @click="viewReport(row.filename)"
                >
                  查看
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-empty
            v-if="!stats.recent_reports?.length"
            description="暂无报告"
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- 分类分布 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="24">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span>报告分类分布</span>
            </div>
          </template>

          <div class="category-stats">
            <div
              v-for="(count, category) in stats.category_distribution"
              :key="category"
              class="category-item"
            >
              <div class="category-bar">
                <div
                  class="category-bar-fill"
                  :style="{
                    width: getPercentage(count) + '%',
                    background: getCategoryColor(category),
                  }"
                ></div>
              </div>
              <div class="category-info">
                <span class="category-name">{{ category }}</span>
                <span class="category-count">{{ count }} 份</span>
              </div>
            </div>
          </div>

          <el-empty
            v-if="!Object.keys(stats.category_distribution).length"
            description="暂无数据"
          />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAppStore } from "../stores/app";

const router = useRouter();
const store = useAppStore();

const stats = computed(() => store.dashboardStats);
const currentTask = computed(() => store.currentTask);

// 导航
const goToTask = () => router.push("/task");
const goToReports = () => router.push("/reports");
const goToSettings = () => router.push("/settings");
const viewReport = (filename) =>
  router.push({ name: "ReportDetail", params: { filename } });

// 辅助函数
const getTaskStatusType = (status) => {
  const map = { running: "warning", completed: "success", failed: "danger" };
  return map[status] || "info";
};

const getTaskStatusText = (status) => {
  const map = { running: "运行中", completed: "已完成", failed: "失败" };
  return map[status] || status;
};

const getCategoryType = (category) => {
  const map = {
    综合: "",
    社会: "warning",
    政治: "danger",
    科技: "success",
    生活: "info",
    高校: "primary",
  };
  return map[category] || "";
};

const getCategoryColor = (category) => {
  const colors = {
    综合: "#10b981",
    社会: "#f59e0b",
    政治: "#ef4444",
    科技: "#3b82f6",
    生活: "#8b5cf6",
    高校: "#06b6d4",
    其他: "#6b7280",
  };
  return colors[category] || "#6b7280";
};

const getPercentage = (count) => {
  const total = Object.values(stats.value.category_distribution).reduce(
    (a, b) => a + b,
    0
  );
  return total ? Math.round((count / total) * 100) : 0;
};

onMounted(() => {
  store.fetchDashboardStats();
});
</script>

<style scoped>
.dashboard {
  max-width: 1400px;
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

/* 统计卡片 */
.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-label {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #1f2937;
}

/* 内容区 */
.content-row {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}
/* 快速操作卡片样式 */
.action-card {
  height: 100%;
  padding: 20px; /* 保证卡片内边距，内容不贴边 */
}

/* 按钮容器：占满卡片宽度，垂直排列 */
.quick-actions {
  display: flex;
  flex-direction: column;
  gap: 12px; /* 按钮间距 */
  margin-bottom: 20px;
  width: 100%; /* 强制占满卡片宽度，作为按钮的居中基准 */
}

:deep(.el-button.action-btn) {
  /* 把宽度从auto改成基于父容器的百分比，既饱满又不占满 */
  width: 70%;
  height: 48px;
  font-size: 15px;
  padding: 0 24px;
  border-radius: 8px;
  margin: 0 auto; /* 保持居中 */
  display: inline-block;
}

/* 图标与文字间距（保持视觉舒适） */
:deep(.action-btn .el-icon) {
  margin-right: 8px;
}
.task-status-card {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
}

.task-status-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.task-status-title {
  font-weight: 500;
  color: #374151;
}

.task-progress {
  margin-bottom: 8px;
}

.task-message {
  font-size: 13px;
  color: #6b7280;
  margin: 0;
}

/* 系统状态 */
.system-status {
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #d1fae5;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  font-size: 14px;
  color: #374151;
}

.status-item:not(:last-child) {
  border-bottom: 1px solid #d1fae5;
}

/* 报告列表 */
.reports-card {
  height: 100%;
}

.report-title-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.report-icon {
  color: #10b981;
}

.report-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 图表区 */
.chart-row {
  margin-bottom: 20px;
}

.category-stats {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.category-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.category-bar {
  height: 8px;
  background: #f3f4f6;
  border-radius: 4px;
  overflow: hidden;
}

.category-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s ease;
}

.category-info {
  display: flex;
  justify-content: space-between;
  font-size: 14px;
}

.category-name {
  color: #374151;
  font-weight: 500;
}

.category-count {
  color: #6b7280;
}
</style>
