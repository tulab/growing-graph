"""graph 模块路由聚合：组合四层 api 子路由。"""
from fastapi import APIRouter

from .api import graph, instance, schema, transaction

router = APIRouter()
router.include_router(graph.router)
router.include_router(schema.router)
router.include_router(instance.router)
router.include_router(transaction.router)
