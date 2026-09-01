"""schema 层路由：/api/schema（类型字典 list / stat / object·link·property 增删改查，写支持批量）。

统一约定：无 query，一律 POST + body 传参。查询/列表统一 `/object/list` 等：body 带 `ids`
（空/省略 = 全部，非空 = 仅这些 id），可与 type/q/object_type_id 过滤组合。批量写端点统一
`{graph_id, items[]}`（一次只操作一个图谱，graph_id 在顶层，items 恒为数组，update/delete 的
items 须都属于该图谱）；property 类型绑定 object_type_id。
"""
from fastapi import APIRouter, Depends

from ..deps import get_current_user, get_schema_service
from ..schemas import (
    BatchIn, LinkTypeCreate, LinkTypeListIn, LinkTypeUpdate,
    ObjectTypeCreate, ObjectTypeListIn, ObjectTypeUpdate,
    PropertyTypeCreate, PropertyTypeListIn, PropertyTypeUpdate, StatIn, TypesIn,
)
from ..service.schema_service import SchemaService

router = APIRouter(prefix="/api/schema", tags=["schema"])


@router.post("/types")
def types(body: TypesIn, user: dict = Depends(get_current_user),
          svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.types(user["user_id"], body.graph_id)


@router.post("/stat")
def stat(body: StatIn, user: dict = Depends(get_current_user),
         svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.stat(user["user_id"], body.graph_id)


# ================================================================ object
@router.post("/object/list")
def list_object(body: ObjectTypeListIn, user: dict = Depends(get_current_user),
                svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.list_kind(user["user_id"], "object", body.graph_id,
                         ids=body.ids, type=body.type, q=body.q)


@router.post("/object/create")
def create_object(body: BatchIn[ObjectTypeCreate],
                  user: dict = Depends(get_current_user),
                  svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.create_kind(user["user_id"], "object", body.graph_id, body.items)


@router.post("/object/update")
def update_object(body: BatchIn[ObjectTypeUpdate],
                  user: dict = Depends(get_current_user),
                  svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.update_kind(user["user_id"], "object", body.graph_id, body.items)


@router.post("/object/delete")
def delete_object(body: BatchIn[str], user: dict = Depends(get_current_user),
                  svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.delete_kind(user["user_id"], "object", body.graph_id, body.items)


# ================================================================ link
@router.post("/link/list")
def list_link(body: LinkTypeListIn, user: dict = Depends(get_current_user),
              svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.list_kind(user["user_id"], "link", body.graph_id,
                         ids=body.ids, type=body.type, q=body.q)


@router.post("/link/create")
def create_link(body: BatchIn[LinkTypeCreate],
                user: dict = Depends(get_current_user),
                svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.create_kind(user["user_id"], "link", body.graph_id, body.items)


@router.post("/link/update")
def update_link(body: BatchIn[LinkTypeUpdate],
                user: dict = Depends(get_current_user),
                svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.update_kind(user["user_id"], "link", body.graph_id, body.items)


@router.post("/link/delete")
def delete_link(body: BatchIn[str], user: dict = Depends(get_current_user),
                svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.delete_kind(user["user_id"], "link", body.graph_id, body.items)


# ================================================================ property（绑定 object_type）
@router.post("/property/list")
def list_property(body: PropertyTypeListIn, user: dict = Depends(get_current_user),
                  svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.list_kind(user["user_id"], "property", body.graph_id,
                         ids=body.ids, object_type_id=body.object_type_id, type=body.type, q=body.q)


@router.post("/property/create")
def create_property(body: BatchIn[PropertyTypeCreate],
                    user: dict = Depends(get_current_user),
                    svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.create_kind(user["user_id"], "property", body.graph_id, body.items)


@router.post("/property/update")
def update_property(body: BatchIn[PropertyTypeUpdate],
                    user: dict = Depends(get_current_user),
                    svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.update_kind(user["user_id"], "property", body.graph_id, body.items)


@router.post("/property/delete")
def delete_property(body: BatchIn[str], user: dict = Depends(get_current_user),
                    svc: SchemaService = Depends(get_schema_service)) -> dict:
    return svc.delete_kind(user["user_id"], "property", body.graph_id, body.items)
