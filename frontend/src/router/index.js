import { createRouter, createWebHistory } from "vue-router";

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
        meta: { title: "驾驶舱", icon: "Odometer" },
      },
      {
        path: "task",
        name: "Task",
        component: () => import("../views/Task.vue"),
        meta: { title: "任务管理", icon: "Operation" },
      },
      {
        path: "reports",
        name: "Reports",
        component: () => import("../views/Reports.vue"),
        meta: { title: "历史报告", icon: "Document" },
      },
      {
        path: "reports/:filename",
        name: "ReportDetail",
        component: () => import("../views/ReportDetail.vue"),
        meta: { title: "报告详情", hidden: true },
      },
      {
        path: "logs",
        name: "Logs",
        component: () => import("../views/Logs.vue"),
        meta: { title: "系统日志", icon: "Monitor" },
      },
      {
        path: "settings",
        name: "Settings",
        component: () => import("../views/Settings.vue"),
        meta: { title: "系统设置", icon: "Setting" },
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
