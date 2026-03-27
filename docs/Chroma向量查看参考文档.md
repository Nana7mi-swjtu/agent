# Chroma 向量查看命令（命令行）

以下命令用于查看 ChromaDB 中的 embedding 向量，基于脚本 `view_chroma_vectors.py`。

## 前置条件

- 已安装依赖：`uv sync`
- Chroma 持久化目录已配置（默认读取 `.env` 的 `RAG_CHROMADB_PERSIST_DIR`）

## 常用命令

### 1) 仅列出所有 collection

```powershell
uv run python view_chroma_vectors.py --list-only
```

### 2) 查看第一个 collection 的第一条向量（采样 16 维）

```powershell
uv run python view_chroma_vectors.py --sample-size 16
```

### 3) 指定 collection + chunk_id 查看向量采样

```powershell
uv run python view_chroma_vectors.py --collection <collection_name> --chunk-id <chunk_id> --sample-size 16
```

### 4) 指定 collection + chunk_id 查看完整向量

```powershell
uv run python view_chroma_vectors.py --collection <collection_name> --chunk-id <chunk_id> --full
```

## 可选参数

- `--persist-dir <path>`：手动指定 Chroma 持久化目录
- `--collection <name>`：指定 collection 名称
- `--chunk-id <id>`：指定要查询的 chunk_id
- `--sample-size <n>`：向量采样长度（默认 16，最大 512）
- `--full`：输出完整向量
- `--list-only`：只列出 collection 并退出

