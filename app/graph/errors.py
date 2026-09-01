"""业务错误码：五位数字码，统一返回 {code, message, detail}。

分段：1xxxx 请求、2xxxx 权限、3xxxx 资源、4xxxx 冲突/校验、5xxxx 服务端。
HTTP 状态映射：请求/校验 400，未认证 401，无权 403，资源 404，服务端 500。
20002（无权）用于 graph 归属/权限校验；20001（未认证）用于身份请求头缺失或非法。
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ---- 请求 1xxxx
E_PARAM_MISSING = 10001
E_PARAM_TYPE = 10002
E_PARAM_RANGE = 10003
E_BODY_FORMAT = 10004
# ---- 权限 2xxxx
E_UNAUTHORIZED = 20001
E_FORBIDDEN = 20002
# ---- 资源 3xxxx
E_GRAPH_NOT_FOUND = 30001
E_TYPE_NOT_FOUND = 30002
E_NODE_NOT_FOUND = 30003
E_LINK_NOT_FOUND = 30004
E_OPERATION_NOT_FOUND = 30005
# ---- 冲突 / 校验 4xxxx
E_TYPE_DUP = 40001
E_TYPE_OCCUPIED = 40002
E_DIM_KEY = 40003
E_NODE_TYPE = 40004
E_PROPERTY_KEY = 40005
E_LINK_TYPE = 40006
# ---- 服务端 5xxxx
E_STORE = 50001
E_UNKNOWN = 50002

_MESSAGES = {
    E_PARAM_MISSING: "参数缺失",
    E_PARAM_TYPE: "参数类型错误",
    E_PARAM_RANGE: "参数越界或非法枚举",
    E_BODY_FORMAT: "请求体格式错误",
    E_UNAUTHORIZED: "未认证",
    E_FORBIDDEN: "无权访问该图谱",
    E_GRAPH_NOT_FOUND: "图谱不存在",
    E_TYPE_NOT_FOUND: "类型不存在",
    E_NODE_NOT_FOUND: "节点不存在",
    E_LINK_NOT_FOUND: "关系不存在",
    E_OPERATION_NOT_FOUND: "操作记录不存在",
    E_TYPE_DUP: "类型码重复",
    E_TYPE_OCCUPIED: "删除被占用类型",
    E_DIM_KEY: "维度键非法",
    E_NODE_TYPE: "节点类型不在类型字典",
    E_PROPERTY_KEY: "属性键不在属性字典",
    E_LINK_TYPE: "关系类型不在类型字典",
    E_STORE: "存储层错误",
    E_UNKNOWN: "未知错误",
}

_HTTP_STATUS: dict[int, int] = {}
for _codes, _status in (
    ((E_PARAM_MISSING, E_PARAM_TYPE, E_PARAM_RANGE, E_BODY_FORMAT), 400),
    ((E_UNAUTHORIZED,), 401),
    ((E_FORBIDDEN,), 403),
    ((E_GRAPH_NOT_FOUND, E_TYPE_NOT_FOUND, E_NODE_NOT_FOUND, E_LINK_NOT_FOUND, E_OPERATION_NOT_FOUND), 404),
    ((E_TYPE_DUP, E_TYPE_OCCUPIED, E_DIM_KEY, E_NODE_TYPE, E_PROPERTY_KEY, E_LINK_TYPE), 400),
    ((E_STORE, E_UNKNOWN), 500),
):
    for _c in _codes:
        _HTTP_STATUS[_c] = _status


class AppError(Exception):
    """业务异常：携带五位业务码。"""

    def __init__(self, code: int, detail: str = "", message: str | None = None) -> None:
        self.code = code
        self.message = message or _MESSAGES.get(code, "未知错误")
        self.detail = detail
        super().__init__(f"{self.message}: {detail}")


def install_error_handler(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _on_app_error(request: Request, exc: AppError):
        return JSONResponse(
            status_code=_HTTP_STATUS.get(exc.code, 400),
            content={"code": exc.code, "message": exc.message, "detail": exc.detail},
        )
