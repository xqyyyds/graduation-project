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

    <template v-else-if="reportMeta">
      <el-card class="report-header-card" shadow="never">
        <div class="report-header">
          <div class="header-info">
            <h1 class="report-title">{{ reportMeta.title }}</h1>
            <div class="report-meta">
              <el-tag :type="getCategoryType(reportMeta.category)">
                {{ reportMeta.category }}
              </el-tag>
              <span class="meta-divider">|</span>
              <el-icon><Calendar /></el-icon>
              <span>{{ reportMeta.created_at }}</span>
              <span class="meta-divider">|</span>
              <el-icon><Document /></el-icon>
              <span>{{ formatSize(reportMeta.size) }}</span>
              <template v-if="reportPeriod">
                <span class="meta-divider">|</span>
                <span>研判周期：{{ reportPeriod }}</span>
              </template>
            </div>
            <div class="artifact-pills">
              <span
                v-for="artifact in availableArtifacts"
                :key="artifact.key"
                class="artifact-pill"
                :class="{ available: artifact.available }"
              >
                {{ artifact.label }}
              </span>
            </div>
          </div>
          <div class="header-actions">
            <el-dropdown @command="handleDownload">
              <el-button>
                <el-icon><Download /></el-icon>
                下载报告
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="md"
                    >下载 Markdown</el-dropdown-item
                  >
                  <el-dropdown-item command="html">下载 HTML</el-dropdown-item>
                  <el-dropdown-item command="pdf">下载 PDF</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button
              v-if="activeTab === 'markdown' && hasMarkdownArchive"
              type="primary"
              @click="copyContent"
            >
              <el-icon><DocumentCopy /></el-icon>
              复制 Markdown
            </el-button>
          </div>
        </div>
      </el-card>

      <el-card
        v-if="tabOptions.length > 1"
        class="report-tabs-card"
        shadow="never"
      >
        <div class="tabs-row">
          <el-segmented v-model="activeTab" :options="tabOptions" />
          <span class="tabs-tip">
            结构化报告为主展示，Markdown 仅保留为原始归档视图。
          </span>
        </div>
      </el-card>

      <template v-if="activeTab === 'structured' && structuredReport">
        <section class="section-card">
          <div class="section-title">前言：舆情态势综述</div>
          <div class="preface-body">
            <template v-if="structuredReport.preface.paragraphs?.length">
              <p
                v-for="(item, index) in structuredReport.preface.paragraphs"
                :key="`pref-para-${index}`"
              >
                {{ item }}
              </p>
            </template>
            <template v-else>
              <p>{{ structuredReport.preface.overview }}</p>
              <p
                v-for="(item, index) in structuredReport.preface
                  .characteristics || []"
                :key="`pref-${index}`"
              >
                {{ item }}
              </p>
              <p>{{ structuredReport.preface.compliance_perspective }}</p>
              <p>{{ structuredReport.preface.trend_connection }}</p>
              <p>{{ structuredReport.preface.conclusion }}</p>
            </template>
          </div>
        </section>

        <section class="section-card">
          <div class="section-title">第一部分：本期热点舆情总览</div>
          <el-table :data="structuredReport.overview_table || []" stripe>
            <el-table-column prop="seq" label="序号" width="80" />
            <el-table-column prop="time" label="时间" width="140" />
            <el-table-column
              prop="event_name"
              label="事件名称"
              min-width="280"
            />
            <el-table-column prop="heat_value" label="热度值" width="120" />
          </el-table>
        </section>

        <section class="section-card">
          <div class="section-title">第二部分：重点舆情深读</div>
          <div class="deep-read-grid">
            <article
              v-for="(item, index) in structuredReport.deep_reads || []"
              :key="`${item.event_name}-${index}`"
              class="deep-read-card"
            >
              <div class="deep-read-index">重点 {{ index + 1 }}</div>
              <h3>{{ item.editorial_title || item.event_name }}</h3>
              <div v-if="item.one_line_verdict" class="verdict-box">
                {{ item.one_line_verdict }}
              </div>
              <div v-if="item.event_overview" class="deep-read-block">
                <div class="subsection-title">事件概况</div>
                <p>{{ item.event_overview }}</p>
              </div>
              <div v-if="item.public_opinions?.length" class="deep-read-block">
                <div class="subsection-title">舆论观点画像</div>
                <ul class="opinion-list">
                  <li
                    v-for="(opinion, opIndex) in item.public_opinions"
                    :key="opIndex"
                  >
                    {{ opinion }}
                  </li>
                </ul>
              </div>
              <div v-if="item.depth_analysis" class="deep-read-block">
                <div class="subsection-title">深度研判</div>
                <p>{{ item.depth_analysis }}</p>
              </div>
              <div v-if="item.key_quotes?.length" class="quotes-grid">
                <div
                  v-for="(quote, quoteIndex) in item.key_quotes"
                  :key="quoteIndex"
                  class="quote-chip"
                >
                  {{ quote }}
                </div>
              </div>
            </article>
          </div>
        </section>

        <section class="section-card">
          <div class="section-title">第三部分：违规风险透视</div>
          <div class="summary-strip">
            <div class="summary-card">
              <span class="summary-label">确认违规案例</span>
              <strong>{{
                structuredReport.compliance?.summary?.total_cases || 0
              }}</strong>
            </div>
            <div class="summary-card">
              <span class="summary-label">涉及事件</span>
              <strong>{{
                structuredReport.compliance?.summary?.event_count || 0
              }}</strong>
            </div>
          </div>
          <div
            v-if="structuredReport.compliance?.summary?.phase_summary"
            class="summary-narrative"
          >
            {{ structuredReport.compliance.summary.phase_summary }}
          </div>
          <div class="appendix-grid">
            <article class="appendix-card">
              <h3>风险等级分布</h3>
              <el-table
                :data="structuredReport.compliance?.summary?.risk_levels || []"
                stripe
              >
                <el-table-column
                  prop="label"
                  label="风险等级"
                  min-width="160"
                />
                <el-table-column prop="count" label="次数" width="120" />
              </el-table>
            </article>
            <article class="appendix-card">
              <h3>主要违规类别</h3>
              <el-table
                :data="
                  (
                    structuredReport.compliance?.summary?.categories || []
                  ).slice(0, 8)
                "
                stripe
              >
                <el-table-column
                  prop="label"
                  label="违规类别"
                  min-width="220"
                />
                <el-table-column prop="count" label="次数" width="120" />
              </el-table>
            </article>
          </div>
        </section>

        <section class="section-card">
          <div class="section-title">第四部分：未来趋势与战略预警</div>
          <div class="forecast-grid">
            <article
              v-for="(topic, index) in structuredReport.forecast?.topics || []"
              :key="`${topic.topic_name}-${index}`"
              class="forecast-card"
            >
              <h3>{{ index + 1 }}. {{ topic.topic_name }}</h3>
              <div
                v-if="forecastTopicSummary(topic)"
                class="forecast-summary-box"
              >
                <div class="forecast-summary-label">预警摘要</div>
                <p>{{ forecastTopicSummary(topic) }}</p>
              </div>
              <div
                v-for="(point, pointIndex) in topic.points || []"
                :key="pointIndex"
                class="forecast-point"
              >
                <div class="forecast-point-header">
                  <div class="point-title">{{ point.subtitle }}</div>
                  <span v-if="point.likelihood" class="case-tag">
                    {{ point.likelihood }}
                  </span>
                </div>
                <p class="point-paragraph">
                  {{ forecastPointParagraph(point) }}
                </p>
              </div>
            </article>
          </div>
        </section>

        <section class="section-card">
          <div class="section-title">附录：违规数据监测</div>
          <div class="appendix-grid">
            <article class="appendix-card">
              <h3>风险等级分布</h3>
              <el-table
                :data="structuredReport.appendix_stats?.risk_levels || []"
                stripe
              >
                <el-table-column
                  prop="label"
                  label="风险等级"
                  min-width="160"
                />
                <el-table-column prop="count" label="次数" width="120" />
              </el-table>
            </article>
            <article class="appendix-card">
              <h3>违规类别分布</h3>
              <el-table
                :data="structuredReport.appendix_stats?.categories || []"
                stripe
              >
                <el-table-column
                  prop="label"
                  label="违规类别"
                  min-width="220"
                />
                <el-table-column prop="count" label="次数" width="120" />
              </el-table>
            </article>
            <article class="appendix-card">
              <h3>依据条款分布</h3>
              <el-table
                :data="structuredReport.appendix_stats?.laws || []"
                stripe
              >
                <el-table-column prop="label" label="条款" min-width="260" />
                <el-table-column prop="count" label="次数" width="120" />
              </el-table>
            </article>
          </div>
          <div class="appendix-detail-list">
            <article
              v-for="(eventGroup, index) in structuredReport.appendix_cases ||
              []"
              :key="`${eventGroup.event_name}-${index}`"
              class="appendix-card"
            >
              <h3>{{ index + 1 }}. {{ eventGroup.event_name }}</h3>
              <div class="case-list">
                <div
                  v-for="(caseItem, caseIndex) in eventGroup.cases"
                  :key="`${eventGroup.event_name}-${caseIndex}`"
                  class="case-card"
                >
                  <div class="case-meta">
                    <span class="case-tag">{{ caseItem.source_type }}</span>
                    <span class="case-tag">{{ caseItem.category }}</span>
                    <span
                      class="case-tag"
                      :class="{ 'risk-high': caseItem.risk_level === 'High' }"
                    >
                      {{ caseItem.risk_level }}
                    </span>
                  </div>
                  <div class="case-detail">
                    <span class="detail-label">来源ID</span>
                    <span>{{ caseItem.source_id }}</span>
                  </div>
                  <div class="case-detail">
                    <span class="detail-label">序号</span>
                    <span>{{ caseItem.index }}</span>
                  </div>
                  <div class="case-detail">
                    <span class="detail-label">所属事件</span>
                    <span>{{
                      caseItem.event_name || eventGroup.event_name
                    }}</span>
                  </div>
                  <div class="case-detail">
                    <span class="detail-label">违规摘录</span>
                    <span>{{ caseItem.quote }}</span>
                  </div>
                  <div class="case-detail">
                    <span class="detail-label">判定理由</span>
                    <span>{{ caseItem.reasoning }}</span>
                  </div>
                  <div class="case-detail">
                    <span class="detail-label">主要依据</span>
                    <span>{{ caseItem.primary_law }}</span>
                  </div>
                  <div class="case-detail">
                    <span class="detail-label">证据链</span>
                    <span>{{ caseItem.evidence_chain }}</span>
                  </div>
                  <div class="case-detail">
                    <span class="detail-label">处置建议</span>
                    <span>{{ caseItem.disposal_suggestion }}</span>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </section>
      </template>

      <el-card v-else class="report-content-card" shadow="never">
        <div class="markdown-panel-header">
          <div>
            <h3>Markdown 归档视图</h3>
            <p>这里保留原始导出版，便于复制、归档或核对成品差异。</p>
          </div>
          <el-button
            v-if="hasMarkdownArchive"
            type="primary"
            plain
            @click="copyContent"
          >
            <el-icon><DocumentCopy /></el-icon>
            复制 Markdown
          </el-button>
        </div>
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { marked } from "marked";
import { ElMessage } from "element-plus";
import api from "../api";
import {
  buildForecastParagraph,
  buildForecastTopicSummary,
} from "./reportPresentation";
import { sanitizeRenderedMarkdown } from "./markdownSanitizer";

const route = useRoute();
const router = useRouter();

const loading = ref(true);
const reportMeta = ref(null);
const structuredReport = ref(null);
const content = ref("");
const artifacts = ref(null);
const markdownRef = ref(null);
const activeTab = ref("structured");

const hasStructuredReport = computed(() => Boolean(structuredReport.value));
const hasMarkdownArchive = computed(() => Boolean(content.value));
const tabOptions = computed(() => {
  const options = [];
  if (hasStructuredReport.value) {
    options.push({ label: "结构化成品", value: "structured" });
  }
  if (hasMarkdownArchive.value) {
    options.push({ label: "Markdown 归档", value: "markdown" });
  }
  return options;
});

const availableArtifacts = computed(() => {
  const source = artifacts.value || {};
  return [
    { key: "json", label: "JSON", available: Boolean(source.json) },
    { key: "html", label: "HTML", available: Boolean(source.html) },
    { key: "pdf", label: "PDF", available: Boolean(source.pdf) },
    { key: "markdown", label: "Markdown", available: Boolean(source.markdown) },
  ];
});

const reportPeriod = computed(
  () => structuredReport.value?.meta?.report_period || "",
);

const renderedContent = computed(() => {
  if (!content.value) return "";
  marked.setOptions({
    breaks: true,
    gfm: true,
  });
  const cleanContent = content.value
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
    .replace(/^\s*\n+/, "");
  return sanitizeRenderedMarkdown(marked(cleanContent));
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

const handleDownload = (format) => {
  const filename = route.params.filename;
  window.open(api.downloadReport(filename, format), "_blank");
};

const forecastTopicSummary = (topic) => buildForecastTopicSummary(topic);
const forecastPointParagraph = (point) => buildForecastParagraph(point);

const copyContent = async () => {
  try {
    await navigator.clipboard.writeText(content.value);
    ElMessage.success("Markdown 已复制到剪贴板");
  } catch (error) {
    ElMessage.error("复制失败");
  }
};

const buildMetaFromFilename = (filename, rawContent = "", jsonData = null) => {
  if (jsonData?.meta) {
    return {
      filename,
      title: jsonData.meta.title || filename,
      category: jsonData.meta.category || "综合",
      created_at: jsonData.meta.generated_at || "-",
      size: new Blob([rawContent || JSON.stringify(jsonData)]).size,
    };
  }

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

  let created_at = "-";
  try {
    created_at = `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(
      6,
      8,
    )} ${timeStr.slice(0, 2)}:${timeStr.slice(2, 4)}`;
  } catch {
    created_at = "-";
  }

  return {
    filename,
    title: filename,
    category,
    created_at,
    size: new Blob([rawContent]).size,
  };
};

const loadReport = async () => {
  const filename = decodeURIComponent(route.params.filename || "");
  if (!filename) {
    loading.value = false;
    return;
  }

  loading.value = true;
  try {
    const [markdownResponse, jsonResponse, artifactsResponse] =
      await Promise.allSettled([
        api.getReportContent(filename),
        api.getReportJson(filename),
        api.getReportArtifacts(filename),
      ]);

    if (markdownResponse.status === "fulfilled") {
      content.value = markdownResponse.value.content || "";
    }

    if (jsonResponse.status === "fulfilled") {
      structuredReport.value = jsonResponse.value;
    } else {
      activeTab.value = "markdown";
    }

    if (artifactsResponse.status === "fulfilled") {
      artifacts.value = artifactsResponse.value;
    }

    if (structuredReport.value) {
      activeTab.value = "structured";
    } else if (content.value) {
      activeTab.value = "markdown";
    }

    reportMeta.value = buildMetaFromFilename(
      filename,
      content.value,
      structuredReport.value,
    );
  } catch (error) {
    console.error("加载报告失败:", error);
    reportMeta.value = null;
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  loadReport();
});
</script>

<style scoped>
.report-detail {
  max-width: 1280px;
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

.report-header-card,
.report-tabs-card,
.section-card,
.report-content-card {
  margin-bottom: 20px;
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
}

.report-title {
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  margin: 0 0 12px 0;
  line-height: 1.35;
}

.report-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.meta-divider {
  color: var(--border-color);
}

.artifact-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.artifact-pill {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px dashed var(--border-color);
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.72);
}

.artifact-pill.available {
  color: var(--primary-color);
  border-style: solid;
  border-color: rgba(37, 99, 235, 0.2);
  background: rgba(37, 99, 235, 0.08);
}

.header-actions {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
}

.tabs-row {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: center;
  flex-wrap: wrap;
}

.tabs-tip {
  font-size: 13px;
  color: var(--text-muted);
}

.section-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 18px;
  box-shadow: var(--shadow-sm);
  padding: 24px;
}

.section-title {
  margin-bottom: 18px;
  padding: 12px 16px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  border-radius: 14px;
  background: linear-gradient(
    135deg,
    rgba(37, 99, 235, 0.08),
    rgba(37, 99, 235, 0.02)
  );
  border-left: 4px solid var(--primary-color);
}

.preface-body p {
  margin: 12px 0;
  line-height: 1.9;
  color: var(--text-secondary);
}

.deep-read-grid,
.forecast-grid,
.compliance-groups,
.appendix-grid {
  display: grid;
  gap: 18px;
}

.deep-read-card,
.forecast-card,
.compliance-group,
.appendix-card {
  border: 1px solid var(--border-color);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.9),
    rgba(248, 250, 252, 0.95)
  );
  border-radius: 18px;
  padding: 18px 20px;
}

.deep-read-card h3,
.forecast-card h3,
.compliance-group h3,
.appendix-card h3 {
  margin: 0 0 12px;
  font-size: 18px;
  color: var(--text-primary);
}

.deep-read-index {
  display: inline-flex;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 700;
  border-radius: 999px;
  margin-bottom: 12px;
  color: var(--primary-color);
  background: rgba(37, 99, 235, 0.1);
}

.verdict-box {
  padding: 12px 14px;
  margin-bottom: 14px;
  font-weight: 700;
  color: var(--text-primary);
  background: rgba(16, 185, 129, 0.08);
  border-left: 4px solid #10b981;
  border-radius: 0 12px 12px 0;
}

.opinion-list {
  padding-left: 20px;
  color: var(--text-secondary);
}

.quotes-grid {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.deep-read-block {
  margin-top: 16px;
}

.subsection-title {
  margin-bottom: 8px;
  font-size: 16px;
  font-weight: 800;
  color: var(--text-primary);
}

.quote-chip {
  padding: 10px 12px;
  border-radius: 12px;
  color: var(--text-secondary);
  background: var(--el-fill-color-extra-light, #f8fafc);
}

.summary-strip {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.summary-card {
  min-width: 180px;
  flex: 1;
  border-radius: 18px;
  border: 1px solid var(--border-color);
  background: linear-gradient(
    180deg,
    rgba(59, 130, 246, 0.08),
    rgba(59, 130, 246, 0.02)
  );
  padding: 18px;
}

.summary-label {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.summary-card strong {
  font-size: 28px;
  color: var(--text-primary);
}

.summary-narrative {
  margin: 18px 0 20px;
  padding: 18px 20px;
  border-radius: 16px;
  border: 1px solid var(--border-color);
  background: linear-gradient(
    180deg,
    rgba(37, 99, 235, 0.05),
    rgba(37, 99, 235, 0.01)
  );
  color: var(--text-secondary);
  line-height: 1.8;
}

.case-list {
  display: grid;
  gap: 12px;
}

.case-card {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid var(--border-color);
  background: rgba(255, 255, 255, 0.78);
}

.case-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.case-tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: var(--primary-color);
  background: rgba(37, 99, 235, 0.1);
}

.case-tag.risk-high {
  color: #b91c1c;
  background: rgba(185, 28, 28, 0.12);
}

.case-quote {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.case-detail {
  display: grid;
  gap: 4px;
  margin-top: 10px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.detail-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}

.forecast-point {
  margin-top: 12px;
  padding: 16px 18px;
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.92);
}

.forecast-summary-box {
  margin-bottom: 14px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(29, 78, 216, 0.12);
  background: linear-gradient(
    180deg,
    rgba(29, 78, 216, 0.08),
    rgba(29, 78, 216, 0.02)
  );
}

.forecast-summary-label {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 800;
  color: var(--primary-color);
  letter-spacing: 0.06em;
}

.forecast-summary-box p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.9;
}

.forecast-point-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.point-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 10px;
}

.point-paragraph {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.95;
}

.appendix-detail-list {
  display: grid;
  gap: 18px;
  margin-top: 18px;
}

.report-content-card :deep(.el-card__body) {
  overflow-x: auto;
  padding: 24px;
}

.markdown-panel-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}

.markdown-panel-header h3 {
  margin: 0 0 6px;
  font-size: 17px;
  color: var(--text-primary);
}

.markdown-panel-header p {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

.markdown-body {
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-primary);
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0 24px;
  table-layout: fixed;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--border-color);
  padding: 10px 12px;
  vertical-align: top;
}

.markdown-body :deep(th) {
  background: var(--el-fill-color-extra-light, #f8fafc);
}

.error-state {
  padding: 100px 0;
}

@media (max-width: 900px) {
  .report-header {
    flex-direction: column;
  }

  .header-actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .tabs-row,
  .markdown-panel-header,
  .forecast-point-header {
    flex-direction: column;
    align-items: stretch;
  }

  .summary-card {
    min-width: 0;
  }

  .section-card {
    padding: 18px 16px;
  }

  .report-title {
    font-size: 24px;
  }

  .section-title {
    font-size: 17px;
  }

  .case-card,
  .forecast-point,
  .deep-read-card,
  .appendix-card {
    padding: 14px;
  }

  .markdown-body {
    font-size: 14px;
  }
}
</style>
