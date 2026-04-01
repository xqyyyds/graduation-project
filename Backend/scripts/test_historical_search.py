"""
测试使用 get_web_context 方法进行搜索
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.config import settings
from app.services.utils import get_web_context

# 打印当前配置的 API key（部分隐藏）
api_key = settings.TAVILY_API_KEY
masked_key = api_key[:8] + "..." if api_key else "None"
print(f"当前 TAVILY_API_KEY: {masked_key}")
print(f"完整 Key: {api_key}")
print(f"{'='*80}\n")

# 测试搜索
query = "2025年1月 中国发生的重大新闻事"
print(f"搜索查询: {query}")
print(f"{'='*80}\n")

result = get_web_context(query, search_depth="basic", max_results=2)

print("搜索结果:")
print(f"{'='*80}\n")
print(result)
print(f"\n{'='*80}")
print(f"结果长度: {len(result)} 字符")