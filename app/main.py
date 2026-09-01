"""FastAPI 入口：组装 graph 包（自包含：配置 / 存储引擎 / 路由）→ CORS → 错误处理。

graph 是唯一业务包（app/graph/），配置、存储、错误、校验均收敛在包内，无 core/modules 分层。
本服务只提供 API，不托管静态前端。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .graph import router as graph_router
from .graph.config import settings
from .graph.db import Database
from .graph.errors import install_error_handler
from .graph.stores.graph_store import SqliteGraphStore
from .graph.stores.sqlite_store import SqliteStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = Database(settings.sqlite_url)
    sqlite = SqliteStore(db)
    graph = SqliteGraphStore(sqlite)
    app.state.db = db
    app.state.sqlite_store = sqlite
    app.state.graph_store = graph
    yield
    db.dispose()


app = FastAPI(title="知识图谱构建系统", version="0.3.0", lifespan=lifespan)
install_error_handler(app)
if settings.cors_allow_localhost:
    # 未配置 CORS 来源：默认放行全部 localhost 来源（任意端口）
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.include_router(graph_router)
