<template>
  <el-container class="layout-container">
    <el-aside :width="sidebarCollapsed ? '70px' : '240px'" class="app-sidebar">
      <div class="logo-area">
        <div class="logo-icon-box">
          <el-icon :size="24" color="#fff"><DataAnalysis /></el-icon>
        </div>
        <transition name="fade">
          <span v-show="!sidebarCollapsed" class="logo-text">舆情研判平台</span>
        </transition>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="sidebarCollapsed"
        background-color="transparent"
        text-color="#94a3b8"
        active-text-color="#fff"
        :collapse-transition="false"
        router
        class="sidebar-menu"
      >
        <template v-for="route in menuRoutes" :key="route.path">
          <el-menu-item
            :index="route.path.startsWith('/') ? route.path : '/' + route.path"
            class="menu-item"
          >
            <el-icon><component :is="route.meta.icon" /></el-icon>
            <template #title>
              <span class="menu-title">{{ route.meta.title }}</span>
            </template>
          </el-menu-item>
        </template>
      </el-menu>

      <div class="sidebar-footer" @click="toggleSidebar">
        <el-icon :class="{ 'rotate-180': sidebarCollapsed }"><Fold /></el-icon>
      </div>
    </el-aside>

    <el-container class="main-wrapper">
      <el-header class="app-header">
        <div class="header-left">
          <el-breadcrumb separator-class="el-icon-arrow-right">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="header-right">
          <transition name="fade">
            <div v-if="isTaskRunning" class="status-indicator running">
              <span class="pulse-dot"></span>
              <span>分析引擎运行中</span>
            </div>
          </transition>

          <div class="time-display">{{ currentTime }}</div>

          <el-avatar :size="32" class="user-avatar" style="background: #3b82f6"
            >Xqr</el-avatar
          >
        </div>
      </el-header>

      <el-main class="app-content">
        <router-view v-slot="{ Component }">
          <transition name="slide-up" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import { useAppStore } from "../stores/app";
import dayjs from "dayjs";

const route = useRoute();
const store = useAppStore();

const sidebarCollapsed = computed(() => store.sidebarCollapsed);
const isTaskRunning = computed(() => store.isTaskRunning);
const toggleSidebar = () => store.toggleSidebar();

const currentTime = ref("");
let timer = null;

const updateTime = () => {
  currentTime.value = dayjs().format("HH:mm:ss");
};

const menuRoutes = computed(() => {
  const layoutRoute = route.matched.find((r) => r.name === "Layout");
  return layoutRoute?.children?.filter((r) => !r.meta?.hidden) || [];
});

const activeMenu = computed(() => route.path);
const currentTitle = computed(() => route.meta?.title || "首页");

onMounted(() => {
  updateTime();
  timer = setInterval(updateTime, 1000);
  store.restoreTaskPolling();
});

onUnmounted(() => {
  clearInterval(timer);
});
</script>

<style scoped>
.layout-container {
  height: 100vh;
  width: 100vw;
  background-color: var(--bg-body);
}

/* 侧边栏：深空蓝风格 */
.app-sidebar {
  background-color: var(--bg-sidebar);
  border-right: 1px solid rgba(255, 255, 255, 0.05);
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  z-index: 20;
}

.logo-area {
  height: 70px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  overflow: hidden;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.logo-icon-box {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 0 15px rgba(37, 99, 235, 0.4);
}

.logo-text {
  margin-left: 12px;
  font-size: 16px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  padding-top: 16px;
}

/* 菜单项深度定制 */
:deep(.menu-item) {
  margin: 4px 12px;
  border-radius: 8px;
  height: 50px;
  transition: all 0.2s;
}

:deep(.menu-item:hover) {
  background-color: rgba(255, 255, 255, 0.08) !important;
  color: #fff !important;
}

:deep(.menu-item.is-active) {
  background: linear-gradient(90deg, #2563eb 0%, #1d4ed8 100%) !important;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
  color: #fff !important;
}

:deep(.menu-item .el-icon) {
  font-size: 20px;
  margin-right: 12px;
}

:deep(.el-menu--collapse .menu-item .el-icon) {
  margin-right: 0;
}

.sidebar-footer {
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  cursor: pointer;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  transition: all 0.2s;
}
.sidebar-footer:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.05);
}

/* 主区域 */
.main-wrapper {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.app-header {
  height: 64px;
  background: var(--el-bg-color-overlay, rgba(255, 255, 255, 0.8));
  backdrop-filter: blur(8px); /* 微调毛玻璃强度 */
  border-bottom: 1px solid
    var(--el-border-color-light, rgba(226, 232, 240, 0.8));
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  z-index: 10;
  position: sticky;
  top: 0;
  transition: background-color 0.2s, border-color 0.2s;
}

/* 任务状态指示灯 */
.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(16, 185, 129, 0.08); /* subtle */
  border-radius: 20px;
  font-size: 12px;
  color: var(--success-color, #059669);
  font-weight: 500;
  margin-right: 20px;
}
.pulse-dot {
  background: var(--success-color, #10b981);
}
.pulse-dot {
  width: 8px;
  height: 8px;
  background: #10b981;
  border-radius: 50%;
  animation: pulse 1.5s infinite;
}
@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4);
  }
  70% {
    box-shadow: 0 0 0 6px rgba(16, 185, 129, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
  }
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.time-display {
  font-family: "Inter", monospace;
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 14px;
}

.user-avatar {
  cursor: pointer;
  border: 2px solid #fff;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
}

.app-content {
  padding: 24px;
  overflow-y: auto;
  scroll-behavior: smooth;
}

.rotate-180 {
  transform: rotate(180deg);
}
</style>
