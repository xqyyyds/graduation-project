<template>
  <div class="logs-container">
    <div class="logs-toolbar">
      <div class="toolbar-left">
        <h2 class="terminal-title">
          <el-icon><Monitor /></el-icon> SYSTEM KERNEL LOGS
        </h2>
      </div>
      <div class="toolbar-right">
        <div class="connection-status" :class="{ active: connected }">
          <span class="status-dot"></span>
          {{ connected ? 'CONNECTED' : 'DISCONNECTED' }}
        </div>
        <el-divider direction="vertical" />
        <el-switch v-model="autoScroll" active-text="Auto-Scroll" size="small" />
        <el-button type="danger" size="small" plain @click="clearLogs" :icon="Delete">Clear</el-button>
      </div>
    </div>

    <div class="terminal-window" ref="terminalRef">
      <div class="terminal-content">
        <div v-if="logs.length === 0" class="terminal-placeholder">
          <el-icon :size="60"><Promotion /></el-icon>
          <p>Waiting for data stream...</p>
        </div>
        
        <div v-for="(log, index) in logs" :key="index" class="log-row" :class="getLogClass(log.level)">
          <span class="log-gutter">{{ index + 1 }}</span>
          <span class="log-time">[{{ log.timestamp }}]</span>
          <span class="log-level">{{ log.level }}</span>
          <span class="log-msg">{{ log.message }}</span>
        </div>
      </div>
    </div>

    <div class="status-bar">
      <div class="sb-section">
        <el-icon><List /></el-icon>
        <span>Total: {{ logs.length }}</span>
      </div>
      <div class="sb-section info">
        <span>INFO: {{ countByLevel("INFO") }}</span>
      </div>
      <div class="sb-section warning" v-if="countByLevel('WARNING') > 0">
        <el-icon><Warning /></el-icon>
        <span>WARN: {{ countByLevel("WARNING") }}</span>
      </div>
      <div class="sb-section error" v-if="countByLevel('ERROR') > 0">
        <el-icon><CircleClose /></el-icon>
        <span>ERR: {{ countByLevel("ERROR") }}</span>
      </div>
      <div class="sb-spacer"></div>
      <div class="sb-section">
        <span>UTF-8</span>
      </div>
      <div class="sb-section">
        <span>Port: 8000</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from "vue";
import { Delete, Monitor, Promotion, Warning, CircleClose, List } from '@element-plus/icons-vue';

// 核心数据
const logs = ref([]);
const connected = ref(false);
const autoScroll = ref(true);
const terminalRef = ref(null);

// WebSocket 变量
let ws = null;
let reconnectTimer = null;
let heartbeatTimer = null;

// 1. 真实的 WebSocket 连接逻辑
const connectWebSocket = () => {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  // ⚠️ 连接到你的真实后端地址
  ws = new WebSocket("ws://localhost:8000/ws/logs");

  ws.onopen = () => {
    connected.value = true;
    console.log("System Terminal: Connection Established.");
    startHeartbeat();
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      
      // 添加日志到数组
      logs.value.push(data);

      // 性能优化：限制前端只保留最近 1000 条日志
      if (logs.value.length > 1000) {
        logs.value = logs.value.slice(-800);
      }

      // 自动滚动处理
      if (autoScroll.value) {
        nextTick(() => {
          scrollToBottom();
        });
      }
    } catch (e) {
      // 忽略非 JSON 格式的心跳响应 (pong)
    }
  };

  ws.onclose = () => {
    connected.value = false;
    console.warn("System Terminal: Connection Lost. Retrying in 5s...");
    stopHeartbeat();
    // 断线重连机制
    reconnectTimer = setTimeout(connectWebSocket, 5000);
  };

  ws.onerror = (error) => {
    console.error("WebSocket Error:", error);
    connected.value = false;
  };
};

// 2. 心跳保活 (防止长时间无日志自动断开)
const startHeartbeat = () => {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send("ping");
    }
  }, 30000); // 30秒一次
};

const stopHeartbeat = () => {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
};

// 3. 辅助功能
const scrollToBottom = () => {
  if (terminalRef.value) {
    terminalRef.value.scrollTop = terminalRef.value.scrollHeight;
  }
};

const clearLogs = () => {
  logs.value = [];
};

// 统计逻辑
const countByLevel = (lvl) => {
  if (lvl === 'WARNING') {
    return logs.value.filter(l => l.level === 'WARNING' || l.level === 'WARN').length;
  }
  return logs.value.filter(l => l.level === lvl).length;
};

// 样式映射
const getLogClass = (lvl) => {
  const map = { 
    'INFO': 'l-info', 
    'WARNING': 'l-warn', 'WARN': 'l-warn',
    'ERROR': 'l-err', 
    'DEBUG': 'l-debug' 
  };
  return map[lvl] || 'l-info';
};

// 监听自动滚动开关
watch(autoScroll, (val) => {
  if (val) nextTick(scrollToBottom);
});

// 生命周期管理
onMounted(() => {
  connectWebSocket();
  startHeartbeat();
});

onBeforeUnmount(() => {
  if (ws) ws.close();
  if (reconnectTimer) clearTimeout(reconnectTimer);
  stopHeartbeat();
});
</script>

<style scoped>
.logs-container {
  display: flex; flex-direction: column; height: calc(100vh - 120px); /* 减去顶部Header高度 */
  background: #1e1e1e; border-radius: 12px; overflow: hidden;
  box-shadow: 0 10px 30px rgba(0,0,0,0.2); border: 1px solid #333;
}

/* 工具栏 */
.logs-toolbar {
  height: 48px; background: #252526; display: flex; align-items: center; justify-content: space-between;
  padding: 0 16px; border-bottom: 1px solid #333;
}
.terminal-title {
  color: #ccc; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px; margin: 0; letter-spacing: 0.5px;
}
.toolbar-right { display: flex; align-items: center; gap: 12px; }

.connection-status { font-size: 12px; color: #666; display: flex; align-items: center; gap: 6px; font-weight: 600; }
.connection-status.active { color: #10b981; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

/* 终端窗口 */
.terminal-window {
  flex: 1; overflow-y: auto; padding: 10px 0;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 13px; line-height: 1.5; color: #d4d4d4;
  background-image: repeating-linear-gradient(0deg, transparent, transparent 1px, #222 1px, #222 2px); /* 扫描线效果微弱背景 */
  background-size: 100% 4px;
}
.terminal-content { padding: 0 16px; }

/* 滚动条 */
.terminal-window::-webkit-scrollbar { width: 10px; background: #1e1e1e; }
.terminal-window::-webkit-scrollbar-thumb { background: #424242; border-radius: 5px; border: 2px solid #1e1e1e; }

/* 日志行 */
.log-row { display: flex; gap: 12px; padding: 2px 0; border-bottom: 1px solid rgba(255,255,255,0.02); }
.log-row:hover { background: rgba(255,255,255,0.05); }

.log-gutter { color: #555; width: 40px; text-align: right; user-select: none; font-size: 12px; }
.log-time { color: #569cd6; }
.log-level { width: 60px; font-weight: bold; }
.log-msg { white-space: pre-wrap; word-break: break-all; flex: 1; }

.l-info .log-level { color: #4fc1ff; }
.l-warn .log-level { color: #dcdcaa; }
.l-warn .log-msg { color: #dcdcaa; }
.l-err .log-level { color: #f44747; }
.l-err .log-msg { color: #ff8080; }

.terminal-placeholder {
  height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: #444; margin-top: 100px;
}

/* 底部状态栏 */
.status-bar {
  height: 24px; background: #007acc; color: #fff; display: flex; align-items: center;
  font-family: sans-serif; font-size: 11px; padding: 0 8px; cursor: default;
}
.sb-section { padding: 0 8px; display: flex; align-items: center; gap: 4px; height: 100%; }
.sb-section:hover { background: rgba(255,255,255,0.1); }
.sb-section.warning { background: #cca700; }
.sb-section.error { background: #c90000; }
.sb-spacer { flex: 1; }
</style>