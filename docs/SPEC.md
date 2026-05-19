# OpenSourceCopilot · 功能规格说明书（SPEC）

> 本文档是项目**单一事实源（Single Source of Truth）**：分模块列出全部待实现功能、验收标准、与当前进度。
> **维护约定**：每完成一个子功能，**在同一次 PR 中**勾选对应 checkbox 并更新「最近更新」一行；新需求先进入 §11 待规划区，再分配到模块。
> 与 `README.md` §5 的对应关系：README 的状态表是**面向首次访问者的概览**，本 SPEC 是**面向开发者的实施清单**。两者用 `SPEC-ID` 串联（形如 `M3-RAG-02`）。

- **最近更新**：2026-05-19 · 完成 M1-ETL-01~03（GitHub 客户端、仓库元数据、Issue/PR 拉取）
- **状态图例**：⚪ 未开始 / 🟡 进行中 / 🟢 已完成 / 🔴 阻塞 / ⏸ 暂缓

---

## 0 · 全局质量门（Definition of Done）

任何标记为 🟢 的功能必须同时满足：

- [ ] 代码已合入 `main`，且 `pytest -q` 全绿
- [ ] 关键路径有至少 1 条单测或集成测试
- [ ] 对外接口（REST / 函数签名）在 `schemas.py` 或类型注解中定义
- [ ] 涉及外部服务（Neo4j / Milvus / GitHub / LLM）时，写明降级 / 缓存策略
- [ ] 在本 SPEC 对应条目打勾，并在「最近更新」里追加一行

---

## 1 · M1 — 数据采集与缓存（ETL）

**目标**：把 GitHub 上的种子仓库元数据、Issue、PR、代码 AST 落到本地缓存，供后续模块消费。
**代码位置**：`backend/app/etl/` · `scripts/seed_repos.py` · `data/`
**负责人**：D

| SPEC-ID | 子功能 | 状态 | 验收标准 |
|---|---|---|---|
| M1-ETL-01 | GitHub REST 客户端封装（带 token 轮询 + 限流退避） | 🟢 | 单 token 用尽自动切换；429 走指数退避；单元测 mock 限流响应 |
| M1-ETL-02 | 仓库元数据采集（stars / topics / license / 主语言） | 🟢 | 给定 owner/repo 入参可返回 `RepoMeta` Pydantic 对象 |
| M1-ETL-03 | Issue & PR 批量拉取（含 labels、author_association、comments） | 🟢 | 支持增量更新（since 参数），10 仓库 × 100 条 < 5 min |
| M1-ETL-04 | SQLite 全量缓存（`data/cache.db`） | ⚪ | 二次访问命中率 ≥ 95%；schema 版本化 |
| M1-ETL-05 | tree-sitter 代码 AST 解析（Python / TS 优先） | ⚪ | 每文件输出 `Function` 节点 + `Function-CALLS->Function` 关系 |
| M1-ETL-06 | 种子仓库脚本 `scripts/seed_repos.py` | ⚪ | `python scripts/seed_repos.py --config configs/seed.yaml` 一键灌库 |
| M1-ETL-07 | 异常 & 重试上报（日志结构化） | ⚪ | 用 `loguru` 输出 JSON 行；失败任务进死信表 |

---

## 2 · M2 — 知识图谱（Neo4j）

**目标**：把 ETL 数据写入 Neo4j，本体严格遵循 `docs/proposal.md` §4 模块 1。
**代码位置**：`backend/app/kg/`
**负责人**：D

| SPEC-ID | 子功能 | 状态 | 验收标准 |
|---|---|---|---|
| M2-KG-01 | 本体定义（7 实体 + 8 关系）+ 约束 / 索引 | 🟢 | `schema.py` 已存在；启动时自动 `CREATE CONSTRAINT` |
| M2-KG-02 | Neo4j 异步客户端（连接池 + 重试） | 🟡 | `client.py` 骨架就绪；待补连接池配置 |
| M2-KG-03 | 批量写入器（`UNWIND` + APOC 事务） | ⚪ | 单事务 ≥ 5k 节点，失败回滚 |
| M2-KG-04 | 常用 Cypher 查询封装（issue→module 邻接、PR→file 影响域） | ⚪ | 提供 6 个具名查询函数，每个有 docstring + 单测 |
| M2-KG-05 | 图谱健康检查端点 `/api/v1/kg/stats` | ⚪ | 返回各类节点 / 边计数，供前端徽章展示 |
| M2-KG-06 | 子图导出接口（前端 Cytoscape 用） | ⚪ | 给定中心节点 + 跳数返回 `{nodes, edges}` JSON |

---

## 3 · M3 — 向量库与嵌入

**目标**：双嵌入空间（代码 / 文档）入 Milvus，支持 HybridRAG 第二路。
**代码位置**：`backend/app/vector/`
**负责人**：B

| SPEC-ID | 子功能 | 状态 | 验收标准 |
|---|---|---|---|
| M3-VEC-01 | BGE-zh 文档嵌入封装 | 🟡 | `embeddings.py` 接口就绪；待补本地推理 / API 切换开关 |
| M3-VEC-02 | UniXcoder 代码嵌入封装 | ⚪ | 输入 `(language, code)` 返回 768d 向量；支持 batch |
| M3-VEC-03 | Milvus collection schema（issues / code / pr_titles） | ⚪ | 3 个 collection 自动建立，IVF_FLAT 索引参数可配 |
| M3-VEC-04 | 批量入库器 | ⚪ | 10k 条向量 < 30s 入库 |
| M3-VEC-05 | ANN 召回接口（topK + 元数据过滤） | ⚪ | 支持按 `repo` / `lang` filter；P95 < 200ms |
| M3-VEC-06 | Embedding 缓存层（文本哈希 → 向量） | ⚪ | 命中率 ≥ 80%，存 SQLite |

---

## 4 · M4 — GCN / GAT 图学习（招牌 ①）

**目标**：两个学习任务（Issue 友好度二分类 + Contributor×Repo 异构匹配）。
**代码位置**：`backend/app/gcn/` · `scripts/train_gcn.py`
**负责人**：A

| SPEC-ID | 子功能 | 状态 | 验收标准 |
|---|---|---|---|
| M4-GCN-01 | 数据加载器（Neo4j → PyG `HeteroData`） | 🟡 | 模型类骨架已存在，loader 待补 |
| M4-GCN-02 | 节点特征工程（标签 / 长度 / 圈复杂度 / 历史 PR 行数） | ⚪ | 每个特征有缺失值兜底，写入 `Issue.features` 数组属性 |
| M4-GCN-03 | 2 层 GCN 友好度分类模型 + 训练循环 | ⚪ | F1 ≥ 0.7（验证集），训练日志可视化 |
| M4-GCN-04 | R-GCN / HAN 异构嵌入匹配 | ⚪ | Top-3 仓库召回准确率 ≥ 0.6 |
| M4-GCN-05 | Ablation：BERT 文本基线 vs GCN | ⚪ | 报告中给出 F1/Precision/Recall 表 |
| M4-GCN-06 | 模型持久化 + 在线推理服务 | ⚪ | `model.pt` 加载 < 2s；FastAPI 注入单例 |
| M4-GCN-07 | 训练 loss / F1 曲线导出（report 素材） | ⚪ | 输出 `data/artifacts/gcn_curve.png` |

---

## 5 · M5 — HybridRAG（招牌 ②）

**目标**：BM25 + 向量 + 图谱三路并行召回 → LLM 重排 → 带可点击引用的答案。
**代码位置**：`backend/app/rag/`
**负责人**：B

| SPEC-ID | 子功能 | 状态 | 验收标准 |
|---|---|---|---|
| M5-RAG-01 | BM25 召回器（`rank-bm25`，索引按 repo 分片） | ⚪ | Top-20 召回 < 100ms |
| M5-RAG-02 | 向量召回器（复用 M3-VEC-05） | ⚪ | 同上 |
| M5-RAG-03 | 图召回器（实体抽取 → Cypher 子图扩展） | ⚪ | LLM NER → Neo4j 邻接查询返回相关 Issue/PR |
| M5-RAG-04 | 三路融合 & 去重 | ⚪ | RRF（Reciprocal Rank Fusion）或 LLM 重排，可配置 |
| M5-RAG-05 | 引用 schema 严格校验（`proposal.md` §4 模块 3） | ⚪ | Pydantic v2 校验，违例抛 422 |
| M5-RAG-06 | 端到端延迟监控 | ⚪ | P95 < 5s，超时自动降级（去掉图路） |
| M5-RAG-07 | 三路命中数对比柱状图（report 素材） | ⚪ | 一次评测可生成 `data/artifacts/rag_recall.png` |

---

## 6 · M6 — LangGraph Agent（招牌 ③）

**目标**：8 节点 DAG 端到端 onboarding 规划，保留每步中间结果。
**代码位置**：`backend/app/agent/`
**负责人**：C

| SPEC-ID | 子功能 | 状态 | 验收标准 |
|---|---|---|---|
| M6-AGT-01 | DAG 拓扑搭建（8 节点 + 边） | 🟡 | `graph.py` 已声明节点，待补条件分支 |
| M6-AGT-02 | `SkillExtractor` 节点（LLM 抽取 → 规范化技能集） | ⚪ | 输入自然语言，输出 `List[Skill]` 命中已知库 ≥ 80% |
| M6-AGT-03 | `RepoMatcher` 节点（调用 M4 GCN 嵌入） | ⚪ | 返回 Top-3 + 相似度分数 |
| M6-AGT-04 | `IssueFinder` 节点（调用 M5 HybridRAG） | ⚪ | 返回带引用的 Issue 列表 |
| M6-AGT-05 | `FriendlinessRanker` 节点（M4 友好度模型） | ⚪ | 输出排序 + 置信度 |
| M6-AGT-06 | `PathPredictor` 节点（代码调用图 BFS） | ⚪ | 给定 Issue 返回 Top-5 改动文件预测 |
| M6-AGT-07 | `SimilarPRRetriever` 节点 | ⚪ | 向量 ANN 召回 + 已合并过滤 |
| M6-AGT-08 | `DifficultyEstimator` + `PRDrafter` 节点 | ⚪ | 输出难度星级 + Markdown PR 模板 |
| M6-AGT-09 | 全链路 trace（每步输入 / 输出 / 耗时） | ⚪ | 写入 `OnboardingPlan.trace` 字段，前端可展开 |
| M6-AGT-10 | 单节点失败的 fallback（规则版兜底） | ⚪ | 任一 LLM 节点失败可跑通 happy path |

---

## 7 · M7 — FastAPI 应用层

**目标**：把所有模块通过稳定的 REST 契约暴露给前端。
**代码位置**：`backend/app/main.py` · `backend/app/api.py` · `backend/app/schemas.py`
**负责人**：D

| SPEC-ID | 子功能 | 状态 | 验收标准 |
|---|---|---|---|
| M7-API-01 | `GET /api/v1/health` | 🟢 | 已实现 |
| M7-API-02 | `POST /api/v1/onboarding/plan`（M6 入口） | 🟡 | 路由 stub 已在，返回 501；待接 LangGraph |
| M7-API-03 | `GET /api/v1/repos/search?skill=&topic=` | ⚪ | 调用 M4-GCN-04 |
| M7-API-04 | `GET /api/v1/repos/{owner}/{name}/issues?friendly=true` | ⚪ | 调用 M4-GCN-03 |
| M7-API-05 | `GET /api/v1/kg/subgraph?center=&hops=` | ⚪ | 调用 M2-KG-06，供前端图谱 |
| M7-API-06 | `POST /api/v1/feedback` 用户反馈回写 | ⚪ | 写入 Neo4j `Feedback` 节点，供日后增量训练 |
| M7-API-07 | CORS / 鉴权中间件 | ⚪ | 允许前端域；可选简单 token |
| M7-API-08 | 全局异常处理 + 结构化日志 | ⚪ | 所有 5xx 带 `request_id` |
| M7-API-09 | OpenAPI 文档自动化（含示例） | ⚪ | `/docs` 每个端点至少 1 个 example |

---

## 8 · M8 — 前端工作台（精美化重点）

**设计目标**：**现代、克制、可演示**。不是堆 UI 库，而是用一套清晰的视觉语言把"知识网络可解释"这件事撑起来。
**代码位置**：`frontend/`
**负责人**：D

### 8.1 视觉与体验基线

| SPEC-ID | 子功能 | 状态 | 验收标准 |
|---|---|---|---|
| M8-UI-01 | 设计 Token：色板（深色为主 + 1 个强调色）/ 字号阶 / 圆角 / 阴影 | ⚪ | 写在 `frontend/src/styles/tokens.css`，全局 CSS 变量 |
| M8-UI-02 | 字体：等宽（JetBrains Mono / Fira Code）+ 中文（思源 / Inter 西文） | ⚪ | 通过 `@fontsource` 自托管，避免外网依赖 |
| M8-UI-03 | 引入 Tailwind CSS + shadcn/ui 组件库（或 Radix Primitives 自封装） | ⚪ | 至少落地 Button / Card / Dialog / Tooltip / Tabs |
| M8-UI-04 | 暗黑 / 浅色双主题（默认跟随系统） | ⚪ | `prefers-color-scheme` + 手动切换持久化到 localStorage |
| M8-UI-05 | 动效层：Framer Motion 仅用于过渡与卡片入场（< 250ms） | ⚪ | 不滥用，关闭"减少动效"系统设置时自动停用 |
| M8-UI-06 | 响应式：≥ 1280 三栏，1024 两栏 + 抽屉，< 768 单栏 | ⚪ | Chrome DevTools 三档可视回归 |
| M8-UI-07 | 加载 / 空 / 错误状态统一组件 | ⚪ | Skeleton + EmptyState + ErrorBoundary 三件套 |
| M8-UI-08 | 无障碍：键盘可达 + ARIA + 对比度 AA | ⚪ | Lighthouse a11y ≥ 95 |

### 8.2 业务三屏（对应 `proposal.md` §4 模块 5）

| SPEC-ID | 子功能 | 状态 | 验收标准 |
|---|---|---|---|
| M8-VIEW-01 | **输入面板**：技能标签输入 + 兴趣方向 + 每周时间滑块 | ⚪ | 调用 `POST /api/v1/onboarding/plan` |
| M8-VIEW-02 | **推荐流**：仓库 / Issue 卡片瀑布；卡片含友好度 / 相似度 / 难度 | ⚪ | 行数 / 引用悬浮预览 |
| M8-VIEW-03 | **详情屏**：左 Markdown 计划书 · 右 Cytoscape 子图 · 引用高亮联动 | ⚪ | 点击引用滚动到锚点 + 子图高亮 |
| M8-VIEW-04 | Agent "思考链"侧抽屉：展开 M6 8 个节点的中间结果 | ⚪ | 时间线 + 折叠 JSON viewer |
| M8-VIEW-05 | 仓库子图全屏视图（Cytoscape.js + cola 布局） | ⚪ | 10k 节点保持 ≥ 30fps（启用 canvas 渲染） |
| M8-VIEW-06 | 反馈按钮（👍/👎 + 文字）→ `POST /api/v1/feedback` | ⚪ | 写入 + 本地乐观更新 |

### 8.3 工程基线

| SPEC-ID | 子功能 | 状态 | 验收标准 |
|---|---|---|---|
| M8-FE-01 | Vite + TS + ESLint + Prettier + Husky | ⚪ | 提交前自动 lint，CI 跑 `tsc --noEmit` |
| M8-FE-02 | `pnpm` 或锁定 `npm` 版本 | ⚪ | `engines` 字段明确版本 |
| M8-FE-03 | API client 自动从 OpenAPI 生成（`openapi-typescript`） | ⚪ | 后端契约改动 → `npm run gen:api` 一键同步 |
| M8-FE-04 | 错误边界 + 全局 Toast | ⚪ | Sonner 或 shadcn Toast，错误不白屏 |
| M8-FE-05 | E2E 烟雾测试（Playwright，仅 happy path） | ⚪ | `pnpm test:e2e` 在 CI 跑通 |

---

## 9 · M9 — 部署与运维（持久化后端）

**目标**：把后端跑在一台**长期在线**的机器上，团队成员 + demo 都可访问。
**代码位置**：`docker-compose.yml` · `deploy/`（待建）
**负责人**：D

| SPEC-ID | 子功能 | 状态 | 验收标准 |
|---|---|---|---|
| M9-OPS-01 | 选定生产服务器并完成基础初始化（见 §10 推荐） | ⚪ | 安装 Docker + ufw + fail2ban |
| M9-OPS-02 | `docker-compose.prod.yml`：Neo4j / Milvus / FastAPI / Caddy | ⚪ | `docker compose up -d` 一键起 |
| M9-OPS-03 | Caddy 反向代理 + 自动 HTTPS | ⚪ | 域名 `api.os-copilot.<your-domain>` HTTPS 通 |
| M9-OPS-04 | Neo4j / Milvus 数据卷持久化 + 每日快照 | ⚪ | 重启不掉数据；`/backups/` 滚动 7 天 |
| M9-OPS-05 | systemd unit 守护 docker compose | ⚪ | 服务器重启自动拉起 |
| M9-OPS-06 | GitHub Actions：push 到 `main` → SSH 部署 | ⚪ | 全链路 < 5 min |
| M9-OPS-07 | 监控：Uptime Kuma 或 Healthchecks.io | ⚪ | 后端宕机 5 min 内邮件 / Telegram 告警 |
| M9-OPS-08 | 前端部署到 Vercel / Cloudflare Pages（与后端解耦） | ⚪ | PR 预览环境可用 |
| M9-OPS-09 | `.env.prod` 通过 1Password / GitHub Secrets 注入 | ⚪ | 仓库不出现明文 secret |

---

## 10 · 服务器选型建议（M9-OPS-01 决策参考）

> 本项目同时跑 **Neo4j（≥ 1G RAM）** + **Milvus standalone（≥ 2G RAM）** + **FastAPI**，**建议最低配置 4 vCPU / 8 GB RAM / 80 GB SSD**。
> 推荐顺序按 **"性价比 × 适合课程项目"** 排：

| 优先级 | 平台 | 规格 / 价格示例 | 优点 | 注意点 |
|---|---|---|---|---|
| ⭐⭐⭐ 首选 | **阿里云轻量应用服务器（学生 / 新用户）** | 2C4G 99 元/年（学生 / 首购） | 国内访问稳定、控制台友好；可一键安装 Docker | 仅够跑 Neo4j；Milvus 内存吃紧，考虑用 **Zilliz Cloud Serverless 免费档** 接管向量 |
| ⭐⭐⭐ 首选 | **腾讯云轻量** | 2C4G ~120 元/年；4C8G ~720 元/年 | 同上；带宽更慷慨 | 同上 |
| ⭐⭐ 推荐 | **Hetzner Cloud（欧洲）** | CX22 / CPX21 ≈ €5/月（4C8G） | 性价比之王，按小时计费 | 国内访问稍慢；信用卡支付 |
| ⭐⭐ 推荐 | **DigitalOcean Droplet** | Basic Premium 4C8G $24/月 | 文档好、社区 marketplace 一键 Neo4j 镜像 | 国内访问一般 |
| ⭐⭐ 推荐 | **Fly.io** | Free tier 含 3× shared-cpu-1x（256MB），付费 4C8G ≈ $30/月 | App + VM 混合，自带全球 anycast；后端永久在线无冷启动 | Milvus 难直接跑，需配合 Zilliz Cloud |
| ⭐ 备选 | **Railway** | $5/月起，按用量计费 | 部署体验最丝滑，Git push 即部署 | 不适合长时间空闲（按秒计费会涨）；不建议跑 Neo4j/Milvus |
| ⭐ 备选 | **Render** | Web Service $7/月（永不休眠）+ 私有数据库 | UI 直观 | 比 Railway 贵，且也不适合自托管 Milvus |
| ⭐ 备选 | **Hugging Face Spaces** | 免费 CPU / 付费 GPU | 0 成本、自带 demo URL | 无持久化卷，**仅适合纯 stateless demo** |

### 强烈推荐的拆分架构（**最划算 + 最稳**）

```
[Aliyun / Tencent 轻量 2C4G ≈ ¥100/年]   ← FastAPI + Neo4j（自托管）+ Caddy
              │
              ├──► Zilliz Cloud Serverless（Milvus 托管 · 免费 5GB）
              │       https://zilliz.com/cloud
              │
              ├──► Neo4j AuraDB Free（如自托管嫌重）
              │       https://neo4j.com/cloud/aura-free/
              │
              └──► Vercel / Cloudflare Pages（前端 · 免费）
```

**为什么这个拆分最适合你**：
1. **Milvus 是吃内存大户**，2C4G 机器自己跑容易 OOM；用 Zilliz 免费档把它"卸载"出去，后端机器立刻轻松
2. **Neo4j AuraDB Free** 也能用，但有 200k 节点 / 400k 边上限——如果只跑 5–10 个种子仓库够用；超了再回自托管
3. **前端**完全无状态，扔 Vercel 享受全球 CDN + 自动 HTTPS
4. **总成本**：¥100/年 服务器 + 0（向量 / 前端均免费）≈ **每月不到 ¥10**
5. 课程结束后想保留作品集，**只续费这台轻量服务器即可**

如果你预算更紧或不想买服务器：

- **完全免费方案**：Fly.io 免费 3 个 256MB VM（够跑 FastAPI）+ Zilliz Free + Neo4j Aura Free + Vercel 前端 → 0 元，缺点是 Fly free tier 偶尔冷启动 1–2 秒
- **学校机房 / 实验室**：如果导师能给一台内网机+反向代理（frp/ngrok），也很香

我个人最推荐你选 **腾讯云 / 阿里云 2C4G 轻量**+**Zilliz Cloud 免费档**+**Vercel 前端**，这套体验最接近"商业产品"，答辩演示也最稳。

---

## 11 · 待规划池（Backlog）

> 还没分配到模块的想法。每周例会过一次，决定是 promote 到上方模块、还是 ⏸ 暂缓。

- [ ] 多语言 README 自动摘要（中英对照）
- [ ] PR 模板支持多框架（贡献指南差异）
- [ ] 用户画像本地持久化（IndexedDB）+ "我的 onboarding 历史"
- [ ] 服务端 SSE 流式输出 Agent 中间结果
- [ ] 评测集众包采集（导出 Issue → 人工标注友好度）

---

## 12 · 变更日志

| 日期 | 改动 | 作者 |
|---|---|---|
| 2026-05-19 | 完成 M1-ETL-01~03：GitHub REST 客户端、`RepoMeta` / `GitHubIssue` / `GitHubPullRequest` schema、Issue/PR 分页拉取与 mock 测试 | D |
| 2026-05-19 | 初始化 SPEC，分 9 个模块 + backlog | 全员 |
