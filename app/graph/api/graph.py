"""graph 层路由：/api/graph。

统一 POST + body：查询/列表走 `/list`（body `{ids}`：空 = 当前用户全部图谱，非空 = 指定图谱元数据），
其余端点 graph_id 随 body 传入（与其他层的入参结构一致）。例外：`graph/delete` 允许 `{ids}` 跨图谱批量。
"""
from fastapi import APIRouter, Depends

from app.graph.errors import AppError

from ..deps import get_current_user, get_graph_service
from ..schemas import (
    GraphConnectedIn, GraphCreateIn, GraphDeleteIn, GraphListIn, GraphNeighboursIn,
    GraphOverviewIn, GraphPathsIn, GraphStatsIn, GraphSubgraphsIn, GraphUpdateIn,
)
from ..service.graph_service import GraphService

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.post("/create")
def create_graph(body: GraphCreateIn, user: dict = Depends(get_current_user),
                 svc: GraphService = Depends(get_graph_service)) -> dict:
    """创建图谱（归属 = 当前用户），name / description / dims 维度字典声明（dims 创建后不可改）。"""
    return svc.create_graph(user["user_id"], name=body.name, description=body.description, dims=body.dims)


@router.post("/update")
def update_graph(body: GraphUpdateIn, user: dict = Depends(get_current_user),
                 svc: GraphService = Depends(get_graph_service)) -> dict:
    """更新图谱元数据（仅 name / description；dims 创建后不可修改）。"""
    return svc.update_graph(user["user_id"], body.id, name=body.name, description=body.description)


@router.post("/delete")
def delete_graph(body: GraphDeleteIn, user: dict = Depends(get_current_user),
                 svc: GraphService = Depends(get_graph_service)) -> dict:
    """删除图谱（级联清理类型字典 / 实例 / 操作记录）。高危：不可逆，删除前须确认影响面。"""
    deleted, failed = [], []
    for gid in body.ids:
        try:
            svc.delete_graph(user["user_id"], gid)
            deleted.append(gid)
        except AppError as e:
            failed.append({"id": gid, "code": e.code, "detail": e.detail})
    return {"ok": bool(deleted), "deleted": deleted, "failed": failed}


@router.post("/list")
def list_graphs(body: GraphListIn, user: dict = Depends(get_current_user),
                svc: GraphService = Depends(get_graph_service)) -> dict:
    """图谱查询/列表：ids 空/省略 = 当前用户全部图谱；非空 = 仅这些图谱的元数据。"""
    return svc.list_graphs(user["user_id"], ids=body.ids)


@router.post("/overview")
def overview(body: GraphOverviewIn, user: dict = Depends(get_current_user),
             svc: GraphService = Depends(get_graph_service)) -> dict:
    return svc.overview(user["user_id"], body.graph_id, depth=body.depth)


@router.post("/neighbours")
def neighbours(body: GraphNeighboursIn, user: dict = Depends(get_current_user),
               svc: GraphService = Depends(get_graph_service)) -> dict:
    return svc.neighbours(user["user_id"], body.graph_id, node_id=body.id,
                          direction=body.direction, rels=body.rels, limit=body.limit)


@router.post("/paths")
def paths(body: GraphPathsIn, user: dict = Depends(get_current_user),
          svc: GraphService = Depends(get_graph_service)) -> dict:
    return svc.paths(user["user_id"], body.graph_id, source=body.source, target=body.target,
                     max_length=body.max_length, max_paths=body.max_paths)


@router.post("/subgraphs")
def subgraphs(body: GraphSubgraphsIn, user: dict = Depends(get_current_user),
              svc: GraphService = Depends(get_graph_service)) -> dict:
    return svc.subgraphs(user["user_id"], body.graph_id, ids=body.ids, depth=body.depth,
                         max_nodes=body.max_nodes, max_edges=body.max_edges, rels=body.rels)


@router.post("/connected")
def connected(body: GraphConnectedIn, user: dict = Depends(get_current_user),
              svc: GraphService = Depends(get_graph_service)) -> dict:
    return svc.connected(user["user_id"], body.graph_id, source=body.source, target=body.target)


@router.post("/stats")
def stats(body: GraphStatsIn, user: dict = Depends(get_current_user),
          svc: GraphService = Depends(get_graph_service)) -> dict:
    return svc.stats(user["user_id"], body.graph_id)
