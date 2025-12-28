import time
import subprocess
import os
from datetime import datetime
import sys

# ================= 配置区域 =================
# 1. 自动计算项目根目录 (E:\graduation-project\MediaCrawler)
# 当前脚本所在目录: ...\MediaCrawler\scripts
current_script_dir = os.path.dirname(os.path.abspath(__file__))
# 项目根目录 (父目录): ...\MediaCrawler
PROJECT_ROOT = os.path.dirname(current_script_dir)

# 2. 要执行的命令
# 注意：这里路径是相对于项目根目录的
COMMAND = ["uv", "run", r"scripts\run_weibo_hot_and_search.py"]

# 3. 每天执行的时间点
SCHEDULE_TIMES = ["10:00", "15:00", "21:22"]
# ===========================================

def run_spider():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ 时间到了，开始执行爬虫任务...")
    print(f"📍 执行目录(CWD): {PROJECT_ROOT}")
    
    try:
        # cwd=PROJECT_ROOT 是核心！确保命令像是在根目录执行的一样
        result = subprocess.run(COMMAND, cwd=PROJECT_ROOT, shell=True)
        
        if result.returncode == 0:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ 爬虫执行完成！")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ 爬虫执行出错，返回码: {result.returncode}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ 发生异常: {e}")

def main():
    print(f"🚀 爬虫调度器已启动！(脚本位置: {current_script_dir})")
    print(f"📂 锁定项目根目录: {PROJECT_ROOT}")
    print(f"📅 计划时间: {', '.join(SCHEDULE_TIMES)}")
    print("----------------------------------------")

    last_run_time = None

    while True:
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")

        if current_time_str in SCHEDULE_TIMES:
            # 防止同一分钟内重复触发
            if current_time_str != last_run_time:
                run_spider()
                last_run_time = current_time_str
        
        # 节省资源，每30秒检查一次
        time.sleep(30)

if __name__ == "__main__":
    main()