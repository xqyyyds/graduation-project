<template>
  <div class="dashboard-container">
    <div class="dashboard-header">
      <div class="header-left">
        <h1 class="page-title">舆情研判驾驶舱</h1>
        <p class="page-subtitle">Intelligence Operations Center</p>
      </div>
      <div class="header-right">
        <el-tag
          effect="dark"
          round
          color="var(--el-color-primary)"
          style="border: none"
        >
          {{ currentDate }}
        </el-tag>
      </div>
    </div>

    <el-row :gutter="24" class="stats-overview">
      <el-col
        :xs="24"
        :sm="12"
        :md="6"
        v-for="(item, index) in statCards"
        :key="index"
      >
        <el-card
          class="stat-card"
          shadow="hover"
          :body-style="{ padding: '24px' }"
        >
          <div class="stat-content">
            <div class="stat-text">
              <span class="stat-label">{{ item.label }}</span>
              <div class="stat-num-box">
                <span class="stat-num">{{ item.value }}</span>
                <span class="stat-unit" v-if="item.unit">{{ item.unit }}</span>
              </div>
            </div>
            <div class="stat-icon-wrapper" :class="item.colorClass">
              <el-icon :size="24"><component :is="item.icon" /></el-icon>
            </div>
          </div>
          <div class="mini-progress-bg">
            <div
              class="mini-progress-bar"
              :style="{ width: '100%', background: item.color, opacity: 0.3 }"
            ></div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row
      :gutter="24"
      class="main-content"
      style="align-items: stretch; display: flex; flex-wrap: wrap"
    >
      <el-col :xs="24" :lg="16" class="left-col">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <div class="card-header">
              <div class="title-group">
                <el-icon class="header-icon"><TrendCharts /></el-icon>
                <span>舆情类别分布趋势</span>
              </div>
            </div>
          </template>
          <div class="chart-container" ref="trendChartRef"></div>
        </el-card>

        <el-card class="table-card" shadow="never">
          <template #header>
            <div class="card-header">
              <div class="title-group">
                <el-icon class="header-icon"><List /></el-icon>
                <span>最新生成报告</span>
              </div>
              <el-button link type="primary" @click="goToReports">
                全部档案 <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </template>

          <div class="table-wrapper">
            <el-table
              :data="recentReportsSorted"
              style="width: 100%"
              :show-header="false"
            >
              <el-table-column label="报告名称" min-width="220">
                <template #default="{ row }">
                  <div class="report-name-cell">
                    <div class="file-icon">DOC</div>
                    <span class="text-truncate">{{ row.title }}</span>
                    <el-tag
                      v-if="isNew(row.created_at)"
                      size="small"
                      type="danger"
                      effect="plain"
                      class="new-tag"
                      >NEW</el-tag
                    >
                  </div>
                </template>
              </el-table-column>

              <el-table-column prop="category" width="100" align="center">
                <template #default="{ row }">
                  <el-tag
                    class="category-tag"
                    :type="getCategoryType(row.category)"
                    effect="light"
                    size="small"
                    round
                  >
                    {{ row.category }}
                  </el-tag>
                </template>
              </el-table-column>

              <el-table-column prop="created_at" width="150" align="right">
                <template #default="{ row }">
                  <span class="time-text">{{
                    formatTime(row.created_at)
                  }}</span>
                </template>
              </el-table-column>

              <el-table-column width="60" align="center">
                <template #default="{ row }">
                  <el-button
                    circle
                    size="small"
                    @click="viewReport(row.filename)"
                  >
                    <el-icon><Right /></el-icon>
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8" class="right-col">
        <el-card class="chart-card" shadow="never">
          <template #header>
            <div class="card-header">
              <div class="title-group">
                <el-icon class="header-icon"><PieChart /></el-icon>
                <span>热搜类别占比</span>
              </div>
            </div>
          </template>
          <div class="chart-container pie-container" ref="pieChartRef"></div>
        </el-card>

        <transition name="el-zoom-in-top">
          <div v-if="currentTask" class="active-task-monitor">
            <div class="monitor-header">
              <div class="monitor-left">
                <span class="pulse-dot"></span>
                <span class="monitor-title">正在执行任务...</span>
              </div>
              <span class="monitor-percent">{{ currentTask.progress }}%</span>
            </div>
            <el-progress
              :percentage="currentTask.progress"
              :stroke-width="6"
              :color="customColors"
              :show-text="false"
              striped
              striped-flow
              duration="10"
            />
            <div class="monitor-footer">
              <span class="step-text">{{ currentTask.current_step }}</span>
              <el-button type="primary" link size="small" @click="goToTask"
                >查看详情</el-button
              >
            </div>
          </div>
        </transition>

        <el-card class="action-panel" shadow="never">
          <template #header>
            <div class="card-header">
              <div class="title-group">
                <el-icon class="header-icon"><Lightning /></el-icon>
                <span>快捷操作</span>
              </div>
            </div>
          </template>
          <div class="quick-btn-grid">
            <div class="quick-btn primary" @click="goToTask">
              <div class="btn-icon">
                <el-icon><Plus /></el-icon>
              </div>
              <span>新建任务</span>
            </div>
            <div class="quick-btn" @click="goToReports">
              <div class="btn-icon">
                <el-icon><FolderOpened /></el-icon>
              </div>
              <span>历史档案</span>
            </div>
            <div class="quick-btn" @click="goToSettings">
              <div class="btn-icon">
                <el-icon><Setting /></el-icon>
              </div>
              <span>系统设置</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch, nextTick, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useAppStore } from "../stores/app";
import * as echarts from "echarts";
import dayjs from "dayjs";
import "dayjs/locale/zh-cn";

dayjs.locale("zh-cn");

const router = useRouter();
const store = useAppStore();

const stats = computed(() => store.dashboardStats);
const currentTask = computed(() => store.currentTask);
const currentDate = dayjs().format("YYYY年MM月DD日 dddd");

const trendChartRef = ref(null);
const pieChartRef = ref(null);
let trendChart = null;
let pieChart = null;

const statCards = computed(() => [
  {
    label: "报告总数",
    value: stats.value.total_reports || 0,
    unit: "份",
    icon: "Document",
    colorClass: "bg-blue",
    color: "#3b82f6",
  },
  {
    label: "今日生成",
    value: stats.value.reports_today || 0,
    unit: "份",
    icon: "Timer",
    colorClass: "bg-green",
    color: "#10b981",
  },
  {
    label: "本周累计",
    value: stats.value.reports_this_week || 0,
    unit: "份",
    icon: "TrendCharts",
    colorClass: "bg-orange",
    color: "#f59e0b",
  },
  {
    label: "覆盖类别",
    value: Object.keys(stats.value.category_distribution || {}).length,
    unit: "类",
    icon: "Connection",
    colorClass: "bg-purple",
    color: "#8b5cf6",
  },
]);

const initCharts = () => {
  if (!trendChartRef.value || !pieChartRef.value) return;

  trendChart = echarts.init(trendChartRef.value);
  const categoryNames = Object.keys(stats.value.category_distribution || {});
  const categoryValues = Object.values(stats.value.category_distribution || {});

  const trendOption = {
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    grid: {
      top: "10%",
      left: "2%",
      right: "4%",
      bottom: "2%",
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: categoryNames.length ? categoryNames : ["暂无数据"],
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#94a3b8", interval: 0 },
    },
    yAxis: {
      type: "value",
      splitLine: {
        lineStyle: { type: "dashed", color: "#334155", opacity: 0.3 },
      },
      axisLabel: { color: "#94a3b8" },
    },
    series: [
      {
        name: "报告数量",
        type: "bar",
        barWidth: "40%",
        data: categoryValues.length ? categoryValues : [0],
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "#3b82f6" },
            { offset: 1, color: "#60a5fa" },
          ]),
          borderRadius: [4, 4, 0, 0],
        },
      },
    ],
  };
  trendChart.setOption(trendOption);

  pieChart = echarts.init(pieChartRef.value);
  const sourceForPie =
    stats.value.latest_report_category_violations &&
    Object.keys(stats.value.latest_report_category_violations).length
      ? stats.value.latest_report_category_violations
      : stats.value.category_distribution || {};

  const pieData = Object.entries(sourceForPie)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([name, value]) => ({ name, value }));

  const pieOption = {
    backgroundColor: "transparent",
    tooltip: { trigger: "item" },
    legend: {
      bottom: "0%",
      left: "center",
      icon: "circle",
      itemGap: 20,
      textStyle: { color: "#94a3b8" },
    },
    color: ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"],
    series: [
      {
        name: "类别分布",
        type: "pie",
        radius: ["45%", "70%"],
        center: ["50%", "45%"],
        itemStyle: {
          borderRadius: 8,
          borderColor: "var(--bg-card)",
          borderWidth: 2,
        },
        label: { show: false },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: "bold",
            color: "inherit",
          },
          scale: true,
          scaleSize: 10,
        },
        data: pieData.length ? pieData : [{ value: 0, name: "暂无数据" }],
      },
    ],
  };
  pieChart.setOption(pieOption);
};

const handleResize = () => {
  trendChart?.resize();
  pieChart?.resize();
};
const goToTask = () => router.push("/task");
const goToReports = () => router.push("/reports");
const goToSettings = () => router.push("/settings");
const viewReport = (filename) =>
  router.push({ name: "ReportDetail", params: { filename } });
const getCategoryType = (category) =>
  ({
    综合: "",
    社会: "warning",
    政治: "danger",
    科技: "success",
    生活: "info",
    高校: "primary",
  }[category] || "");
const formatTime = (timeStr) => dayjs(timeStr).format("MM-DD HH:mm");
const recentReportsSorted = computed(() => {
  const arr = stats.value.recent_reports || [];
  return [...arr].sort((a, b) => {
    const ta = a?.created_at ? dayjs(a.created_at).valueOf() : 0;
    const tb = b?.created_at ? dayjs(b.created_at).valueOf() : 0;
    return tb - ta;
  });
});

const isNew = (timeStr) => dayjs().diff(dayjs(timeStr), "hour") < 24;
const customColors = [
  { color: "#f56c6c", percentage: 20 },
  { color: "#e6a23c", percentage: 40 },
  { color: "#5cb87a", percentage: 60 },
  { color: "#1989fa", percentage: 80 },
  { color: "#6f7ad3", percentage: 100 },
];

watch(
  () => stats.value,
  () => {
    nextTick(() => {
      trendChart?.dispose();
      pieChart?.dispose();
      initCharts();
    });
  },
  { deep: true }
);
watch(
  () => store.themeConfig.isDark,
  () => {
    setTimeout(() => {
      trendChart?.dispose();
      pieChart?.dispose();
      initCharts();
    }, 300);
  }
);

onMounted(async () => {
  await store.fetchDashboardStats();
  window.addEventListener("resize", handleResize);
  nextTick(() => initCharts());
});
onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  trendChart?.dispose();
  pieChart?.dispose();
});
</script>

<style scoped>
.dashboard-container {
  max-width: 1600px;
  margin: 0 auto;
}
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
  padding: 0 4px;
}
.page-title {
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.5px;
  margin: 0;
  line-height: 1.2;
}
.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 4px;
  font-family: "Inter", sans-serif;
  letter-spacing: 1px;
  text-transform: uppercase;
  font-weight: 500;
}

.stats-overview {
  margin-bottom: 24px;
}
.el-row {
  display: flex;
  flex-wrap: wrap;
}
.stats-overview .el-col {
  margin-bottom: 24px;
}

.stat-card {
  border: none;
  position: relative;
  overflow: hidden;
  height: 100%;
}
.stat-content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
  position: relative;
  z-index: 2;
}
.stat-label {
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
}
.stat-num-box {
  margin-top: 8px;
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.stat-num {
  font-size: 36px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
  font-family: "Inter", sans-serif;
  letter-spacing: -1px;
}
.stat-unit {
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 500;
}
.stat-icon-wrapper {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  transform: rotate(-10deg);
  transition: all 0.3s;
}
.stat-card:hover .stat-icon-wrapper {
  transform: rotate(0deg) scale(1.1);
}
.bg-blue {
  background: linear-gradient(135deg, #60a5fa, #2563eb);
  box-shadow: 0 8px 16px rgba(37, 99, 235, 0.2);
}
.bg-green {
  background: linear-gradient(135deg, #34d399, #059669);
  box-shadow: 0 8px 16px rgba(5, 150, 105, 0.2);
}
.bg-orange {
  background: linear-gradient(135deg, #fbbf24, #d97706);
  box-shadow: 0 8px 16px rgba(217, 119, 6, 0.2);
}
.bg-purple {
  background: linear-gradient(135deg, #a78bfa, #7c3aed);
  box-shadow: 0 8px 16px rgba(124, 58, 237, 0.2);
}
.mini-progress-bg {
  height: 4px;
  background: var(--bg-body);
  border-radius: 2px;
  overflow: hidden;
  position: relative;
  z-index: 1;
}
.mini-progress-bar {
  height: 100%;
  border-radius: 2px;
}

/* 通用卡片样式 */
.chart-card,
.table-card,
.action-panel {
  border: none;
  margin-bottom: 24px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 16px;
  color: var(--text-primary);
}
.header-icon {
  color: var(--primary-color);
}
.chart-container {
  width: 100%;
  height: 350px;
  min-height: 300px;
}
.pie-container {
  height: 350px;
}

/* 左侧表格布局 */
.table-wrapper {
  height: 480px;
  overflow-y: auto;
  padding-right: 8px;
}
.table-wrapper::-webkit-scrollbar {
  width: 6px;
}
.table-wrapper::-webkit-scrollbar-thumb {
  background-color: var(--border-color);
  border-radius: 3px;
}

/* 右侧列自动填充 */
.right-col {
  display: flex;
  flex-direction: column;
}
.action-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  margin-bottom: 24px;
}
.action-panel :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 24px;
}

/* 任务监控卡片 */
.active-task-monitor {
  background: var(--bg-card);
  border-radius: 16px;
  padding: 20px;
  margin-bottom: 24px;
  box-shadow: var(--shadow-md);
  border: 1px solid rgba(37, 99, 235, 0.1);
  position: relative;
  overflow: hidden;
  color: var(--text-primary);
  flex-shrink: 0;
}
.active-task-monitor::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: var(--primary-color);
}
.monitor-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}
.monitor-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.monitor-title {
  font-weight: 600;
  color: var(--text-primary);
}
.pulse-dot {
  width: 8px;
  height: 8px;
  background: #10b981;
  border-radius: 50%;
  animation: pulse 1.5s infinite;
}
.monitor-percent {
  font-family: "Inter", sans-serif;
  font-weight: 700;
  color: var(--primary-color);
}
.monitor-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  font-size: 12px;
}
.step-text {
  color: var(--text-secondary);
}

/* 快捷按钮组 */
.quick-btn-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}
.quick-btn {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 24px;
  background: var(--bg-body);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
  color: var(--text-primary);
  min-height: 60px;
}
.quick-btn:hover {
  background: var(--bg-card);
  box-shadow: var(--shadow-md);
  transform: translateX(4px);
  border-color: var(--primary-color);
}
.quick-btn.primary {
  background: linear-gradient(
    135deg,
    var(--el-color-primary-light-3) 0%,
    var(--el-color-primary) 100%
  );
  color: #fff;
}
.quick-btn.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 16px rgba(37, 99, 235, 0.25);
}
.quick-btn.primary .btn-icon {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}
.btn-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--bg-card);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-color);
  font-size: 18px;
}

/* 🔥 表格内容修饰 🔥 */
.report-name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.file-icon {
  width: 32px;
  height: 32px;
  background: var(--primary-light);
  color: var(--primary-color);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 800;
  flex-shrink: 0;
}
.text-truncate {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
  font-weight: 500;
  color: var(--text-primary);
}

/* 1. 修复：时间数字等宽对齐 */
.time-text {
  color: var(--text-muted);
  font-size: 13px;
  /* 优先使用等宽字体，并强制开启 tabular-nums 特性 */
  font-family: "Courier New";
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.5px;
}

/* 2. 修复：类别标签固定宽度，视觉一致 */
.category-tag {
  width: 48px; /* 强制固定宽度 */
  justify-content: center; /* 文字居中 */
  border: none; /* 去除边框更干净 */
  font-weight: 600;
}

@media screen and (max-width: 768px) {
  .dashboard-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .stat-num {
    font-size: 28px;
  }
  .chart-container {
    height: 250px;
  }
  .page-subtitle {
    display: none;
  }
}
</style>
