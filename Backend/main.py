import uuid
import datetime
import argparse
import sys

# 1. 引入记忆管理器 (Checkpointer)
from app.db.checkpointer import checkpointer_manager

# 2. 引入工作流图 (Workflow)
# 注意：你刚才把 workflow.py 放到了 agents 目录下
from app.agents.workflow import workflow


def run_task(
    thread_id: str = None,
    start_date: str = None,
    end_date: str = None,
    regenerate_report: bool = False,
    forecast_range: str = "1m",
):
    """
    执行舆情分析全流程
    :param thread_id: 任务ID。传空则新建任务；传旧ID则断点续传。
    :param start_date: 分析开始时间 (YYYY-MM-DD HH:MM:SS)
    :param end_date: 分析结束时间
    :param regenerate_report: 是否仅重新生成报告 (跳过前面的步骤)
    """

    # --- 1. ID 初始化 ---
    if not thread_id:
        # 生成一个带日期的易读 ID
        today = datetime.datetime.now().strftime("%Y%m%d")
        short_uuid = str(uuid.uuid4())[:6]
        thread_id = f"task_{today}_{short_uuid}"
        print(f"\n🆕 [System] 正在初始化新任务...")
    else:
        print(f"\n🔄 [System] 正在尝试恢复任务...")

    print(f"🆔 任务 ID (Thread ID): {thread_id}")
    print(f"📅 分析周期: {start_date or '默认(最近24h)'} ~ {end_date or '默认'}")
    print("-" * 50)

    # --- 2. 注入记忆 & 编译图 ---
    # 使用上下文管理器打开 SQLite 连接
    with checkpointer_manager.get_checkpointer() as checkpointer:

        # 🔥 关键：在这里把 workflow 编译成可运行的 app，并挂载记忆
        app = workflow.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        # --- 🔥 特殊功能：仅重新生成报告 ---
        if regenerate_report:
            if not thread_id:
                print("❌ 错误：使用 --regenerate_report 必须提供 --id 参数")
                return

            print(f"📝 [System] 检测到重新生成报告指令，正在读取缓存状态...")
            snapshot = app.get_state(config)
            if not snapshot.values:
                print("❌ 错误：未找到该任务的有效缓存状态，无法生成报告。")
                return

            print("✅ 缓存读取成功，正在调用 Agent E...")
            # 动态导入避免循环引用
            from app.agents.nodes import agent_e_node

            try:
                agent_e_node(snapshot.values)
                print(f"✨✨ 报告重新生成完毕！ ✨✨")
            except Exception as e:
                print(f"❌ 报告生成失败: {e}")
                import traceback

                traceback.print_exc()
            return

        # --- 3. 准备初始状态 ---
        # LangGraph 的机制：
        # 如果 thread_id 在数据库里存在，它会忽略下面的 initial_state，直接加载历史状态。
        # 如果是新 ID，则使用下面的 initial_state 启动。
        initial_state = {
            "task_id": thread_id,
            "user_query": "启动全流程研判",
            "start_date": start_date,
            "end_date": end_date,
            "forecast_range": forecast_range,  # 预测时间范围
            # 初始化空列表，防止首次运行报错
            "messages": [],
            "core_events": [],
            "analyzed_events": [],
            "audit_results": [],
            "trend_forecast": {},
            "final_report": "",
            "error": "",
            "current_step": "Start",
        }

        # 配置信息 (告诉 LangGraph 当前是哪个线程)
        config = {"configurable": {"thread_id": thread_id}}

        # --- 4. 启动流式运行 ---
        try:
            # app.stream 会一步步执行节点
            # stream_mode="updates" 表示只返回状态更新的部分
            step_count = 0
            for output in app.stream(initial_state, config=config):
                step_count += 1
                for node_name, state_delta in output.items():
                    # 这里可以打印当前节点产出的关键信息
                    step_info = state_delta.get("current_step", "Running...")
                    print(
                        f"✅ [Step {step_count}] 节点 '{node_name}' 完成 -> {step_info}"
                    )

            # --- 5. 任务结束 ---
            print("-" * 50)
            print(f"✨✨ 全流程执行完毕！ ✨✨")

            # 获取最终状态以打印 PDF 路径
            final_snapshot = app.get_state(config)
            final_data = final_snapshot.values

            if final_data.get("final_report"):
                # 这里我们稍微 hack 一下，因为 PDF 路径虽然没在 State 显式定义，
                # 但 Agent E 打印在了控制台。如果你想在这里打印，
                # 可以在 State 加个 pdf_path 字段，或者去 output 文件夹看。
                print(f"📂 请前往项目 output/ 目录查看最新生成的 PDF 报告。")

            print(f"💡 提示：保留 ID '{thread_id}'，下次运行时传入可回溯历史。")

        except KeyboardInterrupt:
            print("\n\n🛑 [System] 用户手动中止任务。")
            print(f"💾 状态已保存。下次运行 run_task('{thread_id}') 可继续。")

        except Exception as e:
            print(f"\n❌ [System] 运行发生异常: {e}")
            import traceback

            traceback.print_exc()
            print(
                f"\n💾 现场已保护。修复 Bug 后运行 run_task('{thread_id}') 可断点续传。"
            )


if __name__ == "__main__":
    # 使用 argparse 让你可以通过命令行传参
    # 用法示例:
    # 1. 直接跑: python main.py
    # 2. 续传:   python main.py --id task_20251020_a1b2
    # 3. 指定时间: python main.py --days 3 (分析过去3天)

    parser = argparse.ArgumentParser(description="舆情分析 Agent 系统启动入口")
    parser.add_argument(
        "--id", type=str, help="任务 ID (Thread ID)，用于断点续传", default=None
    )
    parser.add_argument(
        "--days", type=int, help="分析过去多少天的数据 (默认1天)", default=1
    )
    parser.add_argument(
        "--start",
        type=str,
        help="开始日期 YYYY-MM-DD（可选，只接受日期格式）",
        default=None,
    )
    parser.add_argument(
        "--end",
        type=str,
        help="结束日期 YYYY-MM-DD（可选，只接受日期格式）",
        default=None,
    )
    parser.add_argument(
        "--regenerate_report",
        action="store_true",
        help="【断点陨星】仅重新生成报告（需配合 --id 使用），跳过前面所有步骤，直接读取缓存。",
    )
    parser.add_argument(
        "--forecast",
        type=str,
        choices=["1w", "2w", "1m", "2m"],
        default="1m",
        help="趋势预测时间范围：1w=一周, 2w=半个月, 1m=一个月, 2m=两个月 (默认1m)",
    )

    args = parser.parse_args()

    # 处理时间逻辑（统一为日期 YYYY-MM-DD）
    s_date, e_date = args.start, args.end

    # 如果没指定具体的 start/end，但指定了 days，则自动计算日期区间（只保留日期部分）
    if not s_date and not e_date:
        today = datetime.datetime.now().date()
        e_date = today.isoformat()
        s_date = (today - datetime.timedelta(days=args.days)).isoformat()

    # 严格校验用户输入：只接受 YYYY-MM-DD
    import re

    def _validate_date(d: str) -> str:
        if not d:
            return d
        d = d.strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            print(f"❌ 日期格式错误（应为 YYYY-MM-DD）：{d}")
            sys.exit(1)
        return d

    s_date = _validate_date(s_date)
    e_date = _validate_date(e_date)

    # 🚀 启动！
    run_task(
        thread_id=args.id,
        start_date=s_date,
        end_date=e_date,
        regenerate_report=args.regenerate_report,
        forecast_range=args.forecast,
    )
