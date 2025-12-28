my-agentic-rag/
├── backend/                 # FastAPI 后端 + LangGraph 智能体
├── frontend/                # Vue 3 前端
├── data/                    # 本地数据存储 (Docker挂载卷)
├── docker-compose.yml       # 一键启动 (Frontend + Backend + Mongo + Milvus)
├── .gitignore
└── README.md

backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 入口，初始化 App
│   │
│   ├── api/                 # 接口层 (Routes)
│   │   ├── v1/
│   │   │   ├── chat.py      # 处理前端发来的对话请求 (Stream流式输出)
│   │   │   └── admin.py     # 管理接口 (比如触发爬虫、管理知识库)
│   │
│   ├── core/                # 核心配置
│   │   ├── config.py        # 环境变量加载 (OpenAI Key, DB URL)
│   │   └── events.py        # 启动/关闭时的事件处理
│   │
│   ├── db/                  # 数据库连接
│   │   ├── mongodb.py       # 连接你的 MediaCrawler 数据
│   │   └── vector_store.py  # 连接向量数据库 (Milvus/Chroma)
│   │
│   ├── schemas/             # Pydantic 数据模型 (输入输出定义)
│   │   ├── chat.py          # 定义对话的 Request/Response 格式
│   │   └── graph_state.py   # 定义 LangGraph 的 State 结构
│   │
│   ├── services/            # 通用业务逻辑
│   │   ├── ingestion.py     # RAG 入库逻辑 (把 MongoDB 数据转向量)
│   │   └── retriever.py     # 检索逻辑 (封装向量搜索)
│   │
│   └── agents/              # 🔥 LangGraph 核心区域 (Agentic RAG)
│       ├── __init__.py
│       ├── state.py         # 定义 AgentState (TypedDict)
│       ├── graph.py         # 构建图 (GraphBuilder, add_node, add_edge)
│       │
│       ├── nodes/           # 图的节点 (每个节点是一个函数)
│       │   ├── retrieve.py  # 检索节点
│       │   ├── grade.py     # 评分节点 (评估检索相关性)
│       │   ├── generate.py  # 生成节点 (调用 LLM)
│       │   └── rewrite.py   #由于问题重写节点
│       │
│       └── tools/           # LangChain Tools (给 Agent 用的工具)
│           ├── search_tool.py   # 搜索互联网
│           └── db_tool.py       # 查 MongoDB 里的详细帖子
│
├── .env                     # 环境变量
├── requirements.txt
└── Dockerfile

frontend/
├── src/
│   ├── api/                 # Axios 请求封装
│   │   ├── chat.js          # 调用后端的 /chat 接口
│   │   └── config.js        # 基础配置
│   │
│   ├── assets/              # 静态资源 (Logo, CSS)
│   │
│   ├── components/          # 组件
│   │   ├── ChatWindow.vue   # 聊天主窗口
│   │   ├── MessageItem.vue  # 单条消息气泡 (区分 User/AI)
│   │   ├── InputBox.vue     # 输入框
│   │   └── Sidebar.vue      # 历史记录侧边栏
│   │
│   ├── views/
│   │   ├── HomeView.vue     # 主页面
│   │   └── AdminView.vue    # 后台管理 (查看爬虫状态、知识库管理)
│   │
│   ├── stores/              # Pinia 状态管理
│   │   ├── chatStore.js     # 存储当前的对话历史
│   │
│   ├── utils/               # 工具函数
│   │   └── markdown.js      # 解析 Markdown 输出
│   │
│   ├── App.vue
│   └── main.js
│
├── index.html
├── package.json
└── vite.config.js