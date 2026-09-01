"""图谱存储：SqliteGraphStore（实体层由 SQLite 承载）。

实例形状（纯 dict，与接口一致）：
  节点: {id, type, title, content, property:dict, dim:dict, business_key, created_at, updated_at}
  关系: {id, type, source, target, property:dict, created_at, updated_at}
持久化走 SqliteStore（object / link 表，按 graph_id 分区）；结构性查询（邻居/路径/子图/概览/连通/统计）
加载整图到内存后经 BFS 等纯算法完成（MVP 图规模小，负载可忽略）。
"""
from __future__ import annotations

from app.graph.utils import new_id, utcnow
from .sqlite_store import SqliteStore


def bfs_collect(seeds: list[dict], hop, *, depth: int, max_nodes: int, max_edges: int):
    """受限 BFS：从种子节点集沿 hop() 扩展，受 depth/max_nodes/max_edges 约束。

    hop(node_id) 产出 (neighbor_id, neighbor_node:dict, link:dict)。
    返回 (visited:dict, links:dict, distances:dict, truncated:bool)。
    """
    visited, distances, links = {}, {}, {}
    for s in seeds:
        visited[s["id"]] = s
        distances[s["id"]] = 0
    frontier = [s["id"] for s in seeds]
    truncated = False
    for d in range(1, depth + 1):
        if not frontier:
            break
        nxt = []
        for nid in frontier:
            if len(links) >= max_edges or len(visited) >= max_nodes:
                truncated = True
                break
            for nb_id, nb_obj, link in hop(nid):
                if len(links) >= max_edges or len(visited) >= max_nodes:
                    truncated = True
                    break
                if link["id"] in links:
                    continue
                links[link["id"]] = link
                if nb_id not in visited:
                    visited[nb_id] = nb_obj
                    distances[nb_id] = d
                    nxt.append(nb_id)
            if truncated:
                break
        frontier = nxt
        if truncated:
            break
    return visited, links, distances, truncated


def _hops(data: dict, node_id: str, rels, direction: str):
    for l in data["links"].values():
        if rels and l["type"] not in rels:
            continue
        if l["source"] == node_id and direction in ("out", "both"):
            yield l["target"], dict(data["nodes"][l["target"]]), dict(l)
        elif l["target"] == node_id and direction in ("in", "both"):
            yield l["source"], dict(data["nodes"][l["source"]]), dict(l)


def _slim_node(n: dict) -> dict:
    return {"id": n["id"], "type": n["type"], "title": n["title"]}


def _new_node(data: dict) -> dict:
    return {
        "id": data.get("id") or new_id(),
        "type": data["type"],
        "title": data["title"],
        "content": data.get("content", ""),
        "property": data.get("property", {}),
        "dim": data.get("dim", {}),
        "business_key": data.get("business_key"),
        "created_at": data.get("created_at", utcnow()),
        "updated_at": data.get("updated_at", utcnow()),
    }


def _new_link(data: dict) -> dict:
    return {
        "id": data.get("id") or new_id(),
        "type": data["type"],
        "source": data["source"],
        "target": data["target"],
        "property": data.get("property", {}),
        "created_at": data.get("created_at", utcnow()),
        "updated_at": data.get("updated_at", utcnow()),
    }


class SqliteGraphStore:
    """图谱存储：持久化走 SqliteStore，结构性查询加载整图后纯算法完成。"""

    def __init__(self, sqlite: SqliteStore) -> None:
        self.sqlite = sqlite

    def _data(self, graph_id: str) -> dict:
        return {
            "nodes": {n["id"]: n for n in self.sqlite.list_objects(graph_id)},
            "links": {l["id"]: l for l in self.sqlite.list_links(graph_id)},
        }

    def _require_node(self, data: dict, node_id: str) -> dict:
        if node_id not in data["nodes"]:
            raise KeyError(node_id)
        return data["nodes"][node_id]

    # ---- 基础 CRUD
    def get_node(self, graph_id, node_id):
        return self.sqlite.get_object(graph_id, node_id)

    def get_node_by_business_key(self, graph_id, business_key):
        return self.sqlite.get_object_by_business_key(graph_id, business_key)

    def get_link(self, graph_id, link_id):
        return self.sqlite.get_link(graph_id, link_id)

    def create_node(self, graph_id, data):
        node = _new_node(data)
        return self.sqlite.insert_object(graph_id, node)

    def update_node(self, graph_id, node_id, data):
        patch = {k: data[k] for k in ("type", "title", "content", "property", "dim", "business_key")
                 if k in data}
        if not patch:
            raise KeyError(node_id)
        updated = self.sqlite.update_object(graph_id, node_id, patch)
        if not updated:
            raise KeyError(node_id)
        return updated

    def delete_node(self, graph_id, node_id):
        return self.sqlite.delete_object(graph_id, node_id)

    def create_link(self, graph_id, data):
        link = _new_link(data)
        return self.sqlite.insert_link(graph_id, link)

    def update_link(self, graph_id, link_id, data):
        patch = {k: data[k] for k in ("type", "source", "target", "property") if k in data}
        if not patch:
            raise KeyError(link_id)
        updated = self.sqlite.update_link(graph_id, link_id, patch)
        if not updated:
            raise KeyError(link_id)
        return updated

    def delete_link(self, graph_id, link_id):
        return self.sqlite.delete_link(graph_id, link_id)

    # ---- 查询
    def query_nodes(self, graph_id, *, type=None, dim=None, q=None, limit=None):
        return self.sqlite.query_objects(graph_id, type=type, dim=dim, q=q, limit=limit)

    def query_links(self, graph_id, *, type=None, source=None, target=None):
        return self.sqlite.query_links(graph_id, type=type, source=source, target=target)

    # ---- 结构性查询（内存算法）
    def get_neighbors(self, graph_id, node_id, *, rels=None, direction="both", depth=1,
                      max_nodes=50, max_edges=100):
        data = self._data(graph_id)
        root = self._require_node(data, node_id)
        visited, links, distances, truncated = bfs_collect(
            [dict(root)], lambda nid: _hops(data, nid, rels, direction),
            depth=depth, max_nodes=max_nodes, max_edges=max_edges)
        return {"root": dict(root),
                "nodes": [n for n in visited.values() if n["id"] != node_id],
                "links": list(links.values()), "distances": distances,
                "truncated": truncated}

    def find_paths(self, graph_id, source, target, *, max_length=4, max_paths=5):
        data = self._data(graph_id)
        self._require_node(data, source)
        self._require_node(data, target)
        if source == target:
            return []
        out = []

        def dfs(cur, links, visited):
            if len(out) >= max_paths:
                return
            if cur == target and links:
                out.append(links)
                return
            if len(links) >= max_length:
                return
            for l in data["links"].values():
                if l["source"] == cur and l["target"] not in visited:
                    dfs(l["target"], links + [dict(l)], visited | {l["target"]})

        dfs(source, [], {source})
        return out

    def subgraph(self, graph_id, ids, *, depth=2, max_nodes=50, max_edges=100, rels=None):
        data = self._data(graph_id)
        seeds = [dict(n) for nid in ids if (n := data["nodes"].get(nid))]
        if not seeds:
            raise KeyError(ids[0] if ids else "no seeds")
        visited, links, distances, truncated = bfs_collect(
            seeds, lambda nid: _hops(data, nid, rels, "both"),
            depth=depth, max_nodes=max_nodes, max_edges=max_edges)
        return {"nodes": list(visited.values()), "links": list(links.values()),
                "distances": distances, "truncated": truncated}

    def overview(self, graph_id, *, depth=1, max_nodes=500):
        data = self._data(graph_id)
        nodes = [dict(n) for n in data["nodes"].values()]
        visited, links, distances, truncated = bfs_collect(
            nodes, lambda nid: _hops(data, nid, None, "both"),
            depth=depth, max_nodes=max_nodes, max_edges=max_nodes * 2)
        return {"nodes": [_slim_node(n) for n in visited.values()],
                "links": list(links.values()), "truncated": truncated}

    def connected(self, graph_id, source, target, *, max_length=6):
        data = self._data(graph_id)
        self._require_node(data, source)
        self._require_node(data, target)
        if source == target:
            return True, [source]
        frontier, parent = {source}, {source: None}
        for _ in range(max_length):
            nxt = set()
            for cur in frontier:
                for l in data["links"].values():
                    if l["source"] == cur and l["target"] not in parent:
                        parent[l["target"]] = cur
                        if l["target"] == target:
                            path, cur2 = [], target
                            while cur2 is not None:
                                path.append(cur2)
                                cur2 = parent[cur2]
                            return True, list(reversed(path))
                        nxt.add(l["target"])
            frontier = nxt
            if not frontier:
                break
        return False, []

    def stats(self, graph_id):
        from collections import Counter
        data = self._data(graph_id)
        nodes, links = data["nodes"], data["links"]
        node_by_type = Counter(n["type"] for n in nodes.values())
        link_by_type = Counter(l["type"] for l in links.values())
        connected = {l["source"] for l in links.values()} | {l["target"] for l in links.values()}
        return {
            "node_total": len(nodes), "link_total": len(links),
            "node_by_type": dict(node_by_type), "link_by_type": dict(link_by_type),
            "isolated": [nid for nid in nodes if nid not in connected],
        }
