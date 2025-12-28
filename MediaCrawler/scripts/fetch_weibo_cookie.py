import sys
import time
import json
from pathlib import Path

# --- 1. 路径配置 ---
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
ENV_PATH = PROJECT_ROOT / ".env"
CFG_DIR = PROJECT_ROOT / "config"
STATE_PATH = CFG_DIR / "weibo_state.json"


# --- 2. 写入 .env 的工具函数 ---
def write_env_cookie(cookie_str: str) -> None:
    print(f"📂 更新 .env 文件: {ENV_PATH}")
    if not ENV_PATH.parent.exists():
        ENV_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if ENV_PATH.exists():
        try:
            lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        except:
            lines = []

    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith("WEIBO_COOKIE"):
            lines[i] = f"WEIBO_COOKIE={cookie_str}"
            updated = True
            break

    if not updated:
        lines.append(f"WEIBO_COOKIE={cookie_str}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("✅ .env 写入成功！")


# --- 3. 核心逻辑 ---
def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ 未安装 Playwright，请运行: uv add playwright")
        return

    CFG_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # 🟢 [关键点1] 启动参数优化 (MediaCrawler 同款配置)
        # 这些参数能极大减少显卡报错、黑屏，并移除自动化标记
        browser = p.chromium.launch(
            headless=False,
            chromium_sandbox=False,
            args=[
                "--disable-blink-features=AutomationControlled",  # 核心：去除自动化标记
                "--no-sandbox",
                "--disable-gpu",
                "--disable-infobars",
                "--window-size=1280,800",
                "--disable-dev-shm-usage",
            ],
        )

        # 🟢 [关键点2] 创建上下文时伪装 User-Agent
        # 这一步非常重要，防止微博识别出你是 Python 脚本
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            permissions=["geolocation"],  # 模拟正常权限
        )

        # 🟢 [关键点3] 注入反检测脚本 (Stealth 模式)
        # 在页面加载前，先修改浏览器属性，抹除 selenium/webdriver 特征
        context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """
        )

        page = context.new_page()

        print("🚀 正在加载微博登录页 (已开启防检测模式)...")
        try:
            # 使用 login.php 更纯净，干扰元素少
            page.goto("https://weibo.com/login.php", timeout=60000)
        except Exception:
            print("⚠️ 页面加载较慢，请直接扫码...")

        # 自动获取当前页面的 SUB；若已有登录态会直接得到，若无则会是游客 SUB
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        cookies = context.cookies()
        sub_val = None
        for c in cookies:
            if c.get("name") == "SUB":
                sub_val = c.get("value")
                break

        if sub_val:
            context.storage_state(path=str(STATE_PATH))
            print(f"✅ 浏览器状态已保存: {STATE_PATH}")

            final_str = f"SUB={sub_val};"
            write_env_cookie(final_str)
            print(f"🔑 核心 Cookie: {final_str[:40]}...")
        else:
            print("❌ 未获取到 SUB Cookie，页面可能未加载或账号未登录")

        browser.close()


if __name__ == "__main__":
    main()
