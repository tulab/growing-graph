"""instance 层路由：/api/instance（object / link / property 实例读写 + 复合结构动作）。

统一约定：无 query，一律 POST + body 传参。查询/列表统一 `/object/list` 等：body 带 `ids`
（空/省略 = 全部，非空 = 仅这些 id），可与 type/q/dim/source/target 过滤组合；节点 list 恒返回
links 富化，传单 id 即原详情。批量写端点统一 `{graph_id, items[]}`（一次只操作一个图谱，graph_id
在顶层，items 恒为数组）；非批量单对象动作（insert/remove/attach/detach/property）仍为平铺字段。
"""
from fastapi import APIRouter, Depends

from ..deps import get_current_user, get_instance_service
from ..schemas import (
    BatchIn, LinkCreate, LinkListIn, LinkUpdate,
    ObjectAttach, ObjectCreate, ObjectDetach, ObjectInsert,
    ObjectListIn, ObjectRemove, ObjectUpdate,
    PropertyDeleteIn, PropertyListIn, PropertyWrite,
)
from ..service.instance_service import InstanceService

router = APIRouter(prefix="/api/instance", tags=["instance"])


# ================================================================ object
@router.post("/object/list")
def list_object(body: ObjectListIn, user: dict = Depends(get_current_user),
                svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.list_object(user["user_id"], body.graph_id, ids=body.ids,
                           type=body.type, dim=body.dim, q=body.q, limit=body.limit)


@router.post("/object/create")
def create_object(body: BatchIn[ObjectCreate],
                  user: dict = Depends(get_current_user),
                  svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.create_object(user["user_id"], body.graph_id, body.items)


@router.post("/object/update")
def update_object(body: BatchIn[ObjectUpdate],
                  user: dict = Depends(get_current_user),
                  svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.update_object(user["user_id"], body.graph_id, body.items)


@router.post("/object/delete")
def delete_object(body: BatchIn[str], user: dict = Depends(get_current_user),
                  svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.delete_object(user["user_id"], body.graph_id, body.items)


@router.post("/object/insert")
def insert_object(body: ObjectInsert, user: dict = Depends(get_current_user),
                  svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.insert_object(user["user_id"], body.graph_id, body.model_dump())


@router.post("/object/remove")
def remove_object(body: ObjectRemove, user: dict = Depends(get_current_user),
                  svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.remove_object(user["user_id"], body.graph_id, body.model_dump())


@router.post("/object/attach")
def attach_object(body: ObjectAttach, user: dict = Depends(get_current_user),
                  svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.attach_object(user["user_id"], body.graph_id, body.model_dump())


@router.post("/object/detach")
def detach_object(body: ObjectDetach, user: dict = Depends(get_current_user),
                  svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.detach_object(user["user_id"], body.graph_id, body.model_dump())


# ================================================================ link
@router.post("/link/list")
def list_link(body: LinkListIn, user: dict = Depends(get_current_user),
              svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.list_link(user["user_id"], body.graph_id, ids=body.ids,
                         type=body.type, source=body.source, target=body.target)


@router.post("/link/create")
def create_link(body: BatchIn[LinkCreate],
                user: dict = Depends(get_current_user),
                svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.create_link(user["user_id"], body.graph_id, body.items)


@router.post("/link/update")
def update_link(body: BatchIn[LinkUpdate],
                user: dict = Depends(get_current_user),
                svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.update_link(user["user_id"], body.graph_id, body.items)


@router.post("/link/delete")
def delete_link(body: BatchIn[str], user: dict = Depends(get_current_user),
                svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.delete_link(user["user_id"], body.graph_id, body.items)


# ================================================================ property（高危兜底，绑定 object_id）
@router.post("/property/list")
def list_property(body: PropertyListIn, user: dict = Depends(get_current_user),
                  svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.list_property(user["user_id"], body.graph_id, object_id=body.object_id, type=body.type)


@router.post("/property/create")
def create_property(body: PropertyWrite, user: dict = Depends(get_current_user),
                    svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.write_property(user["user_id"], body.graph_id, "property.create", body.model_dump())


@router.post("/property/update")
def update_property(body: PropertyWrite, user: dict = Depends(get_current_user),
                    svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.write_property(user["user_id"], body.graph_id, "property.update", body.model_dump())


@router.post("/property/delete")
def delete_property(body: PropertyDeleteIn, user: dict = Depends(get_current_user),
                    svc: InstanceService = Depends(get_instance_service)) -> dict:
    return svc.delete_property(user["user_id"], body.graph_id, body.model_dump())
