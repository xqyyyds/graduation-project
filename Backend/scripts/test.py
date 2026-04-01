import json
import os
import sys

# 关键：将父级目录 (Project Root) 加入 sys.path，解决 ModuleNotFoundError: No module named 'app'
# 这允许脚本直接引用 backend 下的 app 模块，无论你在哪里运行它
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from langchain.chat_models import init_chat_model


def verify_api():
    """使用项目中统一的 LLM 封装进行连通性与返回测试（init_chat_model）。"""
    print("初始化 LLM 客户端...")

    try:
        llm = init_chat_model(
            model=settings.LLM_MODEL,  # 例如: glm-4.6
            model_provider="openai",
            api_key=settings.ZHIPU_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0.1,
        )

        print("发送测试提示到 LLM... (可能需要几秒)")
        res = llm.invoke("你好，请问 1+1 等于几？这是一条 API 测试消息。")

        # 尝试友好地解析常见返回类型
        content = None
        try:
            if isinstance(res, dict):
                # OpenAI-style JSON
                if "choices" in res and res["choices"]:
                    content = res["choices"][0]["message"]["content"]
                else:
                    content = json.dumps(res, ensure_ascii=False)
            else:
                # 普通对象或 LangChain 返回，尝试读取常见属性
                content = (
                    getattr(res, "content", None)
                    or getattr(res, "message", None)
                    or str(res)
                )
                # 如果 message 是对象且有 content 属性
                if hasattr(res, "message") and hasattr(res.message, "content"):
                    content = res.message.content
        except Exception:
            content = str(res)

        print("\n 验证成功！")
        print(f"模型回复: {content}")

    except Exception as e:
        print("\n 验证失败或发生异常！")
        print(f"错误: {e}")


if __name__ == "__main__":
    verify_api()
