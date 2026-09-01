"""写操作通用支撑：每次写调用落一条 operation 记录。"""
from __future__ import annotations

from ..stores.sqlite_store import SqliteStore


class WriteMixin:
    """子类需持有 self.sqlite: SqliteStore。"""

    def _log(self, *, user_id: str, graph_id: str, layer: str, action: str, payload: dict) -> dict:
        return self.sqlite.create_operation(
            user_id=user_id, graph_id=graph_id, layer=layer, action=action, payload=payload)
