"""
FastAPI 后端入口
舆情研判系统 API
"""

import os
import glob
import asyncio
import logging
import uuid
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
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

# 导入工作流
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from main import run_task

#  新增导入 mongo_db，用于获取违规统计
from app.db.mongo_manager import mongo_db
from app.core.config import settings
from app.core.llm_factory import resolve_llm_config
from app.core.progress import build_progress_payload
from app.services.render_html import render_report_html, save_report_html
from app.services.render_pdf import save_report_pdf
from app.services.report import render_markdown_from_report_doc

app = FastAPI(
    title="舆情研判系统 API",
    description="社交媒体舆情分析与研判报告生成系统",
    version="1.0.0",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
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
    force_audit_update: bool = False


class TaskStatus(BaseModel):
    """任务状态"""

    task_id: str
    status: str  # running, completed, failed
    progress: int  # 0-100
    current_step: str
    message: str
    stage_id: Optional[str] = None
    stage_label: Optional[str] = None
    stage_progress: Optional[int] = None
    start_time: Optional[int] = None  # 毫秒时间戳
    end_time: Optional[int] = None  # 毫秒时间戳（任务完成或失败时写入）


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
    #  新增字段：违规统计分布
    violation_distribution: dict
    recent_reports: List[ReportSummary]


# =====================================================
# 任务状态存储 (生产环境应使用 Redis)
# =====================================================

task_store = {}


def _task_progress_state(stage_id: str, stage_progress: int, message: str) -> dict:
    payload = build_progress_payload(stage_id, stage_progress, message)
    return {
        "progress": payload["overall_progress"],
        "current_step": payload["stage_label"],
        "message": payload["message"],
        "stage_id": payload["stage_id"],
        "stage_label": payload["stage_label"],
        "stage_progress": payload["stage_progress"],
    }


def update_task_progress(task_id: str, progress: int, step: str, message: str):
    """更新任务进度（供外部调用），保留已有 start_time/end_time 字段"""
    if task_id in task_store:
        existing = dict(task_store.get(task_id, {}))
        existing.update({"status": "running"})
        existing.update(_task_progress_state(step, progress, message))
        task_store[task_id] = existing


async def execute_task(task_id: str, params: TaskCreate):
    """异步执行任务"""
    try:
        task_store[task_id] = {
            "status": "running",
            # 记录任务启动时间（毫秒）用于前端计时与回放
            "start_time": int(datetime.now().timestamp() * 1000),
            **_task_progress_state("prepare", 0, "正在启动任务..."),
        }
        add_system_log("INFO", f" 任务 {task_id} 开始执行")

        # 定义进度回调函数
        def progress_callback(payload: dict):
            # 合并更新，保留 start_time/end_time 等元数据
            existing = dict(task_store.get(task_id, {}))
            existing.update(
                {
                    "status": "running",
                    "progress": payload["overall_progress"],
                    "current_step": payload["stage_label"],
                    "message": payload["message"],
                    "stage_id": payload["stage_id"],
                    "stage_label": payload["stage_label"],
                    "stage_progress": payload["stage_progress"],
                }
            )
            task_store[task_id] = existing
            # 同时记录到日志
            add_system_log(
                "INFO",
                f"[{payload['stage_label']}] {payload['message']} ({payload['overall_progress']}%)",
            )

        # 注意：run_task 是同步、耗时的阻塞函数，不能在事件循环中直接调用。
        # 使用 asyncio.to_thread 将其移到线程池执行，避免阻塞 FastAPI
        await asyncio.to_thread(
            run_task,
            thread_id=task_id,
            start_date=params.start_date,
            end_date=params.end_date,
            regenerate_report=False,
            forecast_range=params.forecast_range,
            category=params.category,
            force_audit_update=params.force_audit_update,
            progress_callback=progress_callback,  # 传递进度回调
        )

        # 合并更新，保留 start_time 等元数据，并写入 end_time
        existing = dict(task_store.get(task_id, {}))
        existing.update(
            {
                "status": "completed",
                "end_time": int(datetime.now().timestamp() * 1000),
                **_task_progress_state("done", 100, "报告生成成功"),
            }
        )
        task_store[task_id] = existing
        add_system_log("INFO", f" 任务 {task_id} 执行完成")
    except Exception as e:
        existing = dict(task_store.get(task_id, {}))
        existing.update(
            {
                "status": "failed",
                "end_time": int(datetime.now().timestamp() * 1000),
                **_task_progress_state("report", 100, str(e)),
            }
        )
        task_store[task_id] = existing
        add_system_log("ERROR", f" 任务 {task_id} 执行失败: {str(e)}")


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

    reports_today = sum(1 for r in reports if today in r.filename)
    reports_this_week = sum(
        1
        for r in reports
        if any(
            (datetime.now() - timedelta(days=i)).strftime("%Y%m%d") in r.filename
            for i in range(7)
        )
    )

    # 1. 统计分类分布 (饼图数据)
    category_dist = {}
    for r in reports:
        cat = r.category
        category_dist[cat] = category_dist.get(cat, 0) + 1

    # 2.  调用 MongoDB 聚合查询获取违规统计 (条形图数据)
    violation_dist = mongo_db.get_dashboard_violation_stats()

    return DashboardStats(
        total_reports=len(reports),
        reports_today=reports_today,
        reports_this_week=reports_this_week,
        category_distribution=category_dist,
        violation_distribution=violation_dist,  #  返回聚合结果
        recent_reports=reports[:10],  # 显示更多报告
    )


@app.post("/api/tasks", response_model=TaskStatus)
async def create_task(params: TaskCreate, background_tasks: BackgroundTasks):
    """创建新的研判任务"""
    # 生成任务ID
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:4]
    task_id = f"task_{now}_{suffix}"

    # 添加后台任务
    background_tasks.add_task(execute_task, task_id, params)

    start_ts = int(datetime.now().timestamp() * 1000)
    task_progress = _task_progress_state("prepare", 0, "任务已创建，正在排队...")
    task_store[task_id] = {
        "status": "running",
        # 记录任务启动时间（毫秒）用于前端计时冻结
        "start_time": start_ts,
        **task_progress,
    }

    return TaskStatus(
        task_id=task_id,
        status="running",
        progress=task_progress["progress"],
        current_step=task_progress["current_step"],
        message="任务已创建",
        stage_id=task_progress["stage_id"],
        stage_label=task_progress["stage_label"],
        stage_progress=task_progress["stage_progress"],
        start_time=start_ts,
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


def _resolve_artifact_path(filename: str, suffix: str) -> Path:
    return (OUTPUT_DIR / filename).with_suffix(suffix)


def _load_report_session(filename: str) -> Optional[dict]:
    try:
        return mongo_db.get_report_session_by_filename(filename)
    except Exception:
        return None


def _load_report_json_or_none(filename: str) -> Optional[dict]:
    file_path = _resolve_artifact_path(filename, ".json")
    if file_path.exists():
        import json

        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    session = _load_report_session(filename) or {}
    report_json = session.get("report_json")
    if isinstance(report_json, dict) and report_json:
        return report_json
    return None


def _materialize_report_artifact(filename: str, format: str) -> Optional[Path]:
    report_json = _load_report_json_or_none(filename)
    if not report_json:
        return None

    target_map = {
        "md": OUTPUT_DIR / filename,
        "json": _resolve_artifact_path(filename, ".json"),
        "html": _resolve_artifact_path(filename, ".html"),
        "pdf": _resolve_artifact_path(filename, ".pdf"),
    }
    target_path = target_map[format]
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if format == "md":
            target_path.write_text(
                render_markdown_from_report_doc(report_json), encoding="utf-8"
            )
        elif format == "json":
            import json

            with open(target_path, "w", encoding="utf-8") as file:
                json.dump(report_json, file, ensure_ascii=False, indent=2)
        elif format == "html":
            save_report_html(report_json, str(target_path))
        elif format == "pdf":
            save_report_pdf(report_json, str(target_path))
    except OSError:
        return None

    return target_path if target_path.exists() else None


@app.get("/api/reports/{filename}/json")
async def get_report_json(filename: str):
    report_json = _load_report_json_or_none(filename)
    if not report_json:
        raise HTTPException(status_code=404, detail="结构化报告不存在")
    return JSONResponse(content=report_json)


@app.get("/api/reports/{filename}/html")
async def get_report_html(filename: str):
    file_path = _resolve_artifact_path(filename, ".html")

    if file_path.exists():
        return FileResponse(
            path=file_path, filename=file_path.name, media_type="text/html"
        )

    report_json = _load_report_json_or_none(filename)
    if not report_json:
        raise HTTPException(status_code=404, detail="HTML 报告不存在")
    return HTMLResponse(content=render_report_html(report_json))


@app.get("/api/reports/{filename}/pdf")
async def get_report_pdf(filename: str):
    file_path = _resolve_artifact_path(filename, ".pdf")

    if not file_path.exists():
        file_path = _materialize_report_artifact(filename, "pdf")
        if not file_path:
            raise HTTPException(status_code=404, detail="PDF 报告不存在")

    return FileResponse(
        path=file_path, filename=file_path.name, media_type="application/pdf"
    )


@app.get("/api/reports/{filename}/artifacts")
async def get_report_artifacts(filename: str):
    session = _load_report_session(filename) or {}
    session_has_report = isinstance(session.get("report_json"), dict) and bool(
        session.get("report_json")
    )
    return {
        "markdown": (OUTPUT_DIR / filename).exists()
        or session_has_report
        or bool(session.get("report_markdown")),
        "json": _resolve_artifact_path(filename, ".json").exists()
        or session_has_report,
        "html": _resolve_artifact_path(filename, ".html").exists()
        or session_has_report,
        "pdf": _resolve_artifact_path(filename, ".pdf").exists() or session_has_report,
        "render_version": session.get("render_version")
        or ((session.get("report_json") or {}).get("meta") or {}).get("render_version"),
    }


@app.get("/api/reports/{filename}/download")
async def download_report(filename: str, format: str = "md"):
    """下载报告文件"""
    file_map = {
        "md": (OUTPUT_DIR / filename, "text/markdown"),
        "json": (_resolve_artifact_path(filename, ".json"), "application/json"),
        "html": (_resolve_artifact_path(filename, ".html"), "text/html"),
        "pdf": (_resolve_artifact_path(filename, ".pdf"), "application/pdf"),
    }
    file_path, media_type = file_map.get(
        format, (OUTPUT_DIR / filename, "text/markdown")
    )

    if format == "html" and not file_path.exists():
        report_json = _load_report_json_or_none(filename)
        if report_json:
            return HTMLResponse(content=render_report_html(report_json))

    if not file_path.exists():
        generated = _materialize_report_artifact(
            filename, format if format in file_map else "md"
        )
        if generated:
            file_path = generated
        elif format == "md":
            session = _load_report_session(filename) or {}
            markdown = session.get("report_markdown")
            if markdown:
                return PlainTextResponse(content=markdown, media_type="text/markdown")
            raise HTTPException(status_code=404, detail="报告不存在")
        elif format == "html":
            report_json = _load_report_json_or_none(filename)
            if report_json:
                return HTMLResponse(content=render_report_html(report_json))
            raise HTTPException(status_code=404, detail="报告不存在")
        else:
            raise HTTPException(status_code=404, detail="报告不存在")

    return FileResponse(path=file_path, filename=file_path.name, media_type=media_type)


@app.delete("/api/reports/{filename}")
async def delete_report(filename: str):
    """删除报告文件"""
    file_path = OUTPUT_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="报告不存在")

    try:
        file_path.unlink()
        for suffix in [".json", ".html", ".pdf"]:
            artifact = _resolve_artifact_path(filename, suffix)
            if artifact.exists():
                artifact.unlink()
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


class LLMConfigInput(BaseModel):
    model: str = ""
    base_url: str = ""
    api_key: str = ""


class LLMSettingsPayload(BaseModel):
    main: LLMConfigInput


class LLMTestParams(BaseModel):
    """用于测试的可选参数（允许不保存直接测试）"""

    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class SearchSettingsPayload(BaseModel):
    tavily_api_key: str = ""


class SearchTestParams(BaseModel):
    tavily_api_key: Optional[str] = None


def _mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) > 10:
        return api_key[:6] + "*" * (len(api_key) - 10) + api_key[-4:]
    return "****"


def _save_tavily_api_key(api_key: str):
    if api_key and "*" not in api_key:
        settings.TAVILY_API_KEY = api_key
        os.environ["TAVILY_API_KEY"] = api_key


def _sync_legacy_llm_settings_from_main(config: LLMConfigInput):
    if config.model:
        settings.LLM_MODEL = config.model
        os.environ["LLM_MODEL"] = config.model
    if config.base_url:
        settings.LLM_BASE_URL = config.base_url
        os.environ["LLM_BASE_URL"] = config.base_url
    if config.api_key and "*" not in config.api_key:
        settings.ZHIPU_API_KEY = config.api_key
        os.environ["ZHIPU_API_KEY"] = config.api_key


def _save_main_llm_config(config: Optional[LLMConfigInput]):
    if not config:
        return
    if config.model:
        settings.FAST_LLM_MODEL = config.model
        os.environ["FAST_LLM_MODEL"] = config.model
    if config.base_url:
        settings.FAST_LLM_BASE_URL = config.base_url
        os.environ["FAST_LLM_BASE_URL"] = config.base_url
    if config.api_key and "*" not in config.api_key:
        settings.FAST_LLM_API_KEY = config.api_key
        os.environ["FAST_LLM_API_KEY"] = config.api_key


def _clear_legacy_strong_llm_env():
    os.environ.pop("STRONG_LLM_MODEL", None)
    os.environ.pop("STRONG_LLM_BASE_URL", None)
    os.environ.pop("STRONG_LLM_API_KEY", None)


@app.get("/api/settings/llm")
async def get_llm_settings():
    """获取当前 LLM 设置（API Key 部分隐藏）"""
    main_config = resolve_llm_config()
    return {
        "main": {
            "model": main_config.model,
            "base_url": main_config.base_url,
            "api_key": _mask_api_key(main_config.api_key),
        },
        "single_llm_mode": True,
        "persistence_mode": "runtime",
    }


@app.post("/api/settings/llm")
async def update_llm_settings(llm_settings: LLMSettingsPayload):
    """更新 LLM 设置（运行时生效，服务重启后需重新加载）"""
    _save_main_llm_config(llm_settings.main)
    _clear_legacy_strong_llm_env()
    _sync_legacy_llm_settings_from_main(llm_settings.main)

    return {
        "status": "ok",
        "message": "LLM 设置已更新（当前为单模型模式；运行时保存，服务重启后需重新加载）",
        "single_llm_mode": True,
        "persistence_mode": "runtime",
    }


@app.post("/api/settings/llm/test")
async def test_llm_connection(params: LLMTestParams):
    """测试 LLM 连接。优先使用传入参数，否则退回到当前 server 配置。增强：先使用 openai SDK 做一次简单请求以捕获认证/地址错误，失败则回退到 langchain 的调用，同时对返回内容做基本检查。"""
    resolved = resolve_llm_config()
    model = params.model or resolved.model
    base_url = params.base_url or resolved.base_url
    api_key = (
        params.api_key
        if params.api_key and "*" not in params.api_key
        else resolved.api_key
    )

    # 记录收到的参数（不记录完整密钥以防泄漏）
    from app.core.logger import logger

    logger.info(
        f"LLM 测试请求: mode=single, model={model}, base_url={'(present)' if base_url else '(none)'}, api_key_present={'yes' if api_key else 'no'}"
    )

    # 1) 尝试使用 openai SDK (v1.x+) 发起最小化请求以捕获常见错误
    openai_err = None
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/") if base_url else None,
        )

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "请回复：连接成功。"}],
            max_tokens=10,
            temperature=0,
        )

        content = resp.choices[0].message.content if resp.choices else str(resp)

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


@app.get("/api/settings/search")
async def get_search_settings():
    return {
        "tavily_api_key": _mask_api_key(settings.TAVILY_API_KEY),
        "persistence_mode": "runtime",
    }


@app.post("/api/settings/search")
async def update_search_settings(search_settings: SearchSettingsPayload):
    _save_tavily_api_key(search_settings.tavily_api_key)
    return {
        "status": "ok",
        "message": "联网搜索设置已更新（当前为运行时保存，服务重启后需重新加载）",
        "persistence_mode": "runtime",
    }


@app.post("/api/settings/search/test")
async def test_search_connection(params: SearchTestParams):
    api_key = (
        params.tavily_api_key
        if params.tavily_api_key and "*" not in params.tavily_api_key
        else settings.TAVILY_API_KEY
    )

    if not api_key:
        return {"status": "error", "message": "未配置 Tavily API Key"}

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        response = client.search(
            query="中国 今日 新闻",
            search_depth="basic",
            max_results=1,
            topic="news",
            include_answer=False,
            include_raw_content=False,
        )
        results = response.get("results", []) if isinstance(response, dict) else []
        return {
            "status": "ok",
            "message": "Tavily 连接成功",
            "result_count": len(results),
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Tavily 连接失败: {str(exc)}",
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
