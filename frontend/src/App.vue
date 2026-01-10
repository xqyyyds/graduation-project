<template>
  <router-view />
</template>

<script setup>
import { onMounted, watch } from "vue";
import { useAppStore } from "./stores/app";
import { TinyColor } from "@ctrl/tinycolor";
import "element-plus/theme-chalk/dark/css-vars.css";

const store = useAppStore();

const applyTheme = () => {
  const { primaryColor, isDark } = store.themeConfig;
  const el = document.documentElement;

  // 1. 处理暗黑模式 Class
  if (isDark) {
    el.classList.add("dark");
  } else {
    el.classList.remove("dark");
  }

  // 2. 设置 Element Plus 主题色核心变量
  // 必须设置 --el-color-primary，Element Plus 组件才会变色
  el.style.setProperty("--el-color-primary", primaryColor);
  el.style.setProperty("--primary-color", primaryColor);

  // 3. 生成色阶 (Light 1-9 & Dark 2)
  // 这是按钮渐变色能生效的关键！
  const baseColor = new TinyColor(primaryColor);

  for (let i = 1; i <= 9; i++) {
    el.style.setProperty(
      `--el-color-primary-light-${i}`,
      baseColor.mix("#ffffff", i * 10).toHexString()
    );
  }

  el.style.setProperty(
    `--el-color-primary-dark-2`,
    baseColor.mix("#000000", 20).toHexString()
  );
};

// 监听配置变化
watch(() => store.themeConfig, applyTheme, { deep: true });

// 初始化
onMounted(() => {
  applyTheme();
});
</script>

<style>
/* 全局宽高设定，防止布局塌陷 */
html,
body,
#app {
  height: 100%;
  margin: 0;
  padding: 0;
}
</style>
