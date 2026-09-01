"""Pydantic 模型：graph 模块各层接口请求/响应形状。

统一约定：**无 query 参数，一律 POST + body 传参**。
- 查询/列表统一为 `.../list`：body 带 `ids` 字段——`ids` 空/省略 = 返回全部（list all），
  `ids` 非空 = 仅返回这些元素的信息；过滤字段（type/q/dim/source/target/…）与 ids 组合（AND）。
- 批量写端点统一 `{graph_id, items[]}`——**一次调用只操作一个图谱**：graph_id 在顶层，
  其余字段均作为 items[] 的子项，items 恒为数组。
- 非批量单对象端点（insert/remove/attach/detach/property）仍为平铺字段。
"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BatchIn(BaseModel, Generic[T]):
    """批量写请求体：graph_id（唯一图谱作用域）+ items[]（批量内容）。一次调用只操作一个图谱。"""
    graph_id: str
    items: list[T] = Field(min_length=1)


# ================================================================ graph 层
class GraphListIn(BaseModel):
    """graph 层 list：ids 空/省略 = 当前用户全部图谱；非空 = 仅返回这些图谱的元数据。"""
    ids: list[str] = Field(default_factory=list)


class GraphCreateIn(BaseModel):
    name: str
    description: str = ""
    dims: list[Any] | None = None     # 维度字典声明：[{key, label, values:[{code, label}]}]（创建后不可修改）


class GraphUpdateIn(BaseModel):
    """更新仅允许 name / description；dims 创建后不可修改（extra 禁止，传 dims 即 422）。"""
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None           # 部分更新：缺省不改
    description: str | None = None


class GraphDeleteIn(BaseModel):
    """graph 层例外：删除对象即图谱本身，允许一次跨图谱批量删除（`{ids: []}`）。"""
    ids: list[str] = Field(min_length=1)


class GraphPathsIn(BaseModel):
    graph_id: str
    source: str
    target: str
    max_length: int = Field(4, ge=1, le=6)
    max_paths: int = Field(5, ge=1, le=10)


class GraphSubgraphsIn(BaseModel):
    graph_id: str
    ids: list[str] = Field(min_length=1)
    depth: int = Field(2, ge=1, le=3)
    max_nodes: int = Field(50, ge=1, le=200)
    max_edges: int = Field(100, ge=1, le=400)
    rels: list[str] | None = None


class GraphOverviewIn(BaseModel):
    graph_id: str
    depth: int = Field(1, ge=1, le=3)


class GraphNeighboursIn(BaseModel):
    graph_id: str
    id: str
    direction: str = "both"
    rels: list[str] | None = None
    limit: int = Field(50, ge=1, le=200)


class GraphConnectedIn(BaseModel):
    graph_id: str
    source: str
    target: str


class GraphStatsIn(BaseModel):
    graph_id: str


# ================================================================ schema 层
class TypesIn(BaseModel):
    graph_id: str


class StatIn(BaseModel):
    graph_id: str


class ObjectTypeListIn(BaseModel):
    graph_id: str
    ids: list[str] = Field(default_factory=list)   # 空/省略 = 全部；非空 = 仅这些 id
    type: str | None = None
    q: str | None = None


class LinkTypeListIn(BaseModel):
    graph_id: str
    ids: list[str] = Field(default_factory=list)
    type: str | None = None
    q: str | None = None


class PropertyTypeListIn(BaseModel):
    graph_id: str
    ids: list[str] = Field(default_factory=list)
    object_type_id: str | None = None
    type: str | None = None
    q: str | None = None


class ObjectTypeCreate(BaseModel):
    """对象类型批量项（`BatchIn[ObjectTypeCreate]`，graph_id 在顶层）。"""
    type: str
    name: str
    description: str = ""
    dim: dict[str, Any] = Field(default_factory=dict)


class ObjectTypeUpdate(BaseModel):
    """对象类型批量项（按 id 部分更新，缺省字段不改）。"""
    id: str
    type: str | None = None
    name: str | None = None
    description: str | None = None
    dim: dict[str, Any] | None = None


class LinkTypeCreate(BaseModel):
    type: str
    name: str
    description: str = ""
    dim: dict[str, Any] = Field(default_factory=dict)


class LinkTypeUpdate(BaseModel):
    id: str
    type: str | None = None
    name: str | None = None
    description: str | None = None
    dim: dict[str, Any] | None = None


class PropertyTypeCreate(BaseModel):
    object_type_id: str                                   # 绑定到哪个对象类型
    type: str
    name: str
    value_type: str = "string"
    description: str = ""
    dim: dict[str, Any] = Field(default_factory=dict)


class PropertyTypeUpdate(BaseModel):
    id: str
    object_type_id: str | None = None
    type: str | None = None
    name: str | None = None
    value_type: str | None = None
    description: str | None = None
    dim: dict[str, Any] | None = None


# ================================================================ instance 层
class ObjectListIn(BaseModel):
    graph_id: str
    ids: list[str] = Field(default_factory=list)   # 空/省略 = 全部；非空 = 仅这些节点
    type: str | None = None
    q: str | None = None
    limit: int | None = Field(None, ge=1, le=100)  # 仅 ids 为空时生效
    dim: dict[str, Any] | None = None              # 维度过滤，键 ∈ graph.dims


class LinkListIn(BaseModel):
    graph_id: str
    ids: list[str] = Field(default_factory=list)   # 空/省略 = 全部；非空 = 仅这些关系
    type: str | None = None
    source: str | None = None
    target: str | None = None


class PropertyListIn(BaseModel):
    """实例属性 list：属性非 id 寻址实体（object_id + type 定位），无 ids。"""
    graph_id: str
    object_id: str | None = None
    type: str | None = None


class ObjectCreate(BaseModel):
    """节点批量项（`BatchIn[ObjectCreate]`，graph_id 在顶层）。"""
    id: str | None = None            # 种子可指定；缺省服务端生成
    type: str
    title: str
    content: str = ""
    property: dict[str, Any] = Field(default_factory=dict)  # 键 ∈ 该类型 property_type
    dim: dict[str, Any] = Field(default_factory=dict)        # 键 ∈ graph.dims


class ObjectUpdate(BaseModel):
    """节点批量项（按 id 部分更新，缺省字段不改）。"""
    id: str
    type: str | None = None
    title: str | None = None
    content: str | None = None
    property: dict[str, Any] | None = None
    dim: dict[str, Any] | None = None


class LinkCreate(BaseModel):
    """关系批量项（`BatchIn[LinkCreate]`，graph_id 在顶层）。"""
    id: str | None = None
    type: str
    source: str
    target: str
    property: dict[str, Any] = Field(default_factory=dict)


class LinkUpdate(BaseModel):
    """关系批量项（按 id 部分更新，缺省字段不改）。"""
    id: str
    type: str | None = None
    source: str | None = None
    target: str | None = None
    property: dict[str, Any] | None = None


class ObjectInsert(BaseModel):
    graph_id: str
    link_id: str
    node: ObjectCreate


class ObjectRemove(BaseModel):
    graph_id: str
    node_id: str


class ObjectAttach(BaseModel):
    graph_id: str
    source_id: str
    link_type: str
    node: ObjectCreate


class ObjectDetach(BaseModel):
    graph_id: str
    source_id: str
    node_id: str


class PropertyWrite(BaseModel):
    graph_id: str
    object_id: str
    type: str
    value: Any


class PropertyDeleteIn(BaseModel):
    graph_id: str
    object_id: str
    type: str


# ================================================================ transaction 层
class TransactionListIn(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    sort: str | None = None
