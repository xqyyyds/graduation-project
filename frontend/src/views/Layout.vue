<template>
  <el-container class="layout-container">
    <!-- 侧边栏 -->
    <el-aside :width="sidebarCollapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo-container">
        <div class="logo">
          <el-icon :size="28" color="#10b981"><DataAnalysis /></el-icon>
          <span v-show="!sidebarCollapsed" class="logo-text">舆情研判平台</span>
        </div>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="sidebarCollapsed"
        :collapse-transition="false"
        router
        class="sidebar-menu"
      >
        <template v-for="route in menuRoutes" :key="route.path">
          <el-menu-item
            :index="
              route.path && route.path.startsWith('/')
                ? route.path
                : '/' + route.path
            "
          >
            <el-icon><component :is="route.meta.icon" /></el-icon>
            <template #title>{{ route.meta.title }}</template>
          </el-menu-item>
        </template>
      </el-menu>

      <!-- 折叠按钮 -->
      <div class="collapse-btn" @click="toggleSidebar">
        <el-icon :size="18">
          <Fold v-if="!sidebarCollapsed" />
          <Expand v-else />
        </el-icon>
      </div>
    </el-aside>

    <!-- 主内容区 -->
    <el-container class="main-container">
      <!-- 顶部栏 -->
      <el-header class="header">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tag v-if="isTaskRunning" type="warning" effect="light">
            <el-icon class="is-loading"><Loading /></el-icon>
            任务运行中
          </el-tag>
          <span class="current-time">{{ currentTime }}</span>
        </div>
      </el-header>

      <!-- 内容区 -->
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
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

const route = useRoute();
const store = useAppStore();

const sidebarCollapsed = computed(() => store.sidebarCollapsed);
const isTaskRunning = computed(() => store.isTaskRunning);
const toggleSidebar = () => store.toggleSidebar();

// 当前时间
const currentTime = ref("");
let timer = null;

const updateTime = () => {
  const now = new Date();
  currentTime.value = now.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

// 菜单路由
const menuRoutes = computed(() => {
  const layoutRoute = route.matched.find((r) => r.name === "Layout");
  if (layoutRoute && layoutRoute.children) {
    return layoutRoute.children.filter((r) => !r.meta?.hidden);
  }
  return [];
});

// 当前激活菜单：找到匹配的顶级子路由，保证在子路由（如 /reports/xxx）时仍高亮父菜单
const activeMenu = computed(() => {
  const path = route.path || "/";
  const menus = menuRoutes.value || [];
  // 找到第一个其 path 与当前路由前缀匹配的菜单项
  const matched = menus.find((r) => {
    const menuPath = r.path && r.path.startsWith("/") ? r.path : "/" + r.path;
    return path === menuPath || path.startsWith(menuPath + "/");
  });
  if (matched) {
    return matched.path && matched.path.startsWith("/")
      ? matched.path
      : "/" + matched.path;
  }
  return path;
});

// 当前标题
const currentTitle = computed(() => {
  return route.meta?.title || "首页";
});

onMounted(() => {
  updateTime();
  timer = setInterval(updateTime, 1000);
  // 恢复任务轮询
  store.restoreTaskPolling();
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<style scoped>
.layout-container {
  height: 100vh;
  background: #f8fafc;
}

/* 侧边栏 */
.sidebar {
  background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  overflow: hidden;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
}

.logo-container {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(0, 0, 0, 0.1);
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-text {
  color: #fff;
  font-size: 17px;
  font-weight: 700;
  white-space: nowrap;
  letter-spacing: 0.5px;
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  background: transparent;
  padding: 16px 0;
}

.sidebar-menu:not(.el-menu--collapse) {
  width: 100%;
}

:deep(.el-menu-item) {
  color: rgba(255, 255, 255, 0.65);
  margin: 6px 12px;
  border-radius: 10px;
  height: 48px;
  transition: all 0.2s;
}

:deep(.el-menu--collapse .el-menu-item) {
  margin: 6px 8px;
  padding: 0 !important;
  display: flex;
  justify-content: center;
}

:deep(.el-menu-item:hover) {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
}

:deep(.el-menu-item.is-active) {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
}

:deep(.el-menu--collapse .el-menu-item.is-active) {
  width: 48px;
  height: 48px;
  margin: 6px auto;
  border-radius: 12px;
}

:deep(.el-menu-item .el-icon) {
  font-size: 20px;
}

.collapse-btn {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  transition: all 0.3s;
}

.collapse-btn:hover {
  color: #10b981;
  background: rgba(16, 185, 129, 0.1);
}

/* 主容器 */
.main-container {
  flex: 1;
  overflow: hidden;
}

/* 顶部栏 */
.header {
  height: 64px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  border-bottom: 1px solid #f1f5f9;
}

.header-left {
  display: flex;
  align-items: center;
}

:deep(.el-breadcrumb__item) {
  font-size: 14px;
}

:deep(.el-breadcrumb__inner) {
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.header-right .el-tag {
  font-weight: 500;
  padding: 6px 12px;
}

.current-time {
  color: #64748b;
  font-size: 14px;
  font-weight: 500;
  font-family: "SF Mono", Monaco, monospace;
}

/* 主内容 */
.main-content {
  padding: 24px;
  overflow-y: auto;
  background: #f8fafc;
}

/* 过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
