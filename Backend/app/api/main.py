"""
FastAPI 后端入口
舆情研判系统 API
"""

import os
import glob
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from pathlib import Path
from collections import deque

from fastapi import (
    FastAPI,
    HTTPException,
    BackgroundTasks,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# 导入工作流
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from main import run_task

app = FastAPI(
    title="舆情研判系统 API",
    description="社交媒体舆情分析与研判报告生成系统",
    version="1.0.0",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 输出目录
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"


# =====================================================
# 日志系统 - 用于前端实时显示
# =====================================================

# 存储最近的日志
log_buffer = deque(maxlen=500)

# WebSocket 连接管理
active_websockets: List[WebSocket] = []


class LogHandler(logging.Handler):
    """自定义日志处理器，将日志发送到前端"""

    def emit(self, record):
        log_entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": record.levelname,
            "message": self.format(record),
        }
        log_buffer.append(log_entry)

        # 安全地异步发送到所有连接的 WebSocket
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(broadcast_log(log_entry))
        except RuntimeError:
            # 如果在非异步上下文中调用
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(broadcast_log(log_entry), loop)
            except Exception:
                pass  # 静默失败，日志已经添加到 buffer


async def broadcast_log(log_entry):
    """广播日志到所有 WebSocket 连接"""
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(log_entry)
        except:
            disconnected.append(ws)

    # 清理断开的连接
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)


# 配置日志
def setup_logging():
    """配置日志系统"""
    handler = LogHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))

    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # 配置常用库的日志
    for logger_name in ["uvicorn", "uvicorn.access", "langchain", "openai"]:
        logger = logging.getLogger(logger_name)
        logger.addHandler(handler)


setup_logging()


# =====================================================
# 数据模型
# =====================================================


class TaskCreate(BaseModel):
    """创建任务请求"""

    start_date: Optional[str] = None
    end_date: Optional[str] = None
    category: str = "综合"
    forecast_range: str = "1m"


class TaskStatus(BaseModel):
    """任务状态"""

    task_id: str
    status: str  # running, completed, failed
    progress: int  # 0-100
    current_step: str
    message: str


class ReportSummary(BaseModel):
    """报告摘要"""

    filename: str
    title: str
    category: str
    created_at: str
    size: int


class DashboardStats(BaseModel):
    """仪表盘统计"""

    total_reports: int
    reports_today: int
    reports_this_week: int
    category_distribution: dict
    recent_reports: List[ReportSummary]


# =====================================================
# 任务状态存储 (生产环境应使用 Redis)
# =====================================================

task_store = {}


def update_task_progress(task_id: str, progress: int, step: str, message: str):
    """更新任务进度（供外部调用）"""
    if task_id in task_store:
        task_store[task_id] = {
            "status": "running",
            "progress": progress,
            "current_step": step,
            "message": message,
        }


async def execute_task(task_id: str, params: TaskCreate):
    """异步执行任务"""
    try:
        task_store[task_id] = {
            "status": "running",
            "progress": 5,
            "current_step": "初始化",
            "message": "正在启动任务...",
        }
        add_system_log("INFO", f"🚀 任务 {task_id} 开始执行")

        # 定义进度回调函数
        def progress_callback(progress: int, step: str, message: str):
            task_store[task_id] = {
                "status": "running",
                "progress": progress,
                "current_step": step,
                "message": message,
            }
            # 同时记录到日志
            add_system_log("INFO", f"[{step}] {message} ({progress}%)")

        # 注意：run_task 是同步、耗时的阻塞函数，不能在事件循环中直接调用。
        # 使用 asyncio.to_thread 将其移到线程池执行，避免阻塞 FastAPI
        await asyncio.to_thread(
            run_task,
            task_id,
            params.start_date,
            params.end_date,
            False,
            params.forecast_range,
            params.category,
            progress_callback,  # 传递进度回调
        )

        task_store[task_id] = {
            "status": "completed",
            "progress": 100,
            "current_step": "完成",
            "message": "报告生成成功",
        }
        add_system_log("INFO", f"✅ 任务 {task_id} 执行完成")
    except Exception as e:
        task_store[task_id] = {
            "status": "failed",
            "progress": 0,
            "current_step": "错误",
            "message": str(e),
        }
        add_system_log("ERROR", f"❌ 任务 {task_id} 执行失败: {str(e)}")


# =====================================================
# API 路由
# =====================================================


@app.get("/")
async def root():
    """健康检查"""
    return {"status": "ok", "message": "舆情研判系统 API 运行中"}


@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# =====================================================
# WebSocket 日志
# =====================================================


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket 端点，用于实时日志推送"""
    await websocket.accept()
    active_websockets.append(websocket)

    # 发送历史日志
    for log in list(log_buffer):
        await websocket.send_json(log)

    try:
        while True:
            # 保持连接，接收心跳
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)


@app.get("/api/logs/recent")
async def get_recent_logs(limit: int = 100):
    """获取最近的日志"""
    logs = list(log_buffer)[-limit:]
    return {"logs": logs}


def add_system_log(level: str, message: str):
    """添加系统日志（供其他模块调用）"""
    log_entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "level": level.upper(),
        "message": message,
    }
    log_buffer.append(log_entry)
    # 安全地创建异步任务，处理没有事件循环的情况
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_log(log_entry))
    except RuntimeError:
        # 如果在非异步上下文中调用（如线程池），使用 run_coroutine_threadsafe
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(broadcast_log(log_entry), loop)
        except Exception:
            pass  # 静默失败，日志已经添加到 buffer


@app.get("/api/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats():
    """获取仪表盘统计数据"""
    reports = list_all_reports()

    today = datetime.now().strftime("%Y%m%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")

    reports_today = sum(1 for r in reports if today in r.filename)
    reports_this_week = sum(
        1
        for r in reports
        if any(
            (datetime.now() - timedelta(days=i)).strftime("%Y%m%d") in r.filename
            for i in range(7)
        )
    )

    # 统计分类分布
    category_dist = {}
    for r in reports:
        cat = r.category
        category_dist[cat] = category_dist.get(cat, 0) + 1

    return DashboardStats(
        total_reports=len(reports),
        reports_today=reports_today,
        reports_this_week=reports_this_week,
        category_distribution=category_dist,
        recent_reports=reports[:10],  # 显示更多报告
    )


@app.get("/api/dashboard/latest-report/violations")
async def get_latest_report_violations():
    """返回最新 report_session 中持久化的违规类别合计统计（直接复用 Agent E 计算结果）。
    返回格式: { "category_counts": {cat: count}, "total_violated_posts": int, "total_violated_comments": int }
    如果不存在结构化统计，返回 { "category_counts": {} }（不再做 MD 解析回退）。"""
    try:
        sessions = mongo_db.get_report_history(limit=1)
        if sessions:
            latest_session = sessions[0]
            counts = latest_session.get("violation_category_counts")
            if isinstance(counts, dict):
                return {
                    "category_counts": counts,
                    "total_violated_posts": latest_session.get(
                        "total_violated_posts", 0
                    ),
                    "total_violated_comments": latest_session.get(
                        "total_violated_comments", 0
                    ),
                }
    except Exception as e:
        add_system_log("ERROR", f"读取 report_sessions 失败: {e}")

    # 未找到结构化统计，按要求不再回退解析 Markdown，直接返回空对象
    return {"category_counts": {}}


@app.post("/api/tasks", response_model=TaskStatus)
async def create_task(params: TaskCreate, background_tasks: BackgroundTasks):
    """创建新的研判任务"""
    # 生成任务ID
    today = datetime.now().strftime("%Y%m%d_%H%M")
    task_id = f"task_{today}"

    # 添加后台任务
    background_tasks.add_task(execute_task, task_id, params)

    task_store[task_id] = {
        "status": "running",
        "progress": 0,
        "current_step": "初始化",
        "message": "任务已创建，正在排队...",
    }

    return TaskStatus(
        task_id=task_id,
        status="running",
        progress=0,
        current_step="初始化",
        message="任务已创建",
    )


@app.get("/api/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    info = task_store[task_id]
    return TaskStatus(task_id=task_id, **info)


@app.get("/api/reports", response_model=List[ReportSummary])
async def get_reports(category: Optional[str] = None):
    """获取报告列表"""
    reports = list_all_reports()

    if category and category != "全部":
        reports = [r for r in reports if r.category == category]

    return reports


@app.get("/api/reports/{filename}")
async def get_report_content(filename: str):
    """获取报告内容"""
    file_path = OUTPUT_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="报告不存在")

    content = file_path.read_text(encoding="utf-8")
    return {"filename": filename, "content": content}


@app.get("/api/reports/{filename}/download")
async def download_report(filename: str):
    """下载报告文件"""
    file_path = OUTPUT_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="报告不存在")

    return FileResponse(path=file_path, filename=filename, media_type="text/markdown")


@app.delete("/api/reports/{filename}")
async def delete_report(filename: str):
    """删除报告文件"""
    file_path = OUTPUT_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="报告不存在")

    try:
        file_path.unlink()
        return {"status": "ok", "message": f"报告 {filename} 已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


def list_all_reports() -> List[ReportSummary]:
    """列出所有报告"""
    reports = []

    if not OUTPUT_DIR.exists():
        return reports

    for file_path in sorted(OUTPUT_DIR.glob("*.md"), reverse=True):
        filename = file_path.name
        stat = file_path.stat()

        # 解析文件名提取信息
        # 格式: 舆情研判_分类_日期_时间.md 或 舆情研判_日期_时间.md
        parts = filename.replace(".md", "").split("_")

        if len(parts) >= 3:
            if len(parts) == 4:
                # 有分类: 舆情研判_政治_20260107_1649
                category = parts[1]
                date_str = parts[2]
                time_str = parts[3]
            else:
                # 无分类: 舆情研判_20260107_1649
                category = "综合"
                date_str = parts[1]
                time_str = parts[2]

            try:
                created_at = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]} {time_str[:2]}:{time_str[2:]}"
            except:
                created_at = datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
        else:
            category = "综合"
            created_at = datetime.fromtimestamp(stat.st_mtime).strftime(
                "%Y-%m-%d %H:%M"
            )

        # 读取标题
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                title = (
                    first_line.replace("#", "").strip()
                    if first_line.startswith("#")
                    else filename
                )
        except:
            title = filename

        reports.append(
            ReportSummary(
                filename=filename,
                title=title,
                category=category,
                created_at=created_at,
                size=stat.st_size,
            )
        )

    return reports


# =====================================================
# 分类选项
# =====================================================


@app.get("/api/categories")
async def get_categories():
    """获取可用分类"""
    return {"categories": ["综合", "社会", "高校", "生活", "科技", "政治", "其他"]}


@app.get("/api/forecast-ranges")
async def get_forecast_ranges():
    """获取预测范围选项"""
    return {
        "ranges": [
            {"value": "1w", "label": "1周"},
            {"value": "2w", "label": "2周"},
            {"value": "1m", "label": "1个月"},
            {"value": "2m", "label": "2个月"},
        ]
    }


# =====================================================
# LLM 设置 API
# =====================================================


from typing import Optional


class LLMSettings(BaseModel):
    """LLM 配置"""

    model: str
    base_url: str
    api_key: str


class LLMTestParams(BaseModel):
    """用于测试的可选参数（允许不保存直接测试）"""

    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


@app.get("/api/settings/llm")
async def get_llm_settings():
    """获取当前 LLM 设置（API Key 部分隐藏）"""
    from app.core.config import settings

    # 隐藏 API Key 中间部分
    api_key = settings.ZHIPU_API_KEY
    if len(api_key) > 10:
        masked_key = api_key[:6] + "*" * (len(api_key) - 10) + api_key[-4:]
    else:
        masked_key = "****"
    return {
        "model": settings.LLM_MODEL,
        "base_url": settings.LLM_BASE_URL,
        "api_key": masked_key,
    }


@app.post("/api/settings/llm")
async def update_llm_settings(llm_settings: LLMSettings):
    """更新 LLM 设置（写入环境变量，重启后生效）"""
    import os
    from app.core.config import settings

    # 更新运行时配置
    if llm_settings.model:
        settings.LLM_MODEL = llm_settings.model
        os.environ["LLM_MODEL"] = llm_settings.model

    if llm_settings.base_url:
        settings.LLM_BASE_URL = llm_settings.base_url
        os.environ["LLM_BASE_URL"] = llm_settings.base_url

    # 只有非掩码的 API Key 才更新
    if llm_settings.api_key and "*" not in llm_settings.api_key:
        settings.ZHIPU_API_KEY = llm_settings.api_key
        os.environ["ZHIPU_API_KEY"] = llm_settings.api_key

    return {"status": "ok", "message": "LLM 设置已更新"}


@app.post("/api/settings/llm/test")
async def test_llm_connection(params: LLMTestParams):
    """测试 LLM 连接。优先使用传入参数，否则退回到当前 server 配置。增强：先使用 openai SDK 做一次简单请求以捕获认证/地址错误，失败则回退到 langchain 的调用，同时对返回内容做基本检查。"""
    from app.core.config import settings

    # 决定使用的配置（传入优先）
    model = params.model or settings.LLM_MODEL
    base_url = params.base_url or settings.LLM_BASE_URL
    api_key = (
        params.api_key
        if params.api_key and "*" not in params.api_key
        else settings.ZHIPU_API_KEY
    )

    # 记录收到的参数（不记录完整密钥以防泄漏）
    from app.core.logger import logger

    logger.info(
        f"LLM 测试请求: model={model}, base_url={'(present)' if base_url else '(none)'}, api_key_present={'yes' if api_key else 'no'}"
    )

    # 1) 尝试使用 openai SDK 发起最小化请求以捕获常见错误
    openai_err = None
    try:
        import openai

        if api_key:
            openai.api_key = api_key
        if base_url:
            openai.api_base = base_url.rstrip("/")

        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": "请回复：连接成功。"}],
            max_tokens=10,
            temperature=0,
        )

        content = None
        if isinstance(resp, dict) and resp.get("choices"):
            content = (
                resp["choices"][0]["message"]["content"]
                if resp["choices"][0].get("message")
                else str(resp)
            )
        else:
            content = str(resp)

        low = (content or "").lower()
        if "连接成功" in low or "success" in low or "ok" in low:
            return {
                "status": "ok",
                "message": "LLM 连接成功",
                "response": (content or "").strip()[:200],
            }
        else:
            return {
                "status": "ok",
                "message": "LLM 连接成功（返回内容未包含显式成功关键字）",
                "response": (content or "").strip()[:200],
            }

    except Exception as e_open:
        openai_err = str(e_open)
        logger.error(f"openai 测试失败: {openai_err}")

    # 2) 回退到 langchain_openai（兼容性）
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            openai_api_base=base_url,
            temperature=0,
            max_tokens=50,
        )
        response = llm.invoke("你好，请回复'连接成功'")
        content = getattr(response, "content", None) or str(response)
        low = (content or "").lower()
        if "连接成功" in low or "success" in low or "ok" in low:
            logger.info("LLM 测试通过（langchain 返回）")
            return {
                "status": "ok",
                "message": "LLM 连接成功",
                "response": (content or "").strip()[:200],
            }
        else:
            logger.warning(f"LLM 返回结果未包含成功关键字: {content}")
            return {
                "status": "ok",
                "message": "LLM 连接成功（返回内容未包含显式成功关键字）",
                "response": (content or "").strip()[:200],
                "openai_error": openai_err,
            }

    except Exception as e_chain:
        logger.error(f"langchain 回退测试失败: {e_chain}")
        return {
            "status": "error",
            "message": f"连接失败: openai_error: {openai_err}; fallback_error: {str(e_chain)}",
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
