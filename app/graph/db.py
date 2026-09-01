"""存储引擎：SQLAlchemy Base + Database（单 SQLite 引擎）。

graph 包内 ORM 模型继承 Base，建表时由 Database 汇总全部表。
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        if path and path != ":memory:":
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)


class Database:
    """单一 SQLite 引擎：建表、取会话、释放。"""

    def __init__(self, url: str) -> None:
        _ensure_sqlite_dir(url)
        self._engine = create_engine(url, echo=False)
        Base.metadata.create_all(self._engine)

    def session(self) -> Session:
        return Session(self._engine)

    def dispose(self) -> None:
        self._engine.dispose()
