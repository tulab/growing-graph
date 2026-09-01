"""服务层公共校验：图谱归属、类型字典、维度/属性键合法性。"""
from app.graph.errors import (
    AppError, E_DIM_KEY, E_FORBIDDEN, E_GRAPH_NOT_FOUND, E_LINK_TYPE,
    E_NODE_TYPE, E_PROPERTY_KEY,
)
from ..stores.sqlite_store import SqliteStore


def require_graph(sqlite: SqliteStore, user_id: str, graph_id: str) -> dict:
    """图谱必须存在且属于当前用户（基于 graph 表校验：user_id 记录归属）。"""
    g = sqlite.get_graph(graph_id)
    if not g:
        raise AppError(E_GRAPH_NOT_FOUND, f"图谱不存在: {graph_id}")
    if g["user_id"] != user_id:
        raise AppError(E_FORBIDDEN, f"无权访问该图谱: {graph_id}")
    return g


def require_object_type(sqlite: SqliteStore, graph_id: str, code: str) -> dict:
    t = sqlite.get_object_type(graph_id, code)
    if not t:
        raise AppError(E_NODE_TYPE, f"节点类型不在类型字典: {code}")
    return t


def require_link_type(sqlite: SqliteStore, graph_id: str, code: str) -> dict:
    t = sqlite.get_link_type(graph_id, code)
    if not t:
        raise AppError(E_LINK_TYPE, f"关系类型不在类型字典: {code}")
    return t


def validate_dim(graph: dict, dim: dict) -> dict:
    """dim 键必须 ∈ graph.dims 声明的维度键。"""
    if not dim:
        return dim
    allowed = {d["key"] for d in (graph["dims"] or []) if isinstance(d, dict)}
    bad = [k for k in dim if k not in allowed]
    if bad:
        raise AppError(E_DIM_KEY, f"维度键不在 graph.dims 中: {bad}")
    return dim


def validate_property(sqlite: SqliteStore, graph_id: str, object_type_id: str, prop: dict) -> dict:
    """property 键必须 ∈ 该 object_type 的 property_type 字典。"""
    if not prop:
        return prop
    known = {t["type"] for t in sqlite.list_property_types(graph_id, object_type_id)}
    bad = [k for k in prop if k not in known]
    if bad:
        raise AppError(E_PROPERTY_KEY, f"属性键不在该对象类型的属性字典: {bad}")
    return prop


def as_dict(item) -> dict:
    """Pydantic 模型 / dict → 纯 dict（供 payload 落库、批量归一）。"""
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if isinstance(item, dict):
        return dict(item)
    return dict(item)

