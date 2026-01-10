import { createRouter, createWebHistory } from "vue-router";

// 路由表配置
const routes = [
  {
    path: "/",
    name: "Layout",
    component: () => import("../views/Layout.vue"),
    redirect: "/dashboard",
    children: [
      {
        path: "dashboard",
        name: "Dashboard",
        component: () => import("../views/Dashboard.vue"),
        // 驾驶舱 -> 改用 DataLine (折线图图标) 更符合数据大屏感觉
        meta: { title: "驾驶舱", icon: "DataLine" },
      },
      {
        path: "task",
        name: "Task",
        component: () => import("../views/Task.vue"),
        // 任务管理 -> 改用 Cpu (芯片/处理) 更符合 AI 研判的感觉
        meta: { title: "任务管理", icon: "Cpu" },
      },
      {
        path: "reports",
        name: "Reports",
        component: () => import("../views/Reports.vue"),
        // 历史报告 -> 改用 Collection (档案集)
        meta: { title: "历史报告", icon: "Collection" },
      },
      {
        path: "reports/:filename",
        name: "ReportDetail",
        component: () => import("../views/ReportDetail.vue"),
        // 详情页 -> 隐藏侧边栏菜单
        meta: { title: "报告详情", hidden: true },
      },
      {
        path: "logs",
        name: "Logs",
        component: () => import("../views/Logs.vue"),
        // 系统日志 -> Monitor (显示器/终端)
        meta: { title: "系统日志", icon: "Monitor" },
      },
      {
        path: "settings",
        name: "Settings",
        component: () => import("../views/Settings.vue"),
        // 系统设置 -> Setting
        meta: { title: "系统设置", icon: "Setting" },
      },
    ],
  },
];

const router = createRouter({
  // 使用 HTML5 History 模式
  history: createWebHistory(),
  routes,
  // 切换路由时滚动到顶部
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition;
    } else {
      return { top: 0 };
    }
  },
});

export default router;