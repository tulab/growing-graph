"""请求身份解析：不内置鉴权，从 X-Identity 请求头读取身份（上游网关 / 微服务调用方注入）。

header 值为 base64(JSON)，JSON 含 user_id（必填）与 agent_id（可选）：
  X-Identity: base64({"user_id":"u1","agent_id":"a1"})
缺失 / 非 base64 / 非 JSON / 缺 user_id → E_UNAUTHORIZED (20001)。
graph 归属与操作记录基于 user_id；agent_id 供审计 / 调用方识别，不做鉴权依据。
"""
import base64
import json

from fastapi import Request

from app.graph.errors import AppError, E_UNAUTHORIZED

_IDENTITY_HEADER = "X-Identity"


def get_current_user(request: Request) -> dict:
    """解析身份头，返回 {"user_id": str, "agent_id": str | None}；缺失/非法即 401。"""
    raw = request.headers.get(_IDENTITY_HEADER)
    if not raw:
        raise AppError(E_UNAUTHORIZED, "缺少身份请求头 X-Identity")
    try:
        data = json.loads(base64.b64decode(raw, validate=True))
    except (ValueError, TypeError):
        raise AppError(E_UNAUTHORIZED, "身份请求头格式非法（须为 base64(JSON)）")
    user_id = data.get("user_id") if isinstance(data, dict) else None
    if not isinstance(user_id, str) or not user_id:
        raise AppError(E_UNAUTHORIZED, "身份请求头缺少 user_id")
    return {"user_id": user_id, "agent_id": data.get("agent_id")}
