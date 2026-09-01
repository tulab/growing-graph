# growing-graph

知识图谱构建系统 · 后端（FastAPI + SQLite 单库，图引擎微服务）。

## 结构

- `app/graph/` —— 自包含图引擎单包：api（四层 RPC graph / schema / instance / transaction）、service、stores、models、schemas，及 config / db / auth / errors / utils
- `docs/` —— 需求 / 设计 / 实现文档
- `data/` —— SQLite 数据文件（`data/data.db`，gitignore）

## 运行

```
uv run uvicorn app.main:app --port 3003
```

- 存储：单文件 SQLite（`data/data.db`），无外部数据库依赖。
- 身份：微服务模型，调用方注入 `X-Identity` 请求头（base64(JSON)，含 user_id），缺失即 401；详见 `docs/设计文档/接口设计/接口语义层次.md` §5。
- 配置：全部有默认值，无需 `.env`（模板见 `.env.example`）。

## 文档

- `docs/设计文档/` —— 架构概览 · 图谱数据模型 · 数据库设计 · 技术栈 · 接口设计（语义层次 / 设计）
- `docs/设计哲学/` —— 需求图谱 Schema 设计（依据文档）
