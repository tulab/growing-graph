"""graph 层服务：图谱创建 / 列表 / 元数据 / 概览 / 邻居 / 路径 / 子图 / 连通性 / 统计。

写（graph.create）落 operation；其余为只读结构查询。
"""
from app.graph.errors import AppError, E_NODE_NOT_FOUND
from ..stores.graph_store import SqliteGraphStore
from ..stores.sqlite_store import SqliteStore
from .common import require_graph, require_link_type
from .ops import WriteMixin

DIRECTIONS = {"out", "in", "both"}


class GraphService(WriteMixin):
    def __init__(self, sqlite: SqliteStore, graph: SqliteGraphStore) -> None:
        self.sqlite = sqlite
        self.graph = graph

    # ---------------------------------------------------------------- 写
    def create_graph(self, user_id: str, *, name: str, description: str = "",
                     dims: list | None = None) -> dict:
        """创建图谱（dims 为维度字典声明，如 [{key, label, values:[{code, label}]}]，创建后不可修改）。"""
        g = self.sqlite.create_graph({"user_id": user_id, "name": name,
                                      "description": description, "dims": dims or []})
        self._log(user_id=user_id, graph_id=g["id"], layer="graph", action="graph.create",
                  payload={"name": name, "description": description, "dims": g["dims"]})
        return g

    def _require(self, user_id: str, graph_id: str) -> dict:
        return require_graph(self.sqlite, user_id, graph_id)

    def update_graph(self, user_id: str, graph_id: str, *, name: str | None = None,
                     description: str | None = None) -> dict:
        """更新图谱元数据（仅 name / description；dims 创建后不可修改；无字段时原样返回）。"""
        g = self._require(user_id, graph_id)
        patch = {}
        if name is not None:
            patch["name"] = name
        if description is not None:
            patch["description"] = description
        if patch:
            g = self.sqlite.update_graph(graph_id, patch)
        self._log(user_id=user_id, graph_id=graph_id, layer="graph", action="graph.update",
                  payload={"id": graph_id, **patch})
        return g

    def delete_graph(self, user_id: str, graph_id: str) -> dict:
        """删除图谱（级联清理类型字典 / 实例 / 操作记录）。高危：不可逆。"""
        self._require(user_id, graph_id)
        self.sqlite.delete_graph(graph_id)
        self._log(user_id=user_id, graph_id=graph_id, layer="graph", action="graph.delete",
                  payload={"id": graph_id})
        return {"ok": True, "id": graph_id}

    def _valid_rels(self, graph_id: str, rels) -> list[str] | None:
        if not rels:
            return None
        rels = list(rels)
        for r in rels:
            require_link_type(self.sqlite, graph_id, r)
        return rels

    @staticmethod
    def _clamp(value, lo, hi, default):
        try:
            v = int(value)
        except (TypeError, ValueError):
            v = default
        return max(lo, min(hi, v))

    # ---------------------------------------------------------------- 列表 / 元数据
    @staticmethod
    def _meta(g: dict) -> dict:
        return {
            "id": g["id"], "name": g["name"], "description": g["description"],
            "owner_user_id": g["user_id"],
            "dims": g["dims"] or [],
            "created_at": g["created_at"], "updated_at": g["updated_at"],
        }

    def list_graphs(self, user_id: str, *, ids: list[str] | None = None) -> dict:
        """图谱查询/列表：ids 空/省略 = 当前用户全部图谱；非空 = 仅这些图谱（归属校验，未命中即忽略）。"""
        graphs = self.sqlite.list_all_graphs(user_id)
        if ids:
            wanted = set(ids)
            graphs = [g for g in graphs if g["id"] in wanted]
        return {"items": [self._meta(g) for g in graphs]}

    # ---------------------------------------------------------------- 结构查询
    def overview(self, user_id: str, graph_id: str, *, depth: int = 1) -> dict:
        self._require(user_id, graph_id)
        depth = self._clamp(depth, 1, 3, 1)
        res = self.graph.overview(graph_id, depth=depth)
        return {"depth": depth, "nodes": res["nodes"], "links": res["links"],
                "truncated": res["truncated"]}

    def neighbours(self, user_id: str, graph_id: str, *, node_id: str,
                   direction: str = "both", rels=None, limit: int = 50) -> dict:
        self._require(user_id, graph_id)
        if direction not in DIRECTIONS:
            raise AppError(E_PARAM_RANGE, f"非法方向: {direction}")
        rels = self._valid_rels(graph_id, rels)
        limit = self._clamp(limit, 1, 200, 50)
        try:
            nb = self.graph.get_neighbors(graph_id, node_id, rels=rels, direction=direction,
                                          depth=1, max_nodes=limit, max_edges=limit * 2)
        except KeyError:
            raise AppError(E_NODE_NOT_FOUND, f"起始节点不存在: {node_id}")
        nodes = [{**n, "distance": nb["distances"].get(n["id"], 0)} for n in nb["nodes"]]
        return {"root": node_id, "nodes": nodes, "links": nb["links"],
                "limit": limit, "truncated": nb["truncated"]}

    def paths(self, user_id: str, graph_id: str, *, source: str, target: str,
              max_length: int = 4, max_paths: int = 5) -> dict:
        self._require(user_id, graph_id)
        for nid in (source, target):
            if not self.graph.get_node(graph_id, nid):
                raise AppError(E_NODE_NOT_FOUND, f"节点不存在: {nid}")
        found = self.graph.find_paths(graph_id, source, target,
                                      max_length=max_length, max_paths=max_paths)
        return {"source": source, "target": target, "total": len(found), "paths": found}

    def subgraphs(self, user_id: str, graph_id: str, *, ids: list[str], depth: int = 2,
                  max_nodes: int = 50, max_edges: int = 100, rels=None) -> dict:
        self._require(user_id, graph_id)
        rels = self._valid_rels(graph_id, rels)
        try:
            sg = self.graph.subgraph(graph_id, ids, depth=depth, max_nodes=max_nodes,
                                     max_edges=max_edges, rels=rels)
        except KeyError as e:
            raise AppError(E_NODE_NOT_FOUND, f"中心节点不存在: {e}")
        return {"nodes": sg["nodes"], "links": sg["links"], "truncated": sg["truncated"]}

    def connected(self, user_id: str, graph_id: str, *, source: str, target: str) -> dict:
        self._require(user_id, graph_id)
        for nid in (source, target):
            if not self.graph.get_node(graph_id, nid):
                raise AppError(E_NODE_NOT_FOUND, f"节点不存在: {nid}")
        connected, path = self.graph.connected(graph_id, source, target)
        return {"connected": connected, "path": path}

    def stats(self, user_id: str, graph_id: str) -> dict:
        self._require(user_id, graph_id)
        return self.graph.stats(graph_id)
