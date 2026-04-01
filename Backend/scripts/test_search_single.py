"""
简单测试单个日期的搜索结果
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.utils import get_web_context


def test_search(date_str: str):
    """测试指定日期的搜索"""
    print(f"\n{'='*80}")
    print(f"测试日期: {date_str}")
    print(f"{'='*80}\n")

    query = f"{date_str} 最热门事件 热搜 新闻 头条"
    print(f"搜索查询: {query}\n")

    print("正在搜索...\n")

    try:
        result = get_web_context(query, search_depth="basic")

        print(f"{'='*80}")
        print("完整搜索结果:")
        print(f"{'='*80}\n")
        print(result)
        print(f"\n{'='*80}")
        print(f"结果长度: {len(result)} 字符")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"❌ 搜索失败: {e}")


if __name__ == "__main__":
    # 测试几个日期
    test_dates = [
        "2025-01-01",
        "2025-01-15",
        "2025-01-31",
    ]

    for date in test_dates:
        test_search(date)
        input("\n按回车继续测试下一个日期...")
