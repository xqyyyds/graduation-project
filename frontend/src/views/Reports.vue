<template>
  <div class="reports-container">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">报告产物中心</h1>
        <p class="page-desc">统一汇总结构化报告、HTML 成品、PDF 成品与 Markdown 归档</p>
      </div>
      <div class="header-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索报告标题..."
          class="search-input"
          clearable
          @input="handleSearch"
        >
          <template #prefix
            ><el-icon><Search /></el-icon
          ></template>
        </el-input>
        <el-button
          type="primary"
          @click="refreshReports"
          :icon="Refresh"
          circle
        />
      </div>
    </div>

    <div class="category-tabs">
      <div
        v-for="cat in ['全部', ...categories]"
        :key="cat"
        class="tab-item"
        :class="{ active: selectedCategory === cat }"
        @click="handleCategoryChange(cat)"
      >
        {{ cat }}
        <span class="tab-dot" v-if="selectedCategory === cat"></span>
      </div>

      <div class="sort-control">
        <span class="sort-label">排序:</span>
        <el-dropdown @command="handleSortChange">
          <span class="sort-value">
            {{ sortOrder === "newest" ? "最新生成" : "最早生成" }}
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="newest">最新生成</el-dropdown-item>
              <el-dropdown-item command="oldest">最早生成</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <transition-group name="list" tag="div" class="reports-grid">
      <div
        v-for="report in paginatedReports"
        :key="report.filename"
        class="report-card"
        :class="getCategoryClass(report.category)"
        @click="viewReport(report.filename)"
      >
        <div class="color-strip"></div>

        <div class="card-body">
          <div class="card-top">
            <div class="file-type-icon">REPORT</div>
            <div class="report-mode-tag">结构化成品</div>
            <el-tag
              :type="getCategoryType(report.category)"
              size="small"
              effect="light"
              round
            >
              {{ report.category }}
            </el-tag>
          </div>

          <h3 class="report-title" :title="report.title">{{ report.title }}</h3>

          <div class="report-meta">
            <div class="meta-row">
              <el-icon><Calendar /></el-icon>
              <span>{{ formatDate(report.created_at) }}</span>
            </div>
            <div class="meta-row">
              <el-icon><Document /></el-icon>
              <span>{{ formatSize(report.size) }}</span>
            </div>
          </div>

          <div class="artifact-row">
            <span
              v-for="artifact in getArtifactBadges(report.filename)"
              :key="artifact.key"
              class="artifact-chip"
              :class="{ active: artifact.available }"
            >
              {{ artifact.label }}
            </span>
          </div>

          <div class="card-actions">
            <el-button
              type="primary"
              size="small"
              text
              bg
              @click.stop="viewReport(report.filename)"
            >
              查看成品
            </el-button>
            <div class="action-right">
              <el-dropdown @command="(format) => downloadReport(report.filename, format)">
                <el-button size="small" circle @click.stop>
                  <el-icon><Download /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="md">下载 Markdown</el-dropdown-item>
                    <el-dropdown-item command="html">下载 HTML</el-dropdown-item>
                    <el-dropdown-item command="pdf">下载 PDF</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-tooltip content="删除档案" placement="top">
                <el-button
                  type="danger"
                  size="small"
                  circle
                  plain
                  @click.stop="confirmDelete(report)"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </div>
        </div>
      </div>
    </transition-group>

    <div v-if="!filteredReports.length" class="empty-wrapper">
      <el-empty description="暂无相关报告产物" :image-size="200" />
    </div>

    <div class="pagination-container" v-if="filteredReports.length > pageSize">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="filteredReports.length"
        layout="prev, pager, next"
        background
        @current-change="scrollToTop"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAppStore } from "../stores/app";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh, Search, ArrowDown } from "@element-plus/icons-vue";
import api from "../api";
import dayjs from "dayjs";

const router = useRouter();
const route = useRoute();
const store = useAppStore();

const selectedCategory = ref("全部");
const searchKeyword = ref("");
const currentPage = ref(1);
const pageSize = ref(20);
const sortOrder = ref("newest");
const artifactMap = ref({});

const categories = computed(() => store.categories);
const reports = computed(() => store.reports);

const filteredReports = computed(() => {
  let result = [...reports.value];
  if (selectedCategory.value !== "全部") {
    result = result.filter((r) => r.category === selectedCategory.value);
  }
  if (searchKeyword.value) {
    const k = searchKeyword.value.toLowerCase();
    result = result.filter((r) => r.title.toLowerCase().includes(k));
  }
  return result.sort((a, b) => {
    return sortOrder.value === "newest"
      ? (b.created_at || "").localeCompare(a.created_at || "")
      : (a.created_at || "").localeCompare(b.created_at || "");
  });
});

const paginatedReports = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredReports.value.slice(start, start + pageSize.value);
});

const getArtifactBadges = (filename) => {
  const source = artifactMap.value[filename] || {};
  return [
    { key: "json", label: "JSON", available: Boolean(source.json) },
    { key: "html", label: "HTML", available: Boolean(source.html) },
    { key: "pdf", label: "PDF", available: Boolean(source.pdf) },
    { key: "markdown", label: "MD", available: Boolean(source.markdown) },
  ];
};

// 样式映射
const getCategoryType = (cat) => {
  const map = {
    社会: "warning",
    政治: "danger",
    科技: "success",
    高校: "primary",
    生活: "info",
  };
  return map[cat] || "";
};

// CSS 类名映射，用于彩色条
const getCategoryClass = (cat) => {
  const map = {
    社会: "cat-orange",
    政治: "cat-red",
    科技: "cat-blue",
    高校: "cat-cyan",
    生活: "cat-purple",
  };
  return map[cat] || "cat-gray";
};

const formatDate = (date) => dayjs(date).format("YYYY-MM-DD HH:mm");
const formatSize = (bytes) =>
  bytes < 1024
    ? bytes + " B"
    : bytes < 1048576
    ? (bytes / 1024).toFixed(1) + " KB"
    : (bytes / 1048576).toFixed(1) + " MB";

const handleCategoryChange = (cat) => {
  selectedCategory.value = cat;
  currentPage.value = 1;
  syncQuery();
};
const handleSortChange = (cmd) => {
  sortOrder.value = cmd;
  currentPage.value = 1;
};
const handleSearch = () => {
  currentPage.value = 1;
  syncQuery();
};
const refreshReports = () => store.fetchReports();
const scrollToTop = () => window.scrollTo({ top: 0, behavior: "smooth" });

const syncQuery = () => {
  const nextQuery = {};
  if (selectedCategory.value && selectedCategory.value !== "全部") {
    nextQuery.category = selectedCategory.value;
  }
  if (searchKeyword.value?.trim()) {
    nextQuery.q = searchKeyword.value.trim();
  }
  router.replace({ name: "Reports", query: nextQuery });
};

const loadVisibleArtifacts = async (list) => {
  const targets = list.filter((item) => !artifactMap.value[item.filename]);
  if (!targets.length) return;

  const results = await Promise.allSettled(
    targets.map((item) => api.getReportArtifacts(item.filename))
  );

  const nextMap = { ...artifactMap.value };
  results.forEach((result, index) => {
    const filename = targets[index].filename;
    nextMap[filename] =
      result.status === "fulfilled"
        ? result.value
        : { markdown: true, json: false, html: false, pdf: false };
  });
  artifactMap.value = nextMap;
};

const viewReport = (filename) =>
  router.push({ name: "ReportDetail", params: { filename } });
const downloadReport = (filename, format = "md") =>
  window.open(api.downloadReport(filename, format), "_blank");

const confirmDelete = (report) => {
  ElMessageBox.confirm(`确认永久删除报告 "${report.title}" ?`, "警告", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  }).then(async () => {
    try {
      await api.deleteReport(report.filename);
      ElMessage.success("报告产物已删除");
      refreshReports();
    } catch (e) {
      ElMessage.error("删除失败");
    }
  });
};

watch(
  () => paginatedReports.value,
  (list) => {
    loadVisibleArtifacts(list);
  },
  { immediate: true }
);

onMounted(() => {
  if (route.query.category && typeof route.query.category === "string") {
    selectedCategory.value = route.query.category;
  }
  if (route.query.q && typeof route.query.q === "string") {
    searchKeyword.value = route.query.q;
  }
  refreshReports();
});
</script>

<style scoped>
.reports-container {
  max-width: 1400px;
  margin: 0 auto;
  min-height: 80vh;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
  padding: 0 4px;
}
.page-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.page-desc {
  color: var(--text-muted);
  font-size: 13px;
  margin-top: 4px;
  letter-spacing: 0.02em;
}

.header-actions {
  display: flex;
  gap: 12px;
}
.search-input {
  width: 240px;
}

/* 分类 Tab */
.category-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 12px;
}
.tab-item {
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 14px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  font-weight: 500;
}
.tab-item:hover {
  color: var(--primary-color);
  background: var(--primary-light);
}
.tab-item.active {
  background: var(--primary-color);
  color: #fff;
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.2);
}

.sort-control {
  margin-left: auto;
  display: flex;
  align-items: center;
  font-size: 13px;
  color: var(--text-muted);
}
.sort-value {
  margin-left: 8px;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 2px;
  font-weight: 600;
}

/* 档案卡片网格 */
.reports-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.report-card {
  background: var(--bg-card);
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border-color);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  display: flex;
  flex-direction: column;
}
.report-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-md);
  border-color: transparent;
}

/* 顶部彩条 */
.color-strip {
  height: 4px;
  width: 100%;
  opacity: 0.8;
}
.cat-orange .color-strip {
  background: #f59e0b;
}
.cat-red .color-strip {
  background: #ef4444;
}
.cat-blue .color-strip {
  background: #3b82f6;
}
.cat-cyan .color-strip {
  background: #06b6d4;
}
.cat-purple .color-strip {
  background: #8b5cf6;
}
.cat-gray .color-strip {
  background: #64748b;
}

.card-body {
  padding: 20px;
  flex: 1;
  display: flex;
  flex-direction: column;
}
.card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.file-type-icon {
  min-width: 64px;
  height: 32px;
  background: var(--el-fill-color-blank, #f1f5f9);
  color: var(--text-secondary);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 800;
  border: 1px solid var(--border-color);
  letter-spacing: 0.08em;
}

.report-mode-tag {
  margin-left: auto;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: var(--primary-color);
  background: rgba(59, 130, 246, 0.08);
}

.report-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 12px 0;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 48px;
}

.report-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}
.meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-muted);
}

.card-actions {
  margin-top: auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--border-color);
  padding-top: 16px;
}

.artifact-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
}

.artifact-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  border: 1px dashed var(--border-color);
  background: rgba(255, 255, 255, 0.72);
}

.artifact-chip.active {
  color: var(--primary-color);
  border-style: solid;
  border-color: rgba(59, 130, 246, 0.18);
  background: rgba(59, 130, 246, 0.08);
}
.action-right {
  display: flex;
  gap: 8px;
  opacity: 0.6;
  transition: opacity 0.2s;
}
.report-card:hover .action-right {
  opacity: 1;
}

.list-enter-active,
.list-leave-active {
  transition: all 0.3s ease;
}
.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: translateY(20px);
}

.pagination-container {
  display: flex;
  justify-content: center;
  margin-top: 40px;
}

@media (max-width: 900px) {
  .page-header,
  .category-tabs {
    flex-direction: column;
    align-items: stretch;
  }

  .header-actions,
  .search-input {
    width: 100%;
  }

  .sort-control {
    margin-left: 0;
    justify-content: space-between;
    width: 100%;
    padding-top: 8px;
  }
}
</style>
