<template>
  <div class="logs-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">系统日志</h1>
        <p class="page-desc">实时查看后端运行状态和任务执行日志</p>
      </div>
      <div class="header-right">
        <el-tag :type="connected ? 'success' : 'danger'" effect="plain">
          <el-icon><Connection /></el-icon>
          {{ connected ? "已连接" : "未连接" }}
        </el-tag>
        <el-button @click="clearLogs" :disabled="logs.length === 0">
          <el-icon><Delete /></el-icon>
          清空日志
        </el-button>
        <el-switch
          v-model="autoScroll"
          active-text="自动滚动"
          inactive-text=""
        />
      </div>
    </div>

    <!-- 日志终端 -->
    <el-card class="terminal-card" shadow="never">
      <div class="terminal" ref="terminalRef">
        <div
          v-for="(log, index) in logs"
          :key="index"
          class="log-line"
          :class="getLogClass(log.level)"
        >
          <span class="log-time">{{ log.timestamp }}</span>
          <span class="log-level">{{ log.level }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
        <div v-if="logs.length === 0" class="empty-logs">
          <el-icon :size="48" color="#9ca3af"><Monitor /></el-icon>
          <p>暂无日志，等待后端输出...</p>
        </div>
      </div>
    </el-card>

    <!-- 统计信息 -->
    <div class="logs-stats">
      <span>共 {{ logs.length }} 条日志</span>
      <span class="stat-item info">
        <el-icon><InfoFilled /></el-icon>
        INFO: {{ countByLevel("INFO") }}
      </span>
      <span class="stat-item warning">
        <el-icon><Warning /></el-icon>
        WARNING: {{ countByLevel("WARNING") }}
      </span>
      <span class="stat-item error">
        <el-icon><CircleClose /></el-icon>
        ERROR: {{ countByLevel("ERROR") }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from "vue";

const logs = ref([]);
const connected = ref(false);
const autoScroll = ref(true);
const terminalRef = ref(null);

let ws = null;
let reconnectTimer = null;

// 连接 WebSocket
const connectWebSocket = () => {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  ws = new WebSocket("ws://localhost:8000/ws/logs");

  ws.onopen = () => {
    connected.value = true;
    console.log("WebSocket 已连接");
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      logs.value.push(data);

      // 限制日志数量
      if (logs.value.length > 1000) {
        logs.value = logs.value.slice(-800);
      }

      // 自动滚动
      if (autoScroll.value) {
        nextTick(() => {
          scrollToBottom();
        });
      }
    } catch (e) {
      // 可能是 pong 响应
    }
  };

  ws.onclose = () => {
    connected.value = false;
    console.log("WebSocket 已断开，5秒后重连...");
    reconnectTimer = setTimeout(connectWebSocket, 5000);
  };

  ws.onerror = (error) => {
    console.error("WebSocket 错误:", error);
    connected.value = false;
  };
};

// 发送心跳
const startHeartbeat = () => {
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send("ping");
    }
  }, 30000);
};

// 滚动到底部
const scrollToBottom = () => {
  if (terminalRef.value) {
    terminalRef.value.scrollTop = terminalRef.value.scrollHeight;
  }
};

// 清空日志
const clearLogs = () => {
  logs.value = [];
};

// 根据级别获取样式类
const getLogClass = (level) => {
  const map = {
    INFO: "log-info",
    WARNING: "log-warning",
    WARN: "log-warning",
    ERROR: "log-error",
    DEBUG: "log-debug",
  };
  return map[level] || "log-info";
};

// 统计某级别日志数量
const countByLevel = (level) => {
  return logs.value.filter((l) => l.level === level).length;
};

// 监听自动滚动变化
watch(autoScroll, (val) => {
  if (val) {
    nextTick(() => {
      scrollToBottom();
    });
  }
});

onMounted(() => {
  connectWebSocket();
  startHeartbeat();
});

onBeforeUnmount(() => {
  if (ws) {
    ws.close();
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
  }
});
</script>

<style scoped>
.logs-page {
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

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 终端样式 */
.terminal-card {
  margin-bottom: 16px;
}

.terminal {
  background: #1e1e1e;
  border-radius: 8px;
  padding: 16px;
  height: 500px;
  overflow-y: auto;
  font-family: "Cascadia Code", "Fira Code", "Monaco", "Consolas", monospace;
  font-size: 13px;
  line-height: 1.6;
}

/* 滚动条样式 */
.terminal::-webkit-scrollbar {
  width: 8px;
}

.terminal::-webkit-scrollbar-track {
  background: #2d2d2d;
  border-radius: 4px;
}

.terminal::-webkit-scrollbar-thumb {
  background: #555;
  border-radius: 4px;
}

.terminal::-webkit-scrollbar-thumb:hover {
  background: #666;
}

/* 日志行 */
.log-line {
  display: flex;
  gap: 12px;
  padding: 2px 0;
  word-break: break-all;
}

.log-time {
  color: #858585;
  flex-shrink: 0;
}

.log-level {
  min-width: 60px;
  flex-shrink: 0;
  font-weight: 600;
}

.log-message {
  color: #d4d4d4;
}

/* 日志级别颜色 */
.log-info .log-level {
  color: #4fc1ff;
}

.log-warning .log-level {
  color: #f59e0b;
}

.log-warning .log-message {
  color: #fcd34d;
}

.log-error .log-level {
  color: #ef4444;
}

.log-error .log-message {
  color: #fca5a5;
}

.log-debug .log-level {
  color: #a78bfa;
}

/* 空状态 */
.empty-logs {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #6b7280;
}

.empty-logs p {
  margin-top: 16px;
}

/* 统计信息 */
.logs-stats {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 16px;
  background: #f9fafb;
  border-radius: 8px;
  font-size: 14px;
  color: #6b7280;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.stat-item.info {
  color: #3b82f6;
}

.stat-item.warning {
  color: #f59e0b;
}

.stat-item.error {
  color: #ef4444;
}
</style>
