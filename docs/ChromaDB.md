# RAG + ChromaDB 运维手册

## 概览

本项目现已包含一个通过功能开关控制的 RAG 流水线，并以 ChromaDB 作为默认向量后端。

- 功能模块：`app/rag/`
- 聊天集成：`app/agent/graph/` + `app/agent/tools/tools.py`
- API 路由：`/api/rag/*`
- 关系型持久化：MySQL 表 `rag_documents`、`rag_chunks`、`rag_index_jobs`、`rag_query_logs`

## 启用配置

请在 `.env` 中设置以下环境变量：

- `RAG_ENABLED=true`
- `RAG_VECTOR_PROVIDER=chromadb`
- `RAG_EMBEDDER_PROVIDER=openai-compatible`
- `RAG_EMBEDDING_MODEL=Qwen-Embedding-8B`
- `RAG_EMBEDDING_VERSION=1`
- `RAG_EMBEDDING_DIMENSION=1536`
- `RAG_EMBEDDING_API_KEY=<your-qwen-api-key>`
- `RAG_EMBEDDING_BASE_URL=<your-openai-compatible-base-url>`
- `RAG_EMBEDDING_TIMEOUT_SECONDS=20`
- `RAG_RERANKER_PROVIDER=openai-compatible`
- `RAG_RERANKER_MODEL=qwen-reranker-v1`
- `RAG_RERANKER_API_KEY=<your-qwen-api-key>`
- `RAG_RERANKER_BASE_URL=<your-openai-compatible-base-url>`
- `RAG_RERANKER_TIMEOUT_SECONDS=20`
- `RAG_RETRIEVAL_TOP_K=5`
- `RAG_RETRIEVAL_SCORE_THRESHOLD=0.0`
- `RAG_ALLOWED_FILE_TYPES=pdf,docx,md,txt,html,csv`
- `RAG_CHROMADB_PERSIST_DIR=uploads/chromadb`
- `RAG_CHROMADB_COLLECTION_PREFIX=rag`

可选项：

- `RAG_AUTO_INDEX_ON_UPLOAD=true`
- `RAG_CHUNK_SIZE=1200`
- `RAG_CHUNK_OVERLAP=150`
- `RAG_INDEX_MAX_WORKERS=2`

## 依赖安装

安装依赖：

```bash
uv sync
```

其中包括：

- `chromadb`
- `pypdf`
- `python-docx`

## 数据库迁移

执行 SQL 迁移：

- `migrations/004_add_rag_tables.sql`

如果 `AUTO_CREATE_DB=true`，当表缺失时，SQLAlchemy 的模型元数据会自动创建这些表。

## API 使用流程

1) 上传文档  
`POST /api/rag/upload` (`multipart/form-data`: `file`, optional `workspaceId`)

2) 启动索引任务  
`POST /api/rag/index` with `{"workspaceId":"...", "documentId":123}`

3) 轮询任务状态  
`GET /api/rag/jobs/<job_id>?workspaceId=...`

4) 检索查询  
`POST /api/rag/search` with `{"workspaceId":"...", "query":"...", "topK":5, "filters":{}}`

所有写接口均需要已认证会话 + `X-CSRF-Token`。

## 可观测性

查询遥测会持久化到 `rag_query_logs`：

- `latency_ms`
- `hit_count`
- `top_scores`
- provider 与 embedding 模型元数据
- `failure_reason`

索引遥测会持久化到 `rag_index_jobs`：

- 状态流转
- 各阶段错误详情
- `duration_ms`
- `chunks_count`

## 发布与回退

- 默认安全模式：`RAG_ENABLED=false`（聊天保持非 RAG 逻辑）。
- 当 RAG 被禁用时：
  - `/api/rag/*` 返回 `404`，响应为 `{"ok": false, "error": "rag feature is disabled"}`。
  - Agent 图中的决策阶段会跳过检索路径。

## 升级到更大后端的迁移触发条件

当满足以下一项或多项时，可考虑从单节点 Chroma 迁移：

- `rag_query_logs.latency_ms` 出现持续的时延回归
- 高写入量导致索引更新竞争
- 多租户规模超出本地持久化能力上限
- 需要分布式高可用/备份语义

由于向量访问已在 `app/rag/providers/interfaces.py` 中抽象为 `VectorStore`，迁移路径风险较低。
