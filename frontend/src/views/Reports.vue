<template>
  <div class="reports-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">历史报告</h1>
        <p class="page-desc">浏览和管理所有舆情研判报告</p>
      </div>
      <div class="header-right">
        <el-button type="primary" @click="refreshReports">
          <el-icon><Refresh /></el-icon>
          刷新列表
        </el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <el-card class="filter-card" shadow="never">
      <div class="filter-bar">
        <div class="filter-item">
          <span class="filter-label">分类筛选</span>
          <el-select
            v-model="selectedCategory"
            placeholder="全部分类"
            @change="handleCategoryChange"
            style="width: 150px"
          >
            <el-option label="全部" value="全部" />
            <el-option
              v-for="cat in categories"
              :key="cat"
              :label="cat"
              :value="cat"
            />
          </el-select>
        </div>

        <div class="filter-item">
          <span class="filter-label">搜索报告</span>
          <el-input
            v-model="searchKeyword"
            placeholder="输入关键词搜索..."
            clearable
            style="width: 240px"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>

        <div class="filter-item">
          <span class="filter-label">排序方式</span>
          <el-select
            v-model="sortOrder"
            style="width: 100px"
            @change="handleSortChange"
          >
            <el-option value="newest" label="最新" />
            <el-option value="oldest" label="最早" />
          </el-select>
        </div>

        <div class="filter-item">
          <span class="filter-label">每页显示</span>
          <el-select
            v-model="pageSize"
            style="width: 100px"
            @change="handlePageSizeChange"
          >
            <el-option :value="25" label="25" />
            <el-option :value="50" label="50" />
            <el-option :value="75" label="75" />
            <el-option :value="100" label="100" />
          </el-select>
        </div>

        <div class="filter-stats">
          共 <span class="count">{{ filteredReports.length }}</span> 份报告
        </div>
      </div>
    </el-card>

    <!-- 报告列表 -->
    <div class="reports-grid">
      <el-card
        v-for="report in paginatedReports"
        :key="report.filename"
        class="report-card"
        shadow="hover"
        @click="viewReport(report.filename)"
      >
        <div class="report-header">
          <div class="report-icon">
            <el-icon :size="32" color="#10b981"><Document /></el-icon>
          </div>
          <el-tag :type="getCategoryType(report.category)" size="small">
            {{ report.category }}
          </el-tag>
        </div>

        <h3 class="report-title">{{ report.title }}</h3>

        <div class="report-meta">
          <div class="meta-item">
            <el-icon><Calendar /></el-icon>
            <span>{{ report.created_at }}</span>
          </div>
          <div class="meta-item">
            <el-icon><Document /></el-icon>
            <span>{{ formatSize(report.size) }}</span>
          </div>
        </div>

        <div class="report-actions">
          <el-button
            type="primary"
            size="small"
            @click.stop="viewReport(report.filename)"
          >
            <el-icon><View /></el-icon>
            查看
          </el-button>
          <el-button size="small" @click.stop="downloadReport(report.filename)">
            <el-icon><Download /></el-icon>
            下载
          </el-button>
          <el-button
            type="danger"
            size="small"
            plain
            @click.stop="confirmDelete(report)"
          >
            <el-icon><Delete /></el-icon>
            删除
          </el-button>
        </div>
      </el-card>
    </div>

    <!-- 分页 -->
    <div class="pagination-wrap" v-if="filteredReports.length > pageSize">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="filteredReports.length"
        layout="prev, pager, next, jumper"
        background
        @current-change="handlePageChange"
      />
    </div>

    <!-- 空状态 -->
    <el-empty
      v-if="!filteredReports.length"
      description="暂无报告"
      class="empty-state"
    >
      <el-button type="primary" @click="goToTask">创建新任务</el-button>
    </el-empty>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAppStore } from "../stores/app";
import { ElMessage, ElMessageBox } from "element-plus";
import api from "../api";

const router = useRouter();
const store = useAppStore();

const selectedCategory = ref("全部");
const searchKeyword = ref("");
const currentPage = ref(1);
const pageSize = ref(25);
const sortOrder = ref("newest"); // 默认最新

const categories = computed(() => store.categories);
const reports = computed(() => store.reports);

// 筛选后的报告（含排序）
const filteredReports = computed(() => {
  let result = [...reports.value];

  if (selectedCategory.value && selectedCategory.value !== "全部") {
    result = result.filter((r) => r.category === selectedCategory.value);
  }

  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase();
    result = result.filter(
      (r) =>
        r.title.toLowerCase().includes(keyword) ||
        r.filename.toLowerCase().includes(keyword)
    );
  }

  // 排序
  result.sort((a, b) => {
    const timeA = a.created_at || "";
    const timeB = b.created_at || "";
    if (sortOrder.value === "newest") {
      return timeB.localeCompare(timeA);
    } else {
      return timeA.localeCompare(timeB);
    }
  });

  return result;
});

// 分页后的报告
const paginatedReports = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  const end = start + pageSize.value;
  return filteredReports.value.slice(start, end);
});

// 辅助函数
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

const formatSize = (bytes) => {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
};

// 排序变更
const handleSortChange = () => {
  currentPage.value = 1;
};

// 操作
const refreshReports = () => {
  store.fetchReports(
    selectedCategory.value !== "全部" ? selectedCategory.value : null
  );
};

const handleCategoryChange = () => {
  currentPage.value = 1; // 切换分类时重置页码
  store.fetchReports(
    selectedCategory.value !== "全部" ? selectedCategory.value : null
  );
};

const handlePageChange = (page) => {
  currentPage.value = page;
  // 滚动到顶部
  window.scrollTo({ top: 0, behavior: "smooth" });
};

const handlePageSizeChange = () => {
  currentPage.value = 1; // 切换每页数量时重置页码
};

const viewReport = (filename) => {
  // 使用命名路由并通过 params 传递文件名，避免手动拼接路径导致重复
  router.push({ name: "ReportDetail", params: { filename } });
};

const downloadReport = (filename) => {
  window.open(api.downloadReport(filename), "_blank");
};

// 删除报告确认
const confirmDelete = (report) => {
  ElMessageBox.confirm(
    `确定要删除报告「${report.title}」吗？此操作不可恢复。`,
    "删除确认",
    {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
      confirmButtonClass: "el-button--danger",
    }
  )
    .then(async () => {
      try {
        await api.deleteReport(report.filename);
        ElMessage.success("报告已删除");
        refreshReports();
      } catch (error) {
        ElMessage.error("删除失败: " + (error.message || "未知错误"));
      }
    })
    .catch(() => {
      // 用户取消
    });
};

const goToTask = () => {
  router.push("/task");
};

onMounted(() => {
  store.fetchReports();
});
</script>

<style scoped>
.reports-page {
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
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

/* 筛选栏 */
.filter-card {
  margin-bottom: 24px;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-label {
  font-size: 14px;
  color: #6b7280;
  white-space: nowrap;
}

.filter-stats {
  margin-left: auto;
  font-size: 14px;
  color: #6b7280;
}

.filter-stats .count {
  color: #10b981;
  font-weight: 600;
}

/* 报告网格 */
.reports-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.report-card {
  cursor: pointer;
  transition: all 0.3s ease;
  border-radius: 12px;
}

.report-card:hover {
  transform: translateY(-4px);
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.report-icon {
  width: 56px;
  height: 56px;
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.report-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 12px 0;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.report-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f3f4f6;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #6b7280;
}

.report-actions {
  display: flex;
  gap: 8px;
}

/* 空状态 */
.empty-state {
  padding: 80px 0;
}

/* 分页 */
.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 32px;
  padding: 16px 0;
}
</style>
