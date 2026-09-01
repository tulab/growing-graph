"""instance 层服务：object/link/property 实例读写 + 复合结构动作（insert/remove/attach/detach）。

校验：节点/关系类型须在类型字典，object 的 property 键须在该对象类型的属性字典内，dim 键 ∈ graph.dims；
link 的 property 为自由键（无属性字典）。方向约束由调用方（应用层）按 link_type.dim 声明自行保证。
每次写调用落 operation（layer=instance，action=`object.create` 等）。
"""
from app.graph.errors import (
    AppError, E_LINK_NOT_FOUND, E_NODE_NOT_FOUND, E_PARAM_RANGE, E_PROPERTY_KEY,
)
from ..stores.graph_store import SqliteGraphStore
from ..stores.sqlite_store import SqliteStore
from .common import (
    as_dict, require_graph, require_link_type, require_object_type,
    validate_dim, validate_property,
)
from .ops import WriteMixin


class InstanceService(WriteMixin):
    def __init__(self, sqlite: SqliteStore, graph: SqliteGraphStore) -> None:
        self.sqlite = sqlite
        self.graph = graph

    # ---------------------------------------------------------------- helpers
    def _require(self, user_id: str, graph_id: str) -> dict:
        return require_graph(self.sqlite, user_id, graph_id)

    def _require_node(self, graph_id: str, node_id: str) -> dict:
        n = self.graph.get_node(graph_id, node_id)
        if not n:
            raise AppError(E_NODE_NOT_FOUND, f"节点不存在: {node_id}")
        return n

    def _require_link(self, graph_id: str, link_id: str) -> dict:
        l = self.graph.get_link(graph_id, link_id)
        if not l:
            raise AppError(E_LINK_NOT_FOUND, f"关系不存在: {link_id}")
        return l

    def _node_links(self, graph_id: str, node_id: str, links: list[dict] | None = None) -> list[dict]:
        links = links if links is not None else self.graph.query_links(graph_id)
        out = []
        for l in links:
            if l["source"] == node_id or l["target"] == node_id:
                out.append({**l, "direction": "out" if l["source"] == node_id else "in",
                            "target": l["target"] if l["source"] == node_id else l["source"]})
        return out

    def _links_of(self, graph_id: str, node_id: str) -> list[dict]:
        seen, out = set(), []
        for l in self.graph.query_links(graph_id, source=node_id) + self.graph.query_links(graph_id, target=node_id):
            if l["id"] not in seen:
                seen.add(l["id"]); out.append(l)
        return out

    # ================================================================ object
    def list_object(self, user_id: str, graph_id: str, *, ids: list[str] | None = None,
                    type: str | None = None, dim: dict | None = None,
                    q: str | None = None, limit: int | None = None) -> dict:
        """节点查询/列表：ids 空/省略 = 全部（可配合 type/dim/q/limit 过滤）；非空 = 仅这些节点（含 links 富化）。"""
        g = self._require(user_id, graph_id)
        if type:
            require_object_type(self.sqlite, graph_id, type)
        if dim:
            validate_dim(g, dim)
        if ids:
            wanted = set(ids)
            nodes = [n for n in self.graph.query_nodes(graph_id) if n["id"] in wanted]
        else:
            nodes = self.graph.query_nodes(graph_id, type=type, dim=dim, q=q, limit=limit)
        links = self.graph.query_links(graph_id)
        return {"items": [{**n, "links": self._node_links(graph_id, n["id"], links)} for n in nodes]}

    def create_object(self, user_id: str, graph_id: str, items) -> dict:
        g = self._require(user_id, graph_id)
        items = [as_dict(i) for i in items]
        created, failed = [], []
        for item in items:
            try:
                node = self._create_node_one(g, graph_id, item)
                created.append(node["id"])
            except AppError as e:
                failed.append({"type": item.get("type"), "title": item.get("title"),
                               "code": e.code, "detail": e.detail})
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action="object.create",
                  payload=items)
        return {"ok": bool(created), "created": created, "failed": failed}

    def _create_node_one(self, graph: dict, graph_id: str, item: dict) -> dict:
        ot = require_object_type(self.sqlite, graph["id"], item["type"])
        validate_property(self.sqlite, graph["id"], ot["id"], item.get("property") or {})
        validate_dim(graph, item.get("dim") or {})
        return self.graph.create_node(graph_id, {
            "id": item.get("id"), "type": item["type"], "title": item["title"],
            "content": item.get("content", ""), "property": item.get("property", {}),
            "dim": item.get("dim", {}), "business_key": item.get("business_key"),
        })

    def update_object(self, user_id: str, graph_id: str, items) -> dict:
        g = self._require(user_id, graph_id)
        items = [as_dict(i) for i in items]
        updated, failed = [], []
        for item in items:
            try:
                cur = self._require_node(graph_id, item["id"])
                patch, _ = self._build_node_patch(g, graph_id, cur, item)
                self.graph.update_node(graph_id, item["id"], patch)
                updated.append(item["id"])
            except AppError as e:
                failed.append({"id": item.get("id"), "code": e.code, "detail": e.detail})
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action="object.update",
                  payload=items)
        return {"ok": bool(updated), "updated": updated, "failed": failed}

    def _build_node_patch(self, graph: dict, graph_id: str, cur: dict, item: dict) -> tuple[dict, dict]:
        patch = {}
        for field in ("type", "title", "content", "property", "dim"):
            if field in item and item[field] is not None:
                patch[field] = item[field]
        if "type" in patch:
            require_object_type(self.sqlite, graph["id"], patch["type"])
        if "property" in patch:
            ot = require_object_type(self.sqlite, graph["id"], patch.get("type", cur["type"]))
            validate_property(self.sqlite, graph["id"], ot["id"], patch["property"])
        if "dim" in patch:
            validate_dim(graph, patch["dim"])
        return patch, {}

    def delete_object(self, user_id: str, graph_id: str, items: list[str]) -> dict:
        self._require(user_id, graph_id)
        deleted, failed = [], []
        for node_id in items:
            try:
                self._require_node(graph_id, node_id)
                self.graph.delete_node(graph_id, node_id)
                deleted.append(node_id)
            except AppError as e:
                failed.append({"id": node_id, "code": e.code, "detail": e.detail})
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action="object.delete",
                  payload={"items": items})
        return {"ok": bool(deleted), "deleted": deleted, "failed": failed}

    def insert_object(self, user_id: str, graph_id: str, body) -> dict:
        g = self._require(user_id, graph_id)
        link = self._require_link(graph_id, body["link_id"])
        node = self._create_node_one(g, graph_id, body["node"])
        new_a = self.graph.create_link(graph_id, {"type": link["type"], "source": link["source"], "target": node["id"]})
        new_b = self.graph.create_link(graph_id, {"type": link["type"], "source": node["id"], "target": link["target"]})
        self.graph.delete_link(graph_id, link["id"])
        out = {"ok": True, "node_id": node["id"], "links": [new_a["id"], new_b["id"]]}
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action="object.insert", payload=body)
        return out

    def remove_object(self, user_id: str, graph_id: str, body) -> dict:
        """移除链中间节点并合并其两条关系（仅允许恰有 1 入 + 1 出两条边；边数不符时报错，不静默删节点）。"""
        self._require(user_id, graph_id)
        node = self._require_node(graph_id, body["node_id"])
        links = self._links_of(graph_id, body["node_id"])
        in_links = [l for l in links if l["target"] == node["id"]]
        out_links = [l for l in links if l["source"] == node["id"]]
        if len(links) != 2 or len(in_links) != 1 or len(out_links) != 1:
            raise AppError(E_PARAM_RANGE,
                           f"remove 仅支持恰有 2 条边的链中间节点（1 入 + 1 出），"
                           f"该节点实际有 {len(links)} 条边（{len(in_links)} 入 / {len(out_links)} 出）")
        il, ol = in_links[0], out_links[0]
        merged = self.graph.create_link(graph_id, {"type": il["type"], "source": il["source"], "target": ol["target"]})
        self.graph.delete_link(graph_id, il["id"])
        self.graph.delete_link(graph_id, ol["id"])
        self.graph.delete_node(graph_id, body["node_id"])
        out = {"ok": True, "merged_link": merged["id"]}
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action="object.remove", payload=body)
        return out

    def attach_object(self, user_id: str, graph_id: str, body) -> dict:
        g = self._require(user_id, graph_id)
        source = self._require_node(graph_id, body["source_id"])
        require_link_type(self.sqlite, graph_id, body["link_type"])
        node = self._create_node_one(g, graph_id, body["node"])
        link = self.graph.create_link(graph_id, {"type": body["link_type"], "source": source["id"], "target": node["id"]})
        out = {"ok": True, "node_id": node["id"], "link_id": link["id"]}
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action="object.attach", payload=body)
        return out

    def detach_object(self, user_id: str, graph_id: str, body) -> dict:
        self._require(user_id, graph_id)
        node = self._require_node(graph_id, body["node_id"])
        links = self._links_of(graph_id, body["node_id"])
        self.graph.delete_node(graph_id, body["node_id"])
        out = {"ok": True, "deleted_links": [l["id"] for l in links]}
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action="object.detach", payload=body)
        return out

    # ================================================================ link
    def list_link(self, user_id: str, graph_id: str, *, ids: list[str] | None = None,
                  type: str | None = None, source: str | None = None,
                  target: str | None = None) -> dict:
        """关系查询/列表：ids 空/省略 = 全部（可配合 type/source/target 过滤）；非空 = 仅这些关系。"""
        self._require(user_id, graph_id)
        links = self.graph.query_links(graph_id, type=type, source=source, target=target)
        if ids:
            wanted = set(ids)
            links = [l for l in links if l["id"] in wanted]
        return {"items": links}

    def create_link(self, user_id: str, graph_id: str, items) -> dict:
        self._require(user_id, graph_id)
        items = [as_dict(i) for i in items]
        created, failed = [], []
        for item in items:
            try:
                require_link_type(self.sqlite, graph_id, item["type"])
                self._require_node(graph_id, item["source"])
                self._require_node(graph_id, item["target"])
                link = self.graph.create_link(graph_id, item)
                created.append(link["id"])
            except AppError as e:
                failed.append({"type": item.get("type"), "source": item.get("source"),
                               "target": item.get("target"), "code": e.code, "detail": e.detail})
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action="link.create",
                  payload=items)
        return {"ok": bool(created), "created": created, "failed": failed}

    def update_link(self, user_id: str, graph_id: str, items) -> dict:
        self._require(user_id, graph_id)
        items = [as_dict(i) for i in items]
        updated, failed = [], []
        for item in items:
            try:
                cur = self._require_link(graph_id, item["id"])
                patch = {f: item[f] for f in ("type", "source", "target", "property")
                         if f in item and item[f] is not None}
                ltype = patch.get("type", cur["type"])
                require_link_type(self.sqlite, graph_id, ltype)
                self._require_node(graph_id, patch.get("source", cur["source"]))
                self._require_node(graph_id, patch.get("target", cur["target"]))
                self.graph.update_link(graph_id, item["id"], patch)
                updated.append(item["id"])
            except AppError as e:
                failed.append({"id": item.get("id"), "code": e.code, "detail": e.detail})
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action="link.update",
                  payload=items)
        return {"ok": bool(updated), "updated": updated, "failed": failed}

    def delete_link(self, user_id: str, graph_id: str, items: list[str]) -> dict:
        self._require(user_id, graph_id)
        deleted, failed = [], []
        for link_id in items:
            try:
                self._require_link(graph_id, link_id)
                self.graph.delete_link(graph_id, link_id)
                deleted.append(link_id)
            except AppError as e:
                failed.append({"id": link_id, "code": e.code, "detail": e.detail})
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action="link.delete",
                  payload={"items": items})
        return {"ok": bool(deleted), "deleted": deleted, "failed": failed}

    # ================================================================ property（高危兜底，绑定 object_id）
    def list_property(self, user_id: str, graph_id: str, *, object_id: str | None = None,
                      type: str | None = None) -> dict:
        self._require(user_id, graph_id)
        nodes = [self._require_node(graph_id, object_id)] if object_id else self.graph.query_nodes(graph_id)
        items = []
        for n in nodes:
            for k, v in (n.get("property") or {}).items():
                if type and k != type:
                    continue
                items.append({"object_id": n["id"], "type": k, "value": v})
        return {"items": items}

    def write_property(self, user_id: str, graph_id: str, action: str, body) -> dict:
        self._require(user_id, graph_id)
        node = self._require_node(graph_id, body["object_id"])
        ot = require_object_type(self.sqlite, graph_id, node["type"])
        if not self.sqlite.get_property_type(graph_id, ot["id"], body["type"]):
            raise AppError(E_PROPERTY_KEY, f"属性键不在该对象类型的属性字典: {body['type']}")
        prop = dict(node.get("property") or {})
        prop[body["type"]] = body["value"]
        self.graph.update_node(graph_id, body["object_id"], {"property": prop})
        out = {"ok": True}
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action=action, payload=body)
        return out

    def delete_property(self, user_id: str, graph_id: str, body) -> dict:
        self._require(user_id, graph_id)
        node = self._require_node(graph_id, body["object_id"])
        before = dict(node.get("property") or {})
        if body["type"] not in before:
            raise AppError(E_PARAM_RANGE, f"节点无属性: {body['type']}")
        prop = dict(before)
        del prop[body["type"]]
        self.graph.update_node(graph_id, body["object_id"], {"property": prop})
        out = {"ok": True}
        self._log(user_id=user_id, graph_id=graph_id, layer="instance", action="property.delete", payload=body)
        return out
