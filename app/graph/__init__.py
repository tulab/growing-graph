"""graph 包：知识图谱构建系统（四层 RPC：graph / schema / instance / transaction）。

自包含单包：配置 / 存储引擎 / 错误 / 校验与四层 api·service·stores 收敛于此，无 core/modules 分层。
对外暴露 router（路由聚合）。不含任何业务字典预置。
"""
from .router import router

__all__ = ["router"]
