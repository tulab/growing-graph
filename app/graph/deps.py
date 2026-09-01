"""FastAPI 依赖注入：从 app.state 取存储单例，组装服务。

鉴权（get_current_user）随配置一并收敛在 graph 包内（auth.py），本模块 re-export 保持 api 导入不变。
"""
from fastapi import Depends, Request

from app.graph.auth import get_current_user  # noqa: F401
from .service.graph_service import GraphService
from .service.instance_service import InstanceService
from .service.schema_service import SchemaService
from .service.transaction_service import TransactionService
from .stores.graph_store import SqliteGraphStore
from .stores.sqlite_store import SqliteStore


def get_sqlite_store(request: Request) -> SqliteStore:
    return request.app.state.sqlite_store


def get_graph_store(request: Request) -> SqliteGraphStore:
    return request.app.state.graph_store


def get_graph_service(
    sqlite: SqliteStore = Depends(get_sqlite_store),
    graph: SqliteGraphStore = Depends(get_graph_store),
) -> GraphService:
    return GraphService(sqlite, graph)


def get_schema_service(
    sqlite: SqliteStore = Depends(get_sqlite_store),
    graph: SqliteGraphStore = Depends(get_graph_store),
) -> SchemaService:
    return SchemaService(sqlite, graph)


def get_instance_service(
    sqlite: SqliteStore = Depends(get_sqlite_store),
    graph: SqliteGraphStore = Depends(get_graph_store),
) -> InstanceService:
    return InstanceService(sqlite, graph)


def get_transaction_service(
    sqlite: SqliteStore = Depends(get_sqlite_store),
) -> TransactionService:
    return TransactionService(sqlite)
