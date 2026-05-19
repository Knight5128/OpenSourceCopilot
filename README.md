# OpenSourceCopilot

OpenSourceCopilot 旨在帮助想参与开源却不知从何下手的开发者，把 GitHub 上的代码、Issue、PR 等知识重组为可推理、可解释、可追溯的网络。输入技能、兴趣方向与每周时间，输出推荐仓库、Issue 优先级、改动路径预测、类似 PR 参考与 PR 模板；底层采用知识图谱（Neo4j）、混合检索（HybridRAG）、图神经网络（GCN/GAT）与 LangGraph 多节点 Agent，前端为 React 工作台，后端为 FastAPI。

---

## 1 · 项目目标

为想参与开源、却苦于"不知道从哪入手"的开发者，提供一份**可执行的 PR 计划书**：

输入 `技能 + 兴趣方向 + 每周时间` → 输出 `推荐仓库 → Issue 排序 → 改动路径预测 → 类似 PR 引用 → PR 模板`，每条结论附**可点击的代码 / Issue / PR 引用链路**。

解决的真实知识管理痛点：开源仓库本身沉淀了海量结构化（代码、PR）与非结构化（Issue、文档）知识，但**新人无法快速调用**。我们用 AI 把它们重组为**可推理、可解释、可追溯**的知识网络。

完整方案设计见 [`docs/proposal.md`](docs/proposal.md)。

---

## 2 · 技术架构

```
┌──────────────────────────── 应用层 ────────────────────────────┐
│        React 工作台   ◄──►   FastAPI                            │
└──────────────┬─────────────────────────┬──────────────────────┘
               │                         │
       ┌───────▼────────┐       ┌────────▼────────┐
       │  LangGraph     │       │  HybridRAG       │
       │  8-Node Agent  │◄─────►│  BM25+Vec+Graph  │
       └───────┬────────┘       └────────┬─────────┘
               │                         │
       ┌───────▼────────┐       ┌────────▼────────┐
       │  GCN / GAT     │       │  Embedding      │
       │  (友好度+匹配) │       │  (BGE+UniXcoder)│
       └───────┬────────┘       └────────┬─────────┘
               │                         │
        ┌──────▼─────────────────────────▼──────┐
        │  Neo4j (KG)   ◄──►   Milvus (Vector)  │
        └───────────────────┬───────────────────┘
                            │
                  ┌─────────▼──────────┐
                  │  GitHub ETL (Cache)│
                  └────────────────────┘
```

三大技术招牌：
1. **GCN/GAT** —— 把 Issue/Contributor/Repo 建模为异构图，做"新手友好度"分类 + 技能匹配嵌入
2. **HybridRAG** —— BM25 + 稠密向量 + 图召回三路融合，回答带可追溯引用
3. **LangGraph 8 节点 Agent** —— 端到端 onboarding 任务规划

---

## 3 · 目录结构

```
OpenSourceCopilot/
├── README.md                ← 项目入口（你正在看的文件）
├── docs/
│   └── proposal.md          ← 完整选题方案与实施路线
├── docker-compose.yml       ← Neo4j + Milvus 一键启动
├── .env.example             ← 环境变量模板
├── pyproject.toml           ← Python 项目元数据
├── requirements.txt         ← Python 依赖清单
├── backend/
│   ├── app/
│   │   ├── main.py          ← FastAPI 入口
│   │   ├── api.py           ← REST 路由
│   │   ├── config.py        ← Pydantic 配置
│   │   ├── schemas.py       ← 通用 Pydantic 模型
│   │   ├── kg/              ← Neo4j 图谱层（schema + client）
│   │   ├── etl/             ← GitHub 数据采集
│   │   ├── vector/          ← Milvus + 嵌入封装
│   │   ├── gcn/             ← 图神经网络模型与训练
│   │   ├── rag/             ← HybridRAG 三路检索
│   │   └── agent/           ← LangGraph 编排
│   └── tests/
├── frontend/                ← React + Vite + TS 工作台
├── scripts/
│   ├── seed_repos.py        ← 种子仓库 ETL 入口
│   └── train_gcn.py         ← GNN 训练入口
└── data/                    ← 本地缓存（git 忽略）
```

---

## 4 · 快速开始

> 全流程在 Windows / macOS / Linux 上均可运行；下方示例以 Windows + PowerShell 为主。

### 4.1 准备环境变量

```powershell
Copy-Item .env.example .env
# 然后用你的编辑器填入 GITHUB_TOKEN、LLM_API_KEY 等
```

### 4.2 启动基础服务（Neo4j + Milvus）

```powershell
docker compose up -d
# 等待健康检查通过：
# - Neo4j Browser  http://localhost:7474  (默认账号 neo4j / changeme)
# - Milvus         localhost:19530
```

### 4.3 后端

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --port 8000
# 健康检查：http://localhost:8000/api/v1/health
```

### 4.4 前端

```powershell
cd frontend
npm install
npm run dev
# 打开 http://localhost:5173
```

### 4.5 跑测试

```powershell
pytest -q
```

---

## 5 · 当前实现状态

> 这是面向首次访问者的**概览**；细粒度的功能清单与进度追踪请看 [`docs/SPEC.md`](docs/SPEC.md)（**Single Source of Truth**，每完成一个子功能都会在那里同步勾选）。

| 模块 | 状态 | 负责人（占位） | SPEC 章节 |
|---|---|---|---|
| 项目骨架 + 文档 | ✅ Done | 全员 | — |
| Neo4j Schema | ✅ 已定义本体 | D | [M2](docs/SPEC.md#2--m2--知识图谱neo4j) |
| GitHub ETL | ✅ 已完成（缓存 / AST / seed / 日志重试） | D | [M1](docs/SPEC.md#1--m1--数据采集与缓存etl) |
| 向量库 + 嵌入封装 | 🟡 客户端就绪，入库待补 | B | [M3](docs/SPEC.md#3--m3--向量库与嵌入) |
| HybridRAG 三路检索 | ⚪ 待开发（Week 2） | B | [M5](docs/SPEC.md#5--m5--hybridrag招牌-) |
| GCN 模型骨架 | 🟡 模型类就绪，训练待补（Week 3） | A | [M4](docs/SPEC.md#4--m4--gcn--gat-图学习招牌-) |
| LangGraph Agent | 🟡 DAG 拓扑就绪，节点逻辑待补（Week 3） | C | [M6](docs/SPEC.md#6--m6--langgraph-agent招牌-) |
| FastAPI API 路由 | 🟡 契约就绪，落地待补 | D | [M7](docs/SPEC.md#7--m7--fastapi-应用层) |
| React 工作台 | 🟡 健康检查页就绪，精美三屏待补（Week 4） | D | [M8](docs/SPEC.md#8--m8--前端工作台精美化重点) |
| 持久化部署 | ⚪ 待选型 | D | [M9](docs/SPEC.md#9--m9--部署与运维持久化后端) |

图例：✅ 完成 / 🟡 进行中 / ⚪ 未开始

---

## 6 · 团队分工

| 成员 | 角色 | 主要模块 |
|---|---|---|
| A | Graph Scientist | `backend/app/gcn/` GCN 训练 + ablation |
| B | Retrieval Engineer | `backend/app/vector/` + `backend/app/rag/` |
| C | Agent Architect | `backend/app/agent/` LangGraph 8 节点 |
| D | Full-stack & Data | `backend/app/etl/` + `backend/app/kg/` + `backend/app/api.py` + `frontend/` |

---

## 7 · 开发规范

- **Python**：`ruff` 统一格式与 lint；`pytest` 跑测试
- **提交**：使用 conventional commit，例如 `feat: add hybrid retriever`
- **分支**：`main` 保持可运行；feature 分支命名 `feat/<member>-<topic>`
- **密钥**：永远不要提交 `.env`；用 `.env.example` 维护字段约定

---

## 8 · 课程要素覆盖

| 章节 | 实现位置 |
|---|---|
| 第 3 章 知识图谱 | `backend/app/kg/schema.py` |
| 第 4 章 图计算（GCN） | `backend/app/gcn/` |
| 第 5 章 图数据库 | `backend/app/kg/client.py` + Neo4j |
| 第 7 章 向量数据库 | `backend/app/vector/` + Milvus |
| 第 9 章 知识增强 Prompt | （待补于 `backend/app/agent/nodes.py`） |
| 第 10 章 知识增强 RAG | `backend/app/rag/hybrid.py` |
| 第 13 章 Agent 系统 | `backend/app/agent/graph.py` |
| 第 15 章 应用 | `backend/app/api.py` + `frontend/` |

---

## 9 · License

MIT (course project, free to fork)
