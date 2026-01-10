<template>
  <div class="report-detail">
    <div class="back-bar">
      <el-button text @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        返回列表
      </el-button>
    </div>

    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading" :size="48"><Loading /></el-icon>
      <p>正在加载报告...</p>
    </div>

    <template v-else-if="report">
      <el-card class="report-header-card" shadow="never">
        <div class="report-header">
          <div class="header-info">
            <h1 class="report-title">{{ report.title }}</h1>
            <div class="report-meta">
              <el-tag :type="getCategoryType(report.category)">{{
                report.category
              }}</el-tag>
              <span class="meta-divider">|</span>
              <el-icon><Calendar /></el-icon>
              <span>{{ report.created_at }}</span>
              <span class="meta-divider">|</span>
              <el-icon><Document /></el-icon>
              <span>{{ formatSize(report.size) }}</span>
            </div>
          </div>
          <div class="header-actions">
            <el-button @click="downloadReport">
              <el-icon><Download /></el-icon>
              下载报告
            </el-button>
            <el-button type="primary" @click="copyContent">
              <el-icon><DocumentCopy /></el-icon>
              复制内容
            </el-button>
          </div>
        </div>
      </el-card>

      <el-card class="report-content-card" shadow="never">
        <div
          class="markdown-body"
          ref="markdownRef"
          v-html="renderedContent"
        ></div>
      </el-card>
    </template>

    <el-empty v-else description="报告加载失败" class="error-state">
      <el-button type="primary" @click="goBack">返回列表</el-button>
    </el-empty>

    <el-dialog
      v-model="cellDialogVisible"
      title="📋 完整内容"
      width="70%"
      :close-on-click-modal="true"
      class="content-dialog"
      destroy-on-close
    >
      <div class="cell-full-content">{{ cellFullContent }}</div>
      <template #footer>
        <el-button @click="copyCell" type="primary">
          <el-icon><DocumentCopy /></el-icon>
          复制内容
        </el-button>
        <el-button @click="cellDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { marked } from "marked";
import { ElMessage } from "element-plus";
import api from "../api";

const route = useRoute();
const router = useRouter();

const loading = ref(true);
const report = ref(null);
const content = ref("");
const markdownRef = ref(null);

// 表格内容弹窗
const cellDialogVisible = ref(false);
const cellFullContent = ref("");

// 渲染 Markdown
const renderedContent = computed(() => {
  if (!content.value) return "";
  marked.setOptions({
    breaks: true,
    gfm: true,
  });
  let cleanContent = content.value;
  cleanContent = cleanContent.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "");
  cleanContent = cleanContent.replace(/^\s*\n+/, "");
  return marked(cleanContent);
});

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
  if (!bytes) return "-";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
};

const goBack = () => {
  router.push("/reports");
};

const downloadReport = () => {
  const filename = route.params.filename;
  window.open(api.downloadReport(filename), "_blank");
};

const copyContent = async () => {
  try {
    await navigator.clipboard.writeText(content.value);
    ElMessage.success("内容已复制到剪贴板");
  } catch (error) {
    ElMessage.error("复制失败");
  }
};

const copyCell = async () => {
  try {
    await navigator.clipboard.writeText(cellFullContent.value);
    ElMessage.success("单元格内容已复制");
  } catch (error) {
    ElMessage.error("复制失败");
  }
};

const handleCellClick = (e) => {
  const cell = e.target.closest("td");
  if (cell && cell.classList.contains("truncated-cell")) {
    cellFullContent.value =
      cell.getAttribute("data-full-text") || cell.textContent || "";
    cellDialogVisible.value = true;
  }
};

const processTable = () => {
  if (!markdownRef.value) return;

  const tables = markdownRef.value.querySelectorAll("table");
  tables.forEach((table) => {
    table.addEventListener("click", handleCellClick);

    try {
      const thCount = table.querySelectorAll("th").length;
      if (thCount === 6) {
        table.classList.add("cols-6");
      }
    } catch (e) {}

    const cells = table.querySelectorAll("td");
    cells.forEach((cell) => {
      const text = cell.textContent || "";
      if (text.length > 60) {
        cell.classList.add("truncated-cell");
        cell.setAttribute("data-full-text", text);
        cell.title = "点击查看完整内容";
      }
    });
  });
};

const cleanupTableListeners = () => {
  if (!markdownRef.value) return;
  const tables = markdownRef.value.querySelectorAll("table");
  tables.forEach((table) => {
    table.removeEventListener("click", handleCellClick);
  });
};

onBeforeUnmount(() => {
  cleanupTableListeners();
});

const loadReport = async () => {
  const filename = route.params.filename;

  if (!filename) {
    loading.value = false;
    return;
  }

  try {
    loading.value = true;
    const data = await api.getReportContent(decodeURIComponent(filename));
    content.value = data.content;

    const parts = filename.replace(".md", "").split("_");
    let category = "综合";
    let dateStr = "";
    let timeStr = "";

    if (parts.length === 4) {
      category = parts[1];
      dateStr = parts[2];
      timeStr = parts[3];
    } else if (parts.length === 3) {
      dateStr = parts[1];
      timeStr = parts[2];
    }

    let title = filename;
    const lines = content.value.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (
        !trimmed ||
        trimmed.startsWith("<style") ||
        trimmed.startsWith("/*") ||
        trimmed.startsWith("*/") ||
        trimmed.includes("{") ||
        trimmed.includes("}") ||
        trimmed.startsWith("</style")
      ) {
        continue;
      }
      if (trimmed.startsWith("#")) {
        title = trimmed.replace(/^#+\s*/, "").trim();
        break;
      }
    }

    let created_at = "";
    try {
      created_at = `${dateStr.slice(0, 4)}-${dateStr.slice(
        4,
        6
      )}-${dateStr.slice(6, 8)} ${timeStr.slice(0, 2)}:${timeStr.slice(2, 4)}`;
    } catch {
      created_at = "-";
    }

    report.value = {
      filename,
      title,
      category,
      created_at,
      size: new Blob([content.value]).size,
    };
  } catch (error) {
    console.error("加载报告失败:", error);
    report.value = null;
  } finally {
    loading.value = false;
    nextTick(() => {
      processTable();
    });
  }
};

onMounted(() => {
  loadReport();
});
</script>

<style scoped>
.report-detail {
  max-width: 1200px;
  margin: 0 auto;
}

.back-bar {
  margin-bottom: 16px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 0;
  color: var(--text-secondary);
}

.loading-state p {
  margin-top: 16px;
}

.report-header-card {
  margin-bottom: 20px;
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
}

.report-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px 0;
  line-height: 1.4;
}

.report-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.meta-divider {
  color: var(--border-color);
}

.header-actions {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
}

.report-content-card {
  margin-bottom: 40px;
}

.report-content-card :deep(.el-card__body) {
  overflow-x: auto;
  padding: 24px;
}

.markdown-body {
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-primary);
}

/* =========================================
   Markdown 样式 - 调亮背景色
   ========================================= */

.markdown-body :deep(h1) {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 32px 0 20px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--primary-color);
  text-align: center;
}

.markdown-body :deep(h2) {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 36px 0 18px;
  padding: 10px 14px;
  background: var(--markdown-h2-bg);
  border-left: 4px solid var(--primary-color);
  border-radius: 0 6px 6px 0;
  line-height: 1.4;
}

.markdown-body :deep(h3) {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 28px 0 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color);
  line-height: 1.4;
}

.markdown-body :deep(h4) {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 32px 0 16px;
  padding: 8px 12px;
  background: var(--markdown-h4-bg);
  border-radius: 6px;
  line-height: 1.4;
}

.markdown-body :deep(h5) {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 16px 0 8px;
  line-height: 1.4;
}

.markdown-body :deep(h6) {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin: 12px 0 6px;
  line-height: 1.4;
}

.markdown-body :deep(p) {
  margin: 12px 0;
  text-align: justify;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 12px 0;
  padding-left: 24px;
}

.markdown-body :deep(li) {
  margin: 8px 0;
}

/* 调整点：Blockquote 背景调亮 */
.markdown-body :deep(blockquote) {
  margin: 16px 0;
  padding: 12px 20px;
  background: var(--el-bg-color);
  border-radius: 8px;
  color: var(--text-secondary);
  border-left: 4px solid var(--border-color);
}

.markdown-body :deep(blockquote h2),
.markdown-body :deep(blockquote h5) {
  border-left: none;
  padding-left: 0;
}

.markdown-body :deep(code) {
  background: var(--el-bg-color);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 14px;
}

.markdown-body :deep(pre) {
  background: var(--el-bg-color);
  color: var(--el-text-color-primary, #f9fafb);
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
}

/* 表格 */
.report-content-card :deep(.el-card__body) {
  overflow-x: auto;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0 24px;
  font-size: 13px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  table-layout: fixed;
}

/* 表头背景也微调一下，使其更亮堂 */
.markdown-body :deep(thead) {
  background: var(--el-bg-color);
}

.markdown-body :deep(th) {
  padding: 12px 14px;
  text-align: left;
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-bottom: 2px solid var(--border-color);
}

/* ... 保持原来的表格列宽逻辑 ... */
.markdown-body :deep(table:has(th:nth-child(2):last-child) th:first-child),
.markdown-body :deep(table:has(th:nth-child(2):last-child) td:first-child) {
  width: 60%;
}
.markdown-body :deep(table:has(th:nth-child(2):last-child) th:last-child),
.markdown-body :deep(table:has(th:nth-child(2):last-child) td:last-child) {
  width: 40%;
  text-align: center;
}

.markdown-body :deep(table:has(th:nth-child(3):last-child) th:first-child),
.markdown-body :deep(table:has(th:nth-child(3):last-child) td:first-child) {
  width: 50%;
}
.markdown-body :deep(table:has(th:nth-child(3):last-child) th:nth-child(2)),
.markdown-body :deep(table:has(th:nth-child(3):last-child) td:nth-child(2)),
.markdown-body :deep(table:has(th:nth-child(3):last-child) th:nth-child(3)),
.markdown-body :deep(table:has(th:nth-child(3):last-child) td:nth-child(3)) {
  width: 25%;
  text-align: center;
}

.markdown-body :deep(table.cols-6) th:first-child,
.markdown-body :deep(table.cols-6) td:first-child {
  width: 5%;
  text-align: center;
}
.markdown-body :deep(table.cols-6) th:nth-child(2),
.markdown-body :deep(table.cols-6) td:nth-child(2) {
  width: 8%;
  text-align: center;
}
.markdown-body :deep(table.cols-6) th:nth-child(3),
.markdown-body :deep(table.cols-6) td:nth-child(3) {
  width: 30%;
}
.markdown-body :deep(table.cols-6) th:nth-child(4),
.markdown-body :deep(table.cols-6) td:nth-child(4) {
  width: 25%;
}
.markdown-body :deep(table.cols-6) th:nth-child(5),
.markdown-body :deep(table.cols-6) td:nth-child(5) {
  width: 22%;
}
.markdown-body :deep(table.cols-6) th:nth-child(6),
.markdown-body :deep(table.cols-6) td:nth-child(6) {
  width: 10%;
}
.markdown-body :deep(table.cols-6) th,
.markdown-body :deep(table.cols-6) td {
  vertical-align: middle;
}

.markdown-body :deep(tbody tr:nth-child(odd)) {
  background: transparent;
}
.markdown-body :deep(tbody tr:nth-child(even)) {
  background: var(--el-bg-color);
}
.markdown-body :deep(tbody tr:hover) {
  background: var(--table-row-hover);
}

.markdown-body :deep(td) {
  padding: 10px 12px;
  text-align: left;
  color: var(--text-primary);
  vertical-align: top;
  line-height: 1.5;
  border: 1px solid var(--border-color);
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.markdown-body :deep(.truncated-cell) {
  cursor: pointer;
  max-height: 80px;
  overflow: hidden;
  position: relative;
}
.markdown-body :deep(.truncated-cell::after) {
  content: " ...点击查看全部";
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 500;
  background: transparent;
}
.markdown-body :deep(.truncated-cell:hover) {
  background: var(--truncated-cell-hover-bg) !important;
}
.markdown-body :deep(.truncated-cell:hover::after) {
  color: var(--primary-hover);
}

.markdown-body :deep(.table-wrapper) {
  overflow-x: auto;
  margin: 20px 0;
}

.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--border-color);
  margin: 24px 0;
}

.markdown-body :deep(strong) {
  color: var(--text-primary);
  font-weight: 600;
}

.markdown-body :deep(em) {
  color: var(--text-secondary);
  font-style: italic;
}

.markdown-body :deep(a) {
  color: var(--primary-color);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color 0.2s;
}
.markdown-body :deep(a:hover) {
  border-bottom-color: var(--primary-color);
}

.error-state {
  padding: 100px 0;
}

.cell-full-content {
  font-size: 15px;
  line-height: 1.9;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 65vh;
  overflow-y: auto;
  padding: 20px 24px;
  background: var(--bg-card);
  border-radius: 12px;
  border: 1px solid var(--border-color);
}

:deep(.content-dialog .el-dialog__header) {
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 16px;
}
:deep(.content-dialog .el-dialog__title) {
  font-weight: 600;
  color: var(--text-primary);
}
:deep(.content-dialog .el-dialog__body) {
  padding: 24px;
}
:deep(.content-dialog .el-dialog__footer) {
  border-top: 1px solid var(--border-color);
  padding-top: 16px;
}
</style>
