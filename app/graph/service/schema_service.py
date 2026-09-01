"""schema 层服务：object/link/property 类型字典的查询与写（批量：一次调用只操作一个图谱），删除受实例占用保护。

property 类型绑定 object_type（某对象类型允许哪些属性键）；object/link 类型按 graph 分区。
批量端点以顶层 graph_id 为唯一作用域，items[] 均为该图谱内的类型（update/delete 校验归属）。
写调用落 operation（layer=schema，action=`{kind}.create/update/delete`）。
"""
from app.graph.errors import AppError, E_TYPE_DUP, E_TYPE_NOT_FOUND, E_TYPE_OCCUPIED
from ..stores.graph_store import SqliteGraphStore
from ..stores.sqlite_store import SqliteStore
from .common import as_dict, require_graph, validate_dim
from .ops import WriteMixin


class SchemaService(WriteMixin):
    def __init__(self, sqlite: SqliteStore, graph: SqliteGraphStore) -> None:
        self.sqlite = sqlite
        self.graph = graph

    # ---------------------------------------------------------------- helpers
    def _list(self, graph_id: str, kind: str) -> list[dict]:
        return getattr(self.sqlite, f"list_{kind}_types")(graph_id)

    def _by_code(self, graph_id: str, kind: str, code: str):
        return getattr(self.sqlite, f"get_{kind}_type")(graph_id, code)

    def _by_id(self, kind: str, type_id: str):
        return self.sqlite.get_type_by_id(kind, type_id)

    def _require_row(self, user_id: str, kind: str, type_id: str) -> dict:
        row = self._by_id(kind, type_id)
        if not row:
            raise AppError(E_TYPE_NOT_FOUND, f"类型不存在: {type_id}")
        require_graph(self.sqlite, user_id, row["graph_id"])
        return row

    def _require_object_type(self, graph_id: str, object_type_id: str) -> dict:
        ot = self.sqlite.get_type_by_id("object", object_type_id)
        if not ot or ot["graph_id"] != graph_id:
            raise AppError(E_TYPE_NOT_FOUND, f"对象类型不存在: {object_type_id}")
        return ot

    def _require_row_in_graph(self, user_id: str, kind: str, type_id: str, graph_id: str) -> dict:
        """类型必须存在、归属校验通过、且属于本次调用指定的图谱（一次性只操作一个图谱）。"""
        row = self._require_row(user_id, kind, type_id)
        if row["graph_id"] != graph_id:
            raise AppError(E_TYPE_NOT_FOUND, f"类型不属于该图谱: {type_id}")
        return row

    def _occupied(self, kind: str, row: dict) -> bool:
        if kind == "object":
            return bool(self.graph.query_nodes(row["graph_id"], type=row["type"]))
        if kind == "link":
            return bool(self.graph.query_links(row["graph_id"], type=row["type"]))
        ot = self.sqlite.get_type_by_id("object", row["object_type_id"])
        if not ot:
            return False
        return any(row["type"] in (n.get("property") or {})
                   for n in self.graph.query_nodes(row["graph_id"], type=ot["type"]))

    # ---------------------------------------------------------------- types / stat
    def types(self, user_id: str, graph_id: str) -> dict:
        require_graph(self.sqlite, user_id, graph_id)
        return {"object": self._list(graph_id, "object"),
                "link": self._list(graph_id, "link"),
                "property": self._list(graph_id, "property")}

    def stat(self, user_id: str, graph_id: str) -> dict:
        require_graph(self.sqlite, user_id, graph_id)
        counts = {k: len(v) for k, v in self.types(user_id, graph_id).items()}
        return {"total": sum(counts.values()), "by_type": counts}

    # ---------------------------------------------------------------- 查询（统一 /list：ids 空=全部，非空=指定）
    def list_kind(self, user_id: str, kind: str, graph_id: str, *,
                  ids: list[str] | None = None,
                  object_type_id: str | None = None,
                  type: str | None = None, q: str | None = None) -> dict:
        require_graph(self.sqlite, user_id, graph_id)
        if kind == "property":
            items = self.sqlite.list_property_types(graph_id, object_type_id)
        else:
            items = self._list(graph_id, kind)
        if ids:
            wanted = set(ids)
            items = [t for t in items if t["id"] in wanted]
        if type:
            items = [t for t in items if t["type"] == type]
        if q:
            low = q.lower()
            items = [t for t in items if low in t["name"].lower()]
        return {"items": items}

    # ---------------------------------------------------------------- create（批量：items[]）
    def create_kind(self, user_id: str, kind: str, graph_id: str, items) -> dict:
        graph = require_graph(self.sqlite, user_id, graph_id)
        items = [as_dict(i) for i in items]
        created, failed = [], []
        for item in items:
            try:
                row = self._create_one(graph, kind, graph_id, item)
                created.append(row["id"])
            except AppError as e:
                failed.append({"type": item.get("type"), "code": e.code, "detail": e.detail})
        self._log(user_id=user_id, graph_id=graph_id, layer="schema", action=f"{kind}.create",
                  payload=items)
        return {"ok": bool(created), "created": created, "failed": failed}

    def _create_one(self, graph: dict, kind: str, graph_id: str, item: dict) -> dict:
        validate_dim(graph, item.get("dim") or {})
        if kind == "property":
            self._require_object_type(graph_id, item["object_type_id"])
            if self.sqlite.get_property_type(graph_id, item["object_type_id"], item["type"]):
                raise AppError(E_TYPE_DUP, f"属性类型重复: {item['type']}")
        elif self._by_code(graph_id, kind, item["type"]):
            raise AppError(E_TYPE_DUP, f"类型码重复: {item['type']}")
        return self.sqlite.create_type(kind, graph_id, item)

    # ---------------------------------------------------------------- update（批量：items[]，强制单图谱）
    def update_kind(self, user_id: str, kind: str, graph_id: str, items) -> dict:
        graph = require_graph(self.sqlite, user_id, graph_id)
        items = [as_dict(i) for i in items]
        updated, failed = [], []
        for item in items:
            try:
                row = self._require_row_in_graph(user_id, kind, item["id"], graph_id)
                if item.get("dim"):
                    validate_dim(graph, item["dim"])
                if kind == "property":
                    new_otid = item.get("object_type_id", row["object_type_id"])
                    new_type = item.get("type", row["type"])
                    if item.get("object_type_id"):
                        self._require_object_type(graph_id, item["object_type_id"])
                    if (new_otid, new_type) != (row["object_type_id"], row["type"]):
                        if self.sqlite.get_property_type(graph_id, new_otid, new_type):
                            raise AppError(E_TYPE_DUP, f"属性类型重复: {new_type}")
                elif item.get("type") and item["type"] != row["type"]:
                    if self._by_code(graph_id, kind, item["type"]):
                        raise AppError(E_TYPE_DUP, f"类型码重复: {item['type']}")
                self.sqlite.update_type(kind, item["id"], item)
                updated.append(item["id"])
            except AppError as e:
                failed.append({"id": item.get("id"), "code": e.code, "detail": e.detail})
        self._log(user_id=user_id, graph_id=graph_id, layer="schema", action=f"{kind}.update",
                  payload=items)
        return {"ok": bool(updated), "updated": updated, "failed": failed}

    # ---------------------------------------------------------------- delete（批量：items[]，强制单图谱）
    def delete_kind(self, user_id: str, kind: str, graph_id: str, items: list[str]) -> dict:
        require_graph(self.sqlite, user_id, graph_id)
        deleted, failed = [], []
        for type_id in items:
            try:
                row = self._require_row_in_graph(user_id, kind, type_id, graph_id)
                if self._occupied(kind, row):
                    raise AppError(E_TYPE_OCCUPIED, f"类型已被实例使用: {row['type']}")
                self.sqlite.delete_type(kind, type_id)
                deleted.append(type_id)
            except AppError as e:
                failed.append({"id": type_id, "code": e.code, "detail": e.detail})
        self._log(user_id=user_id, graph_id=graph_id, layer="schema", action=f"{kind}.delete",
                  payload={"items": items})
        return {"ok": bool(deleted), "deleted": deleted, "failed": failed}
