"""SQLite ORM：graph / schema 三表 / operation / object / link（全部 SQLite 承载）。

时间戳统一 ISO 字符串；dims / dim / property / payload 为 JSON 字符串列。
schema 类型表按 graph 分区；(graph_id, type) 唯一；property_type 另按 object_type_id 绑定。
实例（object / link）按 graph_id 分区，即数据隔离边界。
graph.user_id 记录归属用户（graph 操作校验归属）；operation.user_id 记录操作者（无 user 表）。
"""
from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.graph.db import Base


class Graph(Base):
    __tablename__ = "graph"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # 归属用户（graph 操作校验）
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    dims: Mapped[str] = mapped_column(Text, default="[]")   # json：结构化维度字典（创建后不可修改）
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class ObjectType(Base):
    __tablename__ = "object_type"
    __table_args__ = (UniqueConstraint("graph_id", "type"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    graph_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    dim: Mapped[str] = mapped_column(Text, default="{}")    # json：维度取值
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class LinkType(Base):
    __tablename__ = "link_type"
    __table_args__ = (UniqueConstraint("graph_id", "type"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    graph_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    dim: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class PropertyType(Base):
    """属性类型：绑定到具体 object_type（该对象类型允许哪些属性键）。"""
    __tablename__ = "property_type"
    __table_args__ = (UniqueConstraint("graph_id", "object_type_id", "type"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    graph_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 绑定对象类型
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), default="string")
    description: Mapped[str] = mapped_column(Text, default="")
    dim: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class Operation(Base):
    """操作记录：每次写调用落一条，供审计回溯。"""
    __tablename__ = "operation"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    graph_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    layer: Mapped[str] = mapped_column(String(32), nullable=False)   # graph/schema/instance
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # resource.action
    payload: Mapped[str] = mapped_column(Text, default="{}")         # json：请求体
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class Object(Base):
    """节点实例。property / dim 为 JSON 字符串列。"""
    __tablename__ = "object"
    __table_args__ = (
        Index("ix_object_graph_type", "graph_id", "type"),
        Index("ix_object_graph_bkey", "graph_id", "business_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    graph_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    property: Mapped[str] = mapped_column(Text, default="{}")
    dim: Mapped[str] = mapped_column(Text, default="{}")
    business_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class Link(Base):
    """关系实例。property 为 JSON 字符串列。"""
    __tablename__ = "link"
    __table_args__ = (
        Index("ix_link_graph_type", "graph_id", "type"),
        Index("ix_link_graph_source", "graph_id", "source"),
        Index("ix_link_graph_target", "graph_id", "target"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    graph_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    property: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
