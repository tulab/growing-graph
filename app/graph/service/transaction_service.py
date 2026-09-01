"""transaction 层服务：操作记录列表（每次写调用落一条，只读侧供审计回溯）。"""
from app.graph.errors import AppError, E_PARAM_RANGE
from ..stores.sqlite_store import SqliteStore


class TransactionService:
    def __init__(self, sqlite: SqliteStore) -> None:
        self.sqlite = sqlite

    def list(self, user_id: str, *, page: int = 1, page_size: int = 20,
             sort: str | None = None) -> dict:
        page = max(1, min(int(page), 10_000)) if page else 1
        page_size = max(1, min(int(page_size), 100)) if page_size else 20
        try:
            return self.sqlite.list_operations(user_id, page=page, page_size=page_size, sort=sort or "")
        except ValueError as e:
            raise AppError(E_PARAM_RANGE, str(e))
