"""统一存储（SQLAlchemy + SQLite）：graph / schema 三表 / operation / object / link。

行形状（JSON 列已解析为 Python 对象）：
  graph:     {id, user_id, name, description, dims:list, created_at, updated_at}  # user_id 归属用户
  类型三表:  {id, graph_id, type, name, description, dim:dict, created_at, updated_at}
             property 另含 object_type_id / value_type
  operation: {id, graph_id, user_id, layer, action, payload:dict, created_at}
  object:    {id, graph_id, type, title, content, property:dict, dim:dict, business_key, created_at, updated_at}
  link:      {id, graph_id, type, source, target, property:dict, created_at, updated_at}
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.graph.db import Base, Database
from app.graph.utils import dumps, loads, new_id, utcnow
from ..models import (
    Graph, Link, LinkType, Object, ObjectType, Operation, PropertyType,
)

_JSON_COLS = {
    Graph: {"dims"},
    ObjectType: {"dim"},
    LinkType: {"dim"},
    PropertyType: {"dim"},
    Operation: {"payload"},
    Object: {"property", "dim"},
    Link: {"property"},
}


def _row(row: Any) -> dict:
    out = {k: getattr(row, k) for k in row.__table__.columns.keys()}
    for col in _JSON_COLS.get(type(row), set()):
        out[col] = loads(out.get(col))
    return out


class SqliteStore:
    """图谱持久化：基于本包 Database 引擎的图谱 / 类型 / 操作 / 实例存储。"""

    def __init__(self, db: Database) -> None:
        self._db = db

    def _sess(self) -> Session:
        return self._db.session()

    # ================================================================ graph
    def list_all_graphs(self, user_id: str) -> list[dict]:
        with self._sess() as s:
            return [_row(r) for r in s.scalars(select(Graph).where(Graph.user_id == user_id))]

    def get_graph(self, graph_id: str) -> Optional[dict]:
        with self._sess() as s:
            r = s.get(Graph, graph_id)
            return _row(r) if r else None

    def create_graph(self, data: dict) -> dict:
        now = utcnow()
        row = {
            "id": data.get("id") or new_id(),
            "user_id": data["user_id"],
            "name": data["name"],
            "description": data.get("description", ""),
            "dims": dumps(data.get("dims", [])),
            "created_at": now,
            "updated_at": now,
        }
        with self._sess() as s:
            s.add(Graph(**row)); s.commit()
            return _row(s.get(Graph, row["id"]))

    def touch_graph(self, graph_id: str) -> None:
        with self._sess() as s:
            g = s.get(Graph, graph_id)
            if g:
                g.updated_at = utcnow(); s.commit()

    def update_graph(self, graph_id: str, patch: dict) -> Optional[dict]:
        """部分更新图谱元数据（仅 name / description；dims 创建后不可修改）。未命中返回 None。"""
        data = {k: v for k, v in patch.items() if k in ("name", "description") and v is not None}
        if not data:
            return None
        with self._sess() as s:
            r = s.get(Graph, graph_id)
            if not r:
                return None
            for k, v in data.items():
                setattr(r, k, v)
            r.updated_at = utcnow()
            s.commit()
            return _row(r)

    def delete_graph(self, graph_id: str) -> bool:
        """删除图谱：级联清理其类型字典 / 实例 / 既有操作记录。不可逆。"""
        with self._sess() as s:
            r = s.get(Graph, graph_id)
            if not r:
                return False
            for cls in (Link, Object, PropertyType, LinkType, ObjectType, Operation):
                s.execute(delete(cls).where(cls.graph_id == graph_id))
            s.delete(r)
            s.commit()
            return True

    # ================================================================ schema 三表
    def list_object_types(self, graph_id: str) -> list[dict]:
        with self._sess() as s:
            return [_row(r) for r in s.scalars(select(ObjectType).where(ObjectType.graph_id == graph_id))]

    def list_link_types(self, graph_id: str) -> list[dict]:
        with self._sess() as s:
            return [_row(r) for r in s.scalars(select(LinkType).where(LinkType.graph_id == graph_id))]

    def list_property_types(self, graph_id: str, object_type_id: str | None = None) -> list[dict]:
        with self._sess() as s:
            q = select(PropertyType).where(PropertyType.graph_id == graph_id)
            if object_type_id:
                q = q.where(PropertyType.object_type_id == object_type_id)
            return [_row(r) for r in s.scalars(q)]

    def get_object_type(self, graph_id: str, code: str) -> Optional[dict]:
        with self._sess() as s:
            r = s.scalars(select(ObjectType).where(ObjectType.graph_id == graph_id, ObjectType.type == code)).first()
            return _row(r) if r else None

    def get_link_type(self, graph_id: str, code: str) -> Optional[dict]:
        with self._sess() as s:
            r = s.scalars(select(LinkType).where(LinkType.graph_id == graph_id, LinkType.type == code)).first()
            return _row(r) if r else None

    def get_property_type(self, graph_id: str, object_type_id: str, code: str) -> Optional[dict]:
        with self._sess() as s:
            r = s.scalars(select(PropertyType).where(
                PropertyType.graph_id == graph_id,
                PropertyType.object_type_id == object_type_id,
                PropertyType.type == code)).first()
            return _row(r) if r else None

    def get_type_by_id(self, kind: str, type_id: str) -> Optional[dict]:
        cls = {"object": ObjectType, "link": LinkType, "property": PropertyType}[kind]
        with self._sess() as s:
            r = s.get(cls, type_id)
            return _row(r) if r else None

    def create_type(self, kind: str, graph_id: str, data: dict) -> dict:
        cls = {"object": ObjectType, "link": LinkType, "property": PropertyType}[kind]
        now = utcnow()
        row = {
            "id": data.get("id") or new_id(),
            "graph_id": graph_id,
            "type": data["type"],
            "name": data["name"],
            "description": data.get("description", ""),
            "dim": dumps(data.get("dim", {})),
            "created_at": now,
            "updated_at": now,
        }
        if kind == "property":
            row["object_type_id"] = data["object_type_id"]
            row["value_type"] = data.get("value_type", "string")
        with self._sess() as s:
            s.add(cls(**row)); s.commit()
            return _row(s.get(cls, row["id"]))

    def update_type(self, kind: str, type_id: str, data: dict) -> Optional[dict]:
        cls = {"object": ObjectType, "link": LinkType, "property": PropertyType}[kind]
        fields = {"type", "name", "description", "dim"}
        if kind == "property":
            fields |= {"value_type", "object_type_id"}
        # 部分更新：跳过 None（Pydantic model_dump 会给未设置字段补 None）
        patch = {k: v for k, v in data.items() if k in fields and v is not None}
        if "dim" in patch:
            patch["dim"] = dumps(patch["dim"])
        with self._sess() as s:
            r = s.get(cls, type_id)
            if not r:
                return None
            for k, v in patch.items():
                setattr(r, k, v)
            r.updated_at = utcnow()
            s.commit()
            return _row(r)

    def delete_type(self, kind: str, type_id: str) -> bool:
        cls = {"object": ObjectType, "link": LinkType, "property": PropertyType}[kind]
        with self._sess() as s:
            r = s.get(cls, type_id)
            if not r:
                return False
            s.delete(r); s.commit()
            return True

    # ================================================================ operation
    def list_operations(self, user_id: str, *, page: int, page_size: int, sort: str) -> dict:
        field, desc = self._sort_field(sort, {"created_at", "layer", "action"}, default_desc=True)
        with self._sess() as s:
            total = len(s.scalars(select(Operation).where(Operation.user_id == user_id)).all())
            q = select(Operation).where(Operation.user_id == user_id)
            q = q.order_by(Operation.created_at.desc() if desc else getattr(Operation, field).asc())
            q = q.offset((page - 1) * page_size).limit(page_size)
            items = [_row(r) for r in s.scalars(q)]
        return {"total": total, "items": items}

    def create_operation(self, *, user_id: str, graph_id: str, layer: str, action: str,
                         payload: dict) -> dict:
        now = utcnow()
        op = {
            "id": new_id(),
            "graph_id": graph_id,
            "user_id": user_id,
            "layer": layer,
            "action": action,
            "payload": dumps(payload),
            "created_at": now,
        }
        with self._sess() as s:
            s.add(Operation(**op))
            g = s.get(Graph, graph_id)
            if g:
                g.updated_at = now
            s.commit()
            return _row(s.get(Operation, op["id"]))

    # ================================================================ object（节点实例）
    def list_objects(self, graph_id: str) -> list[dict]:
        with self._sess() as s:
            return [_row(r) for r in s.scalars(select(Object).where(Object.graph_id == graph_id))]

    def get_object(self, graph_id: str, object_id: str) -> Optional[dict]:
        with self._sess() as s:
            r = s.get(Object, object_id)
            if not r or r.graph_id != graph_id:
                return None
            return _row(r)

    def get_object_by_business_key(self, graph_id: str, business_key: str) -> Optional[dict]:
        with self._sess() as s:
            r = s.scalars(select(Object).where(
                Object.graph_id == graph_id, Object.business_key == business_key)).first()
            return _row(r) if r else None

    def insert_object(self, graph_id: str, node: dict) -> dict:
        row = {k: node[k] for k in
               ("id", "type", "title", "content", "property", "dim", "business_key",
                "created_at", "updated_at")}
        row["graph_id"] = graph_id
        for k in ("property", "dim"):
            row[k] = dumps(row[k])
        with self._sess() as s:
            s.add(Object(**row)); s.commit()
            return self.get_object(graph_id, node["id"])

    def update_object(self, graph_id: str, object_id: str, patch: dict) -> Optional[dict]:
        with self._sess() as s:
            r = s.get(Object, object_id)
            if not r or r.graph_id != graph_id:
                return None
            for k, v in patch.items():
                setattr(r, k, dumps(v) if k in ("property", "dim") else v)
            r.updated_at = utcnow()
            s.commit()
            return _row(r)

    def delete_object(self, graph_id: str, object_id: str) -> bool:
        with self._sess() as s:
            r = s.get(Object, object_id)
            if not r or r.graph_id != graph_id:
                return False
            s.delete(r)  # 级联关系
            s.execute(delete(Link).where(
                Link.graph_id == graph_id,
                (Link.source == object_id) | (Link.target == object_id)))
            s.commit()
            return True

    def query_objects(self, graph_id: str, *, type: str | None = None, dim: dict | None = None,
                      q: str | None = None, limit: int | None = None) -> list[dict]:
        def match(n: dict) -> bool:
            if type and n["type"] != type:
                return False
            if dim:
                for k, v in dim.items():
                    if (n.get("dim") or {}).get(k) != v:
                        return False
            if q:
                low = q.lower()
                if low not in n["title"].lower() and low not in (n.get("content") or "").lower():
                    return False
            return True

        out = [n for n in self.list_objects(graph_id) if match(n)]
        return out if limit is None else out[:limit]

    # ================================================================ link（关系实例）
    def list_links(self, graph_id: str) -> list[dict]:
        with self._sess() as s:
            return [_row(r) for r in s.scalars(select(Link).where(Link.graph_id == graph_id))]

    def get_link(self, graph_id: str, link_id: str) -> Optional[dict]:
        with self._sess() as s:
            r = s.get(Link, link_id)
            if not r or r.graph_id != graph_id:
                return None
            return _row(r)

    def insert_link(self, graph_id: str, link: dict) -> dict:
        row = {k: link[k] for k in ("id", "type", "source", "target", "property",
                                    "created_at", "updated_at")}
        row["graph_id"] = graph_id
        row["property"] = dumps(row["property"])
        with self._sess() as s:
            s.add(Link(**row)); s.commit()
            return self.get_link(graph_id, link["id"])

    def update_link(self, graph_id: str, link_id: str, patch: dict) -> Optional[dict]:
        with self._sess() as s:
            r = s.get(Link, link_id)
            if not r or r.graph_id != graph_id:
                return None
            for k, v in patch.items():
                setattr(r, k, dumps(v) if k == "property" else v)
            r.updated_at = utcnow()
            s.commit()
            return _row(r)

    def delete_link(self, graph_id: str, link_id: str) -> bool:
        with self._sess() as s:
            r = s.get(Link, link_id)
            if not r or r.graph_id != graph_id:
                return False
            s.delete(r); s.commit()
            return True

    def query_links(self, graph_id: str, *, type: str | None = None, source: str | None = None,
                    target: str | None = None) -> list[dict]:
        def match(l: dict) -> bool:
            if type and l["type"] != type:
                return False
            if source and l["source"] != source:
                return False
            if target and l["target"] != target:
                return False
            return True

        return [l for l in self.list_links(graph_id) if match(l)]

    # ================================================================ helpers
    @staticmethod
    def _sort_field(sort: str, allowed: set[str], default: str = "created_at",
                    default_desc: bool = False) -> tuple[str, bool]:
        if not sort:
            return default, default_desc
        desc = sort.startswith("-")
        field = sort[1:] if desc else sort
        if field not in allowed:
            raise ValueError(f"非法排序字段: {field}")
        return field, desc
